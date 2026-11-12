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


def TinyReleaseAt(folder, name, change):
    from tests.tiny_release import TinyRelease
    return change(TinyRelease()).write(os.path.join(folder, name))


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
        reviewed = json.loads(self.get(base + "/api/findings")[1])
        self.assertEqual(reviewed["findings"][0]["needs_human_review"], False)     # any tool reading the format sees it
        repair = next(r["id"] for r in reviewed["repairs"] if "F1" in r["addresses"])
        self.assertNotIn("decisions", reviewed)                 # confirming a problem does not approve the suggested fix
        self.post(base + "/api/reviews", {"key": key, "status": "confirmed", "fix": "approved", "reviewer": "R. Engineer",
                                          "role": "research engineer", "note": "checked the two files"})
        reviewed = json.loads(self.get(base + "/api/findings")[1])
        decision = next(d for d in reviewed["decisions"] if d["repair_id"] == repair)
        self.assertEqual((decision["decision"], decision["reviewer_role"]), ("approve", "research engineer"))
        self.assertIn("R. Engineer", decision["reason"])
        self.post(base + "/api/reviews", {"key": key, "status": "dismissed", "reviewer": "R. Engineer", "role": "research engineer"})
        dismissed = json.loads(self.get(base + "/api/findings")[1])
        self.assertEqual(next(d for d in dismissed["decisions"] if d["repair_id"] == repair)["decision"], "reject")
        self.post(base + "/api/reviews", {"key": key, "status": "confirmed", "reviewer": "R. Engineer",
                                          "role": "research engineer", "note": "checked the two files"})
        self.assertEqual(reviewed["x_readyset"]["reviews"][0]["release"], "B")
        self.assertTrue(key.startswith("B|"))                                      # a review belongs to one release
        for query in ("", "?for=A2"):                                             # same finding, different question
            r = json.loads(self.get(base + "/api/findings" + query)[1])["x_readyset"]["reviews"]
            self.assertEqual([(x["finding"], x["status"], x["reviewer"]) for x in r], [("F1", "confirmed", "R. Engineer")])
        self.post(base + "/api/reviews", {"key": key, "status": "cleared"})
        self.assertEqual(json.loads(self.get(base + "/api/findings")[1])["x_readyset"]["reviews"], [])
        self.assertEqual(self.post(base + "/api/reviews", {"key": key, "status": "approved"})[0], 400)

    def waiting(self):
        """A server that knows the trusted release and waits for a new one, plus a changed release on disk."""
        from tests.tiny_release import N1, P1, PROTEIN, TinyRelease
        d = tempfile.mkdtemp()
        a = TinyRelease()
        trusted = a.write(os.path.join(d, "trusted"))
        new = a.copy().swap(PROTEIN, P1, N1).write(os.path.join(d, "hidden-release"))
        base = self.start(releases=(trusted, None), reviews=os.path.join(d, "reviews.json"), settings=None)
        return base, d, new

    def test_a_new_release_can_be_given_as_a_folder_path(self):
        base, _, new = self.waiting()
        self.assertEqual(json.loads(self.get(base + "/api/state")[1])["new"], None)
        self.assertIn("x_readyset", json.loads(self.get(base + "/api/findings")[1]))          # the example, until then
        status, state = self.post(base + "/api/release", {"path": new})
        self.assertEqual((status, state["new_name"]), (200, "hidden-release"))
        doc = json.loads(self.get(base + "/api/findings")[1])
        self.assertEqual((doc["verdict"], doc["findings"][0]["kind"]), ("Conditional", "sample_swap"))
        self.assertEqual(doc["data"]["releases"][1]["name"], "hidden-release")

    def test_a_new_release_can_be_dropped_as_a_zip_or_as_loose_files(self):
        import zipfile
        from control_tower.release import FILES
        base, d, new = self.waiting()
        zip_path = os.path.join(d, "from-the-judges.zip")
        with zipfile.ZipFile(zip_path, "w") as z:
            for f in os.listdir(new):
                z.write(os.path.join(new, f), os.path.join("some", "folder", f))               # nested, as zips often are
            z.writestr("../../escape.txt", "must never be written")
        def upload(name, path, batch):
            with open(path, "rb") as fh:
                req = urllib.request.Request(f"{base}/api/upload?batch={batch}&name={name}", data=fh.read(), method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status
        self.assertEqual(upload("from-the-judges.zip", zip_path, "batch-zip-0001"), 200)
        status, state = self.post(base + "/api/release", {"batch": "batch-zip-0001", "name": "from-the-judges.zip"})
        self.assertEqual((status, state["new_name"]), (200, "from-the-judges"))
        self.assertEqual(json.loads(self.get(base + "/api/findings")[1])["verdict"], "Conditional")
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(state["new"]), "..", "..", "escape.txt")))
        for f in FILES:                                                                         # the same release, file by file
            if os.path.isfile(os.path.join(new, f)):
                upload(f, os.path.join(new, f), "batch-files-0002")
        status, state = self.post(base + "/api/release", {"batch": "batch-files-0002", "name": "hidden-release"})
        self.assertEqual((status, state["new_name"]), (200, "hidden-release"))
        self.assertEqual(json.loads(self.get(base + "/api/findings")[1])["findings"][0]["kind"], "sample_swap")

    def test_two_releases_in_one_zip_are_refused_never_merged(self):
        import zipfile
        from tests.tiny_release import N2, P2, PROTEIN
        base, d, new = self.waiting()
        other = TinyReleaseAt(d, "other-release", lambda r: r.swap(PROTEIN, P2, N2))
        zip_path = os.path.join(d, "two.zip")
        with zipfile.ZipFile(zip_path, "w") as z:
            for folder in (new, other):
                for f in os.listdir(folder):
                    z.write(os.path.join(folder, f), os.path.join(os.path.basename(folder), f))
        status, body = self.post(base + "/api/release", {"path": zip_path})
        self.assertEqual(status, 400)
        self.assertIn("more than one release", body["detail"])
        self.assertNotIn(tempfile.gettempdir(), body["detail"])                   # no internal folders in the message
        both = os.path.join(d, "both")
        os.makedirs(both)
        for folder in (new, other):
            os.symlink(folder, os.path.join(both, os.path.basename(folder)))
        status, body = self.post(base + "/api/release", {"path": both})
        self.assertEqual(status, 400)
        self.assertIn("more than one release", body["detail"])
        self.assertEqual(json.loads(self.get(base + "/api/state")[1])["new"], None)   # nothing was loaded

    def test_the_trusted_release_cannot_be_given_as_the_new_one(self):
        base, d, _ = self.waiting()
        status, body = self.post(base + "/api/release", {"path": os.path.join(d, "trusted")})
        self.assertEqual(status, 400)
        self.assertIn("trusted release itself", body["detail"])

    def test_a_question_that_does_not_fit_is_answered_in_words_on_the_page_too(self):
        from tests.tiny_release import ER, PROTEIN
        bad = [{"id": "Q1", "type": "mean_by_group", "file": PROTEIN, "row": "NOPE", "column": ER, "groups": ["Positive", "Negative"]}]
        base, _ = self.live(question=bad)
        status, body, _ = self.get(base + "/api/findings")
        self.assertEqual(status, 400)
        self.assertIn("no row called NOPE", json.loads(body)["detail"])
        self.assertEqual(self.get(base + "/api/findings?for=A1")[0], 200)          # the registered ones still work

    def test_something_that_is_not_a_release_is_refused_in_plain_words(self):
        base, d, _ = self.waiting()
        empty = os.path.join(d, "empty")
        os.makedirs(empty)
        for bad in ({"path": empty}, {"path": os.path.join(d, "nope")}, {"batch": "../../etc"}):
            status, body = self.post(base + "/api/release", bad)
            self.assertEqual(status, 400, bad)
            self.assertTrue(body["detail"])
        req = urllib.request.Request(f"{base}/api/upload?batch=batch-bad-0003&name=passwords.txt", data=b"x", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=10)
        e.exception.close()
        self.assertEqual(e.exception.code, 400)

    def test_the_audit_report_says_the_same_things_in_plain_english(self):
        base, _ = self.live()
        doc = json.loads(self.get(base + "/api/findings")[1])
        key = doc["x_readyset"]["review_keys"]["F1"]
        self.post(base + "/api/reviews", {"key": key, "status": "confirmed", "reviewer": "R. Engineer", "role": "research engineer"})
        status, body, headers = self.get(base + "/api/report")
        page = body.decode()
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("audit-report.html", headers["Content-Disposition"])
        for expected in ("Release audit report", "Conditional", "Samples exchanged", "Proof you can check",
                         "What this cannot tell you", "Confirmed as a real problem by R. Engineer", "No language model wrote"):
            self.assertIn(expected, page)
        for sample in [e["id"] for e in doc["findings"][0]["evidence"] if e["kind"] == "sample"]:
            self.assertIn(sample, page)                                           # every sample in the finding is named
        self.assertIn("Ready", self.get(base + "/api/report?for=A2")[1].decode())  # the report follows the question

    def test_a_new_analysis_can_be_built_on_the_page_from_what_the_data_holds(self):
        from tests.tiny_release import ER, HISTOLOGY, PROTEIN
        base, _ = self.live()
        options = json.loads(self.get(base + "/api/options")[1])
        self.assertIn(ER, options["columns"])
        self.assertIn(PROTEIN, options["files"])
        self.assertEqual(json.loads(self.get(base + f"/api/options?file={PROTEIN}&q=her")[1])["rows"], ["HER2"])
        values = {v["value"] for v in json.loads(self.get(base + f"/api/options?column={ER}")[1])["values"]}
        self.assertTrue({"Positive", "Negative"} <= values)
        status, made = self.post(base + "/api/question", {"type": "mean_by_group", "title": "HER2 by ER status", "file": PROTEIN,
                                                          "row": "HER2", "column": ER, "groups": ["Positive", "Negative"]})
        self.assertEqual((status, made["id"]), (200, "Q1"))
        doc = json.loads(self.get(base + "/api/findings?for=A1,Q1")[1])
        self.assertEqual(doc["x_readyset"]["analyses_in_question"], ["A1", "Q1"])
        self.assertIn("Q1", [a["id"] for a in doc["x_readyset"]["live"]["available"]])
        self.assertEqual(next(a for a in doc["analyses"] if a["id"] == "Q1")["status"], "changed")   # the swap moves it too
        status, made = self.post(base + "/api/question", {"type": "category_mix", "column": HISTOLOGY})
        self.assertEqual((status, made["id"]), (200, "Q2"))
        status, body = self.post(base + "/api/question", {"type": "mean_by_group", "file": PROTEIN, "row": "NOPE", "column": ER,
                                                          "groups": ["Positive"]})
        self.assertEqual(status, 400)
        self.assertIn("no row called NOPE", body["detail"])

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
