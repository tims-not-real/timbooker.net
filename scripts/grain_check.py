"""What the label's grain does while the label is captured.

    python scripts/grain_check.py                 # this tree
    python scripts/grain_check.py <other-tree>    # this tree against another build

Two things can happen to the paper tooth during a swap, and they are different things
with different causes, so they are measured apart.

**Level.** A named element is lifted out of the root, and the fixed grain on `body::after`
stays in the root, so it cannot reach anything that has been lifted. The blue then loses
that layer for the length of the swap and steps back at the end. This is what Tim reported
from the live site on the cross-document path — "the colour of the blue plate flashes a
little bit, like it goes dim and then bright again" — where it measured 9 to 10 of 255.
`step` is that: the band's mean level at rest minus its mean level mid-swap.

**Texture.** The label's own snapshot is told to fill its group, so while the group's
height animates the picture inside it is squeezed and its two grain layers are resampled
with it. `shimmer` is the mean absolute difference between one painted frame and the one
before it, which is the grain moving and nothing else, because the bands hold no type and
no edge — every part of the label that has one has been lifted out by a name of its own.
`amplitude` is the grain's own size in the same band, so the other two numbers have
something to be a fraction of.

Three bands: the label's blue, the plate column and the page ground outside the wrap. The
last two are the control — whatever is done to the label, they should not move, and a
build that fixes the label by veiling the rest of the page says so here.

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
# The blue band is on both pages, below the stack and right of the credits' 44ch measure,
# so no named part of the label ever covers it.
BANDS = {'label blue': (520, 250, 700, 430),
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
