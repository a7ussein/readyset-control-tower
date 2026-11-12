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
import atexit
import json
import mimetypes
import os
import re
import shutil
import sys
import tempfile
import threading
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlsplit

from .release import FILES

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
        if srv.releases and all(srv.releases):
            ids = [x for x in wanted.split(",") if x] if wanted else list(srv.default_ids)
            unknown = [i for i in ids if i not in srv.available]
            if unknown or not ids:
                return 400, {"detail": f"no analysis called {', '.join(unknown) or '(none)'}; "
                                       f"choose from {', '.join(srv.available)}"}
            key = ",".join(ids)
            with srv.lock:
                if key not in srv.cache:
                    from .analyses import BadQuestion
                    from .compare import compare
                    try:
                        srv.cache[key] = compare(srv.releases[0], srv.releases[1], [srv.available[i] for i in ids])
                    except BadQuestion as e:
                        return 400, {"detail": str(e)}
                    except Exception as e:                       # never drop the connection: say what went wrong
                        sys.stderr.write(f"  comparison failed: {type(e).__name__}: {e}\n")
                        return 500, {"detail": f"The comparison failed ({type(e).__name__}). Check that both folders hold "
                                               f"the release's files, with the trusted release first."}
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

    def _findings(self, wanted, as_report=False):
        status, doc = self._document(wanted)
        if status == 200 and isinstance(doc, dict) and isinstance(doc.get("findings"), list):
            new_release = release_name(doc)
            keys = {f["id"]: review_key(f, new_release) for f in doc["findings"] if isinstance(f, dict) and "id" in f}
            saved = self.server.load_reviews()
            x = doc.setdefault("x_readyset", {}) if isinstance(doc.get("x_readyset", {}), dict) else None
            if x is not None:
                x["review_keys"] = keys
                x["reviews"] = [dict(saved[k], finding=fid, release=new_release) for fid, k in keys.items() if k in saved]
                apply_reviews(doc, {fid: saved[k] for fid, k in keys.items() if k in saved})
        if as_report and status == 200:
            from .report import render
            body = render(doc).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="audit-report.html"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(body)
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
                saved[key] = {"key": key, "status": status, "fix": "approved" if body.get("fix") == "approved" and status == "confirmed" else "",
                              "reviewer": clean(body.get("reviewer")),
                              "role": clean(body.get("role")), "note": clean(body.get("note")),
                              "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            self.server.save_reviews(saved)
        self._json(200, {"saved": status != "cleared", "kept_in": self.server.reviews_path or "memory only"})

    def _local_only(self):
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).hostname not in ("localhost", "127.0.0.1"):
            self._json(403, {"detail": "this can only be done from this computer"})
            return False
        return True

    def _state(self):
        srv = self.server
        trusted, new = srv.releases or (None, None)
        return {"trusted": trusted, "new": new, "files": list(FILES),
                "trusted_name": os.path.basename(os.path.normpath(trusted)) if trusted else None,
                "new_name": os.path.basename(os.path.normpath(new)) if new else None}

    def _options(self, query):
        """What a new analysis can be built from, read from the trusted release: clinical columns, the values in one
        column, and the row names of a measurement file that match some typed text."""
        from . import release
        trusted = (self.server.releases or (None, None))[0]
        clinical = release.path_of(trusted, release.CLINICAL) if trusted else None
        if not clinical:
            return self._json(400, {"detail": "set the trusted release first"})
        try:
            if query.get("column"):
                columns, table = release.read_rows(clinical)
                column = query["column"][0]
                if column not in columns:
                    return self._json(400, {"detail": f"there is no column called {column}"})
                counts = {}
                for sample, cells in table.items():
                    if release.is_primary(sample) and cells.get(column, "") not in release.EMPTY:
                        counts[cells[column]] = counts.get(cells[column], 0) + 1
                top = sorted(counts.items(), key=lambda kv: -kv[1])[:20]
                return self._json(200, {"values": [{"value": v, "samples": n} for v, n in top], "distinct": len(counts)})
            if query.get("file"):
                file = os.path.basename(query["file"][0])
                path = release.path_of(trusted, file) if file in FILES and file != release.CLINICAL else None
                if not path:
                    return self._json(400, {"detail": f"{file} is not a measurement file in the trusted release"})
                with self.server.lock:
                    if file not in self.server.rows:
                        self.server.rows[file] = release.row_names(path)
                    names = self.server.rows[file]
                typed = query.get("q", [""])[0].lower()
                hits = [n for n in names if n.lower().startswith(typed)] + [n for n in names if typed in n.lower() and not n.lower().startswith(typed)]
                return self._json(200, {"rows": hits[:25], "total": len(names)})
            columns, _ = release.read_rows(clinical)
            files = [f for f in FILES if f != release.CLINICAL and release.path_of(trusted, f)
                     and release.layout(release.path_of(trusted, f)) == "column"]
            return self._json(200, {"columns": columns, "files": files})
        except (release.Unreadable, OSError) as e:
            return self._json(400, {"detail": str(e)})

    def _add_question(self):
        """Add an analysis described on the page to the ones the question can be built from."""
        from .analyses import BadQuestion, from_spec
        srv = self.server
        trusted = (srv.releases or (None, None))[0]
        try:
            spec = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 20000)) or b"{}")
            if not isinstance(spec, dict):
                raise ValueError
        except ValueError:
            return self._json(400, {"detail": "expected an analysis description"})
        with srv.lock:
            n = 1
            while f"Q{n}" in srv.available:
                n += 1
            spec = dict(spec, id=f"Q{n}")
            try:
                analysis = from_spec(spec)
                wrong = analysis.problem(trusted) if trusted else None
                if wrong:
                    raise BadQuestion(wrong.split(": ", 1)[-1][:1].upper() + wrong.split(": ", 1)[-1][1:] + ".")
            except BadQuestion as e:
                return self._json(400, {"detail": str(e)})
            srv.available[analysis.id] = spec
            srv.titles[analysis.id] = analysis.title
        self._json(200, {"id": analysis.id, "title": analysis.title})

    def _upload(self, query):
        """One file of a release being dropped on the page, saved into a staging folder for that drop."""
        name = os.path.basename(query.get("name", [""])[0])
        batch = query.get("batch", [""])[0]
        if not re.fullmatch(r"[A-Za-z0-9-]{8,64}", batch) or not (name in FILES or name.lower().endswith(".zip")):
            return self._json(400, {"detail": f"{name or 'that file'} is not one of the release's files or a zip"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            return self._json(413, {"detail": f"{name} is too large"})
        folder = os.path.join(self.server.staging, batch)
        os.makedirs(folder, exist_ok=True)
        if os.path.exists(os.path.join(folder, name if name in FILES else "upload.zip")):
            self.rfile.read(length)
            return self._json(400, {"detail": f"there are two files called {name} in what you dropped. That looks like more than one "
                                              f"release. Give it one release at a time, so they are not mixed together."})
        with open(os.path.join(folder, name if name in FILES else "upload.zip"), "wb") as out:
            left = length
            while left > 0:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk:
                    break
                out.write(chunk)
                left -= len(chunk)
        self._json(200, {"saved": name})

    def _set_release(self):
        """Point the page at a release: {"path": folder or zip}, {"trusted": folder}, or {"batch": id, "name": label}."""
        srv = self.server
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 20000)) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self._json(400, {"detail": "expected a small JSON object"})
        try:
            trusted, new = srv.releases or (None, None)
            if body.get("trusted"):
                trusted = release_folder(str(body["trusted"]), srv.staging)
            if body.get("path"):
                new = release_folder(str(body["path"]), srv.staging)
            if body.get("batch"):
                batch = str(body["batch"])
                if not re.fullmatch(r"[A-Za-z0-9-]{8,64}", batch):
                    raise NotARelease("that upload is not known")
                label = re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.splitext(os.path.basename(str(body.get("name") or "")))[0]).strip("-.")
                staged = os.path.join(srv.staging, batch)
                target = os.path.join(staged, label or "new-release")
                os.makedirs(target, exist_ok=True)
                for f in FILES:
                    if os.path.isfile(os.path.join(staged, f)):
                        os.replace(os.path.join(staged, f), os.path.join(target, f))
                if os.path.isfile(os.path.join(staged, "upload.zip")):
                    unzip_release(os.path.join(staged, "upload.zip"), target)
                new = release_folder(target, srv.staging)
            if trusted and new and os.path.realpath(trusted) == os.path.realpath(new):
                raise NotARelease("that is the trusted release itself. Give it the new release you want to check.")
            if trusted and srv.question_specs:
                problems = question_problems(srv.question_specs, trusted)
                if problems:
                    raise NotARelease("the question file does not fit the trusted release. " + "; ".join(problems))
        except NotARelease as e:
            return self._json(400, {"detail": str(e)})
        with srv.lock:
            srv.releases = (trusted, new)
            srv.cache.clear()
            if not srv.reviews_path:
                srv.reviews_path = "control-tower.reviews.json"
            if trusted:
                remember_trusted(trusted, srv.settings_path)
        self._json(200, self._state())

    def do_POST(self):
        try:
            parts = urlsplit(self.path)
            if parts.path in ("/api/upload", "/api/release", "/api/question") and not self._local_only():
                return
            if parts.path == "/api/question":
                return self._add_question()
            if parts.path == "/api/upload":
                return self._upload(parse_qs(parts.query))
            if parts.path == "/api/release":
                return self._set_release()
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
            if path == "/api/state":
                return self._json(200, self._state())
            if path == "/api/options":
                return self._options(parse_qs(urlsplit(self.path).query))
            if path == "/api/findings":
                return self._findings(parse_qs(urlsplit(self.path).query).get("for", [""])[0])
            if path == "/api/report":
                return self._findings(parse_qs(urlsplit(self.path).query).get("for", [""])[0], as_report=True)
            if path.startswith("/api/"):
                return self._json(404, {"detail": f"no such endpoint: GET {path}"})
            self._static(path)
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_HEAD = do_GET


