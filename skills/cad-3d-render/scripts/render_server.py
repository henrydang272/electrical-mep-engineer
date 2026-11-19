import http.server, base64, os, sys, urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def do_POST(self):
        name = os.path.basename(urllib.parse.urlparse(self.path).path)
        raw = self.rfile.read(int(self.headers['Content-Length']))
        if self.headers.get('Content-Type', '').startswith('application/octet-stream'):
            blob = raw                                   # binary (e.g. MP4 from the video recorder)
        else:
            blob = base64.b64decode(raw.decode().split(',', 1)[1])   # data URL (PNG stills)
        with open(os.path.join(OUT, name), 'wb') as f:
            f.write(blob)
        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

http.server.ThreadingHTTPServer(('127.0.0.1', 8765), H).serve_forever()
