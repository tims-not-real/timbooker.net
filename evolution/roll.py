"""Roll a generation: read the counts, select, mutate, regenerate the lines.

    python -m evolution.roll found                 write generation 0
    python -m evolution.roll roll                  fetch /counts and roll one generation
    python -m evolution.roll roll --counts f.json  the same, from a file
    python -m evolution.roll lines                 regenerate the current lines, no evolution
    python -m evolution.roll verify                the determinism proof
    python -m evolution.roll floortest             the per-line filter does not launder
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
    """slot -> {"shows": n, "pats": n}, from what the Worker of #28 hands back:

        {"gen": 3, "totals": {...},
         "agents": {"a1": {"shows": 2, "pats": 2, "lines": {...}, "hours": {...}}}}

    Only shows and pats per agent are read. The per-line and per-hour breakdowns are the
    endpoint's business; selection has no use for them.

    Deliberately tolerant about the envelope and the key spelling -- `agents` or `counts`
    or a bare mapping, `a1` or `1` or `3:1` -- and deliberately INTOLERANT of parsing
    nothing. A response whose shape had drifted would otherwise read as eight agents with
    no shows, which is indistinguishable from a quiet week, and the job would skip every
    Monday for ever without once saying anything was wrong."""
    d = body
    if isinstance(d, dict):
        for k in ("agents", "counts"):
            if isinstance(d.get(k), (dict, list)):
                d = d[k]
                break
    if isinstance(d, list):
        d = {i: v for i, v in enumerate(d)}
    if not isinstance(d, dict):
        raise Unreachable("counts response is a %s, not an object" % type(d).__name__)
    out = {}
    for k, v in d.items():
        if not isinstance(v, dict) or "shows" not in v:
            continue
        key = str(k)
        if ":" in key:
            g, key = key.split(":", 1)
            if g.isdigit() and int(g) != gen:
                continue
        key = key[1:] if key[:1].lower() == "a" else key
        if not key.isdigit():
            continue
        out[int(key)] = {"shows": int(v.get("shows", 0)),
                         "pats": int(v.get("pats", 0))}
    if not out:
        raise Unreachable("the counts response held no agent with a shows count. The"
                          " shape has drifted, and selecting on it would be selecting"
                          " on zeros.")
    return out


def announce(subject):
    """The one line the commit gets. Written to $GITHUB_OUTPUT when there is one, so
    the workflow does not have to parse stdout and nothing is left on disk."""
    print(subject)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("subject=%s\n" % subject.replace(chr(10), " "))


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
        # The generation does not roll, but the file is still touched, on purpose.
        # GitHub disables a scheduled workflow in a public repo after 60 days with no
        # repository activity. A skip that commits nothing would stop the creature dead
        # after nine quiet weeks, with no error anywhere to say why.
        pop["checked"] = {"date": _today(), "action": "skipped",
                          "reason": "fewer than %d shows for agents %s"
                                    % (P.MIN_SHOWS, thin),
                          "shows": {str(a["slot"]): counts.get(a["slot"], {}).get("shows", 0)
                                    for a in pop["agents"]}}
        P.save(pop, P.POP_PATH)
        announce("Generation %d stands: agents %s were shown fewer than %d times"
                 % (gen, ", ".join(str(s) for s in thin), P.MIN_SHOWS))
        print("Not enough data to select on. Nothing but the checked date moved, which"
              " is what keeps the schedule alive.")
        return 0

    nxt = P.step(pop, counts, {a["slot"]: a.get("ce", 0.0) for a in pop["agents"]})
    nxt["checked"] = {"date": _today(), "action": "rolled"}
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
    sh = nxt["last"]["lineages"]
    announce("Generation %d: %d lineages, biggest %d of %d, %d immigrant%s"
             % (nxt["generation"], len(sh), max(sh.values()), P.N_AGENTS,
                sum(1 for a in nxt["agents"] if a["origin"].startswith("immigrant")),
                "" if sum(1 for a in nxt["agents"]
                          if a["origin"].startswith("immigrant")) == 1 else "s"))
    return 0


def cmd_verify(args):
    """Acceptance check 3: the same population.json regenerates byte-identical lines."""
    pop = P.load()
    quiet = dict(screen=False, log=lambda *x: None)
    a, _ = P.generate(dict(pop, agents=[dict(x) for x in pop["agents"]]), **quiet)
    b, _ = P.generate(dict(pop, agents=[dict(x) for x in pop["agents"]]), **quiet)
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


def cmd_floortest(args):
    """The per-line filter must not launder a bad agent past the agent-level floor.

    If the agent-level floor scored what survived the per-line filter, a broken agent
    would look fluent because its worst output had already been removed, the floor would
    quietly stop firing, and the population could drift out of English with nothing
    saying so. So: a deliberately broken agent -- one draw at sigma 0.45, well past the
    0.2 where the model stops speaking English -- is scored with the per-line filter
    switched ON, dropped into a real eight-agent population, and given the best pat ratio
    in it. It has to die anyway."""
    from . import tinylm
    m = tinylm.model()
    sc = P.scales(m)
    pop = P.load()
    broken = {"slot": 0, "lineage": "broken", "origin": "founder", "born": 0,
              "parent": None, "seeds": [[12345, 0.45]], "line_seed": 777}
    said, ce, rec = P.agent_lines(m, sc, pop, broken, filter_lines=True)
    print("a broken agent at sigma 0.45, per-line filter ON")
    print("  agent-level ce      %.3f   (floor %.2f, over it: %s)"
          % (ce, P.FLUENCY_FLOOR, ce > P.FLUENCY_FLOOR))
    print("  lines published     %d of %d draws" % (rec["published"], rec["drawn"]))
    print("  it says             %s"
          % json.dumps(said[0] if said else "(nothing publishable)"))

    agents = [dict(broken, slot=0)] + [dict(a) for a in pop["agents"][1:]]
    ces = {0: ce}
    counts = {0: {"shows": 100, "pats": 90}}          # patted nine times out of ten
    for a in agents[1:]:
        ces[a["slot"]] = a["ce"]
        counts[a["slot"]] = {"shows": 100, "pats": 10}
    ranked = P.rank(agents, counts, ces)
    print("\ndropped into generation %d and given a 0.90 pat ratio against everyone else's 0.10:"
          % pop["generation"])
    for r in ranked:
        print("  slot %d  %-8s ratio %.2f  ce %5.3f  %s"
              % (r["slot"], r["lineage"], r["ratio"], r["ce"],
                 "DEAD, floored" if r["floored"] else "alive"))
    nxt = P.step({"generation": pop["generation"], "agents": agents,
                  "n_lines": pop["n_lines"], "prompt": pop["prompt"]}, counts, ces)
    survived = any(a["lineage"] == "broken" for a in nxt["agents"])
    ok = ranked[-1]["lineage"] == "broken" and ranked[-1]["floored"] and not survived
    print("\nlast, floored, and gone from the next generation despite the pats: %s" % ok)
    return 0 if ok else 1


def _today():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


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
    p = sub.add_parser("floortest"); p.set_defaults(fn=cmd_floortest)
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