MAX_UPLOAD = 2 << 30
SETTINGS = "control-tower.settings.json"


class NotARelease(Exception):
    """The folder or zip does not hold any of the release's files."""


def unzip_release(zip_path, target):
    """Take only the release's own files out of a zip, by name, wherever they sit inside it. Nothing else is written."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            wanted = [i for i in z.infolist() if not i.is_dir() and os.path.basename(i.filename) in FILES
                      and not os.path.basename(i.filename).startswith("._") and "__MACOSX" not in i.filename]
            folders = sorted({os.path.dirname(i.filename) or "(top level)" for i in wanted})
            if len(folders) > 1:
                raise NotARelease("that zip holds more than one release (" + ", ".join(os.path.basename(f) or f for f in folders[:4])
                                  + "). Give it one release at a time, so they are not mixed together.")
            for info in wanted:
                if info.file_size > MAX_UPLOAD:
                    raise NotARelease(f"{os.path.basename(info.filename)} in that zip is too large")
                with z.open(info) as src, open(os.path.join(target, os.path.basename(info.filename)), "wb") as out:
                    shutil.copyfileobj(src, out)
    except (zipfile.BadZipFile, OSError) as e:
        raise NotARelease(f"that zip could not be opened: {e}")


def release_folder(path, staging):
    """The folder that holds a release's files, given a folder or a zip. Looks one level down for a lone subfolder."""
    path = os.path.abspath(os.path.expanduser(path.strip().strip('"').strip("'")))
    shown = "what you gave" if path.startswith(os.path.abspath(staging)) else path
    if os.path.isfile(path) and path.lower().endswith(".zip"):
        target = os.path.join(staging, uuid.uuid4().hex, os.path.splitext(os.path.basename(path))[0] or "new-release")
        os.makedirs(target, exist_ok=True)
        unzip_release(path, target)
        path = target
    if not os.path.isdir(path):
        raise NotARelease(f"{shown} is not a folder or a zip")
    has = lambda folder: any(os.path.isfile(os.path.join(folder, f)) for f in FILES)
    if not has(path):
        inner = [os.path.join(path, d) for d in sorted(os.listdir(path)) if os.path.isdir(os.path.join(path, d))]
        found = [d for d in inner if has(d)]
        if len(found) > 1:
            raise NotARelease(f"{shown} holds more than one release ({', '.join(os.path.basename(d) for d in found[:4])}). "
                              f"Give it one release at a time.")
        if not found:
            raise NotARelease(f"none of the release's files are in {shown} (looking for {', '.join(FILES[:2])} and the others)")
        path = found[0]
    return path


