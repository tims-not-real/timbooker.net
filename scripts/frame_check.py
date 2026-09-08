"""Every compositor frame of a swap, per band, against the frame before the click (#59).

    python scripts/frame_check.py                        # router legs, headless
    python scripts/frame_check.py --headed               # the same on this machine's GPU
    python scripts/frame_check.py --headed --cross       # cross-document: load a.html, click b
    python scripts/frame_check.py <other-tree> ...       # this tree against another build

A screencast over CDP cannot answer this question: it encodes a PNG per frame and drops
whatever it cannot keep up with, which at real speed is most of a 180ms swap. The tracing
category `disabled-by-default-devtools.screenshot` is what the DevTools performance panel
uses, and it records one small JPEG for every frame the compositor presents, so a flash
that lasts one frame is in the record. That is what this reads.

Four bands are measured on every frame, in grey levels of 255: the label's blue above
the credits at either label height, the plate column, the page ground right of the wrap,
and the gap left of it. A frame is flagged when the label, the ground or the left gap is
more than `--flag` (1.5) away from both the resting frame and the settled one, which is
what a veil, a lost grain or a missing snapshot looks like and what a cross-fade does
not. The plate and the body are printed and never flagged: they change on every swap by
design.

`--cross` loads the standalone document named first and clicks from it, which is the
cross-document path a reader takes who arrived anywhere but home. `--dpr` sets the
device scale factor, because this machine draws at 1.5 and the label's paper is not the
same picture at 1. `--canvas all` leaves the creature and her bubble visible; the
default hides them, because her gesture across a swap falls straight through the label
band and reads as a flash that is not one.

Headless Chromium never shows the flash this was written for, and says so in #59. Run it
headed for the answer and headless for the control. Nothing here writes to the tree.
"""
import io, base64, functools, http.server, socketserver, threading, pathlib, argparse
from PIL import Image
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument('other', nargs='?', default='')
ap.add_argument('--headed', action='store_true')
ap.add_argument('--cross', action='store_true')
ap.add_argument('--legs', default='home:about,about:home,research:about,freelancing:home')
ap.add_argument('--runs', type=int, default=3)
ap.add_argument('--canvas', default='live', choices=['hide', 'live', 'all'])
ap.add_argument('--dpr', type=float, default=1)
ap.add_argument('--width', type=int, default=1400)
ap.add_argument('--flag', type=float, default=1.5)
ap.add_argument('--verbose', action='store_true', help='print every frame, not only flagged')
A = ap.parse_args()

ROOT = pathlib.Path(__file__).resolve().parent.parent
OTHER = pathlib.Path(A.other).resolve() if A.other else None
W, H = A.width, 900
# Headed Chromium on Windows has a 15px scrollbar, which shifts the wrap 7.5px left and
# puts a light strip at the right edge, so the ground band stops well short of it.
BANDS = {'label': (540, 190, 800, 330),
         'plate': (780, 120, 1100, 400),
         'ground': (1290, 420, 1370, 800),
         'body': (160, 700, 700, 880),
         'lgap': (20, 100, 120, 800)}
HIDE = {'hide': 'canvas,#critsay,#critter', 'live': '#critsay,#critter', 'all': ''}[A.canvas]
GO = """(href) => document.querySelector('.label nav a[href="' + href + '"]').click()"""


def serve(root):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    h.log_message = lambda *a, **k: None
    socketserver.TCPServer.allow_reuse_address = True
    s = socketserver.TCPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s.server_address[1]


def bandmean(img, box, sx, sy):
    b = (int(box[0] * sx), int(box[1] * sy), int(box[2] * sx), int(box[3] * sy))
    d = list(img.crop(b).convert('L').getdata())
    return sum(d) / float(len(d))


def hide(p):
    if HIDE:
        p.add_style_tag(content=HIDE + '{visibility:hidden !important}')


def leg(br, port, a, b):
    p = br.new_page(viewport={'width': W, 'height': H}, device_scale_factor=A.dpr)
    p.goto('http://127.0.0.1:%d/%s' % (port, (a + '.html') if A.cross else 'home.html'))
    p.evaluate('() => document.fonts.ready')
    p.wait_for_timeout(800)
    hide(p)
    if a != 'home' and not A.cross:
        p.evaluate(GO, a + '.html')
        p.wait_for_timeout(1300)
    cdp = p.context.new_cdp_session(p)
    events = []
    done = threading.Event()
    cdp.on('Tracing.dataCollected', lambda ev: events.extend(ev['value']))
    cdp.on('Tracing.tracingComplete', lambda ev: done.set())
    cdp.send('Tracing.start', {'transferMode': 'ReportEvents', 'traceConfig': {
        'includedCategories': ['disabled-by-default-devtools.screenshot']}})
    p.wait_for_timeout(400)
    p.evaluate(GO, b + '.html')
    p.wait_for_timeout(1000)
    if A.cross:
        p.wait_for_load_state()
        p.wait_for_timeout(500)
        try:
            hide(p)                     # a fresh document, so hide again
        except Exception:
            pass
    cdp.send('Tracing.end')
    for _ in range(100):
        if done.is_set():
            break
        p.wait_for_timeout(50)
    p.close()
    snaps = sorted((e['ts'], e['args']['snapshot']) for e in events
                   if e.get('name') == 'Screenshot' and 'snapshot' in e.get('args', {}))
    return [(ts, Image.open(io.BytesIO(base64.b64decode(d))).convert('RGB')) for ts, d in snaps]


def report(name, frames):
    if not frames:
        print('== %s  no frames' % name)
        return None
    fw, fh = frames[0][1].size
    sx, sy = fw / float(W), fh / float(H)
    rows = [(ts, {k: bandmean(f, v, sx, sy) for k, v in BANDS.items()}) for ts, f in frames]
    first, last, t0 = rows[0][1], rows[-1][1], rows[0][0]
    print('== %s  %d frames of %dx%d   rest: %s' % (name, len(rows), fw, fh,
          ' '.join('%s %.1f' % (k, first[k]) for k in BANDS)))
    print('   settled: %s' % ' '.join('%s %.1f' % (k, last[k]) for k in BANDS))
    flagged = []
    for i, (ts, m) in enumerate(rows):
        flags = [k for k in ('label', 'ground', 'lgap')
                 if abs(m[k] - first[k]) > A.flag and abs(m[k] - last[k]) > A.flag]
        if flags:
            flagged.append(i)
        if flags or A.verbose:
            print('   %3d %7.1fms  ' % (i, (ts - t0) / 1000.0)
                  + '  '.join('%s %6.2f' % (k, m[k]) for k in BANDS)
                  + (' <-- ' + ','.join(flags) if flags else ''))
    print('   flagged frames: %s' % (flagged or 'none'))
    return len(flagged)


def run(root, title):
    port = serve(root)
    legs = [tuple(x.split(':')) for x in A.legs.split(',')]
    print('%s, %s, %s, dpr %g, canvas %s' % (title, 'headed' if A.headed else 'headless',
          'cross-document' if A.cross else 'router', A.dpr, A.canvas))
    total = {}
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=not A.headed)
        for r in range(A.runs):
            for a, b in legs:
                n = report('%s -> %s, run %d' % (a, b, r), leg(br, port, a, b))
                total[(a, b)] = total.get((a, b), 0) + (n or 0)
        br.close()
    print()
    print('   %-26s %s' % ('leg', 'flagged frames over %d runs' % A.runs))
    for (a, b), n in total.items():
        print('   %-26s %d' % ('%s -> %s' % (a, b), n))
    print()


run(ROOT, 'this tree')
if OTHER:
    run(OTHER, 'other tree: %s' % OTHER)
