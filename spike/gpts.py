"""Tiny language models in plain torch, with no transformers dependency.

The installed transformers cannot import here — numpy 2.5 against a build compiled for an
older numpy ABI — and downgrading numpy in the conda env would break the sweeps that use
it. torch and tokenizers both import fine on their own, and these models are six to nine
layers, so this implements the forward pass directly.

Two things fall out of doing it this way, and both are the reason to keep it:
  - it is the seam the sandboxes are written against: generate(prefix, n)
  - a LoRA is a couple of extra matmuls in here, which is where the population idea has
    to plug in eventually

Two families are supported and they differ in exactly three places, all of them easy to
get silently wrong:

  llama   SimpleStories-V2-5M. 6 layers, hidden 256, 4 query heads over 2 key/value,
          head_dim 64, RoPE theta 10000, vocab 4019, lowercase tokenizer.
          *** RoPE rotates the two HALVES of each head against each other. ***

  gpts2   AxiomicLabs/GPT-S-5M. 9 layers, hidden 192, 6 query heads over 2 key/value,
          head_dim 32, RoPE theta 2500, vocab 4096.
          *** RoPE rotates INTERLEAVED PAIRS, and there is an extra projection that
              removes the component of the attention output lying along its own value
              vector. ***

Using one convention for the other still produces fluent-looking English, just worse, so
neither family is trusted here until its perplexity has been measured. See selftest().
"""
import json
import math
import os

import torch
import torch.nn.functional as F
from safetensors.torch import load_file
from tokenizers import Tokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
DIRS = {"simplestories": os.path.join(HERE, "model-ss"),
        "gpt-s": os.path.join(HERE, "model")}
DEFAULT = "simplestories"


