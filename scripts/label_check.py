"""The label's acceptance check for #51: it does not move on a mobile tab switch.

Written for PR #52, which guarded the symptom below 880, and kept for #54, which removed
the cause: nothing animates the live page during a swap any more, so the label is static
at every width rather than at the ones a breakpoint names.

    python scripts/label_check.py                 # this tree
    python scripts/label_check.py <other-tree>    # this tree against another build

The router only exists in the app document, so every leg is a click inside `home.html`
rather than a page load: for each ordered pair of the five pages it clicks to the first,
waits for the swap to settle, then samples the label's bounding rect on every animation
frame from the click to 500ms after it. The first sample is taken in the same task as the
click, before the browser has laid anything out, so it is the resting frame the rest are
measured against.

Below the stylesheet's one breakpoint the hero is a single column and the label must not
move at all: height and top identical on every frame, and the number reported is the
worst deviation from that resting frame over every leg. Above it the label is two heights
and what is reported is which two, so a build that changes the geometry says so.

Which widths count as mobile is not a list kept here: the hero is asked how many columns
it has been given, so the stylesheet owns the breakpoint and this reads it back.

Reduced motion is left at no-preference on purpose — under `reduce` the router takes the
branch with no view transition and no height animation, so there would be nothing to
measure. Served over http, headless Chromium, device_scale_factor 1. Nothing here writes
to the tree.
"""
import sys, functools, http.server, socketserver, threading, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OTHER = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None

WIDTHS = [380, 420, 560, 640, 879, 881, 1000, 1120, 1400]
PAGES = ['home', 'research', 'freelancing', 'about', 'contact']
LEGS = [(a, b) for a in PAGES for b in PAGES if a != b]

# One task: start the recorder, then click. The sample already pushed is the frame before
# the click, which is the resting label every later frame is compared against.
SAMPLE = """(href) => new Promise(done => {
  const L = document.querySelector('.label'), s = [], t0 = performance.now();
  (function f(){
    const r = L.getBoundingClientRect(), t = performance.now() - t0;
    s.push([t, r.height, r.top]);
    if (t < 500) requestAnimationFrame(f); else done(s);
  })();
  document.querySelector('.label nav a[href="' + href + '"]').click();
})"""

GO = """(href) => document.querySelector('.label nav a[href="' + href + '"]').click()"""

COLS = """() => getComputedStyle(document.querySelector('.hero'))
                   .gridTemplateColumns.split(' ').length"""


def serve(root):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    socketserver.TCPServer.allow_reuse_address = True
    s = socketserver.TCPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s.server_address[1]


def measure(br, port):
    """{width: (cols, {leg: (h0, h1, devH, devTop, peak, frames)})}"""
    out = {}
    for w in WIDTHS:
        p = br.new_page(viewport={'width': w, 'height': 900}, device_scale_factor=1)
        p.goto('http://127.0.0.1:%d/home.html' % port)
        p.evaluate('() => document.fonts.ready')
        p.wait_for_timeout(400)
        cols = p.evaluate(COLS)
        legs = {}
        for a, b in LEGS:
            p.evaluate(GO, a + '.html')         # get onto the page the leg starts from
            p.wait_for_timeout(400)
            s = p.evaluate(SAMPLE, b + '.html')
            p.wait_for_timeout(200)
            h0, t0 = s[0][1], s[0][2]
            legs[(a, b)] = (h0, s[-1][1],
                            max(abs(r[1] - h0) for r in s),
                            max(abs(r[2] - t0) for r in s),
                            max(r[1] for r in s), len(s))
        out[w] = (cols, legs)
        p.close()
    return out


A = serve(ROOT)
B = serve(OTHER) if OTHER else None
with sync_playwright() as pw:
    br = pw.chromium.launch()
    mine = measure(br, A)
    theirs = measure(br, B) if B else None
    br.close()

fails = []
MOBILE = [w for w in WIDTHS if mine[w][0] == 1]
DESK = [w for w in WIDTHS if mine[w][0] != 1]

print('one column, so the label holds still. the hero has one track at %s'
      % ', '.join(str(w) for w in MOBILE))
print()
print('%-6s %6s %6s %10s %10s' % ('width', 'frames', 'legs', 'max |dh|', 'max |dtop|')
      + ('%12s %12s  ' % ('other |dh|', 'other |dtop|') if theirs else '  ') + 'result')
for w in MOBILE:
    legs = mine[w][1]
    dh = max(v[2] for v in legs.values())
    dt = max(v[3] for v in legs.values())
    if dh or dt:
        fails.append('%d: the label moved, max |dh| %.2f, max |dtop| %.2f' % (w, dh, dt))
    line = ('%-6d %6d %6d %10.2f %10.2f'
            % (w, sum(v[5] for v in legs.values()), len(legs), dh, dt))
    if theirs:
        o = theirs[w][1]
        line += '%12.2f %12.2f  ' % (max(v[2] for v in o.values()),
                                     max(v[3] for v in o.values()))
    print(line + ('  pass' if not (dh or dt) else '  FAIL'))
    # The worst legs, this tree and the other one, resting height -> peak -> where it
    # ended, so a build that balloons says by how much and on which swap.
    for a, b in sorted(LEGS, key=lambda k: -(theirs or mine)[w][1][k][2])[:3]:
        v, o = legs[(a, b)], theirs[w][1][(a, b)] if theirs else None
        print('       %-11s -> %-11s %8.2f -> %8.2f -> %8.2f'
              % (a, b, v[0], v[4], v[1])
              + ('   other %8.2f -> %8.2f -> %8.2f' % (o[0], o[4], o[1]) if o else ''))

print()
print('two columns, so the label is two heights, and here is which two')
print()
print('%-6s %-12s %-12s %9s %9s %8s' % ('width', 'from', 'to', 'h0', 'h1', 'travel')
      + ('%10s %8s  result' % ('other', 'delta') if theirs else ''))
for w in DESK:
    for a, b in LEGS:
        v = mine[w][1][(a, b)]
        line = ('%-6d %-12s %-12s %9.2f %9.2f %8.2f'
                % (w, a, b, v[0], v[1], v[1] - v[0]))
        if theirs:
            u = theirs[w][1][(a, b)]
            d = (v[1] - v[0]) - (u[1] - u[0])
            line += '%10.2f %8.2f  %s' % (u[1] - u[0], d, 'same' if not d else 'DIFFERS')
            if d:
                fails.append('%d %s -> %s: travel %.2f, other tree %.2f'
                             % (w, a, b, v[1] - v[0], u[1] - u[0]))
        print(line)

print()
print('%d widths, %d legs each, %d failures' % (len(WIDTHS), len(LEGS), len(fails)))
for f in fails[:40]:
    print('  ' + f)
sys.exit(1 if fails else 0)
