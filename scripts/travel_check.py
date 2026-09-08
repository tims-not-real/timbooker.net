"""What the label's bottom edge actually does during a swap, read off painted pixels.

    python scripts/travel_check.py                 # this tree
    python scripts/travel_check.py <other-tree>    # this tree against another build

`getBoundingClientRect` cannot answer this once the transition owns the movement (#54).
The live element is meant to snap on the frame the DOM changes, so the rect reports two
values whether the snapshot is travelling correctly or not moving at all. So this reads
the frames the compositor produced.

A CDP screencast is started, the click is made, and every frame the browser paints is
kept with its own timestamp. In each frame the label's blue is followed down a column
inside its right padding, where no text or creature can fall, and the last row still
blue is the bottom edge. The first row of body text under it is found the same way, as
the topmost row below that edge carrying anything more than 40 of 255 away from the page
ground, which is above the grain and far below any glyph.

Everything is slowed by the same factor so that a 180ms swap is sampled at enough frames
to tell a ramp from a step: the transition's own animations through an
`animation-duration` override, and anything the router animates itself through a patched
`Element.prototype.animate`. Both by SLOW, so nothing is re-timed relative to anything
else.

What it prints per leg: how many distinct edge positions were painted, the largest step
between two consecutive frames, and the total travel. A jump is two positions and one
step the size of the whole distance. A travel is many positions and no step much larger
than distance/frames. The gap between the label's bottom edge and the first line of body
text is printed with it: it is constant when the body moves with the label, and it is
not when the body trails.

Served over http, headless Chromium, device_scale_factor 1. Nothing here writes to the
tree.
"""
import sys, io, base64, functools, http.server, socketserver, threading, pathlib
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OTHER = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None

SLOW = 10
WIDTH, HEIGHT = 1400, 900
# Home is the only page whose label is a different height, so it is the only leg that
# has anything to travel. Both directions, and one leg between two equal labels as the
# control that should not move at all.
LEGS = [('home', 'about'), ('about', 'home'), ('research', 'about')]

# Timings the transition and the router both live by, multiplied by SLOW. The duration
# override cannot resurrect an animation that is off: `animation:none` sets the name to
# none, and a duration without a name still animates nothing.
SLOWCSS = """
::view-transition-group(*),::view-transition-old(*),::view-transition-new(*){
  animation-duration:%dms !important;
}
""" % (180 * SLOW)
SLOWJS = """
(function(){ var a = Element.prototype.animate;
  Element.prototype.animate = function(k, o){
    if (typeof o === 'number') o = o * %d;
    else if (o && o.duration) o = Object.assign({}, o, {duration: o.duration * %d});
    return a.call(this, k, o); }; })();
""" % (SLOW, SLOW)

# The column to follow the blue down, and the band of the page the body's first line is
# looked for in. Both are read off the resting page rather than guessed.
PROBE = """() => {
  const L = document.querySelector('.label'), r = L.getBoundingClientRect();
  const cs = getComputedStyle(L);
  return {x: Math.round(r.right - parseFloat(cs.paddingRight) / 2),
          top: Math.round(r.top + 4), bottom: Math.round(r.bottom),
          left: Math.round(r.left), right: Math.round(r.right)};
}"""

GO = """(href) => document.querySelector('.label nav a[href="' + href + '"]').click()"""


def serve(root):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    socketserver.TCPServer.allow_reuse_address = True
    s = socketserver.TCPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s.server_address[1]


def near(a, b, tol):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol and abs(a[2] - b[2]) <= tol


def read(img, probe):
    """(bottom edge of the blue, top of the first line of body text) in this frame."""
    px = img.load()
    x, top = probe['x'], probe['top']
    blue = px[x, top]
    edge = top
    for y in range(top, img.height):
        if near(px[x, y], blue, 24):
            edge = y
        elif y - edge > 6:              # six rows clear of it, so grain cannot end it
            break
    ground = px[probe['right'] + 6, min(img.height - 1, edge + 20)] \
        if probe['right'] + 6 < img.width else (0, 0, 0)
    body = None
    for y in range(edge + 2, min(img.height, edge + 400)):
        n = 0
        for xx in range(probe['left'] + 4, probe['right'], 3):
            p = px[xx, y]
            if max(abs(p[0] - ground[0]), abs(p[1] - ground[1]),
                   abs(p[2] - ground[2])) > 40:
                n += 1
                if n > 2:
                    break
        if n > 2:
            body = y
            break
    return edge, body


def leg(br, port, a, b):
    p = br.new_page(viewport={'width': WIDTH, 'height': HEIGHT}, device_scale_factor=1)
    p.add_init_script(SLOWJS)
    p.goto('http://127.0.0.1:%d/home.html' % port)
    p.evaluate('() => document.fonts.ready')
    p.wait_for_timeout(600)
    p.add_style_tag(content=SLOWCSS)
    # The plates and the creature are animations of their own, and a frame of one is not
    # a frame of the swap. Held still so that every frame the screencast returns is one
    # the transition asked for.
    p.add_style_tag(content='canvas,#critsay,#critter{visibility:hidden !important}')
    if a != 'home':
        p.evaluate(GO, a + '.html')
        p.wait_for_timeout(400 * SLOW)
    probe = p.evaluate(PROBE)

    frames = []
    cdp = p.context.new_cdp_session(p)

    def got(ev):
        frames.append((ev['metadata'].get('timestamp', 0), ev['data']))
        try:
            cdp.send('Page.screencastFrameAck', {'sessionId': ev['sessionId']})
        except Exception:
            pass

    cdp.on('Page.screencastFrame', got)
    cdp.send('Page.startScreencast', {'format': 'png', 'everyNthFrame': 1,
                                      'maxWidth': WIDTH, 'maxHeight': HEIGHT})
    p.wait_for_timeout(300)
    frames.clear()
    p.evaluate(GO, b + '.html')
    p.wait_for_timeout(300 * SLOW)
    cdp.send('Page.stopScreencast')
    p.wait_for_timeout(50)

    seen = []
    for t, data in frames:
        img = Image.open(io.BytesIO(base64.b64decode(data))).convert('RGB')
        if img.size != (WIDTH, HEIGHT):
            img = img.resize((WIDTH, HEIGHT))
        seen.append((t,) + read(img, probe))
    p.close()
    return seen


def run(port, label):
    out = {}
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for a, b in LEGS:
            out[(a, b)] = leg(br, port, a, b)
        br.close()
    return out


def report(name, res):
    print('%s, %dx%d, everything slowed %dx' % (name, WIDTH, HEIGHT, SLOW))
    print()
    print('%-11s %-11s %7s %9s %8s %9s %9s'
          % ('from', 'to', 'frames', 'positions', 'travel', 'max step', 'gap min/max'))
    for (a, b), s in res.items():
        e = [r[1] for r in s]
        g = [r[2] - r[1] for r in s if r[2] is not None]
        if not e:
            print('%-11s %-11s   no frames' % (a, b))
            continue
        step = max((abs(e[i] - e[i - 1]) for i in range(1, len(e))), default=0)
        print('%-11s %-11s %7d %9d %8d %9d   %d / %d'
              % (a, b, len(e), len(set(e)), abs(e[-1] - e[0]), step,
                 min(g) if g else -1, max(g) if g else -1))
        print('           edges: ' + ' '.join(str(v) for v in e))
    print()


A = serve(ROOT)
report('this tree', run(A, 'this tree'))
if OTHER:
    report('other tree: %s' % OTHER, run(serve(OTHER), 'other'))