class TinyLM:
    def __init__(self, model_dir, dtype=torch.float32):
        with open(os.path.join(model_dir, "config.json")) as fh:
            c = self.cfg = json.load(fh)
        self.sd = {k: v.to(dtype) for k, v in
                   load_file(os.path.join(model_dir, "model.safetensors")).items()}
        self.tok = Tokenizer.from_file(os.path.join(model_dir, "tokenizer.json"))
        self.kind = "llama" if c.get("model_type") == "llama" else "gpts2"
        self.n_layer = c["num_hidden_layers"]
        self.n_head = c["num_attention_heads"]
        self.n_kv = c["num_key_value_heads"]
        self.hd = c["head_dim"]
        self.n_rep = self.n_head // self.n_kv
        self.xsa = c.get("xsa_projection", False)
        self.eps = c["rms_norm_eps"]
        self.theta = c["rope_theta"]
        self.eos = c.get("eos_token_id")
        # SimpleStories declares 2048 positions but was trained at 512; either way the
        # only thing this bounds here is how much prefix we keep.
        self.max_pos = min(c["max_position_embeddings"], 512)
        self._rope_cache = None
        n = self.n_layer

        if self.kind == "llama":
            self.emb = "model.embed_tokens.weight"
            self.final = "model.norm.weight"
            self.K = [{
                "ln1": "model.layers.%d.input_layernorm.weight" % i,
                "ln2": "model.layers.%d.post_attention_layernorm.weight" % i,
                "q": "model.layers.%d.self_attn.q_proj.weight" % i,
                "k": "model.layers.%d.self_attn.k_proj.weight" % i,
                "v": "model.layers.%d.self_attn.v_proj.weight" % i,
                "o": "model.layers.%d.self_attn.o_proj.weight" % i,
                "gate": "model.layers.%d.mlp.gate_proj.weight" % i,
                "up": "model.layers.%d.mlp.up_proj.weight" % i,
                "down": "model.layers.%d.mlp.down_proj.weight" % i} for i in range(n)]
        else:
            self.emb = "transformer.wte.weight"
            self.final = "transformer.ln_f.weight"
            self.K = [{
                "ln1": "transformer.h.%d.ln_1.weight" % i,
                "ln2": "transformer.h.%d.ln_2.weight" % i,
                "q": "transformer.h.%d.attn.q_proj.weight" % i,
                "k": "transformer.h.%d.attn.k_proj.weight" % i,
                "v": "transformer.h.%d.attn.v_proj.weight" % i,
                "o": "transformer.h.%d.attn.o_proj.weight" % i,
                "gate": "transformer.h.%d.mlp.w_gate.weight" % i,
                "up": "transformer.h.%d.mlp.w_up.weight" % i,
                "down": "transformer.h.%d.mlp.w_down.weight" % i} for i in range(n)]

    # ---------------------------------------------------------------- pieces
    def _rms(self, x, w):
        r = torch.rsqrt(x.float().pow(2).mean(-1, keepdim=True) + self.eps)
        return (x.float() * r).type_as(x) * w

    def _rope(self, q, k, T):
        """The one place the two families genuinely disagree."""
        if self._rope_cache is None or self._rope_cache[0] < T:
            inv = 1.0 / (self.theta ** (torch.arange(0, self.hd, 2, dtype=torch.float32) / self.hd))
            t = torch.arange(max(T, self.max_pos), dtype=torch.float32)
            fr = torch.outer(t, inv)                                   # (T, hd/2)
            if self.kind == "llama":
                emb = torch.cat([fr, fr], dim=-1)                      # (T, hd)
                self._rope_cache = (t.numel(), emb.cos(), emb.sin())
            else:
                self._rope_cache = (t.numel(),
                                    torch.polar(torch.ones_like(fr), fr), None)
        c = self._rope_cache
        # the cache is built on the CPU; agents live on a GPU, so follow the input
        if c[1].device != q.device:
            self._rope_cache = c = (c[0], c[1].to(q.device),
                                    None if c[2] is None else c[2].to(q.device))
        if self.kind == "llama":
            cos, sin = c[1][:T][None, None], c[2][:T][None, None]

            def rot(x):
                h = x.shape[-1] // 2
                half = torch.cat([-x[..., h:], x[..., :h]], dim=-1)
                return x * cos + half * sin
        else:
            fc = c[1][:T][None, None]

            def rot(x):
                z = torch.view_as_complex(x.float().reshape(*x.shape[:-1], -1, 2))
                return torch.view_as_real(z * fc).flatten(-2).type_as(x)
        return rot(q), rot(k)

    # ---------------------------------------------------------------- forward
    @torch.inference_mode()
    def logits(self, ids, lora=None):
        """ids: LongTensor (1, T) -> logits (1, T, vocab).

        No KV cache. Sixty tokens through a 5M model is milliseconds, and recomputing the
        prefix each step removes every special case an incremental path would need."""
        sd = self.sd
        B, T = ids.shape
        x = F.embedding(ids, sd[self.emb])

        def lin(name, inp):
            y = inp @ sd[name].t()
            if lora and name in lora:                       # the genome plugs in here
                A, Bm, scale = lora[name]
                y = y + (inp @ A.t()) @ Bm.t() * scale
            return y

        for kk in self.K:
            h = self._rms(x, sd[kk["ln1"]])
            q = lin(kk["q"], h).view(B, T, self.n_head, self.hd).transpose(1, 2)
            k = lin(kk["k"], h).view(B, T, self.n_kv, self.hd).transpose(1, 2)
            v = lin(kk["v"], h).view(B, T, self.n_kv, self.hd).transpose(1, 2)
            q, k = self._rope(q, k, T)
            k = k.unsqueeze(2).expand(B, self.n_kv, self.n_rep, T, self.hd).reshape(B, self.n_head, T, self.hd)
            v = v.unsqueeze(2).expand(B, self.n_kv, self.n_rep, T, self.hd).reshape(B, self.n_head, T, self.hd)
            y = F.scaled_dot_product_attention(q, k, v, is_causal=True)
            if self.xsa:
                vn = F.normalize(v, dim=-1)
                y = y - (y * vn).sum(-1, keepdim=True) * vn
            y = y.transpose(1, 2).contiguous().view(B, T, self.n_head * self.hd)
            x = x + lin(kk["o"], y)

            h = self._rms(x, sd[kk["ln2"]])
            x = x + lin(kk["down"], F.silu(lin(kk["gate"], h)) * lin(kk["up"], h))

        x = self._rms(x, sd[self.final])
        return x @ sd[self.emb].t()                          # tied head, both families

    # ---------------------------------------------------------------- sampling
    @torch.inference_mode()
    def generate(self, prompt, max_new_tokens=60, temperature=0.9, top_p=0.95, top_k=0,
                 repetition_penalty=1.1, no_repeat_ngram=4, seed=None, lora=None,
                 stop_newline=False, stop_eos=True):
        if seed is not None:
            torch.manual_seed(seed)
        ids = self.tok.encode(prompt).ids if isinstance(prompt, str) else list(prompt)
        ids = torch.tensor([ids], dtype=torch.long)
        start = ids.size(1)
        for _ in range(max_new_tokens):
            lg = self.logits(ids[:, -self.max_pos:], lora=lora)[0, -1].float()

            if repetition_penalty != 1.0:
                seen = torch.unique(ids[0])
                lg[seen] = torch.where(lg[seen] > 0, lg[seen] / repetition_penalty,
                                       lg[seen] * repetition_penalty)
            if no_repeat_ngram and ids.size(1) >= no_repeat_ngram:
                n = no_repeat_ngram
                tail = tuple(ids[0, -(n - 1):].tolist())
                seq = ids[0].tolist()
                for j in range(len(seq) - n + 1):
                    if tuple(seq[j:j + n - 1]) == tail:
                        lg[seq[j + n - 1]] = -float("inf")

            if temperature <= 0:
                nxt = int(lg.argmax())
            else:
                lg = lg / temperature
                if top_k:
                    kth = torch.topk(lg, min(top_k, lg.numel())).values[-1]
                    lg[lg < kth] = -float("inf")
                probs = F.softmax(lg, dim=-1)
                if top_p < 1.0:
                    sp, si = torch.sort(probs, descending=True)
                    cut = torch.cumsum(sp, 0) - sp > top_p
                    sp[cut] = 0.0
                    probs = torch.zeros_like(probs).scatter_(0, si, sp)
                    probs = probs / probs.sum()
                nxt = int(torch.multinomial(probs, 1))
            if stop_eos and self.eos is not None and nxt == self.eos:
                break
            ids = torch.cat([ids, torch.tensor([[nxt]])], dim=1)
            if stop_newline and "\n" in self.tok.decode([nxt]):
                break
        return self.tok.decode(ids[0, start:].tolist())

    def nats(self, text):
        """Cross-entropy per token. The check that RoPE is the right way round."""
        ids = torch.tensor([self.tok.encode(text).ids])
        lg = self.logits(ids)
        return float(F.cross_entropy(lg[0, :-1], ids[0, 1:]))


