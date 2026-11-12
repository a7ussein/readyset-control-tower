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
    def start(self, findings=None, **more):
        httpd = make_server("127.0.0.1", 0, findings, quiet=True, **more)
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

    def post(self, url, payload):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def live(self, **more):
        from tests.tiny_release import N1, P1, PROTEIN, TinyRelease
        d = tempfile.mkdtemp()
        a = TinyRelease()
        b = a.copy().swap(PROTEIN, P1, N1)
        return self.start(releases=(a.write(os.path.join(d, "A")), b.write(os.path.join(d, "B"))),
                          reviews=os.path.join(d, "reviews.json"), **more), d

    def test_live_mode_answers_whichever_question_is_asked(self):
        base, _ = self.live()
        both = json.loads(self.get(base + "/api/findings")[1])
        self.assertEqual((both["verdict"], both["x_readyset"]["analyses_in_question"]), ("Conditional", ["A1", "A2"]))
        self.assertEqual([a["id"] for a in both["x_readyset"]["live"]["available"]], ["A1", "A2"])
        only_a2 = json.loads(self.get(base + "/api/findings?for=A2")[1])
        self.assertEqual((only_a2["verdict"], only_a2["findings"][0]["severity"]), ("Ready", "low"))
        self.assertEqual(self.get(base + "/api/findings?for=A9")[0], 400)

    def test_live_mode_offers_an_analysis_described_in_a_question_file(self):
        from tests.tiny_release import ER, PROTEIN
        q = [{"id": "Q1", "type": "mean_by_group", "title": "HER2 by ER", "file": PROTEIN, "row": "HER2", "column": ER,
              "groups": ["Positive", "Negative"]}]
        base, _ = self.live(question=q)
        doc = json.loads(self.get(base + "/api/findings")[1])
        self.assertEqual(doc["x_readyset"]["analyses_in_question"], ["Q1"])                 # the file sets the default
        self.assertEqual([a["id"] for a in doc["x_readyset"]["live"]["available"]], ["A1", "A2", "Q1"])
        self.assertEqual(json.loads(self.get(base + "/api/findings?for=A1,Q1")[1])["x_readyset"]["analyses_in_question"],
                         ["A1", "Q1"])

    def test_a_review_is_recorded_on_disk_and_follows_the_finding_to_another_question(self):
        base, d = self.live()
        doc = json.loads(self.get(base + "/api/findings")[1])
        key = doc["x_readyset"]["review_keys"]["F1"]
        self.assertEqual(doc["x_readyset"]["reviews"], [])
        status, _ = self.post(base + "/api/reviews", {"key": key, "status": "confirmed", "reviewer": "R. Engineer",
                                                      "role": "research engineer", "note": "checked the two files"})
        self.assertEqual(status, 200)
        with open(os.path.join(d, "reviews.json")) as fh:
            self.assertEqual(json.load(fh)[key]["status"], "confirmed")
        for query in ("", "?for=A2"):                                             # same finding, different question
            r = json.loads(self.get(base + "/api/findings" + query)[1])["x_readyset"]["reviews"]
            self.assertEqual([(x["finding"], x["status"], x["reviewer"]) for x in r], [("F1", "confirmed", "R. Engineer")])
        self.post(base + "/api/reviews", {"key": key, "status": "cleared"})
        self.assertEqual(json.loads(self.get(base + "/api/findings")[1])["x_readyset"]["reviews"], [])
        self.assertEqual(self.post(base + "/api/reviews", {"key": key, "status": "approved"})[0], 400)

    def test_health(self):
        status, body, _ = self.get(self.start() + "/api/health")
        self.assertEqual((status, json.loads(body)["status"]), (200, "ok"))

    def test_it_serves_the_example_findings_by_default(self):
        status, body, _ = self.get(self.start() + "/api/findings")
        self.assertEqual(status, 200)
        served = json.loads(body)
        for added in ("review_keys", "reviews"):                 # the server adds where reviews attach; nothing else
            served["x_readyset"].pop(added)
        with open(EXAMPLE, "rb") as fh:
            self.assertEqual(served, json.load(fh))

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
