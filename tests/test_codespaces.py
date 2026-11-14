"""In a GitHub Codespace the page may be changed from that codespace's own address, and from no other site."""
import json
import os
import threading
import unittest
import urllib.error
import urllib.request

from control_tower.webserver import make_server


def post(port, origin):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/question", data=json.dumps({}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Origin": origin})
    try:
        return urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code


class CodespacesOrigin(unittest.TestCase):
    def serve(self):
        httpd = make_server(port=0, quiet=True)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def setUp(self):
        self.saved = {k: os.environ.pop(k, None) for k in ("CODESPACE_NAME", "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")}
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None) for k, v in self.saved.items()])

    def test_outside_a_codespace_a_github_address_is_refused(self):
        port = self.serve()
        self.assertEqual(post(port, f"https://some-name-{port}.app.github.dev"), 403)
        self.assertNotEqual(post(port, f"http://localhost:{port}"), 403)

    def test_inside_a_codespace_only_its_own_address_is_let_in(self):
        os.environ["CODESPACE_NAME"], os.environ["GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN"] = "some-name", "app.github.dev"
        port = self.serve()
        self.assertNotEqual(post(port, f"https://some-name-{port}.app.github.dev"), 403)
        self.assertEqual(post(port, f"https://other-name-{port}.app.github.dev"), 403)
        self.assertEqual(post(port, "https://evil.example"), 403)


if __name__ == "__main__":
    unittest.main()
