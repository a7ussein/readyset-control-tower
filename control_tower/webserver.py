"""The page, with nothing to install: Python's own HTTP server.

    python3 -m control_tower serve                          -> http://localhost:8010 (opens the browser)
    python3 -m control_tower serve --findings out.json      show a findings file other than the example
    python3 -m control_tower serve --port 9000 --no-open

Serves the built page in web/dist and one findings file. Meant for a laptop, not for the open internet.
"""
import json
import mimetypes
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "web", "dist")
EXAMPLE = os.path.join(ROOT, "docs", "example-findings.json")

NO_PAGE = (b"<!doctype html><meta charset=utf-8><title>ReadySet Control Tower</title>"
           b"<body style='font:16px system-ui;max-width:40rem;margin:4rem auto;padding:0 1rem'>"
           b"<h1>The server is running</h1><p>The page is not built in this copy (<code>web/dist</code> is missing). "
           b"Build it once with <code>cd web &amp;&amp; npm install &amp;&amp; npm run build</code>. "
           b"The findings are at <a href='/api/findings'>/api/findings</a>.</p>")


class Handler(BaseHTTPRequestHandler):
    server_version = "ReadySetControlTower"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if not getattr(self.server, "quiet", False):
            sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj).encode(), "application/json")

    def _findings(self):
        path = self.server.findings_path
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            json.loads(data)
        except OSError:
            return self._json(404, {"detail": f"no findings file at {path}"})
        except ValueError:
            return self._json(500, {"detail": f"{path} is not valid JSON"})
        self._send(200, data, "application/json")

    def _static(self, path):
        dist = os.path.realpath(DIST)
        if not os.path.isfile(os.path.join(dist, "index.html")):
            return self._send(200, NO_PAGE, "text/html; charset=utf-8")
        target = os.path.realpath(os.path.join(dist, unquote(path).lstrip("/")))
        inside = target == dist or target.startswith(dist + os.sep)
        if not inside or not os.path.isfile(target):
            target = os.path.join(dist, "index.html")
        with open(target, "rb") as fh:
            data = fh.read()
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        self._send(200, data, ctype)

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if path == "/api/health":
                return self._json(200, {"status": "ok", "service": "readyset-control-tower"})
            if path == "/api/findings":
                return self._findings()
            if path.startswith("/api/"):
                return self._json(404, {"detail": f"no such endpoint: GET {path}"})
            self._static(path)
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_HEAD = do_GET


def make_server(host="127.0.0.1", port=8010, findings=None, quiet=False):
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    httpd.quiet = quiet
    httpd.findings_path = findings or EXAMPLE
    return httpd


def main(argv):
    host, port, open_browser, findings = "127.0.0.1", int(os.environ.get("PORT") or 8010), True, None
    it = iter(argv)
    for a in it:
        if a == "--port":
            port = int(next(it))
        elif a == "--host":
            host = next(it)
        elif a == "--findings":
            findings = next(it)
        elif a == "--no-open":
            open_browser = False
        else:
            print(__doc__, file=sys.stderr)
            return 64
    try:
        httpd = make_server(host, port, findings)
    except OSError as e:
        print(f"Could not start on port {port}: {e.strerror or e}.\n"
              f"Try another port:  python3 -m control_tower serve --port {port + 1}", file=sys.stderr)
        return 1
    url = f"http://localhost:{port}"
    print(f"ReadySet Control Tower is running at {url}   (Ctrl+C to stop)", flush=True)
    print(f"Showing: {os.path.relpath(httpd.findings_path)}", flush=True)
    if open_browser and host in ("127.0.0.1", "localhost"):
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0
