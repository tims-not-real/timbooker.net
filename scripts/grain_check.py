"""What the paper tooth does to the label during a swap.

    python scripts/grain_check.py                 # this tree
    python scripts/grain_check.py <other-tree>    # this tree against another build

The grain is a fixed full-viewport layer on `body::after` with a blend mode, and it
composes badly with view transitions. Two things can happen to it during a swap, from two
different causes, so they are measured apart.

**Level.** A named element is lifted out of the root, and `body::after` stays in the root,
so it cannot reach anything that has been lifted. Whatever is captured then loses that
layer for the length of the swap and gets it back at the end. `step` is that: the band's
mean level at rest minus its mean level mid-swap. design-goals.md records the same
mechanism under "The plate stopped flashing 2026-09-05", where it measured a drop of 9 to
10 of 255 on the cross-document path and was reported from the live site.

**Texture.** A snapshot told to fill a group whose height is animating is squeezed, and any
grain inside it is resampled and flattens. `shimmer` is the mean absolute difference
between one painted frame and the one before it, which in these bands is the grain moving
and nothing else, because they hold no type and no edge. `amplitude` is the grain's own
size in the same band, so the other two numbers have something to be a fraction of.

This build captures the label, so it reads a step of 4.29 and a shimmer of 1.17 mean and
4.48 peak, against a grain whose amplitude in that band is 2.36. On `main`, where the label
is not captured, every number here is 0.00. That difference is why this branch is parked.

Three bands: the label's blue, the plate column and the page ground outside the wrap. The
last two are the control — whatever is done to the label, they must not move, and a build
that fixes the label by veiling the rest of the page says so here.

1400x900, home -> About, everything slowed ten times, canvases held still, over http,
headless Chromium, device_scale_factor 1. Nothing here writes to the tree.
"""
import io, base64, functools, http.server, socketserver, threading, pathlib, sys
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OTHER = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None

SLOW = 10
W, H = 1400, 900
# The blue band has to be blue on both pages, and the shorter label is what constrains it:
# About's credits sit 145px higher than home's, so a band chosen against home alone catches
# the left edge of them on About and reads 0.37 of a grey level that has nothing to do with
# the grain. It is above the credits at either height and right of their 44ch measure.
BANDS = {'label blue': (540, 190, 800, 330),
         'plate column': (780, 120, 1100, 400),
         'page ground': (1300, 420, 1390, 800)}

SLOWCSS = ("::view-transition-group(*),::view-transition-old(*),::view-transition-new(*)"
           "{animation-duration:%dms !important}" % (180 * SLOW))
SLOWJS = """(function(){ var a = Element.prototype.animate;
  Element.prototype.animate = function(k, o){
    if (o && o.duration) o = Object.assign({}, o, {duration:o.duration * %d});
    return a.call(this, k, o); }; })();""" % SLOW
GO = """(href) => document.querySelector('.label nav a[href="' + href + '"]').click()"""


def serve(root):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    socketserver.TCPServer.allow_reuse_address = True
    s = socketserver.TCPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s.server_address[1]


def band(img, box):
    return list(img.crop(box).convert('L').getdata())


def mad(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / float(len(a))


def mean(v):
    return sum(v) / float(len(v))


def run(port):
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        p = br.new_page(viewport={'width': W, 'height': H}, device_scale_factor=1)
        p.add_init_script(SLOWJS)
        p.goto('http://127.0.0.1:%d/home.html' % port)
        p.evaluate('() => document.fonts.ready')
        p.wait_for_timeout(600)
        p.add_style_tag(content=SLOWCSS)
        p.add_style_tag(content='canvas,#critsay,#critter{visibility:hidden !important}')
        img = Image.open(io.BytesIO(p.screenshot())).convert('RGB')
        rest = {k: band(img, v) for k, v in BANDS.items()}
        frames = []
        cdp = p.context.new_cdp_session(p)

        def got(ev):
            frames.append(ev['data'])
            try:
                cdp.send('Page.screencastFrameAck', {'sessionId': ev['sessionId']})
            except Exception:
                pass

        cdp.on('Page.screencastFrame', got)
        cdp.send('Page.startScreencast', {'format': 'png', 'everyNthFrame': 1,
                                          'maxWidth': W, 'maxHeight': H})
        p.wait_for_timeout(300)
        frames.clear()
        p.evaluate(GO, 'about.html')
        p.wait_for_timeout(300 * SLOW)
        cdp.send('Page.stopScreencast')
        p.wait_for_timeout(80)
        out = []
        for d in frames:
            f = Image.open(io.BytesIO(base64.b64decode(d))).convert('RGB')
            if f.size != (W, H):
                f = f.resize((W, H))
            out.append({k: band(f, v) for k, v in BANDS.items()})
        br.close()
    return rest, out


def report(name, rest, frames):
    print('%s, %d painted frames' % (name, len(frames)))
    if len(frames) < 6:
        print('   too few frames to read')
        return
    for k in BANDS:
        f = [x[k] for x in frames]
        shim = [mad(f[i], f[i - 1]) for i in range(1, len(f))]
        lv = sorted(mean(y) for y in f[2:-2])
        r0, m = mean(rest[k]), lv[len(lv) // 2]
        amp = sum(abs(x - r0) for x in rest[k]) / float(len(rest[k]))
        print('   %-13s shimmer max %5.2f mean %5.2f   amplitude %5.2f   '
              'level rest %6.2f mid-swap %6.2f   step %5.2f'
              % (k, max(shim), mean(shim), amp, r0, m, r0 - m))
    print()


rest, frames = run(serve(ROOT))
report('this tree', rest, frames)
if OTHER:
    rest, frames = run(serve(OTHER))
    report('other tree: %s' % OTHER, rest, frames)
