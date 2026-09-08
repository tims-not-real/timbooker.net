"""What the body text does at the end of a swap, read off full-resolution frames (#63).

    python scripts/text_check.py                     # this tree, headed, DPR 1.5
    python scripts/text_check.py <other-tree>        # this tree against another build
    python scripts/text_check.py --headless          # the control; it hides the effect
    python scripts/text_check.py --out <dir>         # keep the crops, enlarged, to look at

Tim: "when i change states tehre is still a flicker of the body text." The suspect is
anti-aliasing: text drawn in a layer of its own is smoothed in grey, text drawn in the
page on Windows is smoothed with coloured subpixels, and a swap that moves the body
into a layer and back draws every glyph one way for 180ms and the other way before and
after. The tracing screenshots `frame_check.py` reads are 498 wide and JPEG, which is no
use for a glyph's edge, so this takes full screenshots at four moments instead, with
everything slowed ten times so that the moments can be hit: mid-swap, just before the
swap's animations end, the first frame after they have all ended, and one second later.

On a crop of the incoming page's first paragraph, in device pixels:

    pop        mean absolute difference between the frame before the swap's animations
               end and the first frame after. The end of the swap should change nothing
               but the last half-percent of a fade; a jump here is the flicker.
    settle     the same between that first frame and one second later. Something that
               keeps changing after the swap is over shows here.
    fringe     pixels whose three channels differ by more than 20, at rest, mid-swap,
               before the end and after it. The ground and the text are neutral and the
               grain is grey, so a fringe is a subpixel-smoothed edge and nothing else.
               If mid-swap reads near zero and rest reads thousands, the smoothing is
               what switches.

Two legs, the second from a page that has to be reached by a swap first, and the crop is
read off the settled page so every frame is compared on the same box. The creature and
her bubble are hidden; the plates are live and not in the crop. Served over http,
device_scale_factor 1.5 by default because that is Tim's screen. Nothing here writes to
the tree unless --out names somewhere else.
"""
import io, functools, http.server, socketserver, threading, pathlib, argparse
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument('other', nargs='?', default='')
ap.add_argument('--headless', action='store_true')
ap.add_argument('--dpr', type=float, default=1.5)
ap.add_argument('--runs', type=int, default=3)
ap.add_argument('--legs', default='home:about,research:freelancing')
ap.add_argument('--slow', type=int, default=10)
ap.add_argument('--out', default='')
A = ap.parse_args()

ROOT = pathlib.Path(__file__).resolve().parent.parent
OTHER = pathlib.Path(A.other).resolve() if A.other else None
W, H = 1400, 900
SLOW = A.slow
SLOWCSS = ("::view-transition-group(*),::view-transition-old(*),::view-transition-new(*)"
           "{animation-duration:%dms !important}" % (180 * SLOW))
SLOWJS = """(function(){ var a = Element.prototype.animate;
  Element.prototype.animate = function(k, o){
    if (typeof o === 'number') o = o * %d;
    else if (o && o.duration) o = Object.assign({}, o, {duration:o.duration * %d});
    return a.call(this, k, o); }; })();""" % (SLOW, SLOW)
HIDE = '#critsay,#critter{visibility:hidden !important}'
GO = """(href) => document.querySelector('.label nav a[href="' + href + '"]').click()"""
# The swap's own animations: the transition's pseudo-elements on the old build, the body
# sections and the hero on the new one. The plate's own opacity fade is not the swap's.
# AT(frac) resolves once the furthest-along of them has run that fraction of its
# duration; AT(1) resolves once none is left. A screenshot takes tens of milliseconds
# to arrive, which at ten times slow is under a percent of the swap.
AT = """(frac) => new Promise(done => {
  const t0 = performance.now();
  (function f(){
    let on = false, best = 0;
    for (const a of document.getAnimations()){
      const e = a.effect; if (!e) continue;
      const t = e.target;
      const mine = (e.pseudoElement && e.pseudoElement.indexOf('view-transition') >= 0)
                || !!(t && t.matches && t.matches('.body, .hero'));
      if (!mine) continue;
      on = true;
      const d = e.getComputedTiming().duration || 1;
      best = Math.max(best, (a.currentTime || 0) / d);
    }
    // the click's animations exist a frame after the click, so a frac below 1 waits
    // for them to appear, for up to a second; frac 2 is the frame after they have gone
    if (!on){ if (frac >= 2 || performance.now() - t0 > 1000) done(-1); else requestAnimationFrame(f); return; }
    if (best >= frac){ done(best); return; }
    requestAnimationFrame(f);
  })();
})"""
PARA = """(key) => {
  const p = document.querySelector('[data-page="' + key + '"] p');
  const r = p.getBoundingClientRect();
  return {x: r.left, y: r.top, w: r.width, h: r.height};
}"""


