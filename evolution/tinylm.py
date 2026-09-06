"""SimpleStories-V2-5M in plain torch, on the CPU, with no transformers dependency.

Ported from the sandbox (`Github/temp/evo-sandbox/gpts.py`), cut down to the one family
this site uses. The forward pass is written out because it is six layers and because the
weights have to be handed in from outside: an agent is a reconstructed weight dict, not a
checkpoint on disk.

*** RoPE here rotates the two HALVES of each head against each other. *** The other
convention -- interleaved pairs -- still produces fluent-looking English, just worse, so
getting it wrong is silent. `selftest()` is the check: cross-entropy on easy prose.

Two rules hold everything else together:

  - The model is pinned to one revision. A different revision would change every line the
    creature has ever said without changing `population.json`.
  - Sampling never touches a global RNG. Every random number comes from a
    `numpy.random.RandomState` seeded from the population file, because NEP 19 freezes
    that generator's stream across numpy versions and platforms for good.
"""
import json
import math
import os

import numpy as np
import torch
import torch.nn.functional as F
from safetensors.torch import load_file
from tokenizers import Tokenizer

REPO = "SimpleStories/SimpleStories-V2-5M"
REVISION = "c4b3a4bb81297f5316697098e1d4b65c1249daf8"


def model_dir():
    """Where the pretrained weights are. $SS_MODEL_DIR wins; otherwise the HF cache,
    downloading the pinned revision if it is not there yet (21MB)."""
    d = os.environ.get("SS_MODEL_DIR")
    if d:
        return d
    from huggingface_hub import snapshot_download
    return snapshot_download(REPO, revision=REVISION,
                             allow_patterns=["*.json", "*.safetensors"])


