#!/usr/bin/env python3
"""Feasibility spike for issue #29: can a free GitHub runner roll a generation?

Scratch. Nothing here is the implementation of #29 — it is the measurement that says
whether #29 is buildable at all. Delete the whole spike/ directory once the answer is
recorded.

What it does, and times separately:

  download      SimpleStories-V2-5M from the Hub into the HF cache
  load          safetensors -> torch, via the sandbox's gpts.py (unchanged copy)
  reconstruct   8 agents, each `base + sum of seeded Gaussian noise`, sigma scaled per
                tensor by that tensor's own standard deviation
  verify        the lineage sum equals applying the same mutations in order (#29 check 4)
  generate      8 agents x 24 lines, batched, twice, and the two passes are hashed

Peak RSS is sampled from /proc/self/status in a background thread. Everything lands in
one JSON file so the workflow can print a table and a second runner can diff it.
"""
import argparse
import hashlib
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Pin the thread count BEFORE torch is imported: OMP reads it at load time, and the
# determinism question is precisely whether the reduction order in the BLAS calls is
# stable across machines.
THREADS = int(os.environ.get("SPIKE_THREADS", "1"))
for v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(v, str(THREADS))

import torch                                                          # noqa: E402
import torch.nn.functional as F                                       # noqa: E402

REPO = "SimpleStories/SimpleStories-V2-5M"
NEEDED = ["config.json", "model.safetensors", "tokenizer.json"]

# From the sandbox. SimpleStories ignores a prompt ending in an open quote; this one
# conditions it into first-person creature lines.
PROMPT = "a lonely little creature speaks to a visitor. it says: i "

SIGMA_INIT = 0.15        # the spread of the founding population  (#29)
SIGMA_STEP = 0.025       # the per-generation step                 (#29)


# ------------------------------------------------------------------ instrumentation
class Peak(threading.Thread):
    """VmHWM is the kernel's own high-water mark, so it cannot be missed between samples.
    VmRSS is sampled anyway to see the shape of the curve."""

    daemon = True

    def __init__(self):
        super().__init__()
        self.hwm = 0
        self.stop = threading.Event()

    def run(self):
        while not self.stop.wait(0.25):
            self.sample()

    def sample(self):
        try:
            with open("/proc/self/status") as fh:
                for line in fh:
                    if line.startswith("VmHWM:"):
                        self.hwm = max(self.hwm, int(line.split()[1]))
        except OSError:
            pass


TIMES = {}


class phase:
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.t = time.perf_counter()
        return self

    def __exit__(self, *a):
        TIMES[self.name] = round(time.perf_counter() - self.t, 3)
        print("[%-13s] %7.2f s" % (self.name, TIMES[self.name]), flush=True)


def dirsize(path):
    n = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                n += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return n


# ------------------------------------------------------------------ the genome
def noise_like(w, seed, key):
    """One generator per (seed, tensor), so reconstruction does not depend on the order
    the tensors are walked in. A single stream shared across tensors would make the
    lineage silently order-sensitive, which is a bug waiting for the day someone changes
    a dict."""
    h = hashlib.blake2b(("%d|%s" % (seed, key)).encode(), digest_size=8).digest()
    g = torch.Generator().manual_seed(int.from_bytes(h, "big") % (2 ** 63 - 1))
    return torch.randn(w.shape, generator=g, dtype=torch.float32)


def reconstruct(base_sd, keys, scale, lineage):
    """base + sum of seeded Gaussian noise. lineage is [(seed, sigma), ...]."""
    sd = dict(base_sd)
    for k in keys:
        w = base_sd[k].clone()
        for seed, sigma in lineage:
            w.add_(noise_like(w, seed, k), alpha=sigma * scale[k])
        sd[k] = w
    return sd


