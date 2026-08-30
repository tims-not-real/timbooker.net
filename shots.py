"""Full-page screenshots of every built page, plus two at phone width."""
import sys, pathlib
from playwright.sync_api import sync_playwright

PAGES = ['home', 'research', 'freelancing', 'about', 'contact', '404']
HERE = pathlib.Path(__file__).parent


def shoot(pw, name, width, height, out):
    b = pw.chromium.launch()
    p = b.new_page(viewport={'width': width, 'height': height},
                   device_scale_factor=1, reduced_motion='reduce')
    p.goto((HERE / (name + '.html')).as_uri())
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
