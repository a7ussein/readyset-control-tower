"""Reading a release: the six files, their content hashes, and a fingerprint for every sample.

A release is a folder holding up to six files. Two of them have one sample per ROW (clinical, survival); the other
four have one sample per COLUMN and are large. Nothing here assumes which is which: the layout is worked out from
where the TCGA sample ids are.

Cells are read as their exact text. Nothing is parsed as a number, and a blank stays different from "NA".

The large files are never held in memory. They are read in passes:
  row_names()     only the first cell of each line
  fingerprints()  one running hash per sample, over the rows both releases share
  cells()         the actual cells, for a named handful of samples
"""
import csv
import gzip
import hashlib
import os

FILES = ["clinical.tsv", "survival.tsv", "mutation_gene_level.tsv.gz", "protein_rppa.tsv.gz",
         "copy_number_gistic.tsv.gz", "rna_hiseq.tsv.gz"]
CLINICAL, SURVIVAL, PROTEIN = "clinical.tsv", "survival.tsv", "protein_rppa.tsv.gz"

# A profile made only of these holds no information, so it gets no fingerprint (two empty samples are not copies).
EMPTY = {"", "NA", "NaN", "nan", "null", "NULL", "N/A"}

csv.field_size_limit(1 << 30)


class Unreadable(Exception):
    """A file exists but cannot be read as a table."""


def path_of(folder, name):
    p = os.path.join(folder, name)
    return p if os.path.isfile(p) else None


def _open_bytes(path):
    return gzip.open(path, "rb") if path.endswith(".gz") else open(path, "rb")


def _open_text(path):
    return gzip.open(path, "rt", newline="", encoding="utf-8") if path.endswith(".gz") \
        else open(path, "r", newline="", encoding="utf-8")


def content_hash(path):
    """SHA-256 of the decompressed content, so a re-compressed but identical file does not look changed."""
    h = hashlib.sha256()
    try:
        with _open_bytes(path) as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except (OSError, EOFError) as e:
        raise Unreadable(f"{os.path.basename(path)} could not be read: {e}")
    return h.hexdigest()


def is_sample_id(text):
    return isinstance(text, str) and text.startswith("TCGA-") and len(text) >= 15


def sample_type(sample_id):
    return sample_id[13:15]


def is_primary(sample_id):
    return sample_type(sample_id) == "01"


def layout(path):
    """'row' when each line is a sample, 'column' when each column is one. Decided by where the sample ids are."""
    try:
        with _open_text(path) as fh:
            reader = csv.reader(fh, delimiter="\t")
            header = next(reader, None)
            first = next(reader, None)
    except (OSError, EOFError, UnicodeDecodeError, csv.Error) as e:
        raise Unreadable(f"{os.path.basename(path)} could not be read: {e}")
    if not header:
        raise Unreadable(f"{os.path.basename(path)} is empty")
    if any(is_sample_id(h) for h in header[1:]):
        return "column"
    if first and is_sample_id(first[0]):
        return "row"
    if first is None:
        return "column" if len(header) > 1 else "row"
    raise Unreadable(f"{os.path.basename(path)}: no TCGA sample ids in the header or the first column")


# ------------------------------------------------------------------ files with one sample per row --
def read_rows(path):
    """(column names without the id column, {sample id: {column: text}}) for a small sample-per-row file."""
    try:
        with _open_text(path) as fh:
            reader = csv.reader(fh, delimiter="\t")
            header = next(reader)
            columns = header[1:]
            table = {}
            for line in reader:
                if not line:
                    continue
                cells = line[1:] + [""] * (len(columns) - len(line) + 1)
                table[line[0]] = dict(zip(columns, cells))
    except (OSError, EOFError, UnicodeDecodeError, csv.Error, StopIteration) as e:
        raise Unreadable(f"{os.path.basename(path)} could not be read: {e}")
    return columns, table


def row_fingerprints(table, columns):
    """{sample id: fingerprint or None} over the given columns."""
    out = {}
    ordered = sorted(columns)
    for sample, cells in table.items():
        values = [cells.get(c, "") for c in ordered]
        if all(v in EMPTY for v in values):
            out[sample] = None
        else:
            out[sample] = hashlib.blake2b("\x1f".join(values).encode(), digest_size=16).hexdigest()
    return out


