"""The acceptance check for the Game of Life plate on About (#53, #65, #67).

    python scripts/life_check.py          # the tables and a pass/fail line

The first thing it checks is the rule, because everything else on the plate is a
consequence of it and a plate running the wrong rule is a plate running a different
model. B3/S23 is checked twice over: once exhaustively, all 512 neighbourhoods against
both states of the cell in the middle, and once against a published figure — an
R-pentomino stabilises at generation 1103 with a population of 116, which is the number
every Life reference gives and the number a wrong rule cannot land on by accident.

The second thing it checks is the census, which is the plate's other claim: that the
board can be described in a vocabulary the rule does not contain. A census is worth
nothing if it quietly drops what it cannot name, so what is checked is that it adds up —
a known board reads exactly what was put on it, every catalogue shape is found in all
eight of its orientations and across the wrap seam, and over a whole run the cells inside
named objects plus the cells inside unnamed components come to the population, every
frame. It also runs the gun and reports the generation its own stream destroys it on,
which is where the caption's number comes from.

The third thing it checks is how a run ends, which since #67 is the plate stopping. It
steps on every other animation frame, so it runs at half the display's rate, and it has
exactly two exits: the board repeats, or it runs out its cap at 4800 without ever
repeating. Both stop the loop by returning false from tick(), the way Pause does, so the
run button reads Resume and means it. What is checked is that the plate stops, that it
stays stopped, that it never lays the scenario out again, and that Resume is not a dead
button — a settled board is still settled, so a detector that fired on the first tick
after a resume would stop it again and the press would have done nothing.

That last one is where the review of PR #68 found the bug, and the shape of it is the
lesson. The detector was armed by seeing the board take one step that did not repeat,
which never happens on a board of nothing but still lifes: the gun's wreck is 32 cells,
period 1, and not a blinker in it. Draw a cell on that and press Resume and the plate ran
a visibly finished board 4,269 generations to the cap. Every one of the six checks the
issue asked for passed on it, because every one of them settled a board and stopped and
none of them clicked on it afterwards. So the settle is now checked on all three
scenarios after a mark drawn in clear space, on a board that is nothing but still lifes,
and on a board that is completely static — and the cap's caption is checked never to
appear on a board that has stopped moving.

The fourth thing is the scene buttons, which since #67 tell apart the two ways the plate
can be stopped. A Pause the reader pressed and reduced motion are the reader asking for
stillness, and a scenario picked under either is laid out and left still; a run that has
ended is nobody asking for anything, so a scenario picked there starts the next run.

The cap needs 4800 generations, which is 160 seconds at the rate the plate actually runs.
That one check gets a browser launched with vsync off, purely so the generations arrive;
nothing in it depends on the rate, and the rate is measured on an ordinary browser.

It runs the shipped code, not a copy of it. `TBlife(n)` is the whole of the rule and
`TBcensus(cells, n)` the whole of the census, and both take the size of their board as an
argument, so the check builds boards of its own: 640 square for the R-pentomino, well
clear of the 72 the plate uses, and 40 square for the census. Nothing here writes to the
tree; the site is served over http, because on file:// the self-hosted fonts are blocked
by CORS and fill the console with failures that have nothing to do with the page.
"""
import sys, functools, http.server, socketserver, threading, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
WIDTHS = [380, 420, 881, 1120, 1400]
WIDTHS_HIT = [380, 420, 881, 1400]      # 881 is where the plate column is at its narrowest
BIG = 640                       # the R-pentomino's own board: see the note at RULE_R
GUN_DEAD = 272                  # what the caption says, and what GUN_RUN has to find
ONE_LINE = 19.51                # .note is 4.4em, 57.19px, and a line of it is 19.5
EVERY = 4                       # animation frames to a step since #69
CAP = 4800                      # the generations a run gets before the plate stops
# The Gliders scene is the cheap settle: the two gliders touch at 117, the wreck peaks at
# 240 and what is left of it only blinks, so repeats() fires and the plate stops. It is
# deterministic, so the generation it rests on is a number and not a range.
SETTLE_GLIDERS = 300
# The steps the settle detector waits out after every re-arming, which is what repeats()
# needs for its own comparison window to be clear of whatever the reader just did.
WINDOW = 2
SOON = 6                        # generations a re-armed board gets to stop inside
# Launching with vsync off is the only way 4800 generations arrive inside a check. The
# fallback is the same browser at its ordinary rate, which takes about 160 seconds.
FAST = ['--disable-gpu-vsync', '--disable-frame-rate-limit', '--use-gl=swiftshader',
        '--run-all-compositor-stages-before-draw']

H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.TCPServer(('127.0.0.1', 0), H)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = 'http://127.0.0.1:%d/' % PORT

# ---- 1. the rule, exhaustively ------------------------------------------------------
# Every one of the 512 states a 3x3 neighbourhood can be in: 256 arrangements of the eight
# neighbours, each with the cell in the middle alive and dead. The board is 8 squares, so
# that a neighbourhood in the middle of it cannot reach round the wrap and count itself.
RULE_TABLE = """() => {
  const b = TBlife(8), out = [];
  for (let m = 0; m < 256; m++) for (let self = 0; self < 2; self++) {
    b.clear();
    let k = 0;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      if (!dx && !dy) continue;
      if ((m >> k) & 1) b.put(4 + dx, 4 + dy, 1);
      k++;
    }
    if (self) b.put(4, 4, 1);
    b.step();
    out.push(b.cells()[4 * 8 + 4]);
  }
  return out;
}"""

# ---- 2. the rule, against a published figure ----------------------------------------
# The R-pentomino runs for 1103 generations and then stops changing, at 116 cells. It
# throws off six gliders on the way, and a glider covers one cell every four generations,
# so at generation 1103 nothing it has made is more than 276 cells from where it started.
# A 640-square board leaves 320 in every direction, and the check reads back how close the
# pattern actually came to the edge, so a run that wrapped could not be reported as a run
# that did not.
RULE_R = """(n) => {
  const b = TBlife(n), c = n >> 1, marks = {};
  [[1,0],[2,0],[0,1],[1,1],[1,2]].forEach(p => b.put(c + p[0], c + p[1], 1));
  const t0 = performance.now();
  for (let g = 1; g <= 1200; g++) {
    b.step();
    if ((g >= 1100 && g <= 1106) || g === 1200) marks[g] = b.pop();
  }
  const cells = b.cells();
  let lo = n, hi = 0;
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (cells[y * n + x]) {
    lo = Math.min(lo, x, y); hi = Math.max(hi, x, y);
  }
  return {marks: marks, lo: lo, hi: hi, ms: Math.round(performance.now() - t0)};
}"""

# ---- 3. a glider is a glider --------------------------------------------------------
# Five cells, and four generations later the same five cells one square down and one
# across. If that holds, the plate's gliders are gliders.
RULE_GLIDER = """() => {
  const n = 24, b = TBlife(n);
  [[1,0],[2,1],[0,2],[1,2],[2,2]].forEach(p => b.put(5 + p[0], 5 + p[1], 1));
  const before = Array.from(b.cells());
  const pops = [];
  for (let g = 0; g < 4; g++) { b.step(); pops.push(b.pop()); }
  const c = b.cells();
  let moved = true;
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++)
    if (c[((y + 1) % n) * n + (x + 1) % n] !== before[y * n + x]) moved = false;
  return {pops: pops, moved: moved};
}"""

# ---- 4. the census ------------------------------------------------------------------
# The catalogue written out again here, by hand, from the same published shapes the plate
# was built from. Writing it twice is the point: a check that imported the plate's own
# table could only ever prove the table matched itself.
SHAPES_JS = {
    'block':   [[0, 0], [1, 0], [0, 1], [1, 1]],
    'blinker': [[0, 0], [1, 0], [2, 0]],
    'beehive': [[1, 0], [2, 0], [0, 1], [3, 1], [1, 2], [2, 2]],
    'loaf':    [[1, 0], [2, 0], [0, 1], [3, 1], [1, 2], [3, 2], [2, 3]],
    'boat':    [[0, 0], [1, 0], [0, 1], [2, 1], [1, 2]],
    'tub':     [[1, 0], [0, 1], [2, 1], [1, 2]],
    'pond':    [[1, 0], [2, 0], [0, 1], [3, 1], [0, 2], [3, 2], [1, 3], [2, 3]],
    'ship':    [[0, 0], [1, 0], [0, 1], [2, 1], [1, 2], [2, 2]],
    'glider':  [[1, 0], [2, 1], [0, 2], [1, 2], [2, 2]],
}

