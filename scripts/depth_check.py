"""Every path on the 404 page resolves from any depth (#81).

GitHub Pages serves 404.html at whatever address was asked for, without redirecting, so
the document's base URL is that address, and a relative `about.html` asked for at
/pages/about/ resolves to /pages/about/about.html and dies. Every href, src, url() and
preload the build emits is root-absolute for that reason. This proves it: a server that
answers a missing path the way Pages does, three addresses of increasing depth, and every
URL in each response fetched and expected to be a 200. Then the router: on home.html a
tab switch pushes /research.html, and loading that address renders Research.

    python scripts/depth_check.py

Exits non-zero if any same-origin URL is not a 200, or if the router check fails.
"""
import sys, os, re, functools, http.server, socketserver, threading, pathlib
import urllib.request, urllib.parse, urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEPTHS = ['/pages/about/', '/nope', '/a/b/c']


class Pages(http.server.SimpleHTTPRequestHandler):
    """The built tree, with a missing path answered by 404.html at status 404, at the
    address that was asked for. No redirect, which is what GitHub Pages does."""
    def send_head(self):
        p = self.translate_path(self.path)
        if os.path.isfile(p) or os.path.isdir(p):
            return super().send_head()
        f = open(ROOT / '404.html', 'rb')
        self.send_response(404)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(os.fstat(f.fileno()).st_size))
        self.end_headers()
        return f

    def log_message(self, *a):
        pass


def serve():
    h = functools.partial(Pages, directory=str(ROOT))
    socketserver.TCPServer.allow_reuse_address = True
    s = socketserver.TCPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, s.server_address[1]


def get(url):
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# Every URL the document asks the browser for: href and src on any tag, and url() in the
# inlined CSS. The preload is an href on <link rel="preload">, so it is in the first set;
# the tag is kept so the table can say which is which.
ATTR = re.compile(r'<(\w+)\b[^>]*?\b(href|src)="([^"]*)"')
CSSURL = re.compile(r'url\(\s*["\']?([^"\')]*)["\']?\s*\)')
# %23 is `url(#n)` inside the mottle's SVG data URI: a filter reference, not a fetch.
SKIP = ('mailto:', 'data:', 'javascript:', '#', '%23', 'http://', 'https://')


def urls(html):
    out = []
    for tag, attr, raw in ATTR.findall(html):
        out.append((tag + ' ' + attr, raw))
    for raw in CSSURL.findall(html):
        out.append(('css url()', raw))
    seen, uniq = set(), []
    for kind, raw in out:
        if raw.startswith(SKIP):
            continue
        if raw not in seen:
            seen.add(raw)
            uniq.append((kind, raw))
    return uniq


def depths(port):
    """Every same-origin URL on the 404 as served at each depth, and its status."""
    bad = 0
    print('%-14s %-16s %-36s %-44s %s' % ('asked for', 'where', 'as written', 'resolves to', 'status'))
    for d in DEPTHS:
        page = 'http://127.0.0.1:%d%s' % (port, d)
        status, body = get(page)
        assert status == 404, (d, status)
        html = body.decode('utf-8')
        for kind, raw in urls(html):
            target = urllib.parse.urljoin(page, raw)
            code, _ = get(target)
            path = urllib.parse.urlsplit(target).path
            print('%-14s %-16s %-36s %-44s %s' % (d, kind, raw, path, code))
            if code != 200:
                bad += 1
        print()
    return bad


def router(port):
    """home.html: click Research, the address becomes /research.html, and a fresh load
    of that address is Research. And the 404 at depth, in a browser: every resource it
    asks for comes back 200 and Archivo is available to draw with."""
    from playwright.sync_api import sync_playwright
    base = 'http://127.0.0.1:%d' % port
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page(reduced_motion='reduce')
        p.goto(base + '/home.html')
        p.click('.label nav a[href="/research.html"]')   # as the other checks click
        p.wait_for_timeout(400)
        pushed = p.evaluate('location.pathname')
        p.reload()
        p.wait_for_timeout(400)
        shown = p.evaluate("document.querySelector('.body:not([hidden])').dataset.page")
        title = p.title()

        p.goto(base + '/a/b/c')
        p.wait_for_timeout(600)
        res = p.evaluate("performance.getEntriesByType('resource')"
                         ".map(e => [new URL(e.name).pathname, e.responseStatus])")
        font = p.evaluate("document.fonts.check('1em Archivo')")
        b.close()
    print('home.html, click Research   pushes %s' % pushed)
    print('reload %-22s renders %s, title %r' % (pushed, shown, title))
    print('/a/b/c in a browser         Archivo available: %s' % font)
    for path, code in res:
        print('    %-44s %s' % (path, code))
    ok = (pushed == '/research.html' and shown == 'research' and font
          and all(code == 200 for _, code in res))
    return ok


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')      # the titles carry an em dash
    srv, port = serve()
    try:
        bad = depths(port)
        ok = router(port)
    finally:
        srv.shutdown()
    print('%s same-origin URLs not 200 across %d depths; router %s'
          % (bad, len(DEPTHS), 'ok' if ok else 'FAILED'))
    sys.exit(1 if (bad or not ok) else 0)
