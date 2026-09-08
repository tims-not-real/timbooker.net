"""Nothing of the router's is still running when the snapshots come down (#54).

    python scripts/teardown_check.py                 # this tree
    python scripts/teardown_check.py <other-tree>    # this tree against another build

The defect this checks for is a frame of the live page wearing the outgoing page's
layout. The router used to animate the hero's height itself, on the live DOM, while the
view transition was animating its snapshots over the top; the two ran on separate clocks
and the browser tore the snapshots down first, so for about one frame the page underneath
was still carrying `hero.style.height` from the page that had been left, and the
`grid-template-rows:100%` that went with it.

Every animation frame from the click is sampled. The teardown frame is the first one on
which no `::view-transition-*` pseudo-element has an animation left, having had one on
the frame before. What is reported at that frame, and on every frame after it:

    live      animations whose target is the live `.hero` element
    height    the inline height on it, '' when there is none
    rows      the inline grid-template-rows on it
    stale     frames after teardown still carrying either inline style

A build that leaves the movement to the transition reports 0, '', '' and 0 at every
width. Served over http, headless Chromium, device_scale_factor 1, reduced motion left
at no-preference so that the transition actually runs. Nothing here writes to the tree.
"""
import sys, functools, http.server, socketserver, threading, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OTHER = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None

WIDTHS = [380, 420, 560, 640, 881, 1000, 1120, 1400]
# Home is the leg with 145px of hero height between the two ends of it, so it is the leg
# the height animation had anything to do on. The reverse and a flat leg go with it.
LEGS = [('home', 'about'), ('about', 'home'), ('research', 'freelancing')]

SAMPLE = """(href) => new Promise(done => {
  const hero = document.querySelector('.hero'), out = [], t0 = performance.now();
  (function f(){
    const t = performance.now() - t0;
    let vt = 0, live = 0;
    for (const a of document.getAnimations()){
      const e = a.effect;
      if (e && e.pseudoElement && e.pseudoElement.indexOf('view-transition') >= 0) vt++;
      else if (e && e.target === hero) live++;
    }
    out.push([t, vt, live, hero.style.height, hero.style.gridTemplateRows]);
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
    """The first frame with no transition pseudo left, once there has been one."""
    ran = False
    for i, r in enumerate(s):
        if r[1]:
            ran = True
        elif ran:
            return i
    return None


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
            stale = sum(1 for r in s[i:] if r[3] or r[4])
            out[(w, a, b)] = (round(s[i][0], 1), s[i][2], s[i][3], s[i][4], stale,
                              max((r[2] for r in s), default=0))
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
    print('%-6s %-10s %-12s %9s %6s %12s %8s %6s %8s'
          % ('width', 'from', 'to', 'teardown', 'live', 'height', 'rows', 'stale', 'peak'))
    for k, v in res.items():
        if v is None:
            print('%-6d %-10s %-12s   no transition ran' % k)
            bad.append('%d %s -> %s: no transition' % k)
            continue
        t, live, h, rows, stale, peak = v
        ok = not (live or h or rows or stale)
        print('%-6d %-10s %-12s %8.1fms %6d %12s %8s %6d %8d%s'
              % (k[0], k[1], k[2], t, live, repr(h), repr(rows), stale, peak,
                 '' if ok else '   FAIL'))
        if not ok:
            bad.append('%d %s -> %s: live %d, height %r, rows %r, %d stale frame(s)'
                       % (k[0], k[1], k[2], live, h, rows, stale))
    print()
    return bad


bad = report('this tree', mine)
if theirs:
    report('other tree: %s' % OTHER, theirs)
print('%d widths, %d legs each, %d failures' % (len(WIDTHS), len(LEGS), len(bad)))
for b in bad:
    print('  ' + b)
sys.exit(1 if bad else 0)
