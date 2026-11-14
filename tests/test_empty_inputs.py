"""An empty file, a file with only its header, and an empty row must each give an answer, never a crash."""
import gzip
import os
import tempfile
import unittest

from control_tower.compare import compare
from tests.tiny_release import CLINICAL, MUTATION, PROTEIN, TinyRelease


def read(path):
    with (gzip.open(path, "rt") if path.endswith(".gz") else open(path)) as fh:
        return fh.read()


def write(path, text):
    with (gzip.open(path, "wt") if path.endswith(".gz") else open(path, "w")) as fh:
        fh.write(text)


class EmptyInputs(unittest.TestCase):
    def changed(self, file, change):
        d = tempfile.mkdtemp()
        a = TinyRelease()
        folder_a, folder_b = a.write(os.path.join(d, "A")), a.copy().write(os.path.join(d, "B"))
        path = os.path.join(folder_b, file)
        write(path, change(read(path)))
        return compare(folder_a, folder_b)

    def test_a_file_with_nothing_in_it_is_reported_and_the_verdict_is_insufficient_evidence(self):
        for file, empty in ((PROTEIN, ""), (PROTEIN, "\n\n"), (CLINICAL, ""), (MUTATION, "")):
            doc = self.changed(file, lambda text: empty)
            self.assertEqual(doc["verdict"], "Insufficient Evidence", (file, empty))
            self.assertEqual(len(doc["findings"]), 1)
            self.assertIn(f"{file} could not be read", doc["findings"][0]["summary"])
            self.assertIn("is empty", doc["findings"][0]["summary"])

    def test_a_zero_byte_gz_file_is_reported_too(self):
        d = tempfile.mkdtemp()
        a = TinyRelease()
        folder_a, folder_b = a.write(os.path.join(d, "A")), a.copy().write(os.path.join(d, "B"))
        open(os.path.join(folder_b, PROTEIN), "wb").close()
        doc = compare(folder_a, folder_b)
        self.assertEqual(doc["verdict"], "Insufficient Evidence")
        self.assertEqual(doc["findings"][0]["affects_analyses"], ["A1"])

    def test_a_file_with_only_its_header_reports_every_sample_or_row_gone(self):
        clinical = self.changed(CLINICAL, lambda text: text.split("\n")[0] + "\n")
        self.assertEqual([f["kind"] for f in clinical["findings"]], ["membership_change"])
        self.assertEqual(clinical["findings"][0]["affects_analyses"], ["A1", "A2"])
        protein = self.changed(PROTEIN, lambda text: text.split("\n")[0] + "\n")
        self.assertEqual(protein["verdict"], "Blocked")                  # the row A1 reads is gone
        self.assertIn("ERALPHA", protein["findings"][0]["summary"])

    def test_a_blank_line_changes_nothing(self):
        for file in (CLINICAL, PROTEIN):
            doc = self.changed(file, lambda text: text.replace("\n", "\n\n", 2))
            self.assertEqual((doc["verdict"], doc["findings"]), ("Ready", []), file)

    def test_a_row_whose_cells_are_all_blank_is_missing_data(self):
        def blank(text):
            lines = text.split("\n")
            return "\n".join("\t".join([l.split("\t")[0]] + [""] * l.count("\t")) if l.startswith("ERALPHA") else l for l in lines)
        doc = self.changed(PROTEIN, blank)
        self.assertEqual([(f["kind"], f["affects_analyses"]) for f in doc["findings"]], [("missing_data", ["A1"])])
        self.assertEqual(doc["verdict"], "Conditional")

    def test_a_row_that_is_only_its_name_is_missing_data_not_a_new_row(self):
        doc = self.changed(PROTEIN, lambda text: "\n".join("ERALPHA" if l.startswith("ERALPHA") else l for l in text.split("\n")))
        self.assertEqual([f["kind"] for f in doc["findings"]], ["missing_data"])
        self.assertNotIn("appeared", doc["findings"][0]["summary"])

    def test_a_sample_whose_clinical_row_is_all_blank_is_missing_data(self):
        def blank(text):
            lines = text.split("\n")
            lines[1] = "\t".join([lines[1].split("\t")[0]] + [""] * lines[1].count("\t"))
            return "\n".join(lines)
        doc = self.changed(CLINICAL, blank)
        self.assertTrue(doc["findings"])
        self.assertEqual({f["kind"] for f in doc["findings"]}, {"missing_data"})


if __name__ == "__main__":
    unittest.main()
