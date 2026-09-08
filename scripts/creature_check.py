"""The creature's acceptance check for #49: she shows, at one of her two sizes and never
at anything between them, clear of the credits and the nav, at every width and on every
page.

    python scripts/creature_check.py            # the table and a pass/fail line
    python scripts/creature_check.py --all      # every line of the generation, not just
                                                # the longest, through the bubble

Served over http rather than file://, headless Chromium, device_scale_factor 1, and the
longest line of the generation pinned into the bubble, so the widest and tallest bubble
the site can produce is the one measured. Nothing here writes to the tree.
"""
import sys, json, functools, http.server, socketserver, threading, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build_site

WIDTHS = [380, 420, 560, 640, 700, 881, 960, 1000, 1119, 1120, 1400]
PAGES = ['home', 'research', 'freelancing', 'about', 'contact']
LINES = [l['text'] for l in build_site.CREATURE_LINES]
LONGEST = max(LINES, key=len)
ALL = '--all' in sys.argv

H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.TCPServer(('127.0.0.1', 0), H)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

# The creature draws its line at random and types it in over a second, two seconds after
# the page opens. Waiting that out on 55 page loads is a minute of nothing, so the bubble
# is put into its finished state by hand instead: the same class the script adds, and the
# text set straight rather than typed. The measurement is of the box the CSS makes, and
# the box is the same either way.
SHOW = """(t) => {
  const say = document.getElementById('critsay');
  say.textContent = t;
  say.classList.add('on');
}"""

MEASURE = """() => {
  const L = document.querySelector('.label');
  const cr = document.querySelector('.credits');
  const nv = document.querySelector('.label nav');
  const sp = document.getElementById('critter');
  const bu = document.getElementById('critsay');
  const cs = getComputedStyle(L);
  const lr = L.getBoundingClientRect();
  const pad = {
    l: lr.left + parseFloat(cs.paddingLeft), r: lr.right - parseFloat(cs.paddingRight),
    t: lr.top + parseFloat(cs.paddingTop), b: lr.bottom - parseFloat(cs.paddingBottom)};
  const R = e => { const r = e.getBoundingClientRect();
                   return {x: r.left, y: r.top, w: r.width, h: r.height,
                           l: r.left, t: r.top, r: r.right, b: r.bottom}; };
  const vis = e => { const s = getComputedStyle(e), r = e.getBoundingClientRect();
                     return s.display !== 'none' && s.visibility !== 'hidden'
                            && parseFloat(s.opacity) > 0 && r.width > 0 && r.height > 0; };
  const hit = (a, b) => a.l < b.r - 0.01 && b.l < a.r - 0.01
                        && a.t < b.b - 0.01 && b.t < a.b - 0.01;
  // Where the credits actually paint, which is not where their box is: each credit is
  // white-space:nowrap, so a credit wider than the column paints outside it.
  const range = document.createRange();
  let paintR = R(cr).l, paintT = R(cr).b;
  for (const n of cr.childNodes) {
    range.selectNodeContents(n);
    for (const q of range.getClientRects()) {
      paintR = Math.max(paintR, q.right); paintT = Math.min(paintT, q.top);
    }
  }
  const gap = (box) => Math.max(box.l - paintR, paintT - box.b);
  const S = R(sp), B = R(bu), C = R(cr), N = R(nv);
  const cell = parseFloat(getComputedStyle(L).getPropertyValue('--crit-cell'));
  return {
    sprite: S, bubble: B, credits: C, nav: N, pad: pad,
    cell: cell, canvas: [sp.width, sp.height],
    creditsBreaks: getComputedStyle(cr.querySelector('i')).whiteSpace,
    spriteVisible: vis(sp), bubbleVisible: vis(bu),
    free: pad.r - C.r, paintFree: pad.r - paintR,
    bubbleHitsCredits: hit(B, C), bubbleHitsNav: hit(B, N),
    spriteAboveNav: N.t - S.b,
    bubbleInLabel: B.l >= pad.l - 0.01 && B.r <= pad.r + 0.01
                   && B.t >= pad.t - 0.01 && B.b <= pad.b + 0.01,
    spritePaintGap: gap(S), bubblePaintGap: gap(B),
  };
}"""


def check(m):
    c, s = m['cell'], m['sprite']
    return [
        ('1 both visible', m['spriteVisible'] and m['bubbleVisible']),
        # 14 cells by 12 of a whole number of pixels, and the canvas's own width and
        # height are that too, so one canvas pixel is one CSS pixel at either size.
        ('2 sprite %d x %d cells of %g' % (14, 12, c),
         c in (6, 8) and abs(s['w'] - 14 * c) < .01 and abs(s['h'] - 12 * c) < .01
         and m['canvas'] == [14 * c, 12 * c]),
        ('3 bubble clears credits and nav',
         not m['bubbleHitsCredits'] and not m['bubbleHitsNav']),
        ('4 sprite above the nav', m['spriteAboveNav'] > 0),
        ('5 bubble inside the label', m['bubbleInLabel']),
        # Not in the issue, and the one that a box test alone gets wrong: each credit is
        # nowrap, so a credit wider than its column paints outside it.
        ('6 credits paint clear of the sprite', m['spritePaintGap'] > 0),
        ('7 credits paint clear of the bubble', m['bubblePaintGap'] > 0),
    ]


rows, fails = [], []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for w in WIDTHS:
        p = br.new_page(viewport={'width': w, 'height': 900}, device_scale_factor=1)
        for name in PAGES:
            p.goto('http://127.0.0.1:%d/%s.html' % (PORT, name))
            p.wait_for_selector('#critter:not([hidden])')
            p.evaluate(SHOW, LONGEST)
            p.wait_for_timeout(260)     # the bubble's own .18s fade, waited out
            m = p.evaluate(MEASURE)
            bad = [n for n, ok in check(m) if not ok]
            rows.append((w, name, m, bad))
            fails += ['%d %s: %s' % (w, name, n) for n in bad]
            if ALL:
                for t in LINES:
                    p.evaluate(SHOW, t)
                    q = p.evaluate(MEASURE)
                    for n, ok in check(q):
                        if not ok:
                            fails.append('%d %s [%s]: %s' % (w, name, t[:24], n))
        p.close()
    br.close()

print('longest line, %d characters: %s' % (len(LONGEST), LONGEST))
print()
print('%-6s %-12s %5s %6s %6s  %-20s %-22s %6s %6s %6s  %s'
      % ('width', 'page', 'cell', 'free', 'paint', 'sprite', 'bubble',
         'navgap', 'sprgap', 'bubgap', 'nowrap'))
for w, name, m, bad in rows:
    s, b = m['sprite'], m['bubble']
    print('%-6d %-12s %5g %6.1f %6.1f  %-20s %-22s %6.2f %6.1f %6.1f %6s  %s'
          % (w, name, m['cell'], m['free'], m['paintFree'],
             '%.0f,%.0f %gx%g' % (s['x'], s['y'], s['w'], s['h']),
             '%.0f,%.0f %.0fx%.1f' % (b['x'], b['y'], b['w'], b['h']),
             m['spriteAboveNav'], m['spritePaintGap'], m['bubblePaintGap'],
             'kept' if m['creditsBreaks'] == 'nowrap' else 'BROKEN',
             'pass' if not bad else 'FAIL ' + '; '.join(bad)))
print()
print('%d rows, %d failures' % (len(rows), len(fails)))
for f in fails[:40]:
    print('  ' + f)
sys.exit(1 if fails else 0)