# A glider, a block and a blinker, well clear of each other on a board with nothing else
# on it. Twelve cells, three components, and the census has to read exactly that.
CENSUS_KNOWN = """() => {
  const N = 40, b = TBlife(N);
  const put = (cs, ox, oy) => cs.forEach(p => b.put(ox + p[0], oy + p[1], 1));
  put([[1,0],[2,1],[0,2],[1,2],[2,2]], 3, 3);
  put([[0,0],[1,0],[0,1],[1,1]], 20, 3);
  put([[0,0],[1,0],[2,0]], 3, 20);
  return {c: TBcensus(b.cells(), N), pop: b.pop()};
}"""

# Every catalogue shape, in all eight orientations of the square, one at a time on an
# empty board. The plate stores each entry eight ways so that a boat facing the other way
# is still a boat; this is what says it does.
CENSUS_SYM = """(shapes) => {
  const N = 40, bad = [];
  let n = 0;
  for (const k in shapes) for (let t = 0; t < 8; t++) {
    const b = TBlife(N);
    shapes[k].forEach(p => {
      let x = p[0], y = p[1], s;
      if (t & 4) { s = x; x = y; y = s; }
      if (t & 1) x = -x;
      if (t & 2) y = -y;
      b.put((x + 15 + N) % N, (y + 15 + N) % N, 1);
    });
    const c = TBcensus(b.cells(), N);
    n++;
    if ((c.counts[k] || 0) !== 1 || c.comps !== 1 || c.lost) bad.push([k, t, c.counts]);
  }
  return {n: n, bad: bad};
}"""

# The same shapes again, this time laid down over the corner so that each one straddles
# both seams at once. The board wraps, so a block on the edge is a block, and a census
# that walked the board in board coordinates rather than in the component's own would
# find four separate cells here instead of one object.
CENSUS_SEAM = """(shapes) => {
  const N = 40, bad = [];
  let n = 0;
  for (const k in shapes) {
    const b = TBlife(N);
    shapes[k].forEach(p => b.put((N - 1 + p[0]) % N, (N - 1 + p[1]) % N, 1));
    const c = TBcensus(b.cells(), N);
    n++;
    if ((c.counts[k] || 0) !== 1 || c.comps !== 1 || c.lost) bad.push([k, c.counts, c.lost]);
  }
  return {n: n, bad: bad};
}"""

# Soups of its own, run to ash, and the census read off the end of each. The sum is what
# matters: every live cell is inside exactly one component, and every component is either
# named or counted as got away, so the two figures have to come to the population.
CENSUS_SOUP = """(n) => {
  const out = [];
  for (let t = 0; t < 5; t++) {
    const b = TBlife(n);
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++)
      if (Math.random() < 0.5) b.put(x, y, 1);
    let gen = 0;
    while (gen < 4800 && !b.repeats()) { b.step(); gen++; }
    const c = TBcensus(b.cells(), n);
    out.push({gen: gen, pop: b.pop(), named: c.namedCells, lost: c.lostCells,
              comps: c.comps, away: c.lost, counts: c.counts});
  }
  return out;
}"""

# ---- 5. the gun ---------------------------------------------------------------------
# Gosper's gun grows without bound on an open board. This one is not open, so the number
# the caption gives has to come from somewhere, and this is where. Two independent
# readings of the same event: the gun's own 36 by 9 box stops matching what it held one
# period earlier, and the population stops climbing by exactly five a period. The board
# is a torus, so where the pattern is put makes no difference and none is looked for.
GUN_RUN = """(gun) => {
  const N = 72, b = TBlife(N), GX = gun.x, GY = gun.y, G = gun.rows;
  for (let y = 0; y < G.length; y++) for (let x = 0; x < G[y].length; x++)
    if (G[y][x] === 'O') b.put((GX + x) % N, (GY + y) % N, 1);
  const box = () => { let s = '';
    for (let y = 0; y < G.length; y++) for (let x = 0; x < G[0].length; x++)
      s += b.cells()[((GY + y) % N) * N + (GX + x) % N];
    return s; };
  const hist = {0: box()}, pops = {0: b.pop()};
  let body = null, growth = null, settled = null, peak = b.pop(), peakAt = 0;
  for (let g = 1; g <= 1200; g++) {
    b.step();
    hist[g] = box(); pops[g] = b.pop();
    if (pops[g] > peak) { peak = pops[g]; peakAt = g; }
    if (g >= 30) {
      if (body === null && hist[g] !== hist[g - 30]) body = g;
      if (growth === null && pops[g] !== pops[g - 30] + 5) growth = g;
    }
    if (b.repeats()) { settled = g; break; }
  }
  return {body: body, growth: growth, settled: settled, peak: peak, peakAt: peakAt,
          climb: [30, 60, 120, 180, 240, 270].map(g => pops[g])};
}"""

GUN_ROWS = ['........................O...........',
            '......................O.O...........',
            '............OO......OO............OO',
            '...........O...O....OO............OO',
            'OO........O.....O...OO..............',
            'OO........O...O.OO....O.O...........',
            '..........O.....O.......O...........',
            '...........O...O....................',
            '............OO......................']

# ---- reading the board off the picture ----------------------------------------------
# The canvas is one pixel to a cell, so the picture is the board and there is no need to
# reach inside the plate for it. The pale ink is the live cell and the field is the blue.
BOARD = """() => {
  const cv = document.querySelector('.viz[data-plate=about] canvas');
  const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data;
  const n = cv.width, out = new Array(n * n);
  for (let i = 0; i < n * n; i++) out[i] = d[i * 4] > 128 ? 1 : 0;
  return {n: n, cells: out};
}"""

# What the plate does over a stretch of frames, sampled off the picture and off the
# readout: one row per painted frame.
TRACE = """(frames) => new Promise(res => {
  const viz = document.querySelector('.viz[data-plate=about]');
  const cv = viz.querySelector('canvas'), ctx = cv.getContext('2d');
  const out = viz.querySelector('output'), n = cv.width, rows = [];
  (function loop(){
    const d = ctx.getImageData(0, 0, n, n).data;
    let p = 0;
    for (let i = 0; i < n * n; i++) if (d[i * 4] > 128) p++;
    rows.push([parseInt(out.textContent, 10), p]);
    if (rows.length < frames) requestAnimationFrame(loop); else res(rows);
  })();
})"""

# ---- the two inks -------------------------------------------------------------------
# What colour the board is actually painted, which nothing here used to look at. Every
# other check reads the canvas as ones and zeros — `d[i * 4] > 128` — so a plate painting
# its dead ground in the wrong ink passes all of them, and one did: `var DEAD = 272` in
# the same scope as `var DEAD = hex(css('--lat-on'))` rebound the ink to a number, every
# dead cell painted rgb(0,0,0) instead of the field blue, and ten checks passed on it.
#
# The board is read at a known generation with a known population, so the two inks can be
# told apart by how many cells carry them as well as by where they are.
INK = """() => {
  const cv = document.querySelector('.viz[data-plate=about] canvas');
  const n = cv.width, d = cv.getContext('2d').getImageData(0, 0, n, n).data;
  const css = v => getComputedStyle(document.documentElement)
                     .getPropertyValue(v).trim();
  const rgb = h => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16),
                    parseInt(h.slice(5, 7), 16)].join(',');
  const at = (x, y) => { const i = (y * n + x) * 4;
                         return d[i] + ',' + d[i + 1] + ',' + d[i + 2]; };
  const inks = {};
  for (let i = 0; i < n * n; i++) {
    const k = d[i * 4] + ',' + d[i * 4 + 1] + ',' + d[i * 4 + 2];
    inks[k] = (inks[k] || 0) + 1;
  }
  return {n: n, inks: inks, on: rgb(css('--lat-on')), off: rgb(css('--lat-off')),
          onName: css('--lat-on'), offName: css('--lat-off'),
          // the five cells of the glider the Gliders scene puts at MARGIN, MARGIN
          live: [[5, 4], [6, 5], [4, 6], [5, 6], [6, 6]].map(p => at(p[0], p[1])),
          dead: [[36, 36], [0, 0], [71, 71], [40, 8]].map(p => at(p[0], p[1]))};
}"""

