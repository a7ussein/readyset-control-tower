"""The built-in server that shows the page and one findings file. Standard library only."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from control_tower.webserver import EXAMPLE, make_server

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Server(unittest.TestCase):
    def start(self, findings=None):
        httpd = make_server("127.0.0.1", 0, findings, quiet=True)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (httpd.shutdown(), httpd.server_close()))
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    def get(self, url):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read(), e.headers

    def test_health(self):
        status, body, _ = self.get(self.start() + "/api/health")
        self.assertEqual((status, json.loads(body)["status"]), (200, "ok"))

    def test_it_serves_the_example_findings_by_default(self):
        status, body, _ = self.get(self.start() + "/api/findings")
        self.assertEqual(status, 200)
        with open(EXAMPLE, "rb") as fh:
            self.assertEqual(json.loads(body), json.load(fh))

    def test_it_serves_the_findings_file_it_was_pointed_at(self):
        path = os.path.join(tempfile.mkdtemp(), "f.json")
        with open(path, "w") as fh:
            json.dump({"format_version": "0.2", "findings": []}, fh)
        self.assertEqual(json.loads(self.get(self.start(path) + "/api/findings")[1])["findings"], [])

    def test_a_missing_or_broken_findings_file_is_a_plain_error_not_a_crash(self):
        d = tempfile.mkdtemp()
        self.assertEqual(self.get(self.start(os.path.join(d, "nope.json")) + "/api/findings")[0], 404)
        bad = os.path.join(d, "bad.json")
        with open(bad, "w") as fh:
            fh.write("{not json")
        status, body, _ = self.get(self.start(bad) + "/api/findings")
        self.assertEqual(status, 500)
        self.assertIn("not valid JSON", json.loads(body)["detail"])

    def test_the_page_is_served_and_nothing_outside_it_can_be_read(self):
        base = self.start()
        status, body, headers = self.get(base + "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"ReadySet", body)
        for path in ("/..%2F..%2FLICENSE", "/../../LICENSE", "/%2e%2e/%2e%2e/LICENSE", "/assets/../../../LICENSE"):
            self.assertNotIn(b"Apache License", self.get(base + path)[1], path)
        self.assertEqual(self.get(base + "/api/nothing")[0], 404)


if __name__ == "__main__":
    unittest.main()
