"""The tiny release itself must be right, or every detector test built on it means nothing."""
import csv
import gzip
import os
import tempfile
import unittest

from tests.tiny_release import (A1_BEFORE, A2_BEFORE, CLINICAL, ER, FILES, N1, NEW1, N2, NORMAL, P1, PAM50, PROTEIN,
                                SURVIVAL, TinyRelease)


def read(folder, file):
    opener = gzip.open if file.endswith(".gz") else open
    with opener(os.path.join(folder, file), "rt", newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh, delimiter="\t"))


class Tiny(unittest.TestCase):
    def setUp(self):
        self.folder = TinyRelease().write(tempfile.mkdtemp())

    def test_it_writes_the_six_files_in_the_real_layout(self):
        self.assertEqual(sorted(os.listdir(self.folder)), sorted(FILES))
        self.assertEqual(read(self.folder, CLINICAL)[0][0], "sampleID")              # one sample per row
        self.assertEqual(read(self.folder, SURVIVAL)[0][0], "sample")                # one sample per row
        protein = read(self.folder, PROTEIN)
        self.assertEqual(protein[0][0], "Sample_description")                        # one sample per column
        self.assertTrue(all(h.startswith("TCGA-") and len(h) == 15 for h in protein[0][1:]))
        self.assertNotIn(NORMAL, protein[0])                                         # no normals in the protein file

    def test_the_stated_a1_and_a2_results_are_what_the_files_hold(self):
        clinical = {r[0]: dict(zip(read(self.folder, CLINICAL)[0][1:], r[1:])) for r in read(self.folder, CLINICAL)[1:]}
        protein = read(self.folder, PROTEIN)
        era = dict(zip(protein[0][1:], next(r for r in protein if r[0] == "ERALPHA")[1:]))
        used = [s for s in era if s[13:15] == "01" and clinical[s][ER] in ("Positive", "Negative")]
        pos = [float(era[s]) for s in used if clinical[s][ER] == "Positive"]
        neg = [float(era[s]) for s in used if clinical[s][ER] == "Negative"]
        got = {"n_samples": len(used), "n_positive": len(pos), "n_negative": len(neg),
               "mean_positive": round(sum(pos) / len(pos), 3), "mean_negative": round(sum(neg) / len(neg), 3),
               "difference": round(sum(pos) / len(pos) - sum(neg) / len(neg), 3)}
        self.assertEqual(got, A1_BEFORE)
        subtypes = [c[PAM50] for s, c in clinical.items() if s[13:15] == "01" and c[PAM50]]
        self.assertEqual({k: subtypes.count(k) for k in sorted(set(subtypes))}, A2_BEFORE["counts"])
        self.assertEqual(len(subtypes), A2_BEFORE["n_samples"])

    def test_a_tumour_and_its_normal_share_a_survival_row_as_in_the_real_release(self):
        rows = {r[0]: r[1:] for r in read(self.folder, SURVIVAL)[1:]}
        self.assertEqual(rows[P1], rows[NORMAL])

    def test_changes_alter_the_copy_and_never_the_original(self):
        a = TinyRelease()
        b = a.copy().swap(PROTEIN, P1, N1).copy_as(PROTEIN, P1, NEW1, replacing=N2)
        self.assertEqual(a.by_col[PROTEIN][2][P1], ["2.2", "0.10", "1.1"])
        self.assertEqual(b.by_col[PROTEIN][2][P1], ["-1.0", "0.40", "-0.5"])
        self.assertEqual(len(a.by_col[PROTEIN][2]), len(b.by_col[PROTEIN][2]))       # same count, different members


if __name__ == "__main__":
    unittest.main()