# The plate itself, sampled every painted frame: the board read off the picture, the
# census run over that same board, and the caption measured. The census is run on the
# picture rather than reached for inside the plate, so what is checked is the board the
# reader is looking at — and since #69 took the census off the caption, running it here
# is the only thing still checking that what #65 built is right.
#
# .note carries no spans since #69, so the caption is measured with a Range over its own
# text rather than by summing children. The box cannot be measured instead: min-height
# holds it at 57.19 whatever the text does, which is the whole reason a third line used
# to be able to move the plate without the box saying so.
LIVE = """(frames) => new Promise(res => {
  const viz = document.querySelector('.viz[data-plate=about]');
  const cv = viz.querySelector('canvas'), ctx = cv.getContext('2d');
  const note = viz.querySelector('.note'), n = cv.width;
  const cells = new Uint8Array(n * n);
  let short = 0, tall = 0, worst = '', hi = 0, vizH = null, moved = 0, seen = 0;
  const kinds = {}, texts = {};
  (function loop(){
    const d = ctx.getImageData(0, 0, n, n).data;
    let p = 0;
    for (let i = 0; i < n * n; i++) { cells[i] = d[i * 4] > 128 ? 1 : 0; p += cells[i]; }
    const c = TBcensus(cells, n);
    if (c.namedCells + c.lostCells !== p) short++;
    for (const k in c.counts) kinds[k] = (kinds[k] || 0) + 1;
    const rg = document.createRange(); rg.selectNodeContents(note);
    const h = rg.getBoundingClientRect().height;
    if (h > hi) { hi = h; worst = note.textContent; }
    if (h > 19.51) tall++;
    const v = viz.getBoundingClientRect().height;
    if (vizH === null) vizH = v; else if (Math.abs(v - vizH) > 0.01) moved++;
    texts[note.textContent] = 1;
    seen++;
    if (seen < frames) requestAnimationFrame(loop);
    else res({frames: seen, short: short, tall: tall, hi: hi, worst: worst,
              viz: vizH, moved: moved, kinds: kinds, states: Object.keys(texts)});
  })();
})"""

# A drag: a pointerdown and then a run of pointermoves along a straight line, read off the
# picture the same way a click is. The cells between two moves are the point — a pointer
# covers more than one cell a frame, and a line with holes in it is not a line.
DRAG = """([x0, y0, x1, y1, steps]) => {
  const cv = document.querySelector('.viz[data-plate=about] canvas');
  const ctx = cv.getContext('2d'), n = cv.width;
  const grab = () => Array.from(ctx.getImageData(0, 0, n, n).data)
                          .filter((_, i) => i % 4 === 0).map(v => v > 128 ? 1 : 0);
  const a = grab();
  const ev = (t, x, y, b) => cv.dispatchEvent(new PointerEvent(t,
      {clientX: x, clientY: y, buttons: b, bubbles: true, pointerId: 1}));
  ev('pointerdown', x0, y0, 1);
  for (let i = 1; i <= steps; i++)
    ev('pointermove', x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps, 1);
  ev('pointerup', x1, y1, 0);
  const b = grab();
  const changed = [];
  for (let i = 0; i < n * n; i++) if (a[i] !== b[i]) changed.push([i % n, (i / n) | 0]);
  // and a move after the release must draw nothing
  const c0 = grab();
  ev('pointermove', x0, y1, 0);
  const c1 = grab();
  let after = 0;
  for (let i = 0; i < n * n; i++) if (c0[i] !== c1[i]) after++;
  return {n: n, changed: changed, after: after, cells: b};
}"""

# A click, dispatched and read in the same turn of the event loop, so nothing the model
# does can get in between the two pictures. clientX and clientY are worked out from the
# canvas's own rect on the Python side, the way a reader's pointer would land.
CLICK = """([cx, cy]) => {
  const cv = document.querySelector('.viz[data-plate=about] canvas');
  const ctx = cv.getContext('2d'), n = cv.width;
  const grab = () => Array.from(ctx.getImageData(0, 0, n, n).data)
                          .filter((_, i) => i % 4 === 0).map(v => v > 128 ? 1 : 0);
  const a = grab();
  cv.dispatchEvent(new PointerEvent('pointerdown',
                   {clientX: cx, clientY: cy, bubbles: true}));
  const b = grab();
  const changed = [];
  for (let i = 0; i < n * n; i++) if (a[i] !== b[i]) changed.push([i % n, (i / n) | 0]);
  return {n: n, changed: changed};
}"""

# ---- the rate ------------------------------------------------------------------------
# Steps against animation frames rather than against the clock. The wall clock says what
# the reader gets on this display; the ratio says what the plate does on any of them, and
# it is the ratio that is the change. TB.ticks.about is the runtime's own count of the
# frames it has handed the plate, so a skipped tick is counted as a frame and not as a
# step, which is exactly the thing being measured.
RATE = """(frames) => new Promise(res => {
  const out = document.querySelector('.viz[data-plate=about] output');
  const g0 = parseInt(out.textContent, 10), t0 = TB.ticks.about, w0 = performance.now();
  let n = 0;
  (function loop(){
    if (++n < frames) requestAnimationFrame(loop);
    else res({gens: parseInt(out.textContent, 10) - g0, ticks: TB.ticks.about - t0,
              ms: performance.now() - w0});
  })();
})"""

# Everything the plate is saying at once: the generation, what is on the board, what the
# caption says, what the run button says, and whether the loop is up. The three have to
# agree — a button reading Resume over a running loop is the lie this check is for.
STOPPED = """() => {
  const viz = document.querySelector('.viz[data-plate=about]');
  const cv = viz.querySelector('canvas'), n = cv.width;
  const d = cv.getContext('2d').getImageData(0, 0, n, n).data;
  const cells = new Uint8Array(n * n);
  let pop = 0;
  for (let i = 0; i < n * n; i++) { cells[i] = d[i * 4] > 128 ? 1 : 0; pop += cells[i]; }
  const nt = viz.querySelector('.note');
  const rg = document.createRange(); rg.selectNodeContents(nt);
  const h = rg.getBoundingClientRect().height;
  return {gen: parseInt(viz.querySelector('output').textContent, 10), pop: pop,
          run: viz.querySelector('button.run').textContent,
          state: nt.textContent,
          crit: nt.classList.contains('crit'), note: h,
          viz: viz.getBoundingClientRect().height,
          census: TBcensus(cells, n), running: TB.running(), ticks: TB.ticks.about};
}"""

# Presses on named cells, the way a reader's finger lands, with the plate stopped so that
# nothing has moved between them. A press on a dead cell draws and a press on a live one
# rubs out, which is the plate's own rule, so this both puts a block down on empty ground
# and takes a glider off the board depending on where it is aimed.
MARK = """([n, l, t, w, h, cells]) => {
  const cv = document.querySelector('.viz[data-plate=about] canvas');
  for (const p of cells)
    cv.dispatchEvent(new PointerEvent('pointerdown',
      {clientX: l + (p[0] + 0.5) * w / n, clientY: t + (p[1] + 0.5) * h / n,
       bubbles: true}));
  const ctx = cv.getContext('2d'), d = ctx.getImageData(0, 0, n, n).data;
  let pop = 0;
  for (let i = 0; i < n * n; i++) if (d[i * 4] > 128) pop++;
  return pop;
}"""

BOX = """() => {
  const cv = document.querySelector('.viz[data-plate=about] canvas');
  const r = cv.getBoundingClientRect(), s = getComputedStyle(cv);
  return {l: r.left + parseFloat(s.borderLeftWidth),
          t: r.top + parseFloat(s.borderTopWidth),
          w: r.width - parseFloat(s.borderLeftWidth) - parseFloat(s.borderRightWidth),
          h: r.height - parseFloat(s.borderTopWidth) - parseFloat(s.borderBottomWidth),
          n: cv.width};
}"""

# The five cells of the glider the Gliders scene puts at MARGIN, MARGIN. The other one
# goes in at MARGIN + OFFSET, N - 1 - MARGIN, and is the one left standing.
FIRST_GLIDER = [[5, 4], [6, 5], [4, 6], [5, 6], [6, 6]]

# A cell with nothing live inside `pad` of it, read off the picture and across the wrap.
# Settled ash is 97% empty board, so this is what a reader clicking at random hits, and a
# mark drawn there touches none of the ash: whatever the plate does next it does because
# of the mark and not because the mark landed on something.
CLEAR = """(pad) => {
  const cv = document.querySelector('.viz[data-plate=about] canvas');
  const n = cv.width, d = cv.getContext('2d').getImageData(0, 0, n, n).data;
  const on = (x, y) => d[(((y + n) % n) * n + (x + n) % n) * 4] > 128;
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    let clear = true;
    for (let dy = -pad; dy <= pad && clear; dy++)
      for (let dx = -pad; dx <= pad; dx++) if (on(x + dx, y + dy)) { clear = false; break; }
    if (clear) return [x, y];
  }
  return null;
}"""

STOPS = ('() => document.querySelector(".viz[data-plate=about] button.run")'
         '.textContent === "Resume"')


def waits_to_stop(p, ms):
    """A plate that never stops is the failure this is here to catch, so waiting for it
    to stop reports rather than throws: a check that crashes says less than one that goes
    red beside the eighty that did not."""
    try:
        p.wait_for_function(STOPS, timeout=ms)
        return True
    except Exception:
        return False