def apply_in_order(base_sd, keys, scale, lineage):
    """The same mutations applied one generation at a time, which is what actually
    happened historically. Must agree with reconstruct() to the bit. (#29 check 4.)"""
    sd = {k: v.clone() for k, v in base_sd.items()}
    for seed, sigma in lineage:
        for k in keys:
            sd[k].add_(noise_like(sd[k], seed, k), alpha=sigma * scale[k])
    return sd


# ------------------------------------------------------------------ generation
@torch.inference_mode()
def speak(sd, m, n, max_new=26, temperature=0.95, top_p=0.95, seed=0):
    """n utterances from one agent, batched. Same prompt every row, so no padding.

    Lifted from evo_experiment.speak, minus the GPU. The one change is that the logits
    are taken from the last position only: gpts.logits() runs the tied head over every
    position, which on a 4019 vocab is most of the arithmetic and all of it thrown away."""
    torch.manual_seed(seed)
    pid = m.tok.encode(PROMPT).ids
    ids = torch.tensor([pid] * n, dtype=torch.long)
    done = torch.zeros(n, dtype=torch.bool)
    old, m.sd = m.sd, sd
    try:
        for _ in range(max_new):
            lg = last_logits(m, ids).float() / temperature
            p = F.softmax(lg, -1)
            sp, si = torch.sort(p, descending=True, dim=-1)
            cut = torch.cumsum(sp, -1) - sp > top_p
            sp = sp.masked_fill(cut, 0.0)
            p = torch.zeros_like(p).scatter_(1, si, sp)
            nxt = torch.multinomial(p / p.sum(-1, keepdim=True), 1)
            nxt[done] = m.eos if m.eos is not None else 0
            ids = torch.cat([ids, nxt], 1)
            done |= (nxt.squeeze(1) == (m.eos if m.eos is not None else -1))
            if bool(done.all()):
                break
    finally:
        m.sd = old

    outs = []
    for r in range(n):
        t = ids[r, len(pid):].tolist()
        if m.eos in t:
            t = t[:t.index(m.eos)]
        s = m.tok.decode(t).strip()
        for stop in [chr(34), chr(10)]:
            if stop in s:
                s = s.split(stop)[0]
        ends = [j for j in (s.find(c) for c in ".?!") if j > 0]
        s = s[:min(ends) + 1] if ends else s
        s = s.strip()
        outs.append(s if s[:2].lower() == "i " else ("i " + s).strip())
    return outs


@torch.inference_mode()
def last_logits(m, ids):
    """m.logits(), but the head is applied to the final position only."""
    sd = m.sd
    B, T = ids.shape
    x = F.embedding(ids, sd[m.emb])
    for kk in m.K:
        h = m._rms(x, sd[kk["ln1"]])
        q = (h @ sd[kk["q"]].t()).view(B, T, m.n_head, m.hd).transpose(1, 2)
        k = (h @ sd[kk["k"]].t()).view(B, T, m.n_kv, m.hd).transpose(1, 2)
        v = (h @ sd[kk["v"]].t()).view(B, T, m.n_kv, m.hd).transpose(1, 2)
        q, k = m._rope(q, k, T)
        k = k.unsqueeze(2).expand(B, m.n_kv, m.n_rep, T, m.hd).reshape(B, m.n_head, T, m.hd)
        v = v.unsqueeze(2).expand(B, m.n_kv, m.n_rep, T, m.hd).reshape(B, m.n_head, T, m.hd)
        y = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        y = y.transpose(1, 2).contiguous().view(B, T, m.n_head * m.hd)
        x = x + y @ sd[kk["o"]].t()
        h = m._rms(x, sd[kk["ln2"]])
        x = x + (F.silu(h @ sd[kk["gate"]].t()) * (h @ sd[kk["up"]].t())) @ sd[kk["down"]].t()
    x = m._rms(x[:, -1], sd[m.final])
    return x @ sd[m.emb].t()


