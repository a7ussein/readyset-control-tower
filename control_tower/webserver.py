"""The page, with nothing to install: Python's own HTTP server.

    python3 -m control_tower serve                          -> http://localhost:8010 (opens the browser)
    python3 -m control_tower serve RELEASE_A RELEASE_B      compare two folders live; change the question on the page
    python3 -m control_tower serve RELEASE_A RELEASE_B --question q.json     add your own analyses to choose from
    python3 -m control_tower serve --findings out.json      show a findings file other than the example
    python3 -m control_tower serve --port 9000 --no-open

Serves the built page in web/dist, the findings, and the reviews people record. Reviews are kept in a small JSON file:
beside the findings file, or `control-tower.reviews.json` in the current folder in live mode.
Meant for a laptop, not for the open internet.
"""
import json
import mimetypes
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlsplit

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

    def _document(self, wanted):
        """(status, findings document or error). In live mode the two releases are compared for the asked question."""
        srv = self.server
        if srv.releases:
            ids = [x for x in wanted.split(",") if x] if wanted else list(srv.default_ids)
            unknown = [i for i in ids if i not in srv.available]
            if unknown or not ids:
                return 400, {"detail": f"no analysis called {', '.join(unknown) or '(none)'}; "
                                       f"choose from {', '.join(srv.available)}"}
            key = ",".join(ids)
            with srv.lock:
                if key not in srv.cache:
                    from .compare import compare
                    srv.cache[key] = compare(srv.releases[0], srv.releases[1], [srv.available[i] for i in ids])
                doc = json.loads(json.dumps(srv.cache[key]))
            x = doc.setdefault("x_readyset", {})
            x["live"] = {"available": [{"id": i, "title": x.get("analysis_titles", {}).get(i) or srv.titles.get(i, i)}
                                       for i in srv.available]}
            return 200, doc
        try:
            with open(srv.findings_path, "rb") as fh:
                doc = json.loads(fh.read())
        except OSError:
            return 404, {"detail": f"no findings file at {srv.findings_path}"}
        except ValueError:
            return 500, {"detail": f"{srv.findings_path} is not valid JSON"}
        return 200, doc

    def _findings(self, wanted):
        status, doc = self._document(wanted)
        if status == 200 and isinstance(doc, dict) and isinstance(doc.get("findings"), list):
            keys = {f["id"]: review_key(f) for f in doc["findings"] if isinstance(f, dict) and "id" in f}
            saved = self.server.load_reviews()
            x = doc.setdefault("x_readyset", {}) if isinstance(doc.get("x_readyset", {}), dict) else None
            if x is not None:
                x["review_keys"] = keys
                x["reviews"] = [dict(saved[k], finding=fid) for fid, k in keys.items() if k in saved]
        self._json(status, doc)

    def _review(self):
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).hostname not in ("localhost", "127.0.0.1"):
            return self._json(403, {"detail": "reviews can only be recorded from this computer"})
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 20000)) or b"{}")
            key, status = body["key"], body["status"]
            if not isinstance(key, str) or not key or status not in ("confirmed", "dismissed", "cleared"):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._json(400, {"detail": "a review needs a key and a status of confirmed, dismissed or cleared"})
        clean = lambda v: str(v or "").strip()[:500]
        with self.server.lock:
            saved = self.server.load_reviews()
            if status == "cleared":
                saved.pop(key, None)
            else:
                saved[key] = {"key": key, "status": status, "reviewer": clean(body.get("reviewer")),
                              "role": clean(body.get("role")), "note": clean(body.get("note")),
                              "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            self.server.save_reviews(saved)
        self._json(200, {"saved": status != "cleared", "kept_in": self.server.reviews_path or "memory only"})

    def do_POST(self):
        try:
            if urlsplit(self.path).path == "/api/reviews":
                return self._review()
            self._json(404, {"detail": f"no such endpoint: POST {urlsplit(self.path).path}"})
        except (BrokenPipeError, ConnectionResetError):
            pass

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
                return self._findings(parse_qs(urlsplit(self.path).query).get("for", [""])[0])
            if path.startswith("/api/"):
                return self._json(404, {"detail": f"no such endpoint: GET {path}"})
            self._static(path)
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_HEAD = do_GET


def review_key(finding):
    """What a review is attached to: the kind, the file and the samples, so it survives a change of question."""
    evidence = [e for e in finding.get("evidence", []) if isinstance(e, dict)]
    file = next((e.get("file") for e in evidence if e.get("file")), "") or \
        next((e.get("id") for e in evidence if e.get("kind") == "file"), "")
    ids = sorted(str(e.get("id")) for e in evidence if e.get("kind") != "file")
    return "|".join([str(finding.get("kind")), str(file), ",".join(ids)])


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def load_reviews(self):
        if not self.reviews_path:
            return dict(self.memory)
        try:
            with open(self.reviews_path, encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_reviews(self, reviews):
        if not self.reviews_path:
            self.memory = dict(reviews)
            return
        with open(self.reviews_path, "w", encoding="utf-8") as fh:
            json.dump(reviews, fh, indent=2)
            fh.write("\n")


def make_server(host="127.0.0.1", port=8010, findings=None, quiet=False, releases=None, question=None, reviews=None):
    """`releases` = (trusted folder, new folder) compares them live, and `question` is an optional list of analysis
    descriptions that adds to the registered ones. Otherwise one findings file is shown."""
    from .analyses import REGISTRY, from_spec
    httpd = Server((host, port), Handler)
    httpd.quiet = quiet
    httpd.findings_path = findings or EXAMPLE
    httpd.releases, httpd.lock, httpd.cache, httpd.memory = releases, threading.Lock(), {}, {}
    httpd.available = {a.id: a.id for a in REGISTRY}
    httpd.titles = {a.id: a.title for a in REGISTRY}
    httpd.default_ids = list(httpd.available)
    if question:
        asked = [from_spec(q) for q in question]              # raises BadQuestion before the server starts
        for spec, a in zip(question, asked):
            httpd.available[a.id] = spec
            httpd.titles[a.id] = a.title
        httpd.default_ids = [a.id for a in asked]
    # A review is a record, so it is kept on disk beside what it reviews. The built-in example keeps none.
    httpd.reviews_path = reviews or ("control-tower.reviews.json" if releases else
                                     (findings + ".reviews.json" if findings else None))
    return httpd


def main(argv):
    host, port, open_browser, findings = "127.0.0.1", int(os.environ.get("PORT") or 8010), True, None
    folders, question = [], None
    it = iter(argv)
    try:
        for a in it:
            if a == "--port":
                port = int(next(it))
            elif a == "--host":
                host = next(it)
            elif a == "--findings":
                findings = next(it)
            elif a == "--question":
                from .__main__ import load_question
                question = load_question(next(it))
            elif a == "--no-open":
                open_browser = False
            elif not a.startswith("--") and os.path.isdir(a):
                folders.append(a)
            else:
                print(__doc__, file=sys.stderr)
                return 64
    except (StopIteration, OSError, ValueError) as e:
        print(f"error: {e or 'an option is missing its value'}", file=sys.stderr)
        return 64
    if folders and (len(folders) != 2 or findings):
        print("error: give two release folders (the trusted one first), or --findings FILE, not both", file=sys.stderr)
        return 64
    try:
        from .analyses import BadQuestion
        httpd = make_server(host, port, findings, releases=tuple(folders) if folders else None, question=question)
    except BadQuestion as e:
        print(f"error: {e}", file=sys.stderr)
        return 64
    except OSError as e:
        print(f"Could not start on port {port}: {e.strerror or e}.\n"
              f"Try another port:  python3 -m control_tower serve --port {port + 1}", file=sys.stderr)
        return 1
    url = f"http://localhost:{port}"
    print(f"ReadySet Control Tower is running at {url}   (Ctrl+C to stop)", flush=True)
    print(f"Comparing live: {folders[0]}  with  {folders[1]}" if folders
          else f"Showing: {os.path.relpath(httpd.findings_path)}", flush=True)
    if open_browser and host in ("127.0.0.1", "localhost"):
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0
