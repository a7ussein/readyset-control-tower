"""An empty file, a file with only its header, and an empty row must each give an answer, never a crash."""
import gzip
import json
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

    def test_a_table_saved_by_another_program_is_still_read(self):
        # Spreadsheets and editors re-save text in other encodings, and files get packed or unpacked under the same name.
        def as_bytes(encode):
            def change(folder, file):
                path = os.path.join(folder, file)
                with (gzip.open(path, "rb") if path.endswith(".gz") else open(path, "rb")) as fh:
                    raw = fh.read()
                with open(path, "wb") as fh:
                    fh.write(encode(raw))
            return change
        cases = {"Windows-1252": (CLINICAL, lambda raw: raw.decode("utf-8").encode("cp1252")),
                 "UTF-16": (CLINICAL, lambda raw: raw.decode("utf-8").encode("utf-16")),
                 "UTF-8 with a byte-order mark": (CLINICAL, lambda raw: b"\xef\xbb\xbf" + raw),
                 "packed under a plain name": (CLINICAL, gzip.compress),
                 "unpacked under a .gz name": (PROTEIN, lambda raw: raw)}
        for name, (file, encode) in cases.items():
            d = tempfile.mkdtemp()
            a = TinyRelease()
            folder_a, folder_b = a.write(os.path.join(d, "A")), a.copy().write(os.path.join(d, "B"))
            as_bytes(encode)(folder_b, file)
            doc = compare(folder_a, folder_b)
            self.assertEqual((doc["verdict"], doc["findings"]), ("Ready", []), name)

    def workbook(self, tsv_path, out):
        """A minimal Excel workbook holding the same table, written the way a spreadsheet program stores it."""
        import csv, zipfile
        with open(tsv_path, encoding="utf-8") as fh:
            rows = list(csv.reader(fh, delimiter="\t"))
        shared, index = [], {}
        def ref(r, c):
            col, n = "", c + 1
            while n:
                n, rem = divmod(n - 1, 26)
                col = chr(65 + rem) + col
            return f"{col}{r + 1}"
        def cell(r, c, v):
            if v == "":
                return ""                                             # a workbook simply leaves an empty cell out
            index.setdefault(v, len(shared)) == len(shared) and shared.append(v)
            return f'<c r="{ref(r, c)}" t="s"><v>{index[v]}</v></c>'
        main = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        sheet = f"<worksheet {main}><sheetData>" + "".join(
            f'<row r="{r + 1}">' + "".join(cell(r, c, v) for c, v in enumerate(row)) + "</row>" for r, row in enumerate(rows)) + "</sheetData></worksheet>"
        strings = f"<sst {main}>" + "".join(f"<si><t>{v.replace('&', '&amp;').replace('<', '&lt;')}</t></si>" for v in shared) + "</sst>"
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("xl/workbook.xml", "<workbook/>")
            z.writestr("xl/worksheets/sheet1.xml", sheet)
            z.writestr("xl/sharedStrings.xml", strings)

    def test_a_table_saved_as_a_workbook_or_as_comma_separated_text_is_still_read(self):
        # Opening a .tsv on a Mac or in Excel and saving it gives a workbook or a .csv. It is still the same table.
        import csv
        def as_workbook(folder, keep_name):
            path = os.path.join(folder, CLINICAL)
            self.workbook(path, path + ".x")
            os.remove(path)
            os.replace(path + ".x", path if keep_name else os.path.join(folder, "clinical.xlsx"))
        def as_commas(folder, keep_name):
            path = os.path.join(folder, CLINICAL)
            with open(path, encoding="utf-8") as fh:
                rows = list(csv.reader(fh, delimiter="\t"))
            os.remove(path)
            with open(path if keep_name else os.path.join(folder, "clinical.csv"), "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerows(rows)
        for save in (as_workbook, as_commas):
            for keep_name in (True, False):
                d = tempfile.mkdtemp()
                a = TinyRelease()
                folder_a, folder_b = a.write(os.path.join(d, "A")), a.copy().write(os.path.join(d, "B"))
                save(folder_b, keep_name)
                doc = compare(folder_a, folder_b)
                self.assertEqual((doc["verdict"], doc["findings"]), ("Ready", []), (save.__name__, keep_name))
        # and a change made in the spreadsheet is found like any other
        d = tempfile.mkdtemp()
        a = TinyRelease()
        folder_a, folder_b = a.write(os.path.join(d, "A")), a.copy().relabel("PAM50Call_RNAseq", "TCGA-T1-0001-01", "Basal").write(os.path.join(d, "B"))
        as_workbook(folder_b, True)
        self.assertEqual([f["kind"] for f in compare(folder_a, folder_b)["findings"]], ["label_conflict"])

    def test_a_file_that_cannot_be_read_as_a_table_is_refused_in_plain_words(self):
        import zipfile
        def numbers(path):
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("Index/Document.iwa", "x")
        def other_zip(path):
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("notes.txt", "x")
        for make, words in ((numbers, "In Numbers choose File, Export To"), (other_zip, "is a zip, not a table")):
            d = tempfile.mkdtemp()
            a = TinyRelease()
            folder_a, folder_b = a.write(os.path.join(d, "A")), a.copy().write(os.path.join(d, "B"))
            make(os.path.join(folder_b, CLINICAL))
            doc = compare(folder_a, folder_b)
            self.assertEqual(doc["verdict"], "Insufficient Evidence")
            self.assertIn(words, doc["findings"][0]["summary"])
            self.assertNotIn("codec", json.dumps(doc))                          # no programmer's error text reaches the page


if __name__ == "__main__":
    unittest.main()
