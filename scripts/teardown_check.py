"""Nothing of the router's is left behind when a swap's animations end (#54, #63).

    python scripts/teardown_check.py                 # this tree
    python scripts/teardown_check.py <other-tree>    # this tree against another build

The defect this was written for is a frame of the live page wearing the outgoing page's
layout. The router used to animate the hero's height itself, on the live DOM, while a
view transition animated its snapshots over the top; the two ran on separate clocks and
the browser tore the snapshots down first, so for about one frame the page underneath
was still carrying `hero.style.height` from the page that had been left, and the
`grid-template-rows:100%` that went with it.

There is no view transition in the app any more (#63). The router fades the outgoing
section out over the incoming one with one animation on opacity, and travels the hero's
row with another (#60), both `Element.animate`, no fill, no inline style. So the
teardown frame is now the first animation frame on which no `.body` section has an
animation left, having had one on the frame before, and what is reported at that frame
and on every frame after it:

    hero      animations whose target is the live `.hero` element
    height    the inline height on it, '' when there is none
    rows      the inline grid-template-rows on it
    leaving   sections still carrying the `leaving` class
    shown     sections not hidden — exactly one, once the swap is over
    stale     frames after teardown carrying an inline style, a `leaving` section, or
              more or fewer than one shown section

What fails the check is anything but '', '', 0 leaving and 1 shown at teardown and
after. `hero` is reported and does not fail it on its own: the row's travel starts in
the same task as the fade and runs the same .18s, so it can be on its last frame when
the fade ends, which is a row a frame from its final height with the body riding it,
not a page wearing the height it left. The number is printed so a build that leaves an
animation running for longer than that says so.

Served over http, headless Chromium, device_scale_factor 1, reduced motion left at
no-preference so that the swap actually animates. Nothing here writes to the tree.
"""
import sys, functools, http.server, socketserver, threading, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OTHER = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None

WIDTHS = [380, 420, 560, 640, 881, 1000, 1120, 1400]
# Home is the leg with 145px of hero height between the two ends of it, so it is the leg
# the row's travel has anything to do on. The reverse and a flat leg go with it.
LEGS = [('home', 'about'), ('about', 'home'), ('research', 'freelancing')]

SAMPLE = """(href) => new Promise(done => {
  const hero = document.querySelector('.hero'), out = [], t0 = performance.now();
  (function f(){
    const t = performance.now() - t0;
    let body = 0, live = 0;
    for (const a of document.getAnimations()){
      const e = a.effect, el = e && e.target;
      if (!el || !el.matches) continue;
      if (el.matches('.body')) body++;
      else if (el === hero) live++;
    }
    const secs = Array.from(document.querySelectorAll('.body'));
    out.push([t, body, live, hero.style.height, hero.style.gridTemplateRows,
              secs.filter(s => s.classList.contains('leaving')).length,
              secs.filter(s => !s.hidden).length]);
    if (t < 900) requestAnimationFrame(f); else done(out);
  })();
  document.querySelector('.label nav a[href="' + href + '"]').click();
})"""

GO = """(href) => document.querySelector('.label nav a[href="' + href + '"]').click()"""


def serve(root):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    socketserver.TCPServer.allow_reuse_address = True
    s = socketserver.TCPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s.server_address[1]


def teardown(s):
    """The first frame with no body animation left, once there has been one."""
    ran = False
    for i, r in enumerate(s):
        if r[1]:
            ran = True
        elif ran:
            return i
    return None


def bad_frame(r):
    return bool(r[3] or r[4] or r[5] or r[6] != 1)


def measure(br, port):
    out = {}
    for w in WIDTHS:
        p = br.new_page(viewport={'width': w, 'height': 900}, device_scale_factor=1)
        p.goto('http://127.0.0.1:%d/home.html' % port)
        p.evaluate('() => document.fonts.ready')
        p.wait_for_timeout(400)
        for a, b in LEGS:
            p.evaluate(GO, a + '.html')
            p.wait_for_timeout(500)
            s = p.evaluate(SAMPLE, b + '.html')
            p.wait_for_timeout(200)
            i = teardown(s)
            if i is None:
                out[(w, a, b)] = None
                continue
            stale = sum(1 for r in s[i:] if bad_frame(r))
            out[(w, a, b)] = (round(s[i][0], 1), s[i][2], s[i][3], s[i][4], s[i][5],
                              s[i][6], stale, max((r[2] for r in s), default=0))
        p.close()
    return out


A = serve(ROOT)
with sync_playwright() as pw:
    br = pw.chromium.launch()
    mine = measure(br, A)
    theirs = measure(br, serve(OTHER)) if OTHER else None
    br.close()


def report(name, res):
    bad = []
    print(name)
    print()
    print('%-6s %-10s %-12s %9s %5s %8s %6s %8s %6s %6s %5s'
          % ('width', 'from', 'to', 'teardown', 'hero', 'height', 'rows', 'leaving',
             'shown', 'stale', 'peak'))
    for k, v in res.items():
        if v is None:
            print('%-6d %-10s %-12s   no swap animated' % k)
            bad.append('%d %s -> %s: no swap animated' % k)
            continue
        t, live, h, rows, leaving, shown, stale, peak = v
        ok = not (h or rows or leaving or shown != 1 or stale)
        print('%-6d %-10s %-12s %8.1fms %5d %8s %6s %8d %6d %6d %5d%s'
              % (k[0], k[1], k[2], t, live, repr(h), repr(rows), leaving, shown, stale,
                 peak, '' if ok else '   FAIL'))
        if not ok:
            bad.append('%d %s -> %s: height %r, rows %r, %d leaving, %d shown, %d stale '
                       'frame(s), hero %d' % (k[0], k[1], k[2], h, rows, leaving, shown,
                                              stale, live))
    print()
    return bad


bad = report('this tree', mine)
if theirs:
    report('other tree: %s' % OTHER, theirs)
print('%d widths, %d legs each, %d failures' % (len(WIDTHS), len(LEGS), len(bad)))
for b in bad:
    print('  ' + b)
sys.exit(1 if bad else 0)
