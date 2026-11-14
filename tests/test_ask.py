"""The assistant answers from the findings and nothing else, the same way every time."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from control_tower.ask import ask, consistency, understand
from control_tower.compare import compare
from tests.tiny_release import N1, P1, PROTEIN, TinyRelease

ME = {"name": "R. Engineer", "role": "research engineer"}
QUESTIONS = ["Can I use the new release?", "What changed?", "Why does it matter for my results?", "What should I do next?",
             "What can the tool not tell me?", "Which samples are involved?", "How serious is each change?",
             "Who has reviewed the changes?", "Are you an AI model? Will you give the same answer next time?",
             "Which files were compared?", "What is the weather in Boston?", "Will this patient survive?", "confirm F1"]


class Ask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = tempfile.mkdtemp()
        a = TinyRelease()
        cls.folders = a.write(os.path.join(d, "A")), a.copy().swap(PROTEIN, P1, N1).write(os.path.join(d, "B"))
        cls.doc = compare(*cls.folders)
        cls.same = compare(cls.folders[0], cls.folders[0])

    def test_the_same_question_gives_the_same_answer_every_time(self):
        for q in QUESTIONS:
            self.assertEqual(consistency(self.doc, q, 200, ME)["different_answers"], 1, q)

    def test_a_separate_run_of_the_program_gives_the_same_answer_too(self):
        code = ("import json,sys;from control_tower.compare import compare;from control_tower.ask import ask;"
                "d=compare(sys.argv[1],sys.argv[2]);[d['x_readyset'].pop(k,None) for k in ('generated_at','run_seconds')];"
                "print(json.dumps([ask(d,q)['fingerprint'] for q in json.loads(sys.argv[3])]))")
        runs = {subprocess.run([sys.executable, "-c", code, *self.folders, json.dumps(QUESTIONS)], capture_output=True, text=True,
                               env={**os.environ, "PYTHONHASHSEED": seed}).stdout for seed in ("0", "1", "12345")}
        self.assertEqual(len(runs), 1)
        self.assertEqual(len(json.loads(runs.pop())), len(QUESTIONS))

    def test_different_wording_of_one_question_gives_the_same_answer(self):
        prints = {ask(self.doc, q)["fingerprint"] for q in ("Is it safe to use?", "can I use this release", "CAN I USE IT??", "ok to use")}
        self.assertEqual(len(prints), 1)

    def test_the_answer_changes_only_when_the_findings_change(self):
        self.assertNotEqual(ask(self.doc, "Can I use it?")["fingerprint"], ask(self.same, "Can I use it?")["fingerprint"])
        self.assertTrue(ask(self.doc, "Can I use it?")["answer"][0].startswith("Not yet."))
        self.assertTrue(ask(self.same, "Can I use it?")["answer"][0].startswith("Yes."))

    def test_every_answer_carries_a_trace_down_to_the_file_and_the_samples(self):
        reply = ask(self.doc, "why does the swap matter?")
        steps = [t["step"] for t in reply["trace"]]
        self.assertEqual(steps[0], "Read the question")
        self.assertEqual(steps[-1], "Wrote the answer")
        evidence = next(t["detail"] for t in reply["trace"] if t["step"] == "Evidence")
        for part in (PROTEIN, P1, N1):
            self.assertIn(part, evidence)
        self.assertEqual(reply["sources"][0]["samples"], sorted([P1, N1]))

    def test_it_says_so_when_it_cannot_answer_and_refuses_a_clinical_question(self):
        off = ask(self.doc, "What is the weather in Boston?")
        self.assertEqual((off["can_answer"], off["intent"]), (False, None))
        self.assertIn("I cannot answer that from this comparison", off["answer"][0])
        clinical = ask(self.doc, "Should this patient's treatment change?")
        self.assertEqual(clinical["intent"], "clinical")
        self.assertIn("no clinical claims", clinical["answer"][0])

    def test_it_acts_only_in_a_named_persons_name_and_records_nothing_itself(self):
        nobody = ask(self.doc, "confirm F1")
        self.assertIsNone(nobody["action"])
        self.assertIn("named person", nobody["answer"][0])
        mine = ask(self.doc, "approve the fix for F1", ME)
        self.assertEqual((mine["action"]["finding"], mine["action"]["status"], mine["action"]["fix"], mine["action"]["reviewer"],
                          mine["action"]["role"]), ("F1", "confirmed", "approved", "R. Engineer", "research engineer"))
        self.assertIn("Nothing is recorded until you press the button", mine["answer"][-1])
        self.assertEqual(self.doc["findings"][0]["needs_human_review"], True)          # asking changed nothing

    def test_understanding_a_question_uses_no_randomness(self):
        self.assertEqual({understand("why is it rated high?")[0] for _ in range(50)}, {"severity"})


if __name__ == "__main__":
    unittest.main()
