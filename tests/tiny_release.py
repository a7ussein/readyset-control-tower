"""A tiny, hand-made release with the same six files and the same layout as the event's TCGA-BRCA release.

Eight invented samples, three rows per molecular file. Small enough to read by eye, so every expected finding in the
detector tests can be checked by a person. None of these ids or values are real.

    a = TinyRelease()                      # the trusted release
    b = a.copy().swap("protein_rppa.tsv.gz", P1, N1)
    a.write(folder_a); b.write(folder_b)
"""
import copy
import csv
import gzip
import os

# Primary tumours (-01). P = ER-positive, N = ER-negative, U = ER status blank.
P1, P2, P3 = "TCGA-T1-0001-01", "TCGA-T1-0002-01", "TCGA-T1-0003-01"
N1, N2 = "TCGA-T1-0004-01", "TCGA-T1-0005-01"
U1 = "TCGA-T1-0006-01"
NORMAL = "TCGA-T1-0001-11"          # normal tissue from the same patient as P1
MET = "TCGA-T1-0007-06"             # a metastasis
NEW1, NEW2 = "TCGA-T1-0091-01", "TCGA-T1-0092-01"   # ids that are in no file of the trusted release

CLINICAL, SURVIVAL = "clinical.tsv", "survival.tsv"
PROTEIN, MUTATION = "protein_rppa.tsv.gz", "mutation_gene_level.tsv.gz"
COPY_NUMBER, RNA = "copy_number_gistic.tsv.gz", "rna_hiseq.tsv.gz"
FILES = [CLINICAL, SURVIVAL, MUTATION, PROTEIN, COPY_NUMBER, RNA]

ER, PAM50, HISTOLOGY = "breast_carcinoma_estrogen_receptor_status", "PAM50Call_RNAseq", "histological_type"

# With these values, analysis A1 on the trusted release is:
#   3 ER-positive (mean 2.0), 2 ER-negative (mean -0.9), difference 2.9
A1_BEFORE = {"n_samples": 5, "n_positive": 3, "n_negative": 2, "mean_positive": 2.0, "mean_negative": -0.9, "difference": 2.9}
# and analysis A2 is: LumA 3, Basal 2, Her2 1 of 6 subtyped primary tumours
A2_BEFORE = {"n_samples": 6, "counts": {"Basal": 2, "Her2": 1, "LumA": 3}, "percent": {"Basal": 33.3, "Her2": 16.7, "LumA": 50.0}}


