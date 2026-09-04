"""Builds the whole site: home, research, about, contact, 404, llms.txt.

Supersedes home.py, which built the home page alone. Edit this file, not the .html.

The label is the identity, and every page opens on it: the full Blue Note label, name,
data stack, personnel credits, nav. Beside it sits a 23rem column for a live model.
Where a page has no model yet, the hero goes to one column and the label runs the full
width, so there is no empty field waiting to be filled.
"""
import io

FONTS = ("https://fonts.googleapis.com/css2?"
         "family=Archivo:wght@400..700&"
         "family=Archivo+Narrow:wght@400..700&display=swap")

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

CSS = """
:root{
  --bg:#2b2b29; --fg:#f6f6f8; --dim:#a3a39f; --rule:#43433f;
  --accent:#9a9dff; --fill:#0204a7; --on-fill:#f6f6f8; --plate:#333330;
  --lat-on:#0204a7; --lat-mid:#6e6e68; --lat-off:#d8d8dc;
  --grain-page:.30; --grain-blue:.42; --grain-blend:overlay;
}
*{box-sizing:border-box;margin:0;padding:0}
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
}
a{color:inherit}
.link{color:var(--accent); text-decoration:none; border-bottom:1px solid var(--rule)}
.link:hover{border-bottom-color:var(--accent)}
.wrap{max-width:72rem; margin:0 auto; padding:2rem 2rem 6rem}
.hero{display:grid; grid-template-columns:1fr 23rem; gap:2.5rem; align-items:stretch}
/* no model on this page yet: one column, label full width. Holding the 23rem open and
   empty reads as a missing thing, and a big empty field is a failure, not a minimum. */
.hero.solo{grid-template-columns:minmax(0,1fr)}

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
.viz canvas{
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
