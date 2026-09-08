"""Every page against another build of the site, pixel for pixel.

    python scripts/pixel_diff.py <other-tree> [width ...]

The canvases are hidden on both sides: the creature and the plates are animations, and
two screenshots of an animation are never the same picture. The bubble is hidden with
them — it draws a random line of the generation on every load, and #49 moved it on
purpose, so it is the thing under test rather than part of the ground it is tested
against. What is left is the whole of the static page.

The grain on `body::after` is `position:fixed`, so it is locked to the viewport and a
diff of two full-page screenshots taken at different scroll positions reports the grain
sliding rather than the page changing. Both sides are parked at the top and the page
height is reported with the count, so there is no offset to correct.

`Math.random` is replaced with a seeded generator on both sides. Two things on the site
open somewhere random: the chemistry dish's fader (#25), whose knob and readout are not
canvas and so survive the canvases being hidden, and the creature's line. Left alone
they put a few thousand pixels of noise into a diff of the build against itself.
"""
import sys, functools, http.server, socketserver, threading, pathlib, io
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent.parent
OTHER = pathlib.Path(sys.argv[1]).resolve()
WIDTHS = [int(a) for a in sys.argv[2:]] or [1400, 1120]
PAGES = ['home', 'research', 'freelancing', 'about', 'contact']
HIDE = 'canvas, #critsay{visibility:hidden !important}'
SEED = """
  (function(){ var s = 12345;
    Math.random = function(){ s = (s * 1103515245 + 12345) % 2147483648;
                              return s / 2147483648; }; })();
"""


def serve(root):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    socketserver.TCPServer.allow_reuse_address = True
    s = socketserver.TCPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s.server_address[1]


A, B = serve(HERE), serve(OTHER)


def shoot(br, port, name, w):
    p = br.new_page(viewport={'width': w, 'height': 900}, device_scale_factor=1,
                    reduced_motion='reduce')
    p.add_init_script(SEED)
    p.goto('http://127.0.0.1:%d/%s.html' % (port, name))
    p.add_style_tag(content=HIDE)
    # The faces are same-origin and swap in, so a shot taken before they land catches
    # Helvetica in one or two lines of the note and reports it as a change.
    p.evaluate('() => document.fonts.ready')
    p.wait_for_timeout(1400)
    p.evaluate('() => window.scrollTo(0, 0)')
    png = p.screenshot(full_page=True)
    p.close()
    return Image.open(io.BytesIO(png)).convert('RGB')


worst = 0
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for w in WIDTHS:
        for name in PAGES:
            a, b = shoot(br, A, name, w), shoot(br, B, name, w)
            if a.size != b.size:
                print('%-6d %-12s size %s vs %s' % (w, name, a.size, b.size))
                worst = max(worst, 1)
                continue
            d = ImageChops.difference(a, b)
            box = d.getbbox()
            n = sum(1 for px in d.getdata() if px != (0, 0, 0))
            peak = max(max(px) for px in d.getdata())
            worst = max(worst, n)
            print('%-6d %-12s %s  %8d differing pixels, peak %3d%s'
                  % (w, name, a.size, n, peak, '' if not box else '  bbox %s' % (box,)))
    br.close()
print('worst: %d differing pixels' % worst)
sys.exit(1 if worst else 0)
