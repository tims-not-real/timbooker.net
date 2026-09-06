"""The population: lineages, reconstruction, selection, mutation, immigration.

An agent is a seed lineage, not a weight file. `[(seed, sigma), ...]`, and its weights are
the pretrained model plus one seeded Gaussian draw per entry, added in order. Eight agents
as weights are 160MB; as lineages they are a few hundred bytes, so `population.json` is a
file you can read and `git log` is the whole evolutionary history.

Every number in here was measured in the sandbox, not chosen. The important ones:

  SIGMA_FOUND / SIGMA_STEP   Two sigmas, and this is the single most important number in
                             the project. With one sigma -- a step as large as the spread
                             it is stepping through -- the parent-to-child correlation of
                             fitness is -0.09. Nothing is inherited and selection sorts
                             pure noise. Found the population wide at 0.15, step it at
                             0.025.
  SIGMA_STEP again           Below 0.02 nothing changes; above 0.2 it stops speaking
                             English (perplexity 19 -> 60).
  IMMIGRANTS                 One slot in eight is a fresh mutation of the PRETRAINED
                             model, descended from nothing. Without it: by generation 25
                             every agent descended from one founder, and by generation 199
                             one sentence was 99.7% of all output. It was "i be lonely
                             too." Immigration makes that structurally impossible and
                             costs an eighth of the selection pressure, which at 65% of
                             the gain from ten visits is cheap.
  MAX_LINEAGE                No lineage may hold more than half the population. Excess
                             slots are reseeded as immigrants.
  FLUENCY_FLOOR              Cross-entropy of an agent's own lines under the frozen
                             pretrained model. Calibrated: pretrained output 3.96, good
                             evolved lines 3.38, junk from the unfloored control 7.09.
                             A hard floor, not a weighted term -- adding fluency to
                             fitness would fight the pat signal and hand the top score to
                             the blandest sentence available. Below the line you die;
                             above it nobody cares.
  LINE_FLOOR                 The same statistic per line rather than per agent, for
                             deciding what gets published. Measured on generation 0
                             against a hand-labelled set: AUC 0.978, and no clean line
                             above 4.99 against a junk median of 6.50. It stops at 5.5
                             rather than 5.0 because the statistic is predictability
                             under a children's-story model, not grammaticality, so
                             below that it starts cutting short plain sentences -- "i
                             take your songs.", "i see some coins." -- which are the
                             creature's best register. It cuts 14% of draws and no agent
                             needs more than 36 to fill 24.
  MIN_SHOWS                  Ten visits per agent per generation is 65% of the gain at
                             2.5% of the traffic. Under ten shows for any agent the roll
                             is a no-op: do not evolve on nothing.

Selection is on pats/shows, never on pats: agents are not shown equally often.
"""
import hashlib
import json
import os

SIGMA_FOUND = 0.15
SIGMA_STEP = 0.025
N_AGENTS = 8
N_LINES = 24
IMMIGRANTS = 1
KEEP = N_AGENTS // 2
MAX_LINEAGE = N_AGENTS // 2
MIN_SHOWS = 10
FLUENCY_FLOOR = 4.6
LINE_FLOOR = 5.5
HEAD_PUNCT = set(".-:;!?")
TOPUP = 8
MAX_LINE_DRAWS = 120

PROMPT = "a lonely little creature speaks to a visitor. it says: i "

HERE = os.path.dirname(os.path.abspath(__file__))
POP_PATH = os.path.join(HERE, "population.json")
LINES_PATH = os.path.join(HERE, "lines.json")


# ------------------------------------------------------------------ seeds
def seed_for(kind, gen, slot, draw=0):
    """A fresh seed, derived rather than drawn, so a generation can be recomputed from
    nothing but its number. blake2b is in the standard library and is stable across
    versions and platforms. The seed is written into the json regardless: the file is the
    record, this is only how a new one is chosen. `draw` counts rejected births."""
    h = hashlib.blake2b(("%s|%d|%d|%d" % (kind, gen, slot, draw)).encode(),
                        digest_size=8).digest()
    return int.from_bytes(h, "big") % (2 ** 31 - 1)


