"""The command a judge or a script runs: compare two folders, write findings.json, exit with the verdict."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from tests.tiny_release import N1, P1, PROTEIN, RNA, TinyRelease

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Command(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.a = TinyRelease().write(os.path.join(self.d, "A"))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "control_tower", *args], capture_output=True, text=True, cwd=HERE)

    def release(self, name, change):
        return change(TinyRelease()).write(os.path.join(self.d, name))

    def test_it_writes_the_findings_file_and_exits_with_the_verdict(self):
        b = self.release("B", lambda r: r.swap(PROTEIN, P1, N1))
        out = os.path.join(self.d, "findings.json")
        p = self.run_cli("compare", self.a, b, "--out", out)
        self.assertEqual(p.returncode, 1, p.stderr)                      # 1 = Conditional
        doc = json.load(open(out))
        self.assertEqual((doc["verdict"], doc["findings"][0]["kind"]), ("Conditional", "sample_swap"))
        self.assertIn("Conditional", p.stdout)
        self.assertEqual([r["name"] for r in doc["data"]["releases"]], ["A", "B"])

    def test_it_can_also_write_the_plain_english_audit_report(self):
        b = self.release("B", lambda r: r.swap(PROTEIN, P1, N1))
        out, report = os.path.join(self.d, "findings.json"), os.path.join(self.d, "audit.html")
        p = self.run_cli("compare", self.a, b, "--out", out, "--report", report, "--for", "A1")
        self.assertEqual(p.returncode, 1, p.stderr)
        with open(report, encoding="utf-8") as fh:
            page = fh.read()
        for expected in ("Release audit report", "Conditional", P1, N1, "Not yet reviewed", "Suggested fix"):
            self.assertIn(expected, page)
        self.assertEqual(self.run_cli("compare", self.a, b, "--report").returncode, 64)

    def test_the_envelope_command_opens_compares_and_writes_both_reports(self):
        # A stand-in for the organisers' repository: release A, and an unseal.py that "opens" an envelope into a folder.
        repo = os.path.join(self.d, "challenge")
        TinyRelease().write(os.path.join(repo, "data", "tcga-brca", "raw"))
        sealed = TinyRelease().swap(PROTEIN, P1, N1).without_file(RNA).write(os.path.join(repo, "sealed"))
        os.makedirs(os.path.join(repo, "envelopes"))
        with open(os.path.join(repo, "envelopes", "unseal.py"), "w") as fh:
            fh.write("import shutil, sys\n"
                     "if sys.argv[2:] != ['amber', 'falcon', 'river', 'quartz']: sys.exit('that code does not open it')\n"
                     f"shutil.copytree({sealed!r}, 'envelopes/opened/E' + sys.argv[1] + '/release')\n")
        work = os.path.join(self.d, "work")
        os.makedirs(work)
        env = dict(os.environ, PYTHONPATH=HERE, PATH=os.path.dirname(sys.executable))        # no uv: use this Python
        run = lambda *args: subprocess.run([sys.executable, "-m", "control_tower", "envelope", *args, "--challenge", repo, "--port", "1"],
                                           capture_output=True, text=True, cwd=work, env=env)
        bad = run("07", "wrong", "words", "entirely", "here")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("did not open", bad.stderr)
        p = run("07", "amber", "falcon", "river", "quartz")
        self.assertEqual(p.returncode, 1, p.stderr)                                           # Conditional
        with open(os.path.join(work, "findings.json")) as fh:
            doc = json.load(fh)
        self.assertEqual(([f["kind"] for f in doc["findings"]], doc["data"]["releases"][1]["name"]), (["sample_swap"], "E07"))
        self.assertTrue(os.path.isfile(os.path.join(work, "audit-report.html")))
        self.assertIn("page is not running", p.stdout)

    def test_exit_codes_for_the_other_verdicts(self):
        out = os.path.join(self.d, "f.json")
        self.assertEqual(self.run_cli("compare", self.a, self.release("same", lambda r: r), "--out", out).returncode, 0)
        self.assertEqual(self.run_cli("compare", self.a, self.release("norow", lambda r: r.drop_row(PROTEIN, "ERALPHA")), "--out", out).returncode, 2)
        self.assertEqual(self.run_cli("compare", self.a, self.release("nofile", lambda r: r.without_file(PROTEIN)), "--out", out).returncode, 3)
        self.assertEqual(self.run_cli("compare", self.a, self.release("norna", lambda r: r.without_file(RNA)), "--out", out).returncode, 0)

    def test_a_folder_that_does_not_exist_is_a_plain_error(self):
        p = self.run_cli("compare", self.a, os.path.join(self.d, "nowhere"))
        self.assertEqual(p.returncode, 64)
        self.assertIn("is not a folder", p.stderr)
        self.assertNotIn("Traceback", p.stderr)

    def test_a_file_that_is_not_a_table_gives_insufficient_evidence_not_a_crash(self):
        b = self.release("broken", lambda r: r.swap(PROTEIN, P1, N1))
        with open(os.path.join(b, PROTEIN), "wb") as fh:
            fh.write(b"this is not gzip")
        out = os.path.join(self.d, "f.json")
        p = self.run_cli("compare", self.a, b, "--out", out)
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(json.load(open(out))["verdict"], "Insufficient Evidence")

    def test_two_folders_with_the_same_name_are_called_a_and_b(self):
        other = os.path.join(self.d, "elsewhere", "A")
        TinyRelease().swap(PROTEIN, P1, N1).write(other)
        out = os.path.join(self.d, "f.json")
        self.run_cli("compare", self.a, other, "--out", out)
        self.assertEqual([r["name"] for r in json.load(open(out))["data"]["releases"]], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
