"""Builds the whole site: home, research, about, contact, 404, llms.txt.

Supersedes home.py, which built the home page alone. Edit this file, not the .html.

The label is the identity, and every page opens on it: the full Blue Note label, name,
data stack, personnel credits, nav. Beside it sits a 23rem column for a live model.
Where a page has no model yet, the hero goes to one column and the label runs the full
width, so there is no empty field waiting to be filled.
"""
import io

# The type is in the repo. These are the same two variable woff2 files fonts.gstatic.com
# was serving, latin subset, byte for byte, with Google's own descriptors kept: the same
# wght 400-700 range and the same unicode-range, so not a glyph moves. Only the origin
# changes, from a stylesheet on someone else's server that had to answer before anything
# could paint, to one same-origin request that starts while the page is still parsing.
#
# Latin is the whole of it, checked rather than assumed. Everything the site sets in these
# faces is inside that range, the en dash, the em dash, the middle dot and the division
# sign included. The kappa on Research and the three kanji on About have no glyph in any
# Archivo subset Google publishes, so they fell back to Helvetica before and still do.
# Latin-ext and Vietnamese cover nothing the site writes and were never fetched anyway.
#
# These rules go in the CSS below, which is inlined into every page, so there is no
# stylesheet to block the first paint. font-display:swap, so the words are readable while
# the file is in flight.
LATIN = ("U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,"
         "U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD")

FACES = """
@font-face{
  font-family:Archivo; font-style:normal; font-weight:400 700; font-stretch:100%;
  font-display:swap; src:url(fonts/archivo-latin.woff2) format('woff2');
  unicode-range:__LATIN__;
}
@font-face{
  font-family:'Archivo Narrow'; font-style:normal; font-weight:400 700;
  font-display:swap; src:url(fonts/archivo-narrow-latin.woff2) format('woff2');
  unicode-range:__LATIN__;
}
""".replace('__LATIN__', LATIN)

# Two layers, because one is not a scan. A fine tooth plus a coarser mottle.
# Built by concatenation: the SVG is full of literal % escapes, so % formatting fights it.
def turb(freq, octaves, size):
    z = str(size)
    return ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='" + z +
            "' height='" + z + "'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise'"
            " baseFrequency='" + freq + "' numOctaves='" + str(octaves) + "' stitchTiles='stitch'/%3E"
            "%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='" + z +
            "' height='" + z + "' filter='url(%23n)'/%3E%3C/svg%3E")

GRAIN_FINE   = turb('0.95', 4, 200)
GRAIN_MOTTLE = turb('0.035', 4, 620)

