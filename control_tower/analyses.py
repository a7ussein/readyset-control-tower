"""The protected analyses, and the rule for whether a change touches each one.

An analysis is the research question the release is needed for. There are two shapes, and both A1 and A2 are plain
instances of them, so a new question is a few lines of JSON and no new code (see `from_spec`):
  MeanByGroup  the mean of one row of a measurement file, split by a clinical column     (A1)
  CategoryMix  how primary tumours divide among the values of a clinical column          (A2)

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


class MeanByGroup:
    """The mean of one named row of a measurement file, for primary tumours, split by the groups of a clinical column."""
    kind = "mean_by_group"

    def __init__(self, id, title, file, row, column, groups):
        self.id, self.title, self.file, self.row, self.column, self.groups = id, title, file, row, column, list(groups)
        self.files = [CLINICAL, file]

    def reads(self):
        return (f"the {self.row} row of {self.file} and the {self.column} column of {CLINICAL}, for primary tumours "
                f"whose value there is {' or '.join(self.groups)}")

    def inputs(self, folder):
        """(clinical table, the file's sample ids, the row). Raises CannotRun when a needed piece is missing."""
        c, p = release.path_of(folder, CLINICAL), release.path_of(folder, self.file)
        if not c or not p:
            raise CannotRun(f"{CLINICAL if not c else self.file} is not in this release")
        columns, clinical = release.read_rows(c)
        if self.column not in columns:
            raise CannotRun(f"the clinical column {self.column} is not in this release")
        samples, row = release.one_row(p, self.row)
        if row is None:
            raise CannotRun(f"the row {self.row} is not in {self.file} in this release")
        return clinical, samples, row

    def _used(self, clinical, samples):
        return [s for s in samples if is_primary(s) and clinical.get(s, {}).get(self.column) in self.groups]

    def used(self, folder):
        """The samples this analysis reads in this release."""
        try:
            clinical, samples, _ = self.inputs(folder)
        except (CannotRun, release.Unreadable, OSError, EOFError, UnicodeDecodeError):
            return set()
        return set(self._used(clinical, samples))

    def file_samples(self, folder):
        """Every sample id in the measurement file, read or not."""
        path = release.path_of(folder, self.file)
        try:
            return set(release.header_of(path)[1:]) if path else set()
        except (OSError, EOFError, UnicodeDecodeError, StopIteration):
            return set()

    def run(self, folder):
        clinical, samples, row = self.inputs(folder)
        used = self._used(clinical, samples)
        values = {g: [] for g in self.groups}
        sizes = {g: 0 for g in self.groups}
        for s in used:
            group = clinical[s][self.column]
            sizes[group] += 1
            if not _missing(row.get(s)):
                try:
                    values[group].append(float(row[s]))
                except ValueError:
                    raise CannotRun(f"the {self.row} value for {s} is not a number: {row[s]!r}")
        key = {g: g.lower().replace(" ", "_") for g in self.groups}
        out = {"analysis": self.id, "inputs": list(self.files), "n_samples": len(used)}
        out.update({f"n_{key[g]}": sizes[g] for g in self.groups})
        means = {g: _mean(values[g]) for g in self.groups}
        out.update({f"mean_{key[g]}": _round(means[g], 3) for g in self.groups})
        if len(self.groups) == 2:
            out["difference"] = _round(means[self.groups[0]] - means[self.groups[1]], 3)
        out["n_ids_listed"] = len(used)
        return out

    def touched_by(self, change, used, file_samples):
        """Does this change reach a cell the analysis reads? `used` and `file_samples` are unions over both releases."""
        kind, file = change["scope"], change["file"]
        if kind == "file":
            return file in self.files
        if file == self.file:
            if kind == "row":
                return change["key"] == self.row
            if kind == "profile":
                return change["sample"] in used
            if kind == "cell":
                return change["key"] == self.row and change["sample"] in used
        if file == CLINICAL:
            if kind == "column":
                return change["key"] == self.column
            reaches = is_primary(change["sample"]) and change["sample"] in file_samples
            if kind == "profile":
                return reaches
            if kind == "cell":
                return change["key"] == self.column and reaches
        return False


class CategoryMix:
    """How primary tumours divide among the values of one clinical column."""
    kind = "category_mix"

    def __init__(self, id, title, column):
        self.id, self.title, self.column = id, title, column
        self.file, self.row, self.files = CLINICAL, None, [CLINICAL]

    def reads(self):
        return f"the {self.column} column of {CLINICAL}, for primary tumours that have a value there"

    def inputs(self, folder):
        c = release.path_of(folder, CLINICAL)
        if not c:
            raise CannotRun(f"{CLINICAL} is not in this release")
        columns, clinical = release.read_rows(c)
        if self.column not in columns:
            raise CannotRun(f"the clinical column {self.column} is not in this release")
        return clinical

    def used(self, folder):
        try:
            clinical = self.inputs(folder)
        except (CannotRun, release.Unreadable, OSError, EOFError, UnicodeDecodeError):
            return set()
        return {s for s, cells in clinical.items() if is_primary(s) and not _missing(cells.get(self.column))}

    def file_samples(self, folder):
        return set()

    def run(self, folder):
        clinical = self.inputs(folder)
        counts = {}
        for s, cells in clinical.items():
            if is_primary(s) and not _missing(cells.get(self.column)):
                counts[cells[self.column]] = counts.get(cells[self.column], 0) + 1
        total = sum(counts.values())
        ordered = dict(sorted(counts.items()))
        return {"analysis": self.id, "inputs": [CLINICAL], "n_samples": total, "counts": ordered,
                "percent": {k: round(100 * v / total, 1) for k, v in ordered.items()} if total else {},
                "n_ids_listed": total}

    def touched_by(self, change, used, file_samples):
        kind, file = change["scope"], change["file"]
        if file != CLINICAL:
            return False
        if kind == "file":
            return True
        if kind == "column":
            return change["key"] == self.column
        if kind == "profile":
            return is_primary(change["sample"])
        if kind == "cell":
            return change["key"] == self.column and is_primary(change["sample"])
        return False


A1 = MeanByGroup("A1", "ER-alpha protein by clinical ER status", PROTEIN, ER_ROW, ER, ("Positive", "Negative"))
A2 = CategoryMix("A2", "RNA subtype mix of primary tumours", PAM50)
REGISTRY = [A1, A2]


class BadQuestion(Exception):
    """The question names an analysis that does not exist, or describes one that cannot be built."""


def from_spec(spec):
    """An analysis from a small description: a registered id ("A1"), or a dict for a new one.

        {"id": "Q1", "type": "mean_by_group", "title": "HER2 protein by PR status",
         "file": "protein_rppa.tsv.gz", "row": "HER2", "column": "PR_Status_nature2012", "groups": ["Positive", "Negative"]}
        {"id": "Q2", "type": "category_mix", "title": "Histology mix", "column": "histological_type"}
    """
    known = {a.id: a for a in REGISTRY}
    if isinstance(spec, str):
        if spec not in known:
            raise BadQuestion(f"there is no analysis called {spec}; the registered ones are {', '.join(known)}")
        return known[spec]
    if not isinstance(spec, dict):
        raise BadQuestion("an analysis is a registered id or an object")
    if set(spec) == {"id"} and spec["id"] in known:
        return known[spec["id"]]
    try:
        kind, ident = spec["type"], str(spec["id"])
        if ident in known:
            raise BadQuestion(f"{ident} is already the name of a registered analysis; pick another id")
        if kind == "mean_by_group":
            groups = [str(g) for g in spec["groups"]]
            if not groups:
                raise BadQuestion(f"{ident} needs at least one group")
            if spec["file"] not in release.FILES or spec["file"] == CLINICAL:
                raise BadQuestion(f"{ident}: file must be one of the measurement files, not {spec['file']!r}")
            return MeanByGroup(ident, str(spec.get("title") or f"{spec['row']} by {spec['column']}"), spec["file"],
                               str(spec["row"]), str(spec["column"]), groups)
        if kind == "category_mix":
            return CategoryMix(ident, str(spec.get("title") or f"Mix of {spec['column']}"), str(spec["column"]))
    except KeyError as e:
        raise BadQuestion(f"an analysis description is missing {e.args[0]!r}")
    raise BadQuestion(f"unknown analysis type {spec.get('type')!r}; use mean_by_group or category_mix")


def question(specs=None):
    """The list of analyses a run protects. None means every registered one."""
    if specs is None:
        return list(REGISTRY)
    chosen = [from_spec(s) for s in specs]
    if not chosen:
        raise BadQuestion("the question names no analysis")
    ids = [a.id for a in chosen]
    if len(set(ids)) != len(ids):
        raise BadQuestion("the question names the same analysis twice")
    return chosen
