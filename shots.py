"""Full-page screenshots of every built page, plus two at phone width."""
import sys, pathlib, functools, http.server, socketserver, threading
from playwright.sync_api import sync_playwright

PAGES = ['home', 'research', 'freelancing', 'about', 'contact', '404']
HERE = pathlib.Path(__file__).parent

# Over http, the way every scripts/*_check.py does it. The paths the build emits are
# root-absolute (#81), which a file:// document cannot resolve, and file:// blocked the
# fonts anyway.
H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HERE))
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.TCPServer(('127.0.0.1', 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = 'http://127.0.0.1:%d/' % srv.server_address[1]


def shoot(pw, name, width, height, out):
    b = pw.chromium.launch()
    p = b.new_page(viewport={'width': width, 'height': height},
                   device_scale_factor=1, reduced_motion='reduce')
    p.goto(URL + name + '.html')
    p.wait_for_timeout(1400)
    p.screenshot(path=str(HERE / out), full_page=True)
    b.close()


with sync_playwright() as pw:
    for name in PAGES:
        shoot(pw, name, 1400, 900, 'p-%s.png' % name)
        print('p-%s.png' % name)
    shoot(pw, 'home', 420, 860, 'p-home-mob.png')
    shoot(pw, 'research', 420, 860, 'p-research-mob.png')
    print('mobile done')
