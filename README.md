# timbooker.net

The site. Built by hand, no framework yet.

## Build

    python build_site.py     # writes the html and llms.txt
    python shots.py          # full-page proofs into p-*.png

## Source of truth

- `build_site.py` — all the copy, and page assembly. Edit the copy here.
- `site_style.py` — the CSS, the paper grain, the fonts. Edit the look here.
- `fonts/` — Archivo and Archivo Narrow, the same latin woff2 Google Fonts was serving,
  now in the repo. Self-hosted so first paint waits on nothing but this origin, and so a
  reader's browser stops calling Google on every page load. SIL Open Font License; the
  licence sits beside the files, which is what it asks for.
- `design-goals.md` — what any change gets checked against. Read it first. It carries
  every locked decision and every ruling, in order, with the reasoning.
- `principles.md` — the content and architecture principles, signed off 2026-08-27.
- `research-japanese-record-type.md` — the typography research the direction came from.

**Never edit the .html.** It is generated and will be overwritten.

## Pages

home, research, freelancing, about, contact, 404, plus llms.txt.

`index.html` and `home.html` are the same file and carry all five pages as states of one
document, with a router that swaps between them and pushes the real path. The other files
are one complete page each and are what everything without JavaScript sees. Both are
written from the same copy, so there is nothing to keep in sync.

## The creature's population

The creature in the blue label says a line drawn from `evolution/lines.json`. Once a week
a GitHub Action reads the pat counts, kills the agents nobody patted, breeds the ones they
did, mutates, regenerates the lines and commits. Every generation is one commit, so `git
log -- evolution/population.json` is the whole evolutionary history.

### Reading the population file

An agent is not a weight file. It is a **seed lineage**: a list of `[seed, sigma]` pairs,
and its weights are the pretrained SimpleStories-V2-5M plus one seeded Gaussian draw per
pair, added in order. Eight agents as weights would be 160MB in the repo; as lineages they
are three kilobytes.

    "slot": 4,                       where it sits this generation. #28 counts shows and
                                     pats against (generation, slot), so this is the name
                                     a visitor's pat is recorded under.
    "lineage": "f4",                 the founding event it descends from. "f4" is founder
                                     4; "i7.6" is the immigrant born into slot 6 at
                                     generation 7. Descendants keep their ancestor's id,
                                     so a population collapsing onto one founder is
                                     visible in the file rather than guessed at.
    "origin": "child",               founder, survivor, child, immigrant, immigrant-cap.
    "born": 5,                       the generation this lineage entry was created.
    "parent": 1,                     the slot in the PREVIOUS generation it came from.
    "seeds": [[9656684, 0.15],       the genome. One entry per mutation, in order.
              [1008283063, 0.025]]   The first is the founding draw at sigma 0.15; each
                                     later one is a weekly step at 0.025.
    "line_seed": 1414795081,         what its 24 lines were sampled from.
    "ce": 3.927,                     cross-entropy of its own lines under the frozen
                                     pretrained model. Over 4.6 and it dies whatever the
                                     visitors thought.
    "draw": 3                        present only when it was born above that floor and
                                     redrawn. 3 means three rejected founding seeds.

`last` records the roll that produced the current generation: the full ranking it selected
on, which slots were kept, which were reseeded to hold the half-population cap, and the
lineage shares. `checked` records when the job last ran, including a run that decided not
to evolve. `env` records the model revision and the torch and numpy versions, because
**determinism is a property of a pinned environment, not of the maths** — torch 2.6
produces a completely different 192 lines from 2.9.

`lines.json` holds the 192 published lines with the slot and lineage that said each one,
and a `screen` block saying what was filtered out and at what threshold.

### Rolling a generation back

The lines are committed, so a rollback is a file restore and a rebuild. Find the
generation you want and take both files from it:

    git log --oneline -- evolution/population.json
    git checkout <sha> -- evolution/population.json evolution/lines.json
    python build_site.py
    git commit -am "Back to generation N"

Nothing else has to be undone. Weights are never committed, so there is no large object to
restore and nothing to garbage-collect. The next Monday rolls forward from whatever
`population.json` then says, so a rollback also rewinds the evolution rather than only the
page.

### Running it by hand

    python -m evolution.roll found          write generation 0 (refuses to overwrite)
    python -m evolution.roll roll           fetch /counts, select, mutate, regenerate
    python -m evolution.roll roll --counts evolution/fixtures/counts-example.json
    python -m evolution.roll lines          regenerate the current lines, no evolution
    python -m evolution.roll verify         regenerate twice and compare
    python -m evolution.roll reconstruct    lineage equals the mutations applied in order
    python -m evolution.roll floortest      a broken agent still dies with the filter on
    python -m evolution.roll simulate 20    selection only, fake counts, lineage shares

`roll` writes nothing at all unless it reaches the end. If the counts endpoint is
unreachable it exits non-zero and changes nothing; if any agent has been shown fewer than
ten times it leaves the generation standing and moves only the `checked` date.

## Next

Jekyll on GitHub Pages, so adding an entry is one markdown file. Not started.

Earlier exploration — roughly 120 dead mockups, type tests and slider studies — stayed
behind in `Github/temp/mockups/`. Nothing here depends on it.
