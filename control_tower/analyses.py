"""The protected analyses, and the rule for whether a change touches each one.

A1 and A2 reproduce the organisers' `reference_analyses.py` so that "before" and "after" are numbers anyone can check
with their script. That script reads files with pandas, so two of its habits are copied here on purpose:
  - pandas treats a blank cell and words like "NA" or "null" as missing;
  - a sample whose value is missing still counts toward its group's size, but not toward the mean.

Each analysis also says which changes touch it. That is the whole of "affects A1 / does not affect A2".
"""
import math

from . import release
from .release import CLINICAL, PROTEIN, is_primary

ER = "breast_carcinoma_estrogen_receptor_status"
PAM50 = "PAM50Call_RNAseq"
ER_ROW = "ERALPHA"

# What pandas reads as a missing value by default.
PANDAS_MISSING = {"", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan", "1.#IND", "1.#QNAN", "<NA>",
                  "N/A", "NA", "NULL", "NaN", "None", "n/a", "nan", "null"}


class CannotRun(Exception):
    """An input the analysis needs is not in this release."""


def _missing(text):
    return text is None or text in PANDAS_MISSING


def _mean(values):
    return math.fsum(values) / len(values) if values else float("nan")


def _round(x, places):
    return None if x != x else round(x, places)


class A1:
    id = "A1"
    title = "ER-alpha protein by clinical ER status"
    files = [CLINICAL, PROTEIN]

    @staticmethod
    def inputs(folder):
        """(clinical table, protein sample ids, the ER-alpha row). Raises CannotRun when a needed piece is missing."""
        c, p = release.path_of(folder, CLINICAL), release.path_of(folder, PROTEIN)
        if not c or not p:
            raise CannotRun(f"{CLINICAL if not c else PROTEIN} is not in this release")
        columns, clinical = release.read_rows(c)
        if ER not in columns:
            raise CannotRun(f"the clinical column {ER} is not in this release")
        samples, row = release.one_row(p, ER_ROW)
        if row is None:
            raise CannotRun(f"the protein row {ER_ROW} is not in this release")
        return clinical, samples, row

    @classmethod
    def used(cls, folder):
        """The samples A1 reads in this release: primary tumours with protein data and a Positive or Negative ER status."""
        try:
            clinical, samples, _ = cls.inputs(folder)
        except (CannotRun, release.Unreadable, OSError, EOFError, UnicodeDecodeError):
            return set()
        return {s for s in samples if is_primary(s) and clinical.get(s, {}).get(ER) in ("Positive", "Negative")}

    @classmethod
    def run(cls, folder):
        clinical, samples, row = cls.inputs(folder)
        used = [s for s in samples if is_primary(s) and clinical.get(s, {}).get(ER) in ("Positive", "Negative")]
        groups = {"Positive": [], "Negative": []}
        sizes = {"Positive": 0, "Negative": 0}
        for s in used:
            status = clinical[s][ER]
            sizes[status] += 1
            if not _missing(row.get(s)):
                try:
                    groups[status].append(float(row[s]))
                except ValueError:
                    raise CannotRun(f"the {ER_ROW} value for {s} is not a number: {row[s]!r}")
        pos, neg = _mean(groups["Positive"]), _mean(groups["Negative"])
        return {"analysis": "A1", "inputs": [CLINICAL, PROTEIN], "n_samples": len(used),
                "n_positive": sizes["Positive"], "n_negative": sizes["Negative"],
                "mean_positive": _round(pos, 3), "mean_negative": _round(neg, 3),
                "difference": _round(pos - neg, 3), "n_ids_listed": len(used)}

    @staticmethod
    def touched_by(change, used, protein_samples):
        """Does this change reach a cell A1 reads? `used` and `protein_samples` are unions over both releases."""
        kind, file = change["scope"], change["file"]
        if kind == "file":
            return file in (CLINICAL, PROTEIN)
        if file == PROTEIN:
            if kind == "row":
                return change["key"] == ER_ROW
            if kind == "profile":
                return change["sample"] in used
            if kind == "cell":
                return change["key"] == ER_ROW and change["sample"] in used
        if file == CLINICAL:
            if kind == "column":
                return change["key"] == ER
            reaches = is_primary(change["sample"]) and change["sample"] in protein_samples
            if kind == "profile":
                return reaches
            if kind == "cell":
                return change["key"] == ER and reaches
        return False


class A2:
    id = "A2"
    title = "RNA subtype mix of primary tumours"
    files = [CLINICAL]

    @staticmethod
    def inputs(folder):
        c = release.path_of(folder, CLINICAL)
        if not c:
            raise CannotRun(f"{CLINICAL} is not in this release")
        columns, clinical = release.read_rows(c)
        if PAM50 not in columns:
            raise CannotRun(f"the clinical column {PAM50} is not in this release")
        return clinical

    @classmethod
    def used(cls, folder):
        try:
            clinical = cls.inputs(folder)
        except (CannotRun, release.Unreadable, OSError, EOFError, UnicodeDecodeError):
            return set()
        return {s for s, cells in clinical.items() if is_primary(s) and not _missing(cells.get(PAM50))}

    @classmethod
    def run(cls, folder):
        clinical = cls.inputs(folder)
        counts = {}
        for s, cells in clinical.items():
            if is_primary(s) and not _missing(cells.get(PAM50)):
                counts[cells[PAM50]] = counts.get(cells[PAM50], 0) + 1
        total = sum(counts.values())
        ordered = dict(sorted(counts.items()))
        return {"analysis": "A2", "inputs": [CLINICAL], "n_samples": total, "counts": ordered,
                "percent": {k: round(100 * v / total, 1) for k, v in ordered.items()}, "n_ids_listed": total}

    @staticmethod
    def touched_by(change, used, protein_samples):
        kind, file = change["scope"], change["file"]
        if file != CLINICAL:
            return False
        if kind == "file":
            return True
        if kind == "column":
            return change["key"] == PAM50
        if kind == "profile":
            return is_primary(change["sample"])
        if kind == "cell":
            return change["key"] == PAM50 and is_primary(change["sample"])
        return False


REGISTRY = [A1, A2]
