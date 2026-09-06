"""Roll a generation: read the counts, select, mutate, regenerate the lines.

    python -m evolution.roll found                 write generation 0
    python -m evolution.roll roll                  fetch /counts and roll one generation
    python -m evolution.roll roll --counts f.json  the same, from a file
    python -m evolution.roll lines                 regenerate the current lines, no evolution
    python -m evolution.roll verify                the determinism proof
    python -m evolution.roll reconstruct           the lineage proof
    python -m evolution.roll simulate 20           selection only, fake counts, 20 rolls

`roll` writes nothing at all unless it gets to the end. If the endpoint is unreachable it
fails loudly; if any agent has been shown fewer than MIN_SHOWS times it says so and exits
clean, having changed nothing.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from . import population as P

COUNTS_URL = os.environ.get("PAT_COUNTS_URL", "")


class Unreachable(RuntimeError):
    pass


def fetch_counts(gen, url=None, timeout=20):
    """GET /counts?gen=N from the Worker of #28.

    Tolerant about the envelope and strict about the two numbers: a pat count without a
    show count says nothing, because agents are not shown equally often."""
    url = url or COUNTS_URL
    if not url:
        raise Unreachable("no counts endpoint: set PAT_COUNTS_URL")
    full = "%s%sgen=%d" % (url, "&" if "?" in url else "?", gen)
    try:
        with urllib.request.urlopen(full, timeout=timeout) as r:
            if r.status != 200:
                raise Unreachable("%s returned HTTP %d" % (full, r.status))
            body = json.loads(r.read().decode("utf-8"))
    except Unreachable:
        raise
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise Unreachable("%s: %s" % (full, e))
    return parse_counts(body, gen)


def parse_counts(body, gen):
    """slot -> {"shows": n, "pats": n}, from whatever shape the endpoint hands back.

    Accepts `{"counts": {...}}` or a bare mapping, and keys of `3`, `"3"` or `"7:3"`."""
    d = body.get("counts", body) if isinstance(body, dict) else body
    if isinstance(d, list):
        d = {i: v for i, v in enumerate(d)}
    out = {}
    for k, v in d.items():
        s = str(k)
        if ":" in s:
            g, s = s.split(":", 1)
            if int(g) != gen:
                continue
        try:
            slot = int(s)
        except ValueError:
            continue
        out[slot] = {"shows": int(v.get("shows", 0)), "pats": int(v.get("pats", 0))}
    return out


def write(pop, lines, log=print):
    P.save(pop, P.POP_PATH)
    P.save(lines, P.LINES_PATH)
    log("wrote %s and %s" % (os.path.relpath(P.POP_PATH), os.path.relpath(P.LINES_PATH)))


# ------------------------------------------------------------------ commands
def cmd_found(args):
    if os.path.exists(P.POP_PATH) and not args.force:
        sys.exit("%s already exists; --force to replace it" % P.POP_PATH)
    pop = P.found(0)
    print("founding %d agents at sigma %.3f" % (P.N_AGENTS, P.SIGMA_FOUND))
    lines, _ = P.generate(pop)
    write(pop, lines)
    return 0


def cmd_lines(args):
    pop = P.load()
    lines, ce = P.generate(pop, screen=False)
    write(pop, lines)
    return 0


def cmd_roll(args):
    pop = P.load()
    gen = pop["generation"]
    if args.counts:
        counts = parse_counts(json.load(open(args.counts)), gen)
        print("counts from %s" % args.counts)
    else:
        counts = fetch_counts(gen, args.url)
        print("counts from %s" % (args.url or COUNTS_URL))

    rows = P.rank(pop["agents"], counts, {a["slot"]: a.get("ce", 0.0)
                                          for a in pop["agents"]})
    print("generation %d, as the visitors left it:" % gen)
    print("  slot lineage      shows  pats   pats/shows    ce")
    for r in rows:
        print("  %4d %-12s %5d %5d      %7.4f  %5.3f%s"
              % (r["slot"], r["lineage"], r["shows"], r["pats"], r["ratio"],
                 r["ce"] or 0.0, "  FLOORED" if r["floored"] else ""))

    thin = P.thin_data(counts, pop["agents"])
    if thin:
        print("SKIPPED: not enough data. Agents %s have fewer than %d shows."
              % (", ".join(str(s) for s in thin), P.MIN_SHOWS))
        print("Nothing written. Do not evolve on nothing.")
        return 0

    nxt = P.step(pop, counts, {a["slot"]: a.get("ce", 0.0) for a in pop["agents"]})
    print("\ngeneration %d:" % nxt["generation"])
    for a in nxt["agents"]:
        print("  slot %d  %-12s %-14s parent %s"
              % (a["slot"], a["lineage"], a["origin"],
                 "-" if a["parent"] is None else str(a["parent"])))
    if nxt["last"]["reseeded_for_cap"]:
        print("  reseeded for the half-population cap: slots %s"
              % nxt["last"]["reseeded_for_cap"])
    print("  lineages: %s" % json.dumps(nxt["last"]["lineages"]))
    lines, _ = P.generate(nxt)
    write(nxt, lines)
    return 0


def cmd_verify(args):
    """Acceptance check 3: the same population.json regenerates byte-identical lines."""
    pop = P.load()
    a, _ = P.generate(dict(pop, agents=[dict(x) for x in pop["agents"]]), screen=False,
                      log=lambda *x: None)
    b, _ = P.generate(dict(pop, agents=[dict(x) for x in pop["agents"]]), screen=False,
                      log=lambda *x: None)
    sa = json.dumps(a, sort_keys=True, ensure_ascii=False).encode()
    sb = json.dumps(b, sort_keys=True, ensure_ascii=False).encode()
    on_disk = open(P.LINES_PATH, "rb").read() if os.path.exists(P.LINES_PATH) else b""
    sc = json.dumps(json.loads(on_disk.decode("utf-8")), sort_keys=True,
                    ensure_ascii=False).encode() if on_disk else None
    print("generation %d, %d lines" % (pop["generation"], len(a["lines"])))
    print("  run 1 sha256 %s" % _sha(sa))
    print("  run 2 sha256 %s" % _sha(sb))
    print("  run 1 == run 2: %s" % (sa == sb))
    if sc is not None:
        print("  committed lines.json sha256 %s" % _sha(sc))
        print("  run 1 == committed: %s" % (sa == sc))
    return 0 if sa == sb and (sc is None or sa == sc) else 1


def cmd_reconstruct(args):
    """Acceptance check 4: reconstructing from the lineage equals applying the
    mutations in order. The norm difference has to be zero, not small."""
    import torch
    from . import tinylm
    m = tinylm.model()
    sc = P.scales(m)
    pop = P.load()
    a = pop["agents"][0]
    child = {"seeds": [list(s) for s in a["seeds"]]
             + [[P.seed_for("mut", 999, 0), P.SIGMA_STEP]]}

    stepwise = {k: v.clone() for k, v in m.sd.items()}
    for seed, sigma in child["seeds"]:
        P.add_noise(stepwise, m, sc, int(seed), float(sigma))
    fresh = P.reconstruct(m, sc, child)

    parent = P.reconstruct(m, sc, a)
    from_parent = {k: v.clone() for k, v in parent.items()}
    s, g = child["seeds"][-1]
    P.add_noise(from_parent, m, sc, int(s), float(g))

    def norm(x, y):
        return float(sum(float((x[k] - y[k]).double().pow(2).sum()) for k in x)) ** 0.5

    def drift(x):
        num = den = 0.0
        for k in x:
            d = (x[k] - m.sd[k]).double()
            num += float(d.pow(2).sum())
            den += d.numel() * sc[k] ** 2
        return (num / den) ** 0.5

    print("lineage %s + one step" % json.dumps(a["seeds"]))
    print("  ||reconstructed - applied in order||   = %.17g" % norm(fresh, stepwise))
    print("  ||reconstructed - parent + one step||  = %.17g" % norm(fresh, from_parent))
    print("  tensors that differ in any bit         = %d"
          % sum(0 if torch.equal(fresh[k], stepwise[k]) else 1 for k in fresh))
    print("  drift from pretrained, in weight stds  = %.4f  (parent %.4f)"
          % (drift(fresh), drift(parent)))
    return 0 if norm(fresh, stepwise) == 0.0 and norm(fresh, from_parent) == 0.0 else 1


def cmd_simulate(args):
    """Acceptance check 5: fake counts, N generations, and no lineage over half.

    Selection only. The model is not run, because what is being checked is the
    bookkeeping and not the language."""
    import random
    rnd = random.Random(args.seed)
    pop = P.found(0)
    worst = 0
    print("gen  lineages  biggest  founders left  immigrants  shares")
    for g in range(args.n):
        counts, ce = {}, {}
        for a in pop["agents"]:
            shows = rnd.randint(20, 120)
            counts[a["slot"]] = {"shows": shows,
                                 "pats": int(shows * rnd.betavariate(2, 8))}
            # a tenth of agents drift over the floor in any given generation
            ce[a["slot"]] = 4.9 if rnd.random() < 0.1 else round(rnd.uniform(3.9, 4.5), 3)
        pop = P.step(pop, counts, ce)
        sh = P.lineage_shares(pop["agents"])
        big = max(sh.values())
        worst = max(worst, big)
        founders = sum(v for k, v in sh.items() if k.startswith("f"))
        imm = sum(1 for a in pop["agents"] if a["origin"].startswith("immigrant"))
        print("%3d  %8d  %7d  %13d  %10d  %s"
              % (pop["generation"], len(sh), big, founders, imm, json.dumps(sh)))
    print("\nbiggest lineage over %d generations: %d of %d (cap %d)"
          % (args.n, worst, P.N_AGENTS, P.MAX_LINEAGE))
    return 0 if worst <= P.MAX_LINEAGE else 1


def _sha(b):
    import hashlib
    return hashlib.sha256(b).hexdigest()[:16]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="evolution.roll", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("found"); p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_found)
    p = sub.add_parser("lines"); p.set_defaults(fn=cmd_lines)
    p = sub.add_parser("roll")
    p.add_argument("--counts"); p.add_argument("--url")
    p.set_defaults(fn=cmd_roll)
    p = sub.add_parser("verify"); p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("reconstruct"); p.set_defaults(fn=cmd_reconstruct)
    p = sub.add_parser("simulate")
    p.add_argument("n", type=int, nargs="?", default=20)
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(fn=cmd_simulate)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except Unreachable as e:
        sys.exit("counts endpoint unreachable: %s\nNothing written." % e)


if __name__ == "__main__":
    sys.exit(main())