def serve(root):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    h.log_message = lambda *a, **k: None
    socketserver.TCPServer.allow_reuse_address = True
    s = socketserver.TCPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s.server_address[1]


def shot(p, clip):
    # Only the paragraph. A full viewport at DPR 1.5 takes the best part of a second to
    # arrive, which is most of a swap slowed ten times; the paragraph arrives in tens of
    # milliseconds, and it is the only thing measured.
    return Image.open(io.BytesIO(p.screenshot(clip=clip))).convert('RGB')


def mad(a, b):
    d = ImageChops.difference(a, b).convert('L')
    px = list(d.getdata())
    return sum(px) / float(len(px))


def fringe(img):
    n = 0
    for r, g, b in img.getdata():
        if max(abs(r - g), abs(g - b), abs(r - b)) > 20:
            n += 1
    return n


def leg(br, port, a, b, run, outdir, name):
    p = br.new_page(viewport={'width': W, 'height': H}, device_scale_factor=A.dpr)
    p.add_init_script(SLOWJS)
    p.goto('http://127.0.0.1:%d/home.html' % port)
    p.evaluate('() => document.fonts.ready')
    p.wait_for_timeout(800)
    p.add_style_tag(content=SLOWCSS + HIDE)
    settle = 300 * SLOW + 800
    # A dry swap to the destination first, to learn where its first paragraph sits, then
    # back, so the measured swap starts from the page it is meant to start from.
    p.evaluate(GO, b + '.html')
    p.wait_for_timeout(settle)
    r = p.evaluate(PARA, b)
    clip = {'x': r['x'], 'y': r['y'], 'width': r['w'], 'height': min(r['h'], H - r['y'])}
    p.evaluate(GO, a + '.html')
    p.wait_for_timeout(settle)
    p.evaluate(GO, b + '.html')
    at = [p.evaluate(AT, 0.5)]
    mid = shot(p, clip)
    at.append(p.evaluate(AT, 0.96))
    pre = shot(p, clip)
    at.append(p.evaluate(AT, 2))
    post = shot(p, clip)
    p.wait_for_timeout(1000)
    rest = shot(p, clip)
    p.close()
    c = {'mid': mid, 'pre': pre, 'post': post, 'rest': rest}
    out = {'pop': mad(c['pre'], c['post']), 'settle': mad(c['post'], c['rest']),
           'fringe': dict((k, fringe(v)) for k, v in c.items()),
           'px': c['rest'].width * c['rest'].height, 'at': at}
    if outdir:
        for k, v in c.items():
            big = v.resize((v.width * 3, v.height * 3), Image.NEAREST)
            big.save(outdir / ('%s-%s-%s-r%d-%s.png' % (name, a, b, run, k)))
    return out


def run(root, name, outdir):
    port = serve(root)
    legs = [tuple(x.split(':')) for x in A.legs.split(',')]
    print('%s, %dx%d at DPR %g, %s, slowed %dx' % (name, W, H, A.dpr,
          'headless' if A.headless else 'headed', SLOW))
    print('%-24s %4s %7s %7s   %s' % ('leg', 'run', 'pop', 'settle',
                                     'fringe px: rest / mid-swap / before end / after end   of'))
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=A.headless)
        for a, b in legs:
            for i in range(A.runs):
                o = leg(br, port, a, b, i, outdir, name)
                f = o['fringe']
                print('%-24s %4d %7.2f %7.2f   %6d / %6d / %6d / %6d   %d   shots at %.2f %.2f %.0f'
                      % ('%s -> %s' % (a, b), i, o['pop'], o['settle'],
                         f['rest'], f['mid'], f['pre'], f['post'], o['px'], o['at'][0], o['at'][1], o['at'][2]))
        br.close()
    print()


outdir = None
if A.out:
    outdir = pathlib.Path(A.out)
    outdir.mkdir(parents=True, exist_ok=True)
run(ROOT, 'this tree', outdir)
if OTHER:
    run(OTHER, 'other tree: %s' % OTHER, outdir)