class TinyRelease:
    def __init__(self):
        # files with one sample per ROW: {sample id: {column: text}}
        self.by_row = {
            CLINICAL: ("sampleID", [ER, PAM50, HISTOLOGY], {
                P1: {ER: "Positive", PAM50: "LumA", HISTOLOGY: "Ductal"},
                P2: {ER: "Positive", PAM50: "LumA", HISTOLOGY: "Ductal"},
                P3: {ER: "Positive", PAM50: "LumA", HISTOLOGY: "Lobular"},
                N1: {ER: "Negative", PAM50: "Basal", HISTOLOGY: "Ductal"},
                N2: {ER: "Negative", PAM50: "Basal", HISTOLOGY: "Ductal"},
                U1: {ER: "", PAM50: "Her2", HISTOLOGY: "Ductal"},
                NORMAL: {ER: "Positive", PAM50: "Normal", HISTOLOGY: ""},
                MET: {ER: "Positive", PAM50: "", HISTOLOGY: "Ductal"}}),
            # A tumour and a normal from one patient share a survival record: identical rows are NORMAL here.
            SURVIVAL: ("sample", ["_PATIENT", "OS", "OS.time"], {
                P1: {"_PATIENT": "TCGA-T1-0001", "OS": "0", "OS.time": "1200"},
                NORMAL: {"_PATIENT": "TCGA-T1-0001", "OS": "0", "OS.time": "1200"},
                P2: {"_PATIENT": "TCGA-T1-0002", "OS": "1", "OS.time": "640"},
                P3: {"_PATIENT": "TCGA-T1-0003", "OS": "0", "OS.time": "2100"},
                N1: {"_PATIENT": "TCGA-T1-0004", "OS": "1", "OS.time": "300"},
                N2: {"_PATIENT": "TCGA-T1-0005", "OS": "0", "OS.time": "900"},
                U1: {"_PATIENT": "TCGA-T1-0006", "OS": "0", "OS.time": "50"},
                MET: {"_PATIENT": "TCGA-T1-0007", "OS": "1", "OS.time": "410"}}),
        }
        # files with one sample per COLUMN: (name of the first header cell, row names, {sample id: [cell per row]})
        self.by_col = {
            PROTEIN: ("Sample_description", ["ERALPHA", "HER2", "PR"], {
                P1: ["2.2", "0.10", "1.1"], P2: ["2.0", "0.20", "1.3"], P3: ["1.8", "0.30", "0.9"],
                N1: ["-1.0", "0.40", "-0.5"], N2: ["-0.8", "0.50", "-0.7"], U1: ["0.5", "1.90", "0.2"],
                MET: ["1.5", "0.60", "0.8"]}),                                   # no normals, as in the real file
            MUTATION: ("sample", ["GATA3", "PIK3CA", "TP53"], {
                P1: ["0", "1", "0"], P2: ["1", "0", "0"], P3: ["0", "1", "1"],
                N1: ["0", "0", "1"], N2: ["1", "1", "1"], U1: ["0", "0", "0"]}),
            COPY_NUMBER: ("Gene Symbol", ["ERBB2", "MYC", "PTEN"], {
                P1: ["0", "1", "0"], P2: ["0", "0", "-1"], P3: ["1", "1", "0"],
                N1: ["0", "2", "-1"], N2: ["0", "1", "-2"], U1: ["2", "0", "0"]}),
            RNA: ("sample", ["ESR1", "ERBB2", "MKI67"], {
                P1: ["12.1", "9.0", "7.1"], P2: ["11.8", "9.2", "7.4"], P3: ["11.5", "9.1", "6.9"],
                N1: ["5.2", "9.3", "10.2"], N2: ["5.6", "9.4", "10.8"], U1: ["8.0", "14.1", "9.0"],
                NORMAL: ["9.9", "8.8", "4.0"], MET: ["11.0", "9.5", "9.9"]}),
        }
        self.absent = set()            # files left out of the folder altogether

    def copy(self):
        return copy.deepcopy(self)

    # ---- the kinds of change the organisers describe, and a few they do not ----
    def swap(self, file, x, y):
        """Two samples trade their whole profile inside one file."""
        t = self._samples(file)
        t[x], t[y] = t[y], t[x]
        return self

    def copy_as(self, file, source, new_id, replacing=None):
        """`new_id` appears carrying an exact copy of `source`'s profile; optionally `replacing` disappears."""
        t = self._samples(file)
        if replacing:
            del t[replacing]
        t[new_id] = copy.deepcopy(t[source])
        return self

    def rename(self, file, old, new):
        """`old` disappears and `new` appears carrying its profile."""
        t = self._samples(file)
        t[new] = t.pop(old)
        return self

    def remove(self, file, sample):
        del self._samples(file)[sample]
        return self

    def relabel(self, column, sample, value, file=CLINICAL):
        self.by_row[file][2][sample][column] = value
        return self

    def set_cell(self, file, row, sample, value):
        name, rows, table = self.by_col[file]
        table[sample][rows.index(row)] = value
        return self

    def drop_row(self, file, row):
        name, rows, table = self.by_col[file]
        i = rows.index(row)
        rows.pop(i)
        for cells in table.values():
            cells.pop(i)
        return self

    def reorder_columns(self, file):
        name, rows, table = self.by_col[file]
        self.by_col[file] = (name, rows, dict(reversed(list(table.items()))))
        return self

    def without_file(self, file):
        self.absent.add(file)
        return self

    def _samples(self, file):
        return (self.by_row[file] if file in self.by_row else self.by_col[file])[2]

    # ---- writing ----
    def write(self, folder):
        os.makedirs(folder, exist_ok=True)
        for file in FILES:
            if file in self.absent:
                continue
            opener = gzip.open if file.endswith(".gz") else open
            with opener(os.path.join(folder, file), "wt", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh, delimiter="\t", lineterminator="\n")
                if file in self.by_row:
                    key, columns, table = self.by_row[file]
                    w.writerow([key] + columns)
                    for sample, cells in table.items():
                        w.writerow([sample] + [cells[c] for c in columns])
                else:
                    name, rows, table = self.by_col[file]
                    w.writerow([name] + list(table))
                    for i, row in enumerate(rows):
                        w.writerow([row] + [cells[i] for cells in table.values()])
        return folder