# ------------------------------------------------------------------ founding
def env():
    """What the lines were made with. Determinism is a property of a pinned environment,
    not of the maths: torch 2.6 produces a completely different 192 lines from 2.9, all
    192 of them and not a handful. And an upstream reupload of the model would silently
    re-base every lineage in the file, so the revision is pinned and written down too."""
    import numpy as np
    import torch
    from . import tinylm
    return {"model": tinylm.REPO, "revision": tinylm.REVISION,
            "torch": torch.__version__, "numpy": np.__version__}


def found(gen=0):
    """Generation 0. Eight founders, each one draw of the pretrained model at 0.15."""
    agents = []
    for slot in range(N_AGENTS):
        agents.append({
            "slot": slot,
            "lineage": "f%d" % slot,
            "origin": "founder",
            "born": gen,
            "parent": None,
            "seeds": [[seed_for("found", gen, slot), SIGMA_FOUND]],
            "line_seed": seed_for("line", gen, slot),
        })
    return {
        "schema": 1,
        "generation": gen,
        "n_agents": N_AGENTS,
        "n_lines": N_LINES,
        "prompt": PROMPT,
        "sigma": {"found": SIGMA_FOUND, "step": SIGMA_STEP},
        "env": env(),
        "agents": agents,
        "last": {"action": "founded"},
    }


def immigrant(gen, slot, reason="immigrant"):
    """A fresh mutation of the pretrained model, descended from nothing.

    It is founded at 0.15, not stepped at 0.025, because an immigrant has to be as far
    from the base model as a founder is. At 0.025 it would arrive as a near-copy of the
    pretrained model and be selected out on its first generation, which is not
    immigration, it is a rounding error."""
    return {
        "slot": slot,
        "lineage": "i%d.%d" % (gen, slot),
        "origin": reason,
        "born": gen,
        "parent": None,
        "seeds": [[seed_for("immig", gen, slot), SIGMA_FOUND]],
        "line_seed": seed_for("line", gen, slot),
    }


# ------------------------------------------------------------------ selection
def rank(agents, counts, ce=None):
    """Order the slots by pats/shows, with the floored ones dead at the bottom.

    `counts` maps slot -> {"shows": n, "pats": n}. `ce` maps slot -> cross-entropy of
    that agent's lines under the frozen base model, or None to skip the floor."""
    rows = []
    for a in agents:
        s = counts.get(a["slot"], {})
        shows = int(s.get("shows", 0))
        pats = int(s.get("pats", 0))
        c = None if ce is None else float(ce.get(a["slot"], 0.0))
        rows.append({"slot": a["slot"], "lineage": a["lineage"],
                     "shows": shows, "pats": pats,
                     "ratio": (pats / shows) if shows else 0.0,
                     "ce": c, "floored": c is not None and c > FLUENCY_FLOOR})
    alive = [r for r in rows if not r["floored"]]
    if len(alive) < KEEP:
        # never let the population go extinct: take the KEEP most fluent whatever the floor
        order = sorted(rows, key=lambda r: (r["ce"] if r["ce"] is not None else 0.0,
                                            r["slot"]))
        for r in order[:KEEP]:
            r["floored"] = False
        alive = [r for r in rows if not r["floored"]]
    dead = [r for r in rows if r["floored"]]
    alive.sort(key=lambda r: (-r["ratio"], -r["shows"], r["slot"]))
    dead.sort(key=lambda r: (-r["ratio"], -r["shows"], r["slot"]))
    return alive + dead


def thin_data(counts, agents):
    """Which slots have not been seen enough to select on."""
    return [a["slot"] for a in agents
            if int(counts.get(a["slot"], {}).get("shows", 0)) < MIN_SHOWS]