def remember_trusted(path, settings=SETTINGS):
    if not settings:
        return
    try:
        with open(settings, "w", encoding="utf-8") as fh:
            json.dump({"trusted": path}, fh)
    except OSError:
        pass


def default_trusted():
    """The trusted release used last time, or the organisers' repo cloned next to this one as the README says."""
    try:
        with open(SETTINGS, encoding="utf-8") as fh:
            saved = json.load(fh).get("trusted")
        if saved and os.path.isdir(saved):
            return saved
    except (OSError, ValueError, AttributeError):
        pass
    beside = os.path.join(os.path.dirname(ROOT), "oncosys-hackathon-challenge", "data", "tcga-brca", "raw")
    return beside if os.path.isdir(beside) else None


def release_name(doc):
    try:
        return str(doc["data"]["releases"][-1]["name"])
    except (KeyError, IndexError, TypeError):
        return ""


def apply_reviews(doc, reviewed):
    """Write each person's decision where any tool that reads the shared format will find it: the finding no longer
    waits for review, and every repair that addresses it gets a `decisions` entry (approve, or reject)."""
    decisions = [d for d in doc.get("decisions", []) if isinstance(d, dict)] if isinstance(doc.get("decisions"), list) else []
    for f in doc["findings"]:
        r = reviewed.get(f.get("id")) if isinstance(f, dict) else None
        if not r:
            continue
        f["needs_human_review"] = False
        who = r.get("reviewer") or "a reviewer who gave no name"
        said = "Confirmed as a real problem" if r["status"] == "confirmed" else "Dismissed as an expected change"
        if r["status"] == "confirmed" and r.get("fix") == "approved":
            said += ", and the suggested fix approved,"
        reason = f"{said} by {who}" + (f": {r['note']}" if r.get("note") else ".")
        # Confirming that a problem is real does not approve the suggested fix. A decision on the fix is written only
        # when the reviewer approved it too, or dismissed the finding (so the fix is not wanted).
        verdict = "reject" if r["status"] == "dismissed" else ("approve" if r.get("fix") == "approved" else None)
        for repair in doc.get("repairs", []) if isinstance(doc.get("repairs"), list) else []:
            if verdict and isinstance(repair, dict) and f["id"] in (repair.get("addresses") or []) and repair.get("id"):
                decisions = [d for d in decisions if d.get("repair_id") != repair["id"]]
                decisions.append({"repair_id": repair["id"], "decision": verdict,
                                  "reason": reason, "reviewer_role": r.get("role") or "not stated", "original_preserved": True})
    if decisions:
        doc["decisions"] = decisions