# --------------------------------------------------------------- files with one sample per column --
def header_of(path):
    with _open_text(path) as fh:
        return next(csv.reader(fh, delimiter="\t"))


def row_names(path):
    """The first cell of every line after the header, in file order. Cheap: the rest of each line is not parsed."""
    names = []
    try:
        with _open_text(path) as fh:
            next(fh)
            for line in fh:
                if line.strip():
                    names.append(line.split("\t", 1)[0])
    except (OSError, EOFError, UnicodeDecodeError, StopIteration) as e:
        raise Unreadable(f"{os.path.basename(path)} could not be read: {e}")
    return names


def _lines(path, keep, in_order):
    """The data lines whose row name is in `keep`. Streamed when the file already lists them in the wanted order,
    otherwise held and sorted (the fallback for a release that shuffled its rows)."""
    if in_order:
        with _open_text(path) as fh:
            next(fh)
            for line in fh:
                if line.split("\t", 1)[0] in keep:
                    yield line.rstrip("\r\n").split("\t")
    else:
        with _open_text(path) as fh:
            next(fh)
            held = [line.rstrip("\r\n").split("\t") for line in fh if line.split("\t", 1)[0] in keep]
        held.sort(key=lambda cells: cells[0])
        yield from held


def column_fingerprints(path, keep, in_order):
    """{sample id: fingerprint or None}: one running hash per column, over the rows named in `keep`."""
    header = header_of(path)
    samples = header[1:]
    hashers = [hashlib.blake2b(digest_size=16) for _ in samples]
    seen_value = [False] * len(samples)
    n = len(samples)
    try:
        for cells in _lines(path, keep, in_order):
            for i in range(min(n, len(cells) - 1)):
                v = cells[i + 1]
                hashers[i].update(v.encode())
                hashers[i].update(b"\x1f")
                if not seen_value[i] and v not in EMPTY:
                    seen_value[i] = True
    except (OSError, EOFError, UnicodeDecodeError) as e:
        raise Unreadable(f"{os.path.basename(path)} could not be read: {e}")
    return {s: (hashers[i].hexdigest() if seen_value[i] else None) for i, s in enumerate(samples)}


def column_cells(path, wanted, keep):
    """{sample id: {row name: text}} for the samples in `wanted`, over the rows in `keep`."""
    header = header_of(path)
    index = {s: i + 1 for i, s in enumerate(header[1:]) if s in wanted}
    out = {s: {} for s in index}
    with _open_text(path) as fh:
        next(fh)
        for line in fh:
            name = line.split("\t", 1)[0]
            if name not in keep:
                continue
            cells = line.rstrip("\r\n").split("\t")
            for s, i in index.items():
                out[s][name] = cells[i] if i < len(cells) else ""
    return out


def column_differences(path_a, path_b, wanted, keep, in_order):
    """Yield (sample, row name, old text, new text) for every cell that differs, for the samples in `wanted`.

    The two files are walked in step, row by row, so memory depends on how much differs, not on how big the files
    are. The caller can stop early."""
    head_a, head_b = header_of(path_a), header_of(path_b)
    at_a = {s: i + 1 for i, s in enumerate(head_a[1:]) if s in wanted}
    at_b = {s: i + 1 for i, s in enumerate(head_b[1:]) if s in wanted}
    pairs = [(s, at_a[s], at_b[s]) for s in sorted(at_a) if s in at_b]
    for row_a, row_b in zip(_lines(path_a, keep, in_order), _lines(path_b, keep, in_order)):
        name = row_a[0]
        la, lb = len(row_a), len(row_b)
        for s, i, j in pairs:
            a = row_a[i] if i < la else ""
            b = row_b[j] if j < lb else ""
            if a != b:
                yield s, name, a, b


def one_row(path, name):
    """(sample ids, {sample id: text}) for a single named row, or (sample ids, None) if the row is not there."""
    header = header_of(path)
    samples = header[1:]
    with _open_text(path) as fh:
        next(fh)
        for line in fh:
            if line.split("\t", 1)[0] == name:
                cells = line.rstrip("\r\n").split("\t")
                return samples, {s: (cells[i + 1] if i + 1 < len(cells) else "") for i, s in enumerate(samples)}
    return samples, None
