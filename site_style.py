"""Builds the whole site: home, research, about, contact, 404, llms.txt.

Supersedes home.py, which built the home page alone. Edit this file, not the .html.

The label is the identity, and every page opens on it: the full Blue Note label, name,
data stack, personnel credits, nav. Beside it sits a 23rem column for a live model.
Home, Research, Freelancing and About each have one. Contact and 404 hold the column open
and empty rather than collapsing it, so that nothing on the page moves on the day a plate
arrives — which is what happened to About.
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
/* Two columns on every page, whether or not the page has a model in the right one. The
   alternative was letting a page without one run the label full width, and that moves the
   label the day a plate arrives; the floor below is the other half of the same decision. */
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
/* 44ch is the measure it wants, and it keeps it wherever the label is wide enough to
   give the creature her corner as well. Where it is not, the credits give the corner up
   rather than the creature being hidden in it: the bubble's own width and a 4px gutter,
   which is the gap the block already leaves at 1400. That is 176 beside the big creature
   and 88 beside the small one, so it bites below a 478px content box at the one and a
   390px content box at the other — 380, 420, 560, 881 and 1000 of the widths measured.
   The block gets taller and raggeder there, which is the cost of her being on the page. */
.credits{
  margin-top:auto; padding-top:1.9rem; font-size:.75rem; line-height:1.6; opacity:.92;
  max-width:min(44ch, calc(100% - var(--crit-say) - 4px));
  container-type:inline-size;
}
.credits b{font-weight:700}
/* a personnel list breaks between credits, never inside one */
.credits i{font-style:normal; white-space:nowrap}
/* Except where a column that narrow cannot hold one. The longest credit paints 233.8px
   and the full stop that follows it takes the line to 237.2, so under that the nowrap does
   not keep the credit whole, it just paints it out of the block and across the creature
   standing beside it. Breaking inside the credit is the lesser fault, and the smaller
   creature buys the column back everywhere but the phone: it fires under a 413px viewport
   and nowhere else, 380 alone of the widths measured, because 292 of content cannot hold
   a 237.2 line and an 84 creature at once whatever it does with the 55 left over. */
@container (max-width:237px){ .credits i{white-space:normal} }
.label nav{
  display:flex; gap:1.25rem; flex-wrap:wrap; align-items:center;
  font-size:.6875rem; letter-spacing:.16em; text-transform:uppercase;
  margin-top:1.6rem; padding-top:1.4rem; border-top:1px solid rgba(246,246,248,.3);
}
.label nav a{text-decoration:none; opacity:.75}
.label nav a:hover{opacity:1}
.label nav a[aria-current]{opacity:1; box-shadow:inset 0 -2px 0 currentColor}

/* ---- the creature ---- */
/* It takes the free rectangle the label already has: 283 x 127 at x = 357 on a 680
   label, right of the credits and above the nav rule. Fourteen cells by twelve at eight
   pixels is 112 x 96, which sits in there with room for the bubble over its head.
   Nothing is ever scaled. She has two sizes and both are whole cells: --crit-cell is the
   only number that changes, the script reads it back and sets the canvas to fourteen by
   twelve of it, so one canvas pixel is one CSS pixel at either size and every rect the
   script draws still lands on a whole cell. No width or height here, for the same reason
   — the canvas is its own size and a CSS one would only fight the script for it;
   image-rendering keeps the grid true where the device scales the page instead.
   --crit-y is the label's bottom padding plus the height of the nav, so the sprite's feet
   sit a pixel above the rule. The nav is not always one line: it wraps wherever the
   label's content box is under 407px, which is below 495 and again at 881 to 958, where
   the plate column has the label at its narrowest — the second band the issue did not
   know about. A second nav line is 37.6px and a third is another, and --crit-nav is that,
   so there is one number for the floor and one for the nav rather than a set of totals to
   keep in step. */
.label{
  --crit-x:2.5rem; --crit-nav:0px; --crit-y:calc(74px + var(--crit-nav));
  --crit-cell:8; --crit-tail:8px; --crit-say:172px;
}
@media(min-width:881px) and (max-width:958px){ .label{--crit-nav:37.6px} }
@media(max-width:494px){ .label{--crit-nav:37.6px} }
@media(max-width:338px){ .label{--crit-nav:75.2px} }
#critter{
  position:absolute; right:var(--crit-x); bottom:var(--crit-y);
  image-rendering:pixelated; cursor:pointer;
}
/* Small, white, over the creature's head with its tail pointing down at it. Hidden until
   the creature speaks, which it does on load, so in practice it is up for the whole
   visit: somebody deciding whether to click has to be able to read the line. Above her
   rather than beside her, because beside her the corner has to be 294 wide — sprite, gap
   and bubble in a row — and it is that clear of the credits at two of the eleven widths
   measured. Above her the corner has to hold the bubble alone, on the same right edge as
   the sprite, and the credits give that up at every width. It stands twelve cells and a
   10px gap off the floor, which is the sprite's own height and the gap the bubble has
   always kept off her, so it comes down a size with her without a second number. */
#critsay{
  position:absolute; right:var(--crit-x);
  bottom:calc(var(--crit-y) + var(--crit-cell) * 12px + 10px);
  max-width:var(--crit-say); padding:.4rem .55rem; border-radius:11px;
  background:var(--fg); color:var(--bg); font-size:.75rem; line-height:1.35;
  opacity:0; transition:opacity .18s ease; pointer-events:none;
}
/* The tail is two of its own border widths across, and against an 11px corner radius it
   sits in the straight part of the bottom edge on any bubble wider than the sprite. Seven
   cells in from the right puts its point on the middle of a sprite hung off that same
   edge — 48px at eight pixels a cell, 34 at six. A short line makes a bubble narrower
   than that: pinned at seven cells the tail was pushed into the corner, where the radius
   has curved away from it, and it read as a notched-off arrow floating under the bubble
   rather than as a tail. min() keeps the aimed position on a wide bubble and centres it
   once the bubble is too narrow to hold it, and the tail starts 1px inside the edge so
   the curve cannot open a seam at either base corner. */
#critsay::after{
  content:""; position:absolute; bottom:calc(1px - var(--crit-tail));
  right:min(calc(var(--crit-cell) * 7px - var(--crit-tail)), calc(50% - var(--crit-tail)));
  border:var(--crit-tail) solid transparent; border-top-color:var(--fg); border-bottom:0;
}
#critsay.on{opacity:1}
/* The band where she is smaller: six pixels a cell instead of eight, 84 x 72, and the
   bubble comes down with her. Smaller rather than hidden, and a whole cell smaller rather
   than scaled, because a sprite on half pixels is not this sprite.
   Where the line is drawn: at 112 x 96 the corner takes 176 and the widest credit paints
   237.2, so the credits keep whole credits only where the content box holds 413.2. The
   band ends where the box holds 420, a few pixels of margin on that. Content is the
   viewport less 88 below 880 and less 552 above it, so the band is 507 and below, and 881
   to 971, where the plate column has the label at its narrowest.
   The bubble is 84 here, her own width to the pixel, and that is not a coincidence with a
   reason invented for it: 88 of reserve is the most the corner can take at 881 and still
   leave the credits their 237.2, and 84 with the 4px gutter is what fits under that. It
   does make the tail's two positions one — seven cells in from the bubble's right edge is
   the middle of the bubble as well as the middle of her.
   Ten pixels is the smallest type on the site and the bubble does not go under it. The
   line is the whole point of the bubble and it has to be read. */
@media(max-width:507px), (min-width:881px) and (max-width:971px){
  .label{--crit-cell:6; --crit-tail:6px; --crit-say:84px}
  #critsay{font-size:.625rem; padding:.3rem .4rem; border-radius:9px}
}

/* ---- the toy ---- */
.viz{display:flex; flex-direction:column; gap:.6rem}
/* The plate arrives when its model has warmed up, rather than snapping in. The canvas
   is visible by default and the script hides it before it starts work, so with no
   JavaScript there is still an empty plate here rather than a hole. */
.viz canvas{transition:opacity .35s ease;

  display:block; width:100%; height:auto; image-rendering:pixelated;
  border:1px solid var(--rule); background:var(--plate);
}
/* The chemistry dish takes a click, and so does the board on About. This is the whole of
   how either of them says so. */
.viz[data-plate=freelancing] canvas, .viz[data-plate=about] canvas{cursor:crosshair}
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
/* The board on About picks a scenario and stops, which a fader cannot say, so this is
   the first button on the site. It is drawn out of what is already here rather than out
   of a widget library: the type is the .ctrl label's, a size down and letterspaced up to
   the figcaption's, and the 2px inset shadow marking the loaded scenario is the same
   mark the nav puts under the page you are on, because it is saying the same thing.
   No border, no fill, no radius and no hover box — a box drawn round the fader would
   have been the wrong instrument, and it is the wrong instrument here too. Pause and
   Resume carry no mark: the word is the state, and a control that says what it will do
   does not also need to say what it has done.
   It stands 1.25rem, which is the fader's own height, and that is not a detail. The
   plate column is what sets the label's height, and the label is one size on every page
   but home; a control row a few pixels taller than the other three plates' would have
   made About the one page whose label is its own height, and given the router a seven
   pixel travel to animate on the way in and out of it. Same row height, nothing moves. */
.ctrl button{
  font:inherit; font-size:.625rem; letter-spacing:.12em; text-transform:uppercase;
  color:var(--dim); background:none; border:0; padding:0;
  height:1.25rem; line-height:1.25rem;
  cursor:pointer; transition:color .2s ease;
}
/* What you press is bigger than what is painted, and it has to be: the painted words are
   52.5, 33.4 and 39.6 wide by 20 tall, and 33 by 20 is not a target on a phone. The row
   height is not negotiable — it is what keeps About's label at 468.36 and the router with
   nothing to animate — so the pressable box is a transparent child, absolutely positioned
   and therefore invisible to the layout, reaching out past the painted word to 44 in both
   directions. Zero-width space would have been the other way, but padding cancelled by a
   negative margin leaves the box's own size fighting the flex line, and this does not.

   It reaches into open ground and never into the gap a button shares with its neighbour,
   which is why Soup grows rightwards and Pause leftwards: between them sits the space
   margin-left:auto opens, 121px at the narrowest. So no two boxes come near each other —
   11.19px between Gliders and Soup, 11.19 between Pause and the Gen label, and about 100
   between Soup and Pause — and none of them has to be squeezed to keep them apart.

   Vertically it is 11 up and 13 down rather than 12 and 12. There is 13.18px of clear
   above the button and 10 below it, so 44 will not fit between the canvas and the note
   whatever it does; the asymmetry spends the shortfall downwards, over the top 3px of the
   caption, which is text nobody clicks, and leaves 2.18px of the board unclaimed above.
   The board is the thing on this plate you are meant to be able to hit. */
.ctrl button{position:relative}
.ctrl button::before{content:""; position:absolute; top:-11px; right:0; bottom:-13px; left:0}
.ctrl button[data-scene=soup]::before{right:-1rem}
.ctrl .run::before{left:-1rem}
.ctrl button:hover{color:var(--fg)}
.ctrl button[aria-pressed=true]{color:var(--fg); box-shadow:inset 0 -2px 0 currentColor}
.ctrl button:focus-visible{outline:1px solid var(--accent); outline-offset:3px}
/* the scenarios are a pair at the left; the action goes to the right-hand end, against
   the readout, which is where the fader's own handle finishes on the other three */
.ctrl .run{margin-left:auto}
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
   snapshotted unless it is named, and nothing here is named at rest.

   What is named for the length of a swap is the page body and the label in parts. Those
   names are not here, because a
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
/* The stylesheet's own `.label{view-transition-name:label}` is taken off here for the
   same reason the page's name is not written here: it would be set at rest, all the
   time, on the one element that carries the site's identity. The router sets it, and the
   six part names with it, immediately before a swap and clears them at the end. */
html.app .label{view-transition-name:none}
/* And the grain gives its name back, because the reason it was given one has gone. It
   was named so that it would be lifted into the transition layer along with the label
   and could still reach it. Here the label is not lifted at all, so the grain reaches it
   by simply staying where it is. Named, with no root snapshot beneath it in that layer
   to blend with, its overlay has nothing to work against and it lands as a flat grey
   veil over the whole page: 29 of 255, measured, for the length of every swap. */
html.app body::after{view-transition-name:none}
/* The body's group animates, and that is the travel. It did not: it was pinned with
   `animation:none`, because the router was animating the hero's row underneath it and a
   browser re-targets a group at its live element on every frame, so the group
   interpolated towards a target that was itself moving and the body trailed the label by
   up to 36px mid-swap.

   Nothing animates the live page any more (#54), so the target is fixed from the first
   frame and the interpolation is honest. Both settings were then measured off painted
   frames, and which one is right had reversed. Pinned, the group sits on the live element
   — and the live label has snapped, while the label the eye can see is the snapshot, which
   travels. The gap between the label's bottom edge and the first line of body text opened
   from 55px to 200px and closed again over the swap. Animating, that gap is 54 to 56px on
   every frame of every leg, which is what it has always been, and the body and the label
   move as one thing again.

   The pin is kept for the two cases where a group's interpolation is not a movement. */
/* One: where the swap moves the scroll as well as the pages. A navigation keeps your
   place, so the router sometimes scrolls inside the transition's own callback, and then
   every captured rect moves by that much at once and an animating group interpolates it:
   measured at 1400, research scrolled to 1200 then About, the label slid in from off the
   top of the screen — its top edge 0 -> 32 and its bottom edge sweeping 36 -> 499, 463px
   of travel where nothing should have moved. The router sets `jump` for the length of
   those swaps and nothing animates its geometry; only the cross-fade is left, which is
   all a cross-fade needs. Nothing is lost by it: a swap that changes the scroll has the
   label off-screen at one end or the other, so there is no travel to see. */
html.app.jump::view-transition-group(*){animation:none}
/* Two: below the breakpoint, where the hero is one column. Above it the label and the body
   share a row, so the body's position moves by exactly the label's height and the two
   travel as one thing: measured, the page group's translation is 145px at 1400 and 140px
   at 881, which is the label's height change to the pixel. Below it they are stacked with
   the plate column between them, so what moves the body is the plate — 629px between home
   and About at 420, 923px at 640 — and that is a different page arriving, not a movement.
   The plate itself is not captured and hard-cuts for the same reason. So the body cuts
   with it, and the label, which is the same height at every width below here, does not
   move at all. */
@media(max-width:880px){ html.app::view-transition-group(*){animation:none} }

/* ---- and the label travels in parts ----
   Every one of these is held rather than cross-faded, the way the label already is on the
   cross-document path: the old snapshot at opacity 0 and the new at opacity 1, both with
   no animation of their own. Each part is the same content on both pages — only the nav's
   underline differs — so there is nothing a cross-fade is for, and holding them is what
   keeps a line of text from being composited over a copy of itself. What is left animating
   is the group, which is the rect, and that is the travel: the credits, the nav and the
   creature are anchored to the label's bottom edge and ride it up the 145px. */
html.app::view-transition-old(title),html.app::view-transition-old(stack),
html.app::view-transition-old(credits),html.app::view-transition-old(nav),
html.app::view-transition-old(critter),html.app::view-transition-old(critsay){
  animation:none; opacity:0;
}
html.app::view-transition-new(title),html.app::view-transition-new(stack),
html.app::view-transition-new(credits),html.app::view-transition-new(nav),
html.app::view-transition-new(critter),html.app::view-transition-new(critsay){
  animation:none; opacity:1;
}
/* The label's own snapshot is the only one told to fill its group. A UA draws a captured
   image at its natural size against a top edge that does not move, which is why naming the
   whole label did nothing: the group animated its height and the picture inside ignored
   it. Filling the group makes that height visible, and it is the one snapshot here that
   can survive being stretched, because everything with an edge in it — every line of type,
   and the creature, who is pixel art — has been lifted out of it by a name of its own.
   What is left is flat blue and two layers of grain. */
html.app::view-transition-old(label),html.app::view-transition-new(label){
  block-size:100%;
}
/* The cat does not move smoothly, ever. Her canvas is anchored to the label's bottom, so
   an animating group would slide her the 145px in the one case where the script does not
   move her at all — the band where the floor travels but the gesture is the wrong number
   of cells for it and she simply stands on the new floor (#49). Pinned, her group sits on
   the live element and she is where the script put her, which is the only thing allowed to
   place her. The bubble goes with her, being anchored to the same edge. */
html.app::view-transition-group(critter),html.app::view-transition-group(critsay){
  animation:none;
}
/* What capturing the label costs, measured by scripts/grain_check.py against the build
   before it, in a band of the blue that no named part covers, 1400x900:

     the blue's level, at rest 44.88 of 255, mid-swap 40.58      a step of 4.29
     frame to frame in the same band, mean 1.17 and peak 4.48    against a grain
                                                                 whose own amplitude
                                                                 there is 2.36

   The step is the fixed grain on `body::after` no longer reaching the label: it stays in
   the root and the label has been lifted out of it. That is the mechanism design-goals.md
   records under "The plate stopped flashing 2026-09-05", where the same lift measured a
   drop of 9 to 10 of 255 on the cross-document path. It is less than half of that here
   because the label's own two grain layers are captured with it and only the page's layer
   is lost. The frame-to-frame number is the squeeze resampling those two layers, and it
   is a flattening of the mottle as well as a level step.

   The one fix for the step is to name `body::after` so it is lifted too, which is what
   fixed it cross-document. It cannot work here: with the root uncaptured, the grain's
   group has nothing to blend against and lands as a veil over everything that was not
   captured. Built and measured rather than assumed — the label's step went to 0.27 and the
   plate column went 23.19 lighter, the page ground 28.08. Reversed. */

@media(prefers-reduced-motion:reduce){ .viz canvas{transition:none} }

@media(max-width:880px){
  .wrap{padding:1.25rem 1.25rem 4rem}
  .hero{grid-template-columns:minmax(0,1fr)}
  /* the creature keeps to the label's own padding, which is smaller here, and the nav
     sits four pixels nearer the bottom edge for the same reason, so the creature does */
  .label{padding:1.75rem 1.5rem; --crit-x:1.5rem; --crit-y:calc(70px + var(--crit-nav))}
  .title{font-size:1.875rem}
  .rows{grid-template-columns:minmax(0,1fr); gap:0}
  .rows dt{border-bottom:0; padding:1rem 0 .1rem}
  .entry{grid-template-columns:minmax(0,1fr); gap:.7rem}
  .entry .meta{padding-top:0; order:-1}
}
""".replace('__FINE__', GRAIN_FINE).replace('__MOTTLE__', GRAIN_MOTTLE)