def step(pop, counts, ce=None):
    """One generation. Returns the new population dict; `pop` is not modified."""
    gen = pop["generation"] + 1
    ranked = rank(pop["agents"], counts, ce)
    by_slot = {a["slot"]: a for a in pop["agents"]}

    survivors = ranked[:KEEP]
    new = []
    for i, r in enumerate(survivors):
        a = dict(by_slot[r["slot"]])
        a["slot"] = i
        a["parent"] = r["slot"]
        a["origin"] = "survivor"
        new.append(a)

    n_children = N_AGENTS - KEEP - IMMIGRANTS
    for j in range(n_children):
        p = survivors[j % KEEP]
        slot = KEEP + j
        parent = by_slot[p["slot"]]
        new.append({
            "slot": slot,
            "lineage": parent["lineage"],
            "origin": "child",
            "born": gen,
            "parent": p["slot"],
            "seeds": [list(s) for s in parent["seeds"]]
                     + [[seed_for("mut", gen, slot), SIGMA_STEP]],
            "line_seed": 0,
        })
    for j in range(IMMIGRANTS):
        new.append(immigrant(gen, N_AGENTS - IMMIGRANTS + j))

    reseeded = cap_lineages(new, gen)

    for a in new:
        a["line_seed"] = seed_for("line", gen, a["slot"])

    out = dict(pop)
    out["generation"] = gen
    out["env"] = pop.get("env")
    out["agents"] = new
    out["last"] = {
        "action": "rolled",
        "from_generation": pop["generation"],
        "ranking": ranked,
        "kept": [r["slot"] for r in survivors],
        "reseeded_for_cap": reseeded,
        "lineages": lineage_shares(new),
    }
    return out


def cap_lineages(agents, gen):
    """No lineage may hold more than half the population; the excess become immigrants.

    Children go first and the youngest child first, because a survivor earned its slot on
    the counts and a child has not been seen by anyone yet."""
    reseeded = []
    while True:
        shares = {}
        for a in agents:
            shares.setdefault(a["lineage"], []).append(a)
        over = [(k, v) for k, v in shares.items() if len(v) > MAX_LINEAGE]
        if not over:
            return reseeded
        over.sort(key=lambda kv: (-len(kv[1]), kv[0]))
        members = over[0][1]
        # children last-first, then survivors from the bottom of the ranking
        members.sort(key=lambda a: (0 if a["origin"] == "child" else 1, -a["slot"]))
        victim = members[0]
        i = agents.index(victim)
        agents[i] = immigrant(gen, victim["slot"], reason="immigrant-cap")
        reseeded.append(victim["slot"])


def lineage_shares(agents):
    out = {}
    for a in agents:
        out[a["lineage"]] = out.get(a["lineage"], 0) + 1
    return out


# ------------------------------------------------------------------ weights
def keys(m):
    return sorted(m.sd)


def scales(m):
    """Per-tensor standard deviation of the PRETRAINED weights, so one sigma means the
    same thing in the embedding as in an attention projection. Computed from the base
    model and never updated, which is what makes a lineage reconstructible."""
    return {k: float(m.sd[k].float().std()) for k in keys(m)}


def add_noise(sd, m, sc, seed, sigma):
    """One mutation step, in place.

    numpy's legacy RandomState, deliberately. NEP 19 freezes its stream bit for bit
    across numpy versions and platforms for good; `default_rng` carries no such promise
    and torch's CPU generator carries none either. The lineage is only worth writing down
    if the noise it names is the same noise everywhere."""
    import numpy as np
    import torch
    rs = np.random.RandomState(seed)
    for k in keys(m):
        n = rs.standard_normal(tuple(sd[k].shape))
        sd[k] += torch.from_numpy(n).float() * (sigma * sc[k])


def reconstruct(m, sc, agent):
    """base + sum of seeded Gaussian noise, in lineage order."""
    sd = {k: v.clone() for k, v in m.sd.items()}
    for seed, sigma in agent["seeds"]:
        add_noise(sd, m, sc, int(seed), float(sigma))
    return sd


