"""The hosted demo's voice: POST {"text": "..."} -> an MP3 of that text read aloud (ElevenLabs).

Only the words of the answer being read are sent. The key is a secret of the hosting account (ELEVENLABS_API_KEY),
not in this repository and never sent to the browser. Calls are capped so a stranger cannot spend much.
"""
import hashlib
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler

_here = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(_here, "_lib"), os.path.join(os.path.dirname(_here), "py")]
from control_tower import voice  # noqa: E402

_recent, _kept = [], {}
PER_MINUTE = 15


class handler(BaseHTTPRequestHandler):
    def _json(self, status, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._json(200, {"available": voice.available()})

    def do_POST(self):
        origin, host = self.headers.get("Origin"), self.headers.get("Host")
        if not origin or not host or origin.split("://", 1)[-1] != host:      # only the demo page itself may spend the key
            return self._json(403, {"detail": "this is only for the demo page itself"})
        if not voice.available():
            return self._json(503, {"detail": "no voice key is set on the server"})
        try:
            text = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 8000)) or b"{}")["text"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._json(400, {"detail": "expected some text"})
        said = voice.spoken(text)
        mark = hashlib.sha256(said.encode("utf-8")).hexdigest()
        if mark not in _kept:
            now = time.time()
            _recent[:] = [t for t in _recent if now - t < 60]
            if len(_recent) >= PER_MINUTE:
                return self._json(429, {"detail": "too many answers read aloud just now; try again in a minute"})
            _recent.append(now)
            try:
                if len(_kept) > 40:
                    _kept.clear()
                _kept[mark] = voice.speak(said)
            except OSError:
                return self._json(502, {"detail": "the voice service did not answer"})
        audio = _kept[mark]
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(audio)
