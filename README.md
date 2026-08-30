# timbooker.net

The site. Built by hand, no framework yet.

## Build

    python build_site.py     # writes the html and llms.txt
    python shots.py          # full-page proofs into p-*.png

## Source of truth

- `build_site.py` — all the copy, and page assembly. Edit the copy here.
- `site_style.py` — the CSS, the paper grain, the fonts. Edit the look here.
- `design-goals.md` — what any change gets checked against. Read it first. It carries
  every locked decision and every ruling, in order, with the reasoning.
- `principles.md` — the content and architecture principles, signed off 2026-08-27.
- `research-japanese-record-type.md` — the typography research the direction came from.

**Never edit the .html.** It is generated and will be overwritten.

## Pages

home, research, freelancing, about, contact, 404, plus llms.txt.

## Next

Jekyll on GitHub Pages, so adding an entry is one markdown file. Not started.

Earlier exploration — roughly 120 dead mockups, type tests and slider studies — stayed
behind in `Github/temp/mockups/`. Nothing here depends on it.