# ------------------------------------------------------------------ lines
def _tidy(raw):
    """The creature says ONE thing.

    Left alone the model runs on into third-person narration a clause later, which is a
    different phenotype from the one being selected, so it is cut at the first sentence
    end. The prompt ends in a dangling "i", so that is put back unless the continuation
    started with one itself.

    The tokenizer's decoder joins word pieces with spaces, so an apostrophe comes back as
    a word of its own: "don ' t". That is a decode artefact and not something the agent
    did, so it is closed up here rather than left on the page."""
    s = raw.replace(" ' ", "'").strip()
    for stop in ['"', "\n"]:
        if stop in s:
            s = s.split(stop)[0]
    ends = [j for j in (s.find(c) for c in ".?!") if j > 0]
    s = (s[:min(ends) + 1] if ends else s).strip()
    return s if s[:2].lower() == "i " else ("i " + s).strip()


def head_punct(text):
    """True when the first thing after the leading "i" is punctuation.

    `i . you can help me.` and `i - - - change faces.` are broken by shape, not by
    vocabulary, and no fluency threshold catches them: the base model finds a full stop
    after "i" perfectly predictable, so the first of those scores 3.98 nats, well inside
    the clean range. A one-character rule is the right instrument for a one-character
    fault. The comma is deliberately NOT in the set: "i, who have waited here" is
    legitimate English and a shape rule should not quietly cut a construction the model
    might occasionally get right."""
    t = text[1:].lstrip() if text[:1].lower() == "i" else text
    return t[:1] in HEAD_PUNCT


def publishable(text, ce):
    return ce <= LINE_FLOOR and not head_punct(text)


def draw(m, sd, agent, n, prompt, rs):
    return [_tidy(x) for x in m.sample(sd, prompt, n, rs)]


def speak(m, sd, agent, n=N_LINES, prompt=PROMPT):
    """The first n draws, unfiltered. This is the sample the AGENT-LEVEL floor scores."""
    import numpy as np
    return draw(m, sd, agent, n, prompt, np.random.RandomState(int(agent["line_seed"])))


BORN = {"founder": "found", "immigrant": "immig", "immigrant-cap": "immig"}
MAX_BIRTH_DRAWS = 8


def agent_lines(m, sc, pop, a, filter_lines=True):
    """(published lines, agent-level cross-entropy, a record of what was cut).

    The two floors score DIFFERENT sets, and that separation is the whole point:

      - the agent-level floor scores the first n draws, UNFILTERED. If it scored what
        survived the per-line filter instead, the filter would launder bad agents past
        it: every agent would look fluent because its worst output had already been
        removed, the floor would stop firing, and the population could drift out of
        English with nothing to say so. It would not read as a bug, only as a floor that
        never fires.
      - the per-line filter decides only what gets published, and resamples from the
        same stream until the quota is full.

    Every agent's fluency is therefore judged on the same sample size whatever its draw
    count, which is also why the agent statistic stays comparable to the sandbox's."""
    import numpy as np
    n = pop.get("n_lines", N_LINES)
    prompt = pop.get("prompt", PROMPT)
    sd = reconstruct(m, sc, a)
    rs = np.random.RandomState(int(a["line_seed"]))
    said = draw(m, sd, a, n, prompt, rs)
    ce = round(m.output_ce(m.sd, said), 4)
    if not filter_lines:
        return said, ce, {"drawn": n, "examined": n, "published": len(said),
                          "rejected": 0, "duplicate": 0, "short": False}

    scored = list(zip(said, m.line_ce(m.sd, said)))
    while len(_pick(scored, n)[0]) < n and len(scored) < MAX_LINE_DRAWS:
        more = draw(m, sd, a, TOPUP, prompt, rs)
        scored += list(zip(more, m.line_ce(m.sd, more)))
    kept, rec = _pick(scored, n)
    rec.update(drawn=len(scored), published=len(kept), short=len(kept) < n)
    return kept, ce, rec


def _pick(scored, n):
    """The published lines, and what it took. `examined` stops where the quota fills, so
    the counts describe the draws that were actually looked at rather than every draw."""
    kept, seen, rejected, dup, examined = [], set(), 0, 0, 0
    for t, c in scored:
        examined += 1
        if t in seen:
            dup += 1
        elif not publishable(t, c):
            rejected += 1
        else:
            seen.add(t)
            kept.append(t)
            if len(kept) == n:
                break
    return kept, {"examined": examined, "rejected": rejected, "duplicate": dup}