class TinyLM:
    def __init__(self, d=None):
        d = d or model_dir()
        with open(os.path.join(d, "config.json")) as fh:
            c = self.cfg = json.load(fh)
        self.sd = load_file(os.path.join(d, "model.safetensors"))
        self.tok = Tokenizer.from_file(os.path.join(d, "tokenizer.json"))
        self.n_layer = c["num_hidden_layers"]
        self.n_head = c["num_attention_heads"]
        self.n_kv = c["num_key_value_heads"]
        self.hd = c["head_dim"]
        self.n_rep = self.n_head // self.n_kv
        self.eps = c["rms_norm_eps"]
        self.theta = c["rope_theta"]
        self.eos = c.get("eos_token_id")
        # declares 2048 positions, trained at 512; either way this only bounds prefix
        self.max_pos = min(c["max_position_embeddings"], 512)
        self._rope_cache = None
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
            "down": "model.layers.%d.mlp.down_proj.weight" % i}
            for i in range(self.n_layer)]

    # ------------------------------------------------------------------ pieces
    def _rms(self, x, w):
        r = torch.rsqrt(x.float().pow(2).mean(-1, keepdim=True) + self.eps)
        return (x.float() * r).type_as(x) * w

    def _rope(self, q, k, T):
        if self._rope_cache is None or self._rope_cache[0] < T:
            inv = 1.0 / (self.theta ** (torch.arange(0, self.hd, 2, dtype=torch.float32)
                                        / self.hd))
            t = torch.arange(max(T, self.max_pos), dtype=torch.float32)
            fr = torch.outer(t, inv)
            emb = torch.cat([fr, fr], dim=-1)              # halves, not pairs
            self._rope_cache = (t.numel(), emb.cos(), emb.sin())
        cos, sin = self._rope_cache[1][:T][None, None], self._rope_cache[2][:T][None, None]

        def rot(x):
            h = x.shape[-1] // 2
            half = torch.cat([-x[..., h:], x[..., :h]], dim=-1)
            return x * cos + half * sin
        return rot(q), rot(k)

    # ----------------------------------------------------------------- forward
    @torch.inference_mode()
    def logits(self, sd, ids, last_only=False):
        """ids: LongTensor (B, T) -> logits (B, T, vocab), against a supplied weight dict.

        No KV cache. Twenty-six tokens through a 5M model is milliseconds, and recomputing
        the prefix each step removes every special case an incremental path would need.

        `last_only` slices before the tied head. Sampling wants one row and the head is
        256 x 4019, so computing it over every position and throwing all but the last away
        is the most expensive thing in the whole job that nobody looks at."""
        B, T = ids.shape
        x = F.embedding(ids, sd[self.emb])
        for kk in self.K:
            h = self._rms(x, sd[kk["ln1"]])
            q = h @ sd[kk["q"]].t()
            k = h @ sd[kk["k"]].t()
            v = h @ sd[kk["v"]].t()
            q = q.view(B, T, self.n_head, self.hd).transpose(1, 2)
            k = k.view(B, T, self.n_kv, self.hd).transpose(1, 2)
            v = v.view(B, T, self.n_kv, self.hd).transpose(1, 2)
            q, k = self._rope(q, k, T)
            k = k.unsqueeze(2).expand(B, self.n_kv, self.n_rep, T, self.hd)
            v = v.unsqueeze(2).expand(B, self.n_kv, self.n_rep, T, self.hd)
            k = k.reshape(B, self.n_head, T, self.hd)
            v = v.reshape(B, self.n_head, T, self.hd)
            y = F.scaled_dot_product_attention(q, k, v, is_causal=True)
            y = y.transpose(1, 2).contiguous().view(B, T, self.n_head * self.hd)
            x = x + y @ sd[kk["o"]].t()
            h = self._rms(x, sd[kk["ln2"]])
            x = x + (F.silu(h @ sd[kk["gate"]].t()) * (h @ sd[kk["up"]].t())) \
                @ sd[kk["down"]].t()
        if last_only:
            x = x[:, -1:]
        x = self._rms(x, sd[self.final])
        return x @ sd[self.emb].t()                        # tied head

    # ---------------------------------------------------------------- sampling
    @torch.inference_mode()
    def sample(self, sd, prompt, n, rs, max_new=26, temperature=0.95, top_p=0.95):
        """n continuations of one prompt, batched. Every draw comes from `rs`.

        Rows are drawn in a fixed order at every step, so the whole batch is one frozen
        stream: same weights and same seed, same n lines, in the same order, for ever."""
        pid = self.tok.encode(prompt).ids
        ids = torch.tensor([pid] * n, dtype=torch.long)
        done = [False] * n
        for _ in range(max_new):
            lg = self.logits(sd, ids, last_only=True)[:, -1].float() / temperature
            p = F.softmax(lg, -1)
            sp, si = torch.sort(p, descending=True, dim=-1)
            cut = torch.cumsum(sp, -1) - sp > top_p
            sp = sp.masked_fill(cut, 0.0)
            sp = sp / sp.sum(-1, keepdim=True)
            cdf = torch.cumsum(sp, -1)
            nxt = []
            for r in range(n):
                u = rs.random_sample()                     # one draw per row, always
                if done[r]:
                    nxt.append(self.eos)
                    continue
                j = int(torch.searchsorted(cdf[r], torch.tensor(u, dtype=cdf.dtype)))
                j = min(j, cdf.shape[-1] - 1)
                t = int(si[r, j])
                if t == self.eos:
                    done[r] = True
                nxt.append(t)
            ids = torch.cat([ids, torch.tensor(nxt, dtype=torch.long)[:, None]], 1)
            if all(done):
                break
        out = []
        for r in range(n):
            t = ids[r, len(pid):].tolist()
            if self.eos in t:
                t = t[:t.index(self.eos)]
            out.append(self.tok.decode(t))
        return out

    @torch.inference_mode()
    def _nll(self, base_sd, texts):
        """Per-token negative log likelihood of each text under a frozen weight set."""
        ids = [self.tok.encode(t).ids[:self.max_pos] for t in texts]
        keep = [r for r, i in enumerate(ids) if len(i) >= 2]
        if not keep:
            return None, None, keep
        L = max(len(ids[r]) for r in keep)
        X = torch.zeros((len(keep), L), dtype=torch.long)
        M = torch.zeros((len(keep), L), dtype=torch.bool)
        for r, src in enumerate(keep):
            X[r, :len(ids[src])] = torch.tensor(ids[src])
            M[r, :len(ids[src])] = True
        lg = self.logits(base_sd, X)
        lp = F.log_softmax(lg[:, :-1].float(), -1)
        return -lp.gather(2, X[:, 1:].unsqueeze(-1)).squeeze(-1), M[:, 1:], keep

    def output_ce(self, base_sd, texts):
        """Cross-entropy of some agent's own lines, read by the FROZEN pretrained model.

        Not the agent's perplexity on fixed prose, which is the weaker thing: that asks
        whether it can still predict English when what matters is whether it can still
        produce it. And an agent cannot mark its own paper -- fifty rounds of noise can
        leave it perfectly sure that "fubszer" was the right word. The base model never
        mutates, so it is the one yardstick here that cannot bend."""
        nll, mask, keep = self._nll(base_sd, texts)
        if nll is None:
            return 99.0
        return float((nll * mask).sum() / mask.sum())

    def line_ce(self, base_sd, texts):
        """The same statistic, one number per line rather than one per agent."""
        nll, mask, keep = self._nll(base_sd, texts)
        out = [99.0] * len(texts)
        if nll is None:
            return out
        per = (nll * mask).sum(1) / mask.sum(1)
        for r, src in enumerate(keep):
            out[src] = float(per[r])
        return out


_M = None


def model():
    global _M
    if _M is None:
        # one thread, so the reduction order inside a matmul does not depend on how many
        # cores the machine that rolled the generation happened to have
        torch.set_num_threads(1)
        _M = TinyLM()
    return _M


def selftest():
    m = model()
    probe = ("once upon a time there was a small creature who lived in a blue box. every "
             "day it looked out and waited for someone to come.")
    ce = m.output_ce(m.sd, [probe])
    print("%s  %d params  ce %.3f nats  ppl %.1f  (uniform %d)"
          % (REPO, sum(v.numel() for v in m.sd.values()), ce, math.exp(ce),
             m.cfg["vocab_size"]))
    return ce


if __name__ == "__main__":
    ce = selftest()
    m = model()
    rs = np.random.RandomState(0)
    for line in m.sample(m.sd, "a lonely little creature speaks to a visitor. it says: i ",
                         4, rs):
        print("   i" + line.rstrip())