def question_problems(specs, trusted):
    """Why each described analysis cannot be asked of the trusted release; empty when the question fits."""
    from .analyses import REGISTRY, from_spec
    return [w for w in (a.problem(trusted) for a in (from_spec(q) for q in specs) if a not in REGISTRY) if w]


def review_key(finding, new_release=""):
    """What a review is attached to: the release, the kind, the file and the samples. It survives a change of question,
    and it does not carry over to a different release."""
    evidence = [e for e in finding.get("evidence", []) if isinstance(e, dict)]
    file = next((e.get("file") for e in evidence if e.get("file")), "") or \
        next((e.get("id") for e in evidence if e.get("kind") == "file"), "")
    ids = sorted(str(e.get("id")) for e in evidence if e.get("kind") != "file")
    return "|".join([new_release, str(finding.get("kind")), str(file), ",".join(ids)])


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


def make_server(host="127.0.0.1", port=8010, findings=None, quiet=False, releases=None, question=None, reviews=None,
                settings=SETTINGS):
    """`releases` = (trusted folder, new folder) compares them live, and `question` is an optional list of analysis
    descriptions that adds to the registered ones. Otherwise one findings file is shown."""
    from .analyses import REGISTRY, from_spec
    httpd = Server((host, port), Handler)
    httpd.quiet = quiet
    httpd.findings_path = findings or EXAMPLE
    httpd.releases, httpd.lock, httpd.cache, httpd.memory = releases, threading.Lock(), {}, {}
    httpd.settings_path = settings
    httpd.rows = {}
    httpd.staging = tempfile.mkdtemp(prefix="readyset-release-")
    atexit.register(shutil.rmtree, httpd.staging, True)
    httpd.available = {a.id: a.id for a in REGISTRY}
    httpd.titles = {a.id: a.title for a in REGISTRY}
    httpd.default_ids = list(httpd.available)
    httpd.question_specs = question
    if question:
        asked = [from_spec(q) for q in question]              # raises BadQuestion before the server starts
        for spec, a in zip(question, asked):
            httpd.available[a.id] = spec
            httpd.titles[a.id] = a.title
        httpd.default_ids = [a.id for a in asked]
    # A review is a record, so it is kept on disk beside what it reviews. The built-in example keeps none.
    httpd.reviews_path = reviews or ("control-tower.reviews.json" if releases and all(releases) else
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
            elif a in ("--help", "-h"):
                print(__doc__)
                return 0
            elif not a.startswith("--"):
                print(f"error: {a} is not a folder", file=sys.stderr)
                return 64
            else:
                print(__doc__, file=sys.stderr)
                return 64
    except (StopIteration, OSError, ValueError) as e:
        print(f"error: {e or 'an option is missing its value'}", file=sys.stderr)
        return 64
    if len(folders) > 2 or (folders and findings):
        print("error: give the trusted release folder, optionally the new one after it, or --findings FILE", file=sys.stderr)
        return 64
    releases = None
    if folders:
        releases = (folders[0], folders[1] if len(folders) == 2 else None)
        remember_trusted(os.path.abspath(folders[0]))
    elif not findings and default_trusted():
        releases = (default_trusted(), None)             # ready for a release to be dropped on the page
    try:
        from .analyses import BadQuestion
        if question and releases:
            wrong = question_problems(question, releases[0])
            if wrong:
                raise BadQuestion("the question does not fit the trusted release. " + "; ".join(wrong))
        httpd = make_server(host, port, findings, releases=releases, question=question)
    except BadQuestion as e:
        print(f"error: {e}", file=sys.stderr)
        return 64
    except OSError as e:
        print(f"Could not start on port {port}: {e.strerror or e}.\n"
              f"Try another port:  python3 -m control_tower serve --port {port + 1}", file=sys.stderr)
        return 1
    url = f"http://localhost:{port}"
    print(f"ReadySet Control Tower is running at {url}   (Ctrl+C to stop)", flush=True)
    if releases and all(releases):
        print(f"Comparing: {releases[0]}  with  {releases[1]}", flush=True)
    else:
        print(f"Showing: {os.path.relpath(httpd.findings_path)}", flush=True)
        if releases:
            print(f"Trusted release: {releases[0]}. Drop a new release on the page to compare it.", flush=True)
    if open_browser and host in ("127.0.0.1", "localhost"):
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0