rows, fails = [], []


def note(name, ok, detail=''):
    rows.append((name, ok, detail))
    if not ok:
        fails.append(name)


with sync_playwright() as pw:
    br = pw.chromium.launch()

    # ---- the rule ---------------------------------------------------------------
    p = br.new_page(viewport={'width': 1400, 'height': 900})
    p.goto(URL + 'about.html')
    p.wait_for_function('typeof TBlife === "function"')

    got = p.evaluate(RULE_TABLE)
    bad = 0
    for m in range(256):
        s = bin(m).count('1')
        for self in (0, 1):
            want = 1 if (s == 3 or (s == 2 and self)) else 0
            if got[m * 2 + self] != want:
                bad += 1
    note('B3/S23 on all 512 states of a 3x3 neighbourhood: %d right' % (512 - bad),
         bad == 0)

    r = p.evaluate(RULE_R, BIG)
    marks = dict((int(k), v) for k, v in r['marks'].items())
    note('R-pentomino, population 116 at generation 1103 (published)',
         marks.get(1103) == 116,
         '  1100..1106 %s, still %d at 1200, %d ms'
         % ([marks[g] for g in range(1100, 1107)], marks[1200], r['ms']))
    note('and it changed until then: 1102 is not yet 116', marks.get(1102) != 116,
         '  generation 1102 has %d cells' % marks.get(1102))
    note('and the %d-square board never wrapped: nearest cell %d from the edge'
         % (BIG, min(r['lo'], BIG - 1 - r['hi'])),
         min(r['lo'], BIG - 1 - r['hi']) > 20)

    g = p.evaluate(RULE_GLIDER)
    note('a glider stays five cells and moves one square diagonally every four',
         g['pops'] == [5, 5, 5, 5] and g['moved'], '  populations %s' % (g['pops'],))

    # ---- the census -------------------------------------------------------------
    k = p.evaluate(CENSUS_KNOWN)
    c = k['c']
    note('a glider, a block and a blinker on a board with nothing else on it read as '
         'one of each and nothing unmatched',
         c['counts'] == {'glider': 1, 'block': 1, 'blinker': 1} and c['lost'] == 0
         and c['comps'] == 3,
         '  %s, %d components, %d got away, %d cells named of %d alive'
         % (c['counts'], c['comps'], c['lost'], c['namedCells'], k['pop']))

    s = p.evaluate(CENSUS_SYM, SHAPES_JS)
    note('every catalogue shape is found in all eight orientations of the square, '
         '%d of %d' % (s['n'] - len(s['bad']), s['n']), not s['bad'],
         '' if not s['bad'] else '  missed %s' % s['bad'])

    s = p.evaluate(CENSUS_SEAM, SHAPES_JS)
    note('and laid over the corner, straddling both wrap seams at once, %d of %d'
         % (s['n'] - len(s['bad']), s['n']), not s['bad'],
         '' if not s['bad'] else '  missed %s' % s['bad'])

    soups = p.evaluate(CENSUS_SOUP, 72)
    bad = [t for t in soups if t['named'] + t['lost'] != t['pop']]
    note('the census is complete over a settled soup: named cells plus unmatched cells '
         'are the population, %d of %d' % (len(soups) - len(bad), len(soups)), not bad,
         '\n'.join('  ash at %4d, %3d cells in %2d components: %3d named + %3d got away '
                   'in %d, %s' % (t['gen'], t['pop'], t['comps'], t['named'], t['lost'],
                                  t['away'], t['counts']) for t in soups))

    # ---- the gun ----------------------------------------------------------------
    gun = p.evaluate(GUN_RUN, {'x': 18, 'y': 31, 'rows': GUN_ROWS})
    note('the gun grows by exactly five cells a period while it is alive',
         gun['climb'] == [41, 46, 56, 66, 76, 81],
         '  population at 30, 60, 120, 180, 240, 270: %s' % (gun['climb'],))
    note('and its own stream destroys it at generation %s on this board' % gun['body'],
         gun['body'] == GUN_DEAD and gun['growth'] == gun['body'] + 1,
         '  the gun\'s 36 by 9 box stops matching itself one period back at %s, the '
         'population stops climbing at %s,\n  it peaks at %d cells at %s and the wreck '
         'settles at %s' % (gun['body'], gun['growth'], gun['peak'], gun['peakAt'],
                            gun['settled']))
    p.close()

    # ---- the plate: the three scenarios ------------------------------------------
    board_n = 0
    for scene in ('gliders', 'gun', 'soup'):
        p = br.new_page(viewport={'width': 1400, 'height': 900})
        p.goto(URL + 'about.html')
        p.wait_for_function('TB.running() === "about"')
        p.click('.viz[data-plate=about] button[data-scene=%s]' % scene)
        board_n = p.evaluate('document.querySelector(".viz[data-plate=about] canvas").width')
        # The census and the caption are read first, so that they are read off a board
        # that is still moving: since #67 a run ends rather than starting over, and the
        # Gliders scene is settled and stopped by the six hundredth step.
        lv = p.evaluate(LIVE, 300)
        tr = p.evaluate(TRACE, 900)
        p.close()
        note('%s: the census adds up on every frame it is read on, %d of %d'
             % (scene, lv['frames'] - lv['short'], lv['frames']), not lv['short'],
             '  named cells plus unmatched cells are the population, read off the '
             'picture; kinds seen %s' % sorted(lv['kinds']))
        note('%s: the caption stays one line and the plate column does not move'
             % scene, lv['tall'] == 0 and lv['moved'] == 0,
             '  worst caption %.2f of %.2f allowed, .viz %.2f throughout, %d frames\n'
             '  states seen: %s' % (lv['hi'], ONE_LINE, lv['viz'], lv['frames'],
                                    ' / '.join(lv['states'])))
        gens = [t[0] for t in tr]
        pops = [t[1] for t in tr]
        n = board_n
        peak = max(pops)
        steps = [gens[i] - gens[i - 1] for i in range(1, len(gens))]
        restarts = sum(1 for s in steps if s < 0)
        # Half speed, seen from the picture rather than from TB.ticks: the counter goes up
        # by one on a frame and stands still on the next, and never by more than one. The
        # share is only ever about a half here and the check is written to about — this
        # loop and the plate's are two separate raf chains and do not get the same number
        # of callbacks. The exact ratio is measured against TB.ticks further down, which
        # is the runtime's own count of the frames it handed the plate.
        run = steps[:max(i for i, s in enumerate(steps) if s) + 1] if any(steps) else []
        share = float(sum(1 for s in run if s)) / len(run) if run else 0
        note('%s: the counter advances by one at a time, on about one frame in %d'
             % (scene, EVERY), set(steps) <= {0, 1}
             and abs(share - 1.0 / EVERY) <= 0.10,
             '  %d frames, generations %d to %d, the counter moved on %.1f%% of the %d '
             'frames before it stopped, peak population %d (%.1f%% of the board)'
             % (len(gens), gens[0], max(gens), 100.0 * share, len(run), peak,
                100.0 * peak / (n * n)))
        # (5) It never lays itself out again. A relay is the generation going back to
        # nought with the opening board under it, and both halves of that are looked for:
        # the counter never goes backwards, and no single frame swaps one board for
        # another. A soup laid out again jumps from a couple of hundred cells to half the
        # board between two frames, which no generation of Life does.
        jump = max(abs(pops[i] - pops[i - 1]) for i in range(1, len(pops)))
        note('%s: the scenario is never laid out again' % scene,
             restarts == 0 and min(gens) == gens[0] and jump < 0.25 * n * n,
             '  %d generations backwards over %d frames, lowest generation %d against %d '
             'at the first frame, biggest population change between two frames %d of %d'
             % (restarts, len(gens), min(gens), gens[0], jump, n * n))
        # Neither of the two ways a Life board can stop being worth looking at: it never
        # empties, and it thins to ash rather than filling up. The soup starts at half the
        # board by construction, so the test is where it ends, not how high it peaked.
        note('%s: the board neither empties nor fills' % scene,
             min(pops) > 0 and pops[-1] < 0.15 * n * n,
             '  population %d at the first frame, %d at the last, low water %d, of %d'
             % (pops[0], pops[-1], min(pops), n * n))

    # ---- the board is painted in the two inks the palette names -------------------
    # Reduced motion opens the plate paused, so the Gliders scene sits at generation 0
    # with exactly ten live cells and the rest of the board dead: two inks, and which is
    # which is not a guess.
    p = br.new_page(viewport={'width': 1400, 'height': 900}, device_scale_factor=1,
                    reduced_motion='reduce')
    p.goto(URL + 'about.html')
    p.wait_for_function('TB.running() === null && TB.mounted().indexOf("about") >= 0')
    p.click('.viz[data-plate=about] button[data-scene=gliders]')
    p.wait_for_timeout(200)
    m = p.evaluate(INK)
    cells = m['n'] * m['n']
    inks = m['inks']
    note('the board is painted in exactly the two inks the palette names',
         sorted(inks) == sorted([m['on'], m['off']])
         and inks.get(m['on']) == cells - 10 and inks.get(m['off']) == 10,
         '  dead ground %s rgb(%s) on %s cells, live cell %s rgb(%s) on %s of %d\n'
         '  painted: %s' % (m['onName'], m['on'], inks.get(m['on']), m['offName'],
                            m['off'], inks.get(m['off']), cells,
                            ', '.join('rgb(%s) x %d' % (k, v) for k, v in inks.items())))
    note('and a live cell is the pale ink and dead ground the blue, not the other way '
         'round', all(v == m['off'] for v in m['live'])
         and all(v == m['on'] for v in m['dead']),
         '  the glider\'s five cells read %s, four cells of empty board read %s'
         % (sorted(set(m['live'])), sorted(set(m['dead']))))
    # and running, on the soup, where every cell is one or the other and nothing else
    p.click('.viz[data-plate=about] button[data-scene=soup]')
    p.click('.viz[data-plate=about] button.run')
    p.wait_for_timeout(600)
    m2 = p.evaluate(INK)
    note('and it stays the two inks with the model running', sorted(m2['inks'])
         == sorted([m2['on'], m2['off']]),
         '  %s' % ', '.join('rgb(%s) x %d' % (k, v) for k, v in m2['inks'].items()))
    p.close()

    # ---- the caption at the widths, and the narrowest is the one that matters -----
    # 340 CSS px at 380, which is the least the note is ever given. Everything the
    # caption can say has to be one line there as well as at 1400.
    for w in (380, 420, 881, 1120):
        p = br.new_page(viewport={'width': w, 'height': 900}, device_scale_factor=1)
        p.goto(URL + 'about.html')
        p.wait_for_function('TB.running() === "about"')
        lv = p.evaluate(LIVE, 300)
        nw = p.evaluate("""() => document.querySelector('.viz[data-plate=about] .note')
                                  .getBoundingClientRect().width""")
        note('%d: the caption is one line and the plate column is still %.2f'
             % (w, lv['viz']), lv['tall'] == 0 and lv['moved'] == 0,
             '  note %.0f wide, worst caption %.2f of %.2f allowed over %d frames'
             % (nw, lv['hi'], ONE_LINE, lv['frames']))
        p.close()

    # ---- the gun's caption says the generation this tree measured -----------------
    p = br.new_page(viewport={'width': 1400, 'height': 900})
    p.goto(URL + 'about.html')
    p.wait_for_function('TB.running() === "about"')
    p.click('.viz[data-plate=about] button[data-scene=gun]')
    p.wait_for_timeout(400)
    before = p.text_content('.viz[data-plate=about] .note')
    gen_before = int(p.text_content('.viz[data-plate=about] output'))
    p.wait_for_function('parseInt(document.querySelector(".viz[data-plate=about] output")'
                        '.textContent, 10) > %d' % (GUN_DEAD + 5), timeout=30000)
    after = p.text_content('.viz[data-plate=about] .note')
    note('the gun scene says it is alive before %d and gone after' % GUN_DEAD,
         gen_before < GUN_DEAD and 'gone' not in before and str(GUN_DEAD) in after,
         '  at generation %d: %r\n  past %d: %r' % (gen_before, before, GUN_DEAD, after))
    p.close()

    # ---- the random field keeps its own first fifty generations -------------------
    # A soup throws off a glider almost at once, so an ungated glider line would take a
    # third of the window the field's line is a claim about. Sampled every painted frame
    # from the load: below fifty the field's line, and the glider line only above it.
    p = br.new_page(viewport={'width': 1400, 'height': 900})
    p.goto(URL + 'about.html')
    p.wait_for_function('TB.running() === "about"')
    seen = p.evaluate("""() => new Promise(res => {
      const viz = document.querySelector('.viz[data-plate=about]');
      const st = viz.querySelector('.note'), out = viz.querySelector('output');
      const rows = [];
      (function loop(){
        rows.push([parseInt(out.textContent, 10), st.textContent]);
        if (rows.length < 260) requestAnimationFrame(loop); else res(rows);
      })();
    })""")
    early = [r for r in seen if r[0] < 50 and 'real pattern' in r[1]]
    late = [r for r in seen if r[0] >= 50 and 'real pattern' in r[1]]
    under = [r for r in seen if r[0] < 50]
    note('the random field keeps its own first fifty generations', not early,
         '  %d frames under generation 50, none of them the glider line; %d frames '
         'above it say it' % (len(under), len(late)))
    p.close()

    # ---- a drag draws ------------------------------------------------------------
    # Under reduced motion the plate opens paused, so between the two pictures the drag
    # is the only thing that has happened.
    p = br.new_page(viewport={'width': 1400, 'height': 900}, device_scale_factor=1,
                    reduced_motion='reduce')
    p.goto(URL + 'about.html')
    p.wait_for_function('TB.running() === null && TB.mounted().indexOf("about") >= 0')
    p.wait_for_timeout(200)
    box = p.evaluate("""() => {
      const cv = document.querySelector('.viz[data-plate=about] canvas');
      const r = cv.getBoundingClientRect(), s = getComputedStyle(cv);
      return {l: r.left + parseFloat(s.borderLeftWidth),
              t: r.top + parseFloat(s.borderTopWidth),
              w: r.width - parseFloat(s.borderLeftWidth) - parseFloat(s.borderRightWidth),
              h: r.height - parseFloat(s.borderTopWidth) - parseFloat(s.borderBottomWidth),
              n: cv.width};
    }""")
    n = box['n']
    ax, ay, bx = 8, 36, 60
    px = lambda cx: box['l'] + (cx + 0.5) * box['w'] / n
    py = lambda cy: box['t'] + (cy + 0.5) * box['h'] / n
    # six moves across 52 cells, so most of the line is cells no pointermove landed on
    r = p.evaluate(DRAG, [px(ax), py(ay), px(bx), py(ay), 6])
    row = [r['cells'][ay * n + x] for x in range(ax, bx + 1)]
    off = [c for c in r['changed'] if c[1] != ay or c[0] < ax or c[0] > bx]
    note('a drag draws the whole line it crosses, not the cells the moves landed on',
         len(set(row)) == 1 and not off and len(r['changed']) > 6,
         '  %d cells from (%d,%d) to (%d,%d) all read %d, %d changed, %d of them off '
         'the line' % (len(row), ax, ay, bx, ay, row[0], len(r['changed']), len(off)))
    note('and the pointer stops drawing when it is let go', r['after'] == 0,
         '  %d cells changed by a move after the release' % r['after'])
    p.close()

    # ---- pause and resume --------------------------------------------------------
    p = br.new_page(viewport={'width': 1400, 'height': 900})
    p.goto(URL + 'about.html')
    p.wait_for_function('TB.running() === "about"')
    p.wait_for_timeout(600)
    p.click('.viz[data-plate=about] button.run')
    g0 = p.text_content('.viz[data-plate=about] output')
    b0 = p.evaluate(BOARD)
    p.wait_for_timeout(1200)
    g1 = p.text_content('.viz[data-plate=about] output')
    b1 = p.evaluate(BOARD)
    note('pause stops the generation counter', g0 == g1, '  %s then %s' % (g0, g1))
    note('and stops the board', b0['cells'] == b1['cells'])
    note('and the loop with it, rather than spinning on a flag',
         p.evaluate('TB.running()') is None)
    note('the button says what it will do next',
         p.text_content('.viz[data-plate=about] button.run') == 'Resume')
    # A click lands on one cell while it is paused, which is the whole point of the pause,
    # and on one cell while it is running, which the widths table below cannot show because
    # it measures with the model stopped.
    mid = p.evaluate("""() => {
      const cv = document.querySelector('.viz[data-plate=about] canvas');
      const r = cv.getBoundingClientRect();
      return [r.left + r.width / 2, r.top + r.height / 2];
    }""")
    r = p.evaluate(CLICK, mid)
    note('a click toggles one cell while it is paused', len(r['changed']) == 1)
    p.click('.viz[data-plate=about] button.run')
    p.wait_for_timeout(400)
    g2 = int(p.text_content('.viz[data-plate=about] output'))
    note('resume carries on from where it stopped', g2 > int(g1),
         '  paused at %s, running again at %d' % (g1, g2))
    r = p.evaluate(CLICK, mid)
    note('and a click toggles one cell while it is running', len(r['changed']) == 1)
    p.close()

    # ---- (1) a quarter speed ------------------------------------------------------
    # One step every four animation frames. The ratio is the claim, because it is the
    # quarter that holds on a 144Hz display as well as on this one; the wall clock is
    # reported beside it because it is what the reader on this machine actually gets.
    # The tolerance is EVERY and not 2: a sample can open anywhere inside a cycle, so it
    # can be short by as much as one whole cycle less a frame.
    p = br.new_page(viewport={'width': 1400, 'height': 900})
    p.goto(URL + 'about.html')
    p.wait_for_function('TB.running() === "about"')
    p.wait_for_timeout(400)
    m = p.evaluate(RATE, 300)
    note('one step every %d animation frames' % EVERY,
         abs(m['ticks'] - EVERY * m['gens']) <= EVERY and m['gens'] > 50,
         '  %d steps on %d frames in %.0f ms: %.1f steps a second at %.1f frames a '
         'second, %.3f frames a step'
         % (m['gens'], m['ticks'], m['ms'], m['gens'] * 1000.0 / m['ms'],
            m['ticks'] * 1000.0 / m['ms'], float(m['ticks']) / m['gens']))
    p.close()

    # ---- (2, 3, 4) it stops on settling, says so, and Resume is not dead ----------
    # The Gliders scene is the cheap settle and a deterministic one: the collision burns
    # out and what is left only blinks, so repeats() fires. Note where it rests — one
    # step past a still life and two past a blinker, because that is what repeats()
    # compares against, so the number is a little past where the board truly finished.
    p = br.new_page(viewport={'width': 1400, 'height': 900})
    p.goto(URL + 'about.html')
    p.wait_for_function('TB.running() === "about"')
    p.click('.viz[data-plate=about] button[data-scene=gliders]')
    stopped = waits_to_stop(p, 90000)
    s0 = p.evaluate(STOPPED)
    p.wait_for_timeout(1500)
    s1 = p.evaluate(STOPPED)
    note('it stops when it settles, and the raf loop is down rather than spinning',
         stopped and s0['running'] is None and s1['running'] is None
         and s1['ticks'] == s0['ticks'],
         '  rests at generation %d with %d cells, %d components; the runtime handed the '
         'plate %d frames and %d more over the next 1500ms'
         % (s0['gen'], s0['pop'], s0['census']['comps'], s0['ticks'],
            s1['ticks'] - s0['ticks']))
    note('and Gen holds where it stopped', s0['gen'] == s1['gen'] == SETTLE_GLIDERS,
         '  generation %d, then %d 1500ms later, against the %d this scene settles on'
         % (s0['gen'], s1['gen'], SETTLE_GLIDERS))
    note('and the board holds with it', s0['pop'] == s1['pop'],
         '  %d cells, then %d' % (s0['pop'], s1['pop']))
    note('the run button reads Resume on a board that stopped by itself',
         s0['run'] == 'Resume', '  it reads %r' % s0['run'])
    note('and the caption says why it stopped, in one line',
         'stops' in s0['state'] and s0['crit'] and s0['note'] <= ONE_LINE,
         '  %r\n  %.2f of %.2f allowed, .viz %.2f'
         % (s0['state'], s0['note'], ONE_LINE, s0['viz']))
    # (4) and the press does something. A settled board is still settled, so a plate that
    # read the settle off the first tick after the resume would advance the counter by
    # exactly one and stop again, which is a dead button with a number on it. The board
    # gets WINDOW steps in which it may not be called finished, so a live Resume is worth
    # exactly that many generations here and a dead one is worth one.
    p.click('.viz[data-plate=about] button.run')
    p.wait_for_timeout(1200)
    s2 = p.evaluate(STOPPED)
    note('Resume on a settled board is not a dead button',
         s2['gen'] >= s0['gen'] + WINDOW,
         '  generation %d to %d, %d steps, against the %d a dead one would be worth'
         % (s0['gen'], s2['gen'], s2['gen'] - s0['gen'], 1))
    # and then it stops again, because the board is finished and there is nothing there to
    # resume. Running on would be Gen climbing on a board the reader can see is not moving.
    p.wait_for_timeout(1000)
    s3 = p.evaluate(STOPPED)
    note('and then it stops again, rather than running finished ash on to the cap',
         s3['gen'] == s2['gen'] and s3['running'] is None and s3['run'] == 'Resume',
         '  generation %d, then %d a second later, loop %s, button %r'
         % (s2['gen'], s3['gen'], s3['running'], s3['run']))
    # The three things a reader can do to a stopped plate, and the one thing that has to
    # be true after each of them: the button's word is what the loop is doing.
    p.click('.viz[data-plate=about] button.run')
    p.wait_for_timeout(200)
    s4 = p.evaluate(STOPPED)
    note('Pause: the word and the loop agree',
         s4['run'] == 'Resume' and s4['running'] is None,
         '  button %r, loop %s' % (s4['run'], s4['running']))
    r = p.evaluate(CLICK, p.evaluate("""() => {
      const r = document.querySelector('.viz[data-plate=about] canvas')
                        .getBoundingClientRect();
      return [r.left + r.width / 2, r.top + r.height / 2];
    }"""))
    p.wait_for_timeout(200)
    s5 = p.evaluate(STOPPED)
    note('drawing on a stopped board: the word and the loop still agree',
         s5['run'] == 'Resume' and s5['running'] is None
         and len(r['changed']) == 1 and s5['gen'] == s4['gen'],
         '  %d cell changed, generation still %d, button %r, loop %s'
         % (len(r['changed']), s5['gen'], s5['run'], s5['running']))
    p.close()

    # ---- the settle detector arms on the window, not on the board moving ---------
    # The bug PR #68 was sent back for. Arming on "the board took a step that did not
    # repeat" never arms on a board of nothing but still lifes, because such a board has
    # no such step in it, so the plate ran a finished board to the cap. Each of the three
    # scenarios is run to settled, marked with one cell in clear ground — which is what a
    # reader clicking on settled ash actually hits — and resumed, and each has to stop
    # again within a few generations rather than climbing to 4800.
    #
    # These use the vsync-off browser: the soup takes 110 seconds to settle at the rate
    # the plate runs and about two here, and nothing in them reads a rate.
    try:
        fast = br.browser_type.launch(args=FAST)
    except Exception:
        fast = br.browser_type.launch(args=FAST[:2])
    for scene in ('gliders', 'gun', 'soup'):
        p = fast.new_page(viewport={'width': 1400, 'height': 900})
        p.goto(URL + 'about.html')
        p.wait_for_function('TB.running() === "about"')
        p.click('.viz[data-plate=about] button[data-scene=%s]' % scene)
        settled = waits_to_stop(p, 180000)
        a = p.evaluate(STOPPED)
        box = p.evaluate(BOX)
        spot = p.evaluate(CLEAR, 2)
        p.evaluate(MARK, [box['n'], box['l'], box['t'], box['w'], box['h'], [spot]])
        p.click('.viz[data-plate=about] button.run')
        again = waits_to_stop(p, 60000)
        # past the 1200ms the hand-drawn line is held for, so the caption under test is
        # the one the plate rests on and not "Changed by hand"
        p.wait_for_timeout(1600)
        b = p.evaluate(STOPPED)
        blinkers = a['census']['counts'].get('blinker', 0)
        note('%s: settled, marked in clear ground and resumed, it stops again within %d '
             'generations' % (scene, SOON),
             settled and again and b['running'] is None
             and WINDOW <= b['gen'] - a['gen'] <= SOON,
             '  settled at %d with %d cells and %d blinkers; marked at %s and resumed, '
             'stopped at %d, %d steps on' % (a['gen'], a['pop'], blinkers, spot, b['gen'],
                                             b['gen'] - a['gen']))
        c = p.evaluate(STOPPED)
        note('%s: and Gen holds there, and it says ash rather than the cap' % scene,
             c['gen'] == b['gen'] and 'Ash' in b['state'] and str(CAP) not in b['state'],
             '  generation %d, and the caption is %r' % (c['gen'], b['state']))
        p.close()

    # A board that is nothing but still lifes is the one arming on movement could not see,
    # so it gets a check of its own by name. The gun's wreck is measured to be exactly
    # that, and a block drawn on clear ground beside it leaves a board that is completely
    # static: not one cell changes from the resume to the stop.
    p = fast.new_page(viewport={'width': 1400, 'height': 900})
    p.goto(URL + 'about.html')
    p.wait_for_function('TB.running() === "about"')
    p.click('.viz[data-plate=about] button[data-scene=gun]')
    settled = waits_to_stop(p, 180000)
    a = p.evaluate(STOPPED)
    note("the gun's wreck is nothing but still lifes, which is the board the old arming "
         'could not see', settled and a['census']['counts'].get('blinker', 0) == 0,
         '  %d cells at generation %d, %s' % (a['pop'], a['gen'], a['census']['counts']))
    box = p.evaluate(BOX)
    x, y = p.evaluate(CLEAR, 3)
    p.evaluate(MARK, [box['n'], box['l'], box['t'], box['w'], box['h'],
                      [[x, y], [x + 1, y], [x, y + 1], [x + 1, y + 1]]])
    drawn = p.evaluate(STOPPED)
    p.click('.viz[data-plate=about] button.run')
    again = waits_to_stop(p, 60000)
    p.wait_for_timeout(1600)
    b = p.evaluate(STOPPED)
    note('a board that is completely static stops rather than running to the cap',
         again and b['running'] is None and WINDOW <= b['gen'] - a['gen'] <= SOON
         and drawn['pop'] == a['pop'] + 4 and b['pop'] == drawn['pop'],
         '  %d cells settled, a block drawn at %s makes %d, and %d after the resume; it '
         'stopped at generation %d, %d steps on'
         % (a['pop'], (x, y), drawn['pop'], b['pop'], b['gen'], b['gen'] - a['gen']))
    note('and the cap line is never shown on a board that has stopped moving',
         'Ash' in b['state'] and str(CAP) not in b['state'],
         '  the caption is %r' % b['state'])
    p.close()

    # ---- the scene buttons tell the two ways of being stopped apart ---------------
    # Tim's ruling on #67. A Pause the reader pressed and reduced motion are the reader
    # asking for stillness; a run that has ended is nobody asking for anything.
    p = fast.new_page(viewport={'width': 1400, 'height': 900})
    p.goto(URL + 'about.html')
    p.wait_for_function('TB.running() === "about"')
    p.wait_for_timeout(300)
    p.click('.viz[data-plate=about] button[data-scene=gliders]')
    p.wait_for_timeout(400)
    s = p.evaluate(STOPPED)
    note('a scene button while it is running leaves it running',
         s['running'] == 'about' and s['run'] == 'Pause' and s['gen'] > 0,
         '  generation %d, button %r, loop %s' % (s['gen'], s['run'], s['running']))
    p.click('.viz[data-plate=about] button.run')
    p.wait_for_timeout(200)
    p.click('.viz[data-plate=about] button[data-scene=soup]')
    a = p.evaluate(STOPPED)
    p.wait_for_timeout(800)
    b = p.evaluate(STOPPED)
    note('a scene button after a Pause the reader pressed leaves it stopped',
         a['gen'] == b['gen'] == 0 and b['running'] is None and b['run'] == 'Resume'
         and b['pop'] > 2000,
         '  generation %d, then %d after 800ms, %d cells, button %r, loop %s'
         % (a['gen'], b['gen'], b['pop'], b['run'], b['running']))
    p.close()

    p = fast.new_page(viewport={'width': 1400, 'height': 900})
    p.goto(URL + 'about.html')
    p.wait_for_function('TB.running() === "about"')
    p.click('.viz[data-plate=about] button[data-scene=gliders]')
    ended = waits_to_stop(p, 180000)
    p.click('.viz[data-plate=about] button[data-scene=soup]')
    p.wait_for_timeout(500)
    s = p.evaluate(STOPPED)
    note('a scene button after a run has ended starts the next one',
         ended and s['running'] == 'about' and s['run'] == 'Pause' and s['gen'] > 0,
         '  generation %d, button %r, loop %s' % (s['gen'], s['run'], s['running']))
    p.close()

    # The one that matters most: reduced motion is the reader's ask made by the browser,
    # and the ruling beside `var reduce` is that it is the pause rather than a second path
    # through the plate. A scenario picked under it is laid out, painted, and still.
    p = fast.new_page(viewport={'width': 1400, 'height': 900}, reduced_motion='reduce')
    p.goto(URL + 'about.html')
    p.wait_for_function('TB.running() === null && TB.mounted().indexOf("about") >= 0')
    p.click('.viz[data-plate=about] button[data-scene=gliders]')
    a = p.evaluate(STOPPED)
    p.wait_for_timeout(900)
    b = p.evaluate(STOPPED)
    note('a scene button under reduced motion lays the board out and nothing steps',
         a['gen'] == b['gen'] == 0 and b['running'] is None and b['run'] == 'Resume'
         and b['pop'] == 10,
         '  generation %d, then %d after 900ms, %d cells on the board, button %r, loop %s'
         % (a['gen'], b['gen'], b['pop'], b['run'], b['running']))
    p.close()

    # ---- (6) the cap stops rather than relaying -----------------------------------
    # A board with one loose glider on it never repeats, so the settle exit can never
    # fire and the cap is the only way this run can end. The scene puts two gliders down
    # and they collide, so one of them is rubbed out with five presses while the plate is
    # stopped, which leaves the other one alone on an empty board.
    #
    # 4800 generations is 160 seconds at the rate the plate runs, so this runs on the
    # vsync-off browser too. Nothing in the check reads a rate.
    p = fast.new_page(viewport={'width': 1400, 'height': 900}, device_scale_factor=1,
                      reduced_motion='reduce')
    p.goto(URL + 'about.html')
    p.wait_for_function('TB.running() === null && TB.mounted().indexOf("about") >= 0')
    p.click('.viz[data-plate=about] button[data-scene=gliders]')
    p.wait_for_timeout(200)
    box = p.evaluate(BOX)
    left = p.evaluate(MARK, [box['n'], box['l'], box['t'], box['w'], box['h'],
                            FIRST_GLIDER])
    p.click('.viz[data-plate=about] button.run')
    stopped = waits_to_stop(p, 300000)
    s = p.evaluate(STOPPED)
    note('a board carrying a loose glider runs out its cap and stops there',
         stopped and left == 5 and s['gen'] == CAP and s['running'] is None
         and s['pop'] == 5
         and s['census']['counts'].get('glider') == 1 and s['census']['comps'] == 1,
         '  rubbed one glider out and %d cells were left; it stopped at generation %d '
         'with %d cells in %d component, %s, loop %s'
         % (left, s['gen'], s['pop'], s['census']['comps'], s['census']['counts'],
            s['running']))
    note('and it says the cap rather than the ash, in one line',
         str(CAP) in s['state'] and 'Ash' not in s['state'] and s['crit']
         and s['note'] <= ONE_LINE,
         '  %r\n  %.2f of %.2f allowed, .viz %.2f'
         % (s['state'], s['note'], ONE_LINE, s['viz']))
    note('and the run button reads Resume there too', s['run'] == 'Resume',
         '  it reads %r' % s['run'])
    # The cap is a limit on a run and not on the board, so the press works here as well.
    p.click('.viz[data-plate=about] button.run')
    p.wait_for_timeout(600)
    s7 = p.evaluate(STOPPED)
    note('and Resume on a capped board is not dead either',
         s7['gen'] > CAP + 1 and s7['running'] == 'about' and s7['run'] == 'Pause',
         '  generation %d to %d, loop %s, button %r'
         % (s['gen'], s7['gen'], s7['running'], s7['run']))
    p.close()
    fast.close()

    # ---- a click toggles the cell under the cursor, at every width ---------------
    # Reduced motion opens the plate paused, so between the two pictures the click is
    # the only thing that has happened.
    for w in WIDTHS:
        p = br.new_page(viewport={'width': w, 'height': 900}, device_scale_factor=1,
                        reduced_motion='reduce')
        p.goto(URL + 'about.html')
        p.wait_for_function('TB.running() === null && TB.mounted().indexOf("about") >= 0')
        p.wait_for_timeout(200)
        box = p.evaluate("""() => {
          const cv = document.querySelector('.viz[data-plate=about] canvas');
          const r = cv.getBoundingClientRect(), s = getComputedStyle(cv);
          return {l: r.left + parseFloat(s.borderLeftWidth),
                  t: r.top + parseFloat(s.borderTopWidth),
                  w: r.width - parseFloat(s.borderLeftWidth) - parseFloat(s.borderRightWidth),
                  h: r.height - parseFloat(s.borderTopWidth) - parseFloat(s.borderBottomWidth),
                  n: cv.width};
        }""")
        n = box['n']
        targets = [(0, 0), (n - 1, 0), (0, n - 1), (n - 1, n - 1),
                   (n // 2, n // 2), (n // 3, 2 * n // 3)]
        miss = []
        for (tx, ty) in targets:
            cx = box['l'] + (tx + 0.5) * box['w'] / n
            cy = box['t'] + (ty + 0.5) * box['h'] / n
            r = p.evaluate(CLICK, [cx, cy])
            if r['changed'] != [[tx, ty]]:
                miss.append((tx, ty, r['changed'][:4]))
        note('%d: a click changes exactly the cell under it, %d of %d'
             % (w, len(targets) - len(miss), len(targets)),
             not miss, '  cell %.2f CSS px' % (box['w'] / n) +
             ('' if not miss else '  missed %s' % miss))
        p.close()

    # ---- the buttons are bigger to press than they are to look at ---------------
    # The painted word is 20px tall because the control row has to stay 1.25rem, and 33 by
    # 20 is not a target on a phone. Each button carries a transparent ::before that is out
    # of flow, so it reaches past the word without the row knowing. This measures the box
    # that actually takes the press, checks it against 44 both ways, checks no two of them
    # overlap or reach the readout, and then presses one at the far corner of its box —
    # well outside the painted word — to show the box is real and not just measured.
    HITS = """() => {
      const viz = document.querySelector('.viz[data-plate=about]');
      const R = e => { const r = e.getBoundingClientRect();
                       return {l: r.left, t: r.top, r: r.right, b: r.bottom,
                               w: r.width, h: r.height}; };
      const px = v => (v === 'auto' || !v) ? 0 : parseFloat(v);
      const out = {canvas: R(viz.querySelector('canvas')),
                   readout: R(viz.querySelector('output')), hits: []};
      for (const b of viz.querySelectorAll('button')) {
        const s = getComputedStyle(b, '::before'), r = b.getBoundingClientRect();
        const box = {l: r.left + px(s.left), t: r.top + px(s.top),
                     r: r.right - px(s.right), b: r.bottom - px(s.bottom)};
        box.w = box.r - box.l; box.h = box.b - box.t;
        out.hits.push({name: b.textContent.trim(), scene: b.getAttribute('data-scene'),
                       painted: R(b), box: box});
      }
      return out;
    }"""
    # Not under reduced motion, deliberately: there the run button reads Resume, and Pause
    # is the shorter of its two words and so the smaller of its two boxes. Measure the
    # worse one. Below 880 the plate sits under the hero and off the bottom of a 900 tall
    # window, so the row is scrolled to before anything is measured or pressed.
    for w in WIDTHS_HIT:
        p = br.new_page(viewport={'width': w, 'height': 900}, device_scale_factor=1)
        p.goto(URL + 'about.html')
        p.wait_for_timeout(400)
        p.evaluate("""() => document.querySelector('.viz[data-plate=about] .ctrl')
                              .scrollIntoView({block: 'center'})""")
        p.wait_for_timeout(150)
        m = p.evaluate(HITS)
        hs = [h['box'] for h in m['hits']]
        small = ['%s %.2f x %.2f' % (h['name'], h['box']['w'], h['box']['h'])
                 for h in m['hits'] if h['box']['w'] < 44 or h['box']['h'] < 44]
        hit = lambda a, b: (a['l'] < b['r'] - .01 and b['l'] < a['r'] - .01
                            and a['t'] < b['b'] - .01 and b['t'] < a['b'] - .01)
        clash = [(m['hits'][i]['name'], m['hits'][j]['name'])
                 for i in range(len(hs)) for j in range(i + 1, len(hs))
                 if hit(hs[i], hs[j])]
        near = [h['name'] for h in m['hits']
                if hit(h['box'], m['readout']) or hit(h['box'], m['canvas'])]
        note('%d: every button is at least 44 by 44 to press' % w, not small,
             '  ' + ', '.join('%s %.2f x %.2f painted, %.2f x %.2f pressed'
                              % (h['name'], h['painted']['w'], h['painted']['h'],
                                 h['box']['w'], h['box']['h']) for h in m['hits']))
        note('%d: no two pressable boxes overlap, and none reaches the board or the '
             'readout' % w, not clash and not near,
             '  gaps %s, and %.2f of clear board above them'
             % (['%.2f' % (hs[i + 1]['l'] - hs[i]['r']) for i in range(len(hs) - 1)],
                hs[0]['t'] - m['canvas']['b']))
        # Soup is the scenario the plate opens on, so the corner press has something to
        # change: Gliders first, on the word, then Soup from the far corner of its box.
        # Soup is picked by name rather than by position, because it is the button whose
        # box reaches past its word and a middle button's does not have to.
        p.click('.viz[data-plate=about] button[data-scene=gliders]')
        s = [h for h in m['hits'] if h['scene'] == 'soup'][0]
        p.mouse.click(s['box']['r'] - 2, s['box']['b'] - 2)
        p.wait_for_timeout(120)
        note('%d: a press on the corner of the box, clear of the word, lands' % w,
             p.get_attribute('.viz[data-plate=about] button[data-scene=soup]',
                             'aria-pressed') == 'true'
             and s['box']['r'] - 2 > s['painted']['r']
             and s['box']['b'] - 2 > s['painted']['b'],
             '  pressed %.2f, %.2f, which is %.2f right of the word and %.2f below it'
             % (s['box']['r'] - 2, s['box']['b'] - 2,
                s['box']['r'] - 2 - s['painted']['r'], s['box']['b'] - 2 - s['painted']['b']))
        p.close()

    # ---- the row at its worst ----------------------------------------------------
    # 881 is where the plate column is narrowest, and under reduced motion the run button
    # reads Resume, which is the wider of its two words: least room, most asked of it.
    # This is the measurement that says whether another scene button would fit.
    p = br.new_page(viewport={'width': 881, 'height': 900}, device_scale_factor=1,
                    reduced_motion='reduce')
    p.goto(URL + 'about.html')
    p.wait_for_timeout(400)
    p.evaluate("""() => document.querySelector('.viz[data-plate=about] .ctrl')
                          .scrollIntoView({block: 'center'})""")
    p.wait_for_timeout(150)
    m = p.evaluate(HITS)
    row = p.evaluate("""() => document.querySelector('.viz[data-plate=about] .ctrl')
                                .getBoundingClientRect().width""")
    hs = [h['box'] for h in m['hits']]
    painted = sum(h['painted']['w'] for h in m['hits'])
    gaps = ['%.2f' % (hs[i + 1]['l'] - hs[i]['r']) for i in range(len(hs) - 1)]
    slack = hs[-1]['l'] - hs[-2]['r']
    note('881, reduced motion: the row still has %.2f between the last scene button and '
         'the run button' % slack, slack >= 11.19,
         '  row %.0f wide, %d buttons painting %.2f: %s\n'
         '  boxes %s apart, and 11.19 is what two neighbours have always had'
         % (row, len(hs), painted,
            ', '.join('%s %.2f' % (h['name'], h['painted']['w']) for h in m['hits']),
            gaps))
    p.close()

    # ---- it stops on the way out and picks up on the way back -------------------
    p = br.new_page(viewport={'width': 1400, 'height': 900})
    p.goto(URL + 'home.html')
    p.click('.label nav a[href="about.html"]')
    p.wait_for_function('TB.running() === "about"')
    p.wait_for_timeout(700)
    p.click('.label nav a[href="contact.html"]')
    p.wait_for_timeout(400)
    note('the plate stops when you leave About', p.evaluate('TB.running()') is None)
    # Both readings are taken after the swap has settled. Taking the first one before the
    # click would have measured the round trip out to the browser as generations lost.
    a = int(p.text_content('.viz[data-plate=about] output'))
    ta = p.evaluate('TB.ticks.about')
    p.wait_for_timeout(1200)
    b = int(p.text_content('.viz[data-plate=about] output'))
    note('and nothing steps while you are away', p.evaluate('TB.ticks.about') == ta)
    note('and the generation it stopped on is still there', b == a,
         '  %d then %d, 1200ms apart' % (a, b))
    p.click('.label nav a[href="about.html"]')
    p.wait_for_function('TB.running() === "about"')
    p.wait_for_timeout(300)
    c = int(p.text_content('.viz[data-plate=about] output'))
    # It carries on rather than starting again, and the upper bound is what says so: 300ms
    # is about 18 frames and so about 9 steps since #67, and a plate that had started
    # again would be down at that.
    note('and it goes on from there rather than starting again', b < c < b + 25,
         '  %d while away, %d after 300ms back' % (b, c))
    note('one Life plate, mounted once',
         p.evaluate('TB.mounted().filter(k => k === "about").length') == 1)
    p.close()
    br.close()

for name, ok, detail in rows:
    print('%-4s %s' % ('ok' if ok else 'FAIL', name))
    if detail:
        print(detail)
print()
print('%d checks, %d failures' % (len(rows), len(fails)))
for f in fails:
    print('  ' + f)
sys.exit(1 if fails else 0)
