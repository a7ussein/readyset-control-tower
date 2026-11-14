"""The hosted demo's one server function: understand the wording of a question.

POST {"q": "..."} -> {"intent": "limits"} or {"intent": null}

It asks a model one thing: which of the assistant's fixed questions a wording is closest to. It is sent the question
and the list of fixed questions. It never receives findings or data, and it writes no answer. The API key is a secret
of the hosting account (ANTHROPIC_API_KEY); it is not in this repository and is never sent to the browser.
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler

_here = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(_here, "_lib"), os.path.join(os.path.dirname(_here), "py")]
from control_tower import understand_ai  # noqa: E402

_router = None
_recent = []                                  # times of recent calls on this instance, to cap what a stranger can spend
PER_MINUTE = 40


class handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200, {"available": bool(os.environ.get("ANTHROPIC_API_KEY"))})

    def do_POST(self):
        global _router
        origin, host = self.headers.get("Origin"), self.headers.get("Host")
        if origin and host and origin.split("://", 1)[-1] != host:
            return self._send(403, {"detail": "this is only for the demo page itself"})
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return self._send(503, {"detail": "no key is set on the server"})
        try:
            question = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 4000)) or b"{}")["q"]
            if not isinstance(question, str) or not question.strip():
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._send(400, {"detail": "expected a question"})
        now = time.time()
        _recent[:] = [t for t in _recent if now - t < 60]
        if len(_recent) >= PER_MINUTE:
            return self._send(429, {"detail": "too many questions just now; try again in a minute"})
        _recent.append(now)
        if _router is None:
            _router = understand_ai.make_router(key=os.environ["ANTHROPIC_API_KEY"])
        self._send(200, {"intent": _router(question[:500])})