def digest(lines):
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", type=int, default=8)
    ap.add_argument("--lines", type=int, default=24)
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--out", default="spike-result.json")
    ap.add_argument("--lines-out", default="spike-lines.txt")
    ap.add_argument("--label", default=os.environ.get("SPIKE_LABEL", "run"))
    args = ap.parse_args()

    peak = Peak()
    peak.start()
    torch.set_num_threads(THREADS)

    env = {
        "label": args.label,
        "threads_requested": THREADS,
        "torch_threads": torch.get_num_threads(),
        "torch": torch.__version__,
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
    }
    try:
        with open("/proc/cpuinfo") as fh:
            txt = fh.read()
        for line in txt.splitlines():
            if line.startswith("model name"):
                env["cpu"] = line.split(":", 1)[1].strip()
                break
        env["avx512"] = " avx512f " in " " + txt.split("flags")[1].split("\n")[0] + " " \
            if "flags" in txt else None
    except OSError:
        pass
    print(json.dumps(env, indent=2), flush=True)

    # ---- download -------------------------------------------------------------
    from huggingface_hub import snapshot_download
    with phase("download"):
        model_dir = snapshot_download(REPO, allow_patterns=NEEDED)
    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))

    # ---- load -----------------------------------------------------------------
    import gpts
    gpts.DIRS = {"simplestories": model_dir}
    with phase("load"):
        m = gpts.model("simplestories")
    base_sd = m.sd
    keys = [k for k in base_sd if k.endswith(".weight")]
    params = sum(v.numel() for v in base_sd.values())

    with phase("std_scale"):
        scale = {k: float(base_sd[k].float().std()) for k in keys}

    # ---- lineages -------------------------------------------------------------
    # Eight agents at generation 4: one founding mutation at the population sigma, then
    # three steps. That is the shape #29 will have after a month.
    lineages = []
    for a in range(args.agents):
        lin = [(1000 + a, SIGMA_INIT)]
        for gen in range(3):
            lin.append((900000 + 100 * gen + a, SIGMA_STEP))
        lineages.append(lin)

    with phase("reconstruct"):
        agents = [reconstruct(base_sd, keys, scale, lin) for lin in lineages]

    # ---- #29 acceptance check 4 -----------------------------------------------
    with phase("verify_sum"):
        seq = apply_in_order(base_sd, keys, scale, lineages[0])
        worst = max(float((agents[0][k] - seq[k]).abs().max()) for k in keys)
        nrm = sum(float((agents[0][k] - seq[k]).float().pow(2).sum()) for k in keys) ** 0.5
        del seq
    print("lineage sum vs sequential:  max|d| = %g   ||d|| = %g" % (worst, nrm), flush=True)

    # ---- generate -------------------------------------------------------------
    runs = []
    for p in range(args.passes):
        with phase("generate_%d" % p):
            out = []
            for a, sd in enumerate(agents):
                out.append(speak(sd, m, args.lines, seed=4242 + a))
        flat = ["%d\t%d\t%s" % (a, i, s)
                for a, ls in enumerate(out) for i, s in enumerate(ls)]
        runs.append(flat)
        print("  pass %d  %d lines  sha256 %s" % (p, len(flat), digest(flat)), flush=True)

    same_job = all(r == runs[0] for r in runs)
    print("identical across %d passes in this job: %s" % (args.passes, same_job), flush=True)

    with open(args.lines_out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(runs[0]) + "\n")

    peak.sample()
    peak.stop.set()
    result = {
        "env": env,
        "times": TIMES,
        "params": params,
        "agents": args.agents,
        "lines_per_agent": args.lines,
        "peak_rss_mb": round(peak.hwm / 1024.0, 1),
        "lineage_sum_max_abs_diff": worst,
        "lineage_sum_l2_diff": nrm,
        "digest": digest(runs[0]),
        "digests": [digest(r) for r in runs],
        "identical_in_job": same_job,
        "hf_cache_bytes": dirsize(hf_home),
        "sample_lines": runs[0][:6],
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
