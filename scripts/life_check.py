"""The acceptance check for the Game of Life plate on About (#53).

    python scripts/life_check.py          # the tables and a pass/fail line

The first thing it checks is the rule, because everything else on the plate is a
consequence of it and a plate running the wrong rule is a plate running a different
model. B3/S23 is checked twice over: once exhaustively, all 512 neighbourhoods against
both states of the cell in the middle, and once against a published figure — an
R-pentomino stabilises at generation 1103 with a population of 116, which is the number
every Life reference gives and the number a wrong rule cannot land on by accident.

It runs the shipped code, not a copy of it. `TBlife(n)` is the whole of the rule and it
takes the size of its board as an argument, so the check builds a 640-square board of
its own and runs the R-pentomino on that, well clear of the 92 the plate uses. Nothing
here writes to the tree; the site is served over http, because on file:// the
self-hosted fonts are blocked by CORS and fill the console with failures that have
nothing to do with the page.
"""
import sys, functools, http.server, socketserver, threading, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
WIDTHS = [380, 420, 881, 1120, 1400]
BIG = 640                       # the R-pentomino's own board: see the note at RULE_R

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
    p.close()

    # ---- the plate: the two scenarios -------------------------------------------
    board_n = 0
    for scene in ('gliders', 'soup'):
        p = br.new_page(viewport={'width': 1400, 'height': 900})
        p.goto(URL + 'about.html')
        p.wait_for_function('TB.running() === "about"')
        p.click('.viz[data-plate=about] button[data-scene=%s]' % scene)
        board_n = p.evaluate('document.querySelector(".viz[data-plate=about] canvas").width')
        tr = p.evaluate(TRACE, 900)
        p.close()
        gens = [t[0] for t in tr]
        pops = [t[1] for t in tr]
        n = board_n
        peak = max(pops)
        restarts = sum(1 for i in range(1, len(gens)) if gens[i] < gens[i - 1])
        note('%s: the counter advances every painted frame' % scene,
             all(gens[i] - gens[i - 1] in (1, ) for i in range(1, len(gens))
                 if gens[i] > gens[i - 1]),
             '  %d frames, generations %d to %d, peak population %d (%.1f%% of the '
             'board), settles and runs again %d times'
             % (len(gens), gens[0], max(gens), peak, 100.0 * peak / (n * n), restarts))
        # Neither of the two ways a Life board can stop being worth looking at: it never
        # empties, and it thins to ash rather than filling up. The soup starts at half the
        # board by construction, so the test is where it ends, not how high it peaked.
        note('%s: the board neither empties nor fills' % scene,
             min(pops) > 0 and pops[-1] < 0.15 * n * n,
             '  population %d at the first frame, %d at the last, low water %d, of %d'
             % (pops[0], pops[-1], min(pops), n * n))

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
    # is about 18 frames, and a plate that had started again would be down at that.
    note('and it goes on from there rather than starting again', b < c < b + 40,
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