_CACHE = {}


def model(name=DEFAULT):
    if name not in _CACHE:
        _CACHE[name] = TinyLM(DIRS[name])
    return _CACHE[name]


def selftest():
    """Perplexity on prose each model should find easy, against its own uniform baseline.
    A RoPE convention applied to the wrong family still reads like English, so this is the
    only honest way to know the port is right."""
    probes = {
        "simplestories": "once upon a time there was a small creature who lived in a blue "
                         "box. every day it looked out and waited for someone to come.",
        "gpt-s": "The city of Vienna is the capital of Austria. It sits on the river "
                 "Danube and is known for its music and its long history.",
    }
    for name in DIRS:
        if not os.path.isdir(DIRS[name]):
            continue
        m = model(name)
        n = m.nats(probes[name])
        v = m.cfg["vocab_size"]
        print("%-14s %d params  %d layers  ce %.3f nats  ppl %6.1f  (uniform %.1f)"
              % (name, sum(x.numel() for x in m.sd.values()), m.n_layer,
                 n, math.exp(n), v))


if __name__ == "__main__":
    import sys
    import time
    selftest()
    name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    prompt = sys.argv[2] if len(sys.argv) > 2 else "Once upon a time there was a small creature who"
    m = model(name)
    t0 = time.time()
    out = m.generate(prompt, max_new_tokens=60, temperature=0.8, seed=0)
    dt = time.time() - t0
    print("\n%s  %d tok in %.0f ms (%.0f tok/s)" % (name, 60, dt * 1000, 60 / dt))
    print("---")
    print(prompt + out)