CSS = FACES + """
:root{
  --bg:#2b2b29; --fg:#f6f6f8; --dim:#a3a39f; --rule:#43433f;
  --accent:#9a9dff; --fill:#0204a7; --on-fill:#f6f6f8; --plate:#333330;
  --lat-on:#0204a7; --lat-mid:#6e6e68; --lat-off:#d8d8dc;
  --grain-page:.30; --grain-blue:.42; --grain-blend:overlay;
}
*{box-sizing:border-box;margin:0;padding:0}
/* The page states are held in the document and shown one at a time, and .viz sets
   its own display, which would otherwise win against the UA's [hidden] rule. */
[hidden]{display:none !important}
html{-webkit-text-size-adjust:100%}
body{
  background:var(--bg); color:var(--fg); min-height:100vh;
  font-family:Archivo,Helvetica,system-ui,sans-serif;
  font-weight:400; font-size:1rem; line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
/* paper tooth over the whole page */
body::after{
  content:""; position:fixed; inset:0; z-index:9; pointer-events:none;
  background-image:url("__FINE__"), url("__MOTTLE__");
  background-size:200px 200px, 620px 620px;
  opacity:var(--grain-page); mix-blend-mode:var(--grain-blend);
  /* Named, so the grain is carried into the transition layer along with the label
     instead of being left behind in the root snapshot underneath it. Without this the
     label loses its tooth for the length of every navigation and gets it back at the
     end — a step of about 10/255 on the blue, which reads as the plate going dim and
     coming back. See the transition rules at the foot of this file. */
  view-transition-name:grain;
}
a{color:inherit}
.link{color:var(--accent); text-decoration:none; border-bottom:1px solid var(--rule)}
.link:hover{border-bottom-color:var(--accent)}
.wrap{max-width:72rem; margin:0 auto; padding:2rem 2rem 6rem}
.hero{display:grid; grid-template-columns:1fr 23rem; gap:2.5rem; align-items:stretch}
/* no model on this page yet: one column, label full width. Holding the 23rem open and
   empty reads as a missing thing, and a big empty field is a failure, not a minimum. */
/* One width everywhere, and never shorter than 29.25rem, which is what Research needs.
   A floor rather than a fixed height: the hero is align-items:stretch, so the label
   already wants to fill its row, and where the plate column runs taller — home, which
   carries three figures and a note under its canvas — the label stretches to meet it
   instead of stopping 145px short of it. A page with no plate is held open by the floor,
   so nothing shifts on the day a plate arrives. Reverses the one fixed height of
   2026-09-05 on home only; see design-goals.md. */
.label{min-height:29.25rem}

/* ---- the label: blue field, white knocked out, hierarchy by weight ---- */
/* the same object on every page; the nav says which page you are on, so nothing
   on the label repeats it */
.label{
  background:var(--fill); color:var(--on-fill);
  position:relative; isolation:isolate;
  padding:2.25rem 2.5rem 2rem; display:flex; flex-direction:column;
}
.label::before, .label::after{
  content:""; position:absolute; inset:0; z-index:0; pointer-events:none;
  background-image:url("__FINE__"), url("__MOTTLE__");
  background-size:200px 200px, 620px 620px;
}
.label::before{ mix-blend-mode:screen;   opacity:.16; }
.label::after{  mix-blend-mode:multiply; opacity:.30; }
.label > *{position:relative; z-index:1}
.title{font-size:2.25rem; font-weight:700; letter-spacing:-.025em; line-height:1.05}
/* the wordmark goes home from every page but home; it must not look like a link */
.title a{text-decoration:none}
.stack{margin-top:1.4rem; font-size:.8125rem; line-height:1.5}
.stack b{font-weight:700; font-size:.9375rem}
.stack .sm{font-size:.75rem; opacity:.85}
.stack .gap{height:.85rem}
.credits{
  margin-top:auto; padding-top:1.9rem; font-size:.75rem; line-height:1.6; opacity:.92;
  max-width:44ch;
}
.credits b{font-weight:700}
/* a personnel list breaks between credits, never inside one */
.credits i{font-style:normal; white-space:nowrap}
.label nav{
  display:flex; gap:1.25rem; flex-wrap:wrap; align-items:center;
  font-size:.6875rem; letter-spacing:.16em; text-transform:uppercase;
  margin-top:1.6rem; padding-top:1.4rem; border-top:1px solid rgba(246,246,248,.3);
}
.label nav a{text-decoration:none; opacity:.75}
.label nav a:hover{opacity:1}
.label nav a[aria-current]{opacity:1; box-shadow:inset 0 -2px 0 currentColor}

/* ---- the toy ---- */
.viz{display:flex; flex-direction:column; gap:.6rem}
/* The plate arrives when its model has warmed up, rather than snapping in. The canvas
   is visible by default and the script hides it before it starts work, so with no
   JavaScript there is still an empty plate here rather than a hole. */
.viz canvas{transition:opacity .35s ease;

  display:block; width:100%; height:auto; image-rendering:pixelated;
  border:1px solid var(--rule); background:var(--plate);
}
.viz .row{display:grid; grid-template-columns:repeat(3,1fr); gap:.6rem}
.viz .row figure{margin:0}
.viz .row figcaption{
  margin-top:.3rem; font-size:.5625rem; letter-spacing:.1em; text-transform:uppercase;
  color:var(--dim); text-align:center;
}
.ctrl{display:flex; align-items:center; gap:.7rem; margin-top:.2rem}
.ctrl label{font-size:.625rem; letter-spacing:.06em; color:var(--dim); white-space:nowrap}
.ctrl label sub{font-size:.75em}
/* a fader off a mixing desk, not an OS widget: hairline track, ticks, square cap */
.ctrl input[type=range]{
  -webkit-appearance:none; appearance:none;
  flex:1; height:1.25rem; margin:0; background:none; cursor:pointer;
}
.ctrl input[type=range]:focus{outline:none}
.ctrl input[type=range]:focus-visible{outline:1px solid var(--accent); outline-offset:4px}
.ctrl input[type=range]::-webkit-slider-runnable-track{
  height:1.25rem;
  background:
    repeating-linear-gradient(90deg, var(--rule) 0 1px, transparent 1px 7.1428%) 0 100%/100% 5px no-repeat,
    linear-gradient(var(--rule), var(--rule)) 0 50%/100% 1px no-repeat;
}
.ctrl input[type=range]::-moz-range-track{
  height:1.25rem;
  background:
    repeating-linear-gradient(90deg, var(--rule) 0 1px, transparent 1px 7.1428%) 0 100%/100% 5px no-repeat,
    linear-gradient(var(--rule), var(--rule)) 0 50%/100% 1px no-repeat;
}
.ctrl input[type=range]::-webkit-slider-thumb{
  -webkit-appearance:none; appearance:none;
  width:6px; height:16px; border:0; border-radius:0;
  background:var(--accent); margin-top:calc(.625rem - 8px);
  transition:background .2s, height .2s;
}
.ctrl input[type=range]::-moz-range-thumb{
  width:6px; height:16px; border:0; border-radius:0; background:var(--accent);
  transition:background .2s, height .2s;
}
.ctrl input[type=range]:hover::-webkit-slider-thumb{height:20px; margin-top:calc(.625rem - 10px)}
.ctrl input[type=range]:hover::-moz-range-thumb{height:20px}
/* at Tc the cap goes white, so the instrument agrees with the caption */
.crit-on .ctrl input[type=range]::-webkit-slider-thumb{background:var(--fg)}
.crit-on .ctrl input[type=range]::-moz-range-thumb{background:var(--fg)}
.ctrl output{
  font-family:'Archivo Narrow',sans-serif; font-size:.8125rem; letter-spacing:.02em;
  color:var(--dim); min-width:2.4rem; text-align:right; transition:color .3s ease;
}
.crit-on .ctrl output{color:var(--fg)}
.viz .note{
  font-size:.8125rem; line-height:1.5; color:var(--dim);
  min-height:4.4em; transition:color .3s ease;
}
.viz .note.crit{color:var(--fg); font-weight:600}

/* ---- page body ---- */
.body{margin-top:3rem; max-width:54rem}
.prose{max-width:62ch}
.prose p{margin-bottom:1.3rem}
.prose p:last-child{margin-bottom:0}

/* the one-line-each block: catalogue furniture, one row per thing */
.rows{display:grid; grid-template-columns:9.5rem 1fr; margin-top:2.75rem;
      border-top:1px solid var(--rule)}
/* stacked blocks: without this the closing rule and the next block's top rule sit
   2.75rem apart and read as one table with a blank row, worst on mobile */
.rows + .rows{border-top:0}
/* the rule spans the column; the text sits inside it at a readable measure */
.rows dd > span{display:block; max-width:62ch}
.rows dt{
  font-size:.9375rem; font-weight:700; color:var(--fg);
  padding:.9rem 1.5rem .95rem 0; border-bottom:1px solid var(--rule);
}
.rows dt a{color:inherit; text-decoration:none;
           border-bottom:1px solid var(--rule); padding-bottom:1px}
.rows dt a:hover{border-bottom-color:var(--fg)}
.rows dd{
  font-size:.9375rem; line-height:1.55;
  padding:.9rem 0 .95rem; border-bottom:1px solid var(--rule);
}

/* ---- research entries ---- */
.grp{margin-top:3.25rem}
.grp.first{margin-top:2.5rem}
.grp > h2{
  font-size:.8125rem; font-weight:700; color:var(--dim);
  padding-bottom:.7rem; border-bottom:1px solid var(--rule);
}
.entry{
  display:grid; grid-template-columns:minmax(0,1fr) 12rem; gap:2.25rem;
  padding:1.7rem 0; border-bottom:1px solid var(--rule);
}
.entry h3{font-size:1.0625rem; font-weight:700; letter-spacing:-.012em; line-height:1.3;
          max-width:44ch}
.entry p{margin-top:.65rem; font-size:.9375rem; line-height:1.6; max-width:62ch}
.entry .meta{
  font-size:.6875rem; letter-spacing:.06em; line-height:1.6; color:var(--dim);
  padding-top:.28rem;
}

/* ---- about / contact sections ---- */
.sec{margin-top:3.25rem}
.sec > h2{
  font-size:.8125rem; font-weight:700; color:var(--dim);
  padding-bottom:.7rem; margin-bottom:1.6rem;
  border-bottom:1px solid var(--rule);
}
.lede{font-size:1.0625rem; line-height:1.6; max-width:58ch; margin-bottom:1.3rem}

footer{margin-top:4rem; padding-top:1.2rem; border-top:1px solid var(--rule);
       font-size:.6875rem; color:var(--dim); max-width:54rem; line-height:1.6;
       display:flex; flex-wrap:wrap; gap:.5rem 1.5rem; justify-content:space-between;
       align-items:baseline}
footer p{max-width:62ch}
footer p.llms{white-space:nowrap; max-width:none}

/* ---- moving between pages ----
   Cross-document view transitions. Every page stays a complete standalone document,
   so there is no router and no shared shell, and a browser that does not know these
   rules drops them and navigates exactly as it did before.

   Two things are named and carried across rather than cross-faded: the label, which
   is the same object on both pages, and the paper grain, which is the same sheet. A
   named element is lifted out of the root snapshot into the transition's own layer,
   and the grain has to be lifted with it or it can no longer reach it. What crosses
   is what actually differs between the two pages: the plate in the right column, the
   body beneath, the underline in the nav.

   A cross-fade and nothing else. Displacing the incoming page would take the label
   with it, and the label holding still is the whole of the effect. */
@view-transition{navigation:auto}
/* Carried across. Without a name the label's text is composited twice through the
   transition and visibly reloads. */
.label{view-transition-name:label}
/* Held, not cross-faded. Home's label is 145px taller than the others, so its credits
   and nav sit lower, and fading one layout out over the other doubles that text for
   180ms. Nothing else in the label differs between two pages, so there is nothing a
   cross-fade is for: show the new one, drop the old, and the label arrives in its own
   page's shape on the first frame. The group animation is left alone because it is not
   visible — the snapshots are block-size:auto at a width that does not change, so the
   box growing 145px neither scales nor clips them. */
::view-transition-group(label){animation-duration:.18s}
::view-transition-old(label){animation:none; opacity:0}
::view-transition-new(label){animation:none; opacity:1}
::view-transition-group(*),::view-transition-old(*),::view-transition-new(*){
  animation-duration:.18s; animation-timing-function:ease;
}
@media(prefers-reduced-motion:reduce){
  @view-transition{navigation:none}
  /* and where that descriptor is not understood, every animation is over on the
     frame it starts, which comes to the same thing */
  ::view-transition-group(*),::view-transition-old(*),::view-transition-new(*){
    animation-duration:0s !important;
  }
}

/* ---- and moving between them inside one document ----
   The rules above stay, because every page is still written as a complete standalone
   document and a reader who arrives on one navigates out of it the cross-document way.
   These take over only where the router is running, which is where `app` is set on the
   root element by script. With no JavaScript the class is never set and nothing below
   applies.

   The root loses its name, so the document is not captured at all. Nothing is
   snapshotted unless it is named, and the label is not named: it is not lifted out of
   the page, not composited against a copy of itself and not re-laid-out. It is simply
   still there, being the same element it was before the click. That is the whole of the
   fix, and it is one declaration.

   What is named is the page body, and nothing else. That name is not here, because a
   name is not a free declaration. Naming an element promotes it to a compositing layer
   of its own for as long as the name is set, which takes its text off subpixel
   antialiasing — 78,785 pixels of the home page changed against the build before this
   one, every glyph in the body outlined, and the same on every page read inside the app.
   So the router sets that name in script immediately before a swap and clears it at the
   end of it, and at rest nothing on the page is named and nothing is promoted.

   The plate in the right column is not named either, so it is not captured and it hard-
   cuts rather than cross-fading. It was named, and that was the flicker of the ÷3 ÷9 ÷27
   boxes leaving home: a browser puts the outgoing snapshot up once more as the
   transition tears down, and home's plate is 613 tall against Research's 468, so that
   row was the part of it that landed on bare page ground and read as a blink. Ablated
   one thing at a time — the name held for ever, the canvas fade, the height animation,
   the pinned group — not capturing the plate was the only one that stopped it. */
html.app{view-transition-name:none}
html.app .label{view-transition-name:none}
/* And the grain gives its name back, because the reason it was given one has gone. It
   was named so that it would be lifted into the transition layer along with the label
   and could still reach it. Here the label is not lifted at all, so the grain reaches it
   by simply staying where it is. Named, with no root snapshot beneath it in that layer
   to blend with, its overlay has nothing to work against and it lands as a flat grey
   veil over the whole page: 29 of 255, measured, for the length of every swap. */
html.app body::after{view-transition-name:none}
/* The one group there is does not animate, and that is deliberate. A browser re-targets
   a group at the live element on every frame, so an animating group interpolates from
   where the element was towards wherever it is right now — and while the label's row is
   being animated, "right now" is itself moving, so the body only ever reaches the
   product of the two progressions and trails the label by up to 36px mid-swap. Measured,
   and the reason the label's move looked wrong however it was eased.

   Pinned, the group sits exactly on the live element, so the outgoing page and the
   incoming one both travel with the layout and the label's bottom edge and the text
   under it move as one thing. It also means a swap that changes the scroll position
   does not slide: only the cross-fade is animated, which is all a cross-fade needs. */
html.app::view-transition-group(page){animation:none}

@media(prefers-reduced-motion:reduce){ .viz canvas{transition:none} }

@media(max-width:880px){
  .wrap{padding:1.25rem 1.25rem 4rem}
  .hero{grid-template-columns:minmax(0,1fr)}
  .label{padding:1.75rem 1.5rem}
  .title{font-size:1.875rem}
  .rows{grid-template-columns:minmax(0,1fr); gap:0}
  .rows dt{border-bottom:0; padding:1rem 0 .1rem}
  .entry{grid-template-columns:minmax(0,1fr); gap:.7rem}
  .entry .meta{padding-top:0; order:-1}
}
""".replace('__FINE__', GRAIN_FINE).replace('__MOTTLE__', GRAIN_MOTTLE)