def generate(pop, screen=True, filter_lines=True, log=print):
    """Every agent's lines, its fluency, and a record of what the screens removed.

    Two screens, and they act on different things.

    A NEWBORN is screened against the agent floor, and a founder or an immigrant that
    lands above it is redrawn at the same sigma. This is the floor rule applied at birth
    rather than a week later: an agent born above the line dies on its first roll
    whatever the visitors think of it, so leaving it in only spends a week of the site
    saying "i od you unegrane trees" and throws away an eighth of the population. The
    founding sigma is untouched, and a rejected draw is recorded in `draw`, so the
    screening is visible in the file rather than hidden in it.

    A LINE is screened before it is published, on LINE_FLOOR and the punctuation rule.
    That screen never feeds back into who lives -- see agent_lines.

    Mutates `pop`: an accepted redraw is the agent's real seed and has to be written down.
    Returns (lines_doc, ce_by_slot)."""
    from . import tinylm
    m = tinylm.model()
    sc = scales(m)
    pop["env"] = env()             # the lines are only reproducible in the env that made them
    lines, ce, cuts = [], {}, []
    for a in pop["agents"]:
        said, c, rec = agent_lines(m, sc, pop, a, filter_lines)
        kind = BORN.get(a["origin"]) if screen else None
        while kind and c > FLUENCY_FLOOR and a.get("draw", 0) + 1 < MAX_BIRTH_DRAWS:
            a["draw"] = a.get("draw", 0) + 1
            log("  agent %d  %-11s ce %5.3f over the %.2f floor, redrawing (draw %d)"
                % (a["slot"], a["lineage"], c, FLUENCY_FLOOR, a["draw"]))
            a["seeds"] = [[seed_for(kind, a["born"], a["slot"], a["draw"]), SIGMA_FOUND]]
            said, c, rec = agent_lines(m, sc, pop, a, filter_lines)
        if kind and c > FLUENCY_FLOOR:
            log("  agent %d  %-11s still over the floor after %d draws, kept"
                % (a["slot"], a["lineage"], MAX_BIRTH_DRAWS))
        if rec["short"]:
            log("  agent %d  %-11s only %d lines after %d draws"
                % (a["slot"], a["lineage"], rec["published"], rec["drawn"]))
        a["ce"] = c
        ce[a["slot"]] = c
        rec = dict(rec, slot=a["slot"])
        cuts.append(rec)
        for i, t in enumerate(said):
            lines.append({"id": "g%d-a%d-l%02d" % (pop["generation"], a["slot"], i),
                          "agent": a["slot"], "lineage": a["lineage"], "text": t})
        log("  agent %d  %-11s ce %5.3f  %d of %d draws published  %s"
            % (a["slot"], a["lineage"], c, rec["published"], rec["drawn"],
               json.dumps(said[0]) if said else "(nothing)"))
    examined = sum(r["examined"] for r in cuts)
    drawn = sum(r["drawn"] for r in cuts)
    rejected = sum(r["rejected"] for r in cuts)
    dup = sum(r["duplicate"] for r in cuts)
    doc = {"generation": pop["generation"], "prompt": pop.get("prompt", PROMPT),
           "env": env(),
           # what was screened out and on what, so a reader of this file in a year can
           # see it rather than infer it from the code that made the file
           "screen": {"line_floor": LINE_FLOOR if filter_lines else None,
                      "head_punctuation": "".join(sorted(HEAD_PUNCT)) if filter_lines
                                          else None,
                      "agent_floor": FLUENCY_FLOOR,
                      "drawn": drawn, "examined": examined,
                      "published": len(lines),
                      "rejected": rejected, "duplicate": dup,
                      "rejected_pct": round(100.0 * rejected / max(examined, 1), 1),
                      "per_agent": cuts},
           "lines": lines}
    return doc, ce


# ------------------------------------------------------------------ files
def load(path=POP_PATH):
    with open(path) as fh:
        return json.load(fh)


def save(doc, path):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
