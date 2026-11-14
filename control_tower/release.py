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
    """Where a release's file is in a folder. A packed file may have been unpacked by whoever edited it, so
    `x.tsv` stands in for `x.tsv.gz`; when both are there, the one changed most recently is the one meant."""
    found = [p for p in ([os.path.join(folder, name)] + ([os.path.join(folder, name[:-3])] if name.endswith(".gz") else []))
             if os.path.isfile(p)]
    return max(found, key=os.path.getmtime) if found else None


def _is_gzip(path):
    """Decided by the file's first two bytes, not its name: a file may have been unpacked, or packed, and kept its name."""
    try:
        with open(path, "rb") as fh:
            return fh.read(2) == b"\x1f\x8b"
    except OSError:
        return False


def _open_bytes(path):
    return gzip.open(path, "rb") if _is_gzip(path) else open(path, "rb")


_sniffed = {}


def _encoding(path):
    """How the file's text is encoded. A table that went through a spreadsheet or an editor is often no longer UTF-8;
    it is still a table, so it is read as what it is. A file that is not text at all is refused in plain words."""
    try:
        key = (path, os.path.getmtime(path), os.path.getsize(path))
    except OSError:
        key = (path, 0, 0)
    if key in _sniffed:
        return _sniffed[key]
    name = os.path.basename(path)
    try:
        with _open_bytes(path) as fh:
            head = fh.read(4 << 20)
    except (OSError, EOFError) as e:
        raise Unreadable(f"{name} could not be read: {e}")
    if head[:4] == b"PK\x03\x04":
        raise Unreadable(f"{name} is not a text table: it is an Excel workbook or a zip saved under this name. "
                         f"Save it from the spreadsheet as tab-separated text and give that file")
    if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
        found = "utf-16"
    elif head[:3] == b"\xef\xbb\xbf":
        found = "utf-8-sig"
    elif b"\x00" in head[:4096]:
        raise Unreadable(f"{name} is not a text table: it holds binary data. Give the tab-separated text file")
    else:
        try:
            head.decode("utf-8")
            found = "utf-8"
        except UnicodeDecodeError as e:
            # A cut in the middle of a character at the very end of the sample is not a wrong encoding.
            found = "utf-8" if e.start >= len(head) - 4 and len(head) == 4 << 20 else "cp1252"
    _sniffed[key] = found
    return found


def _open_text(path):
    encoding = _encoding(path)
    errors = "strict" if encoding.startswith("utf-8") else "replace"
    if _is_gzip(path):
        return gzip.open(path, "rt", newline="", encoding=encoding, errors=errors)
    return open(path, "r", newline="", encoding=encoding, errors=errors)


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
    """'row' when each line is a sample, 'column' when each column is one. Decided by where the sample ids are.
    None for a file that holds a header and nothing else, which could be either."""
    try:
        with _open_text(path) as fh:
            reader = csv.reader(fh, delimiter="\t")
            header = next(reader, None)
            first = next((line for line in reader if line), None)        # the first line that is not blank
    except (OSError, EOFError, UnicodeDecodeError, csv.Error) as e:
        raise Unreadable(f"{os.path.basename(path)} could not be read: {e}")
    if not header:
        raise Unreadable(f"{os.path.basename(path)} is empty")
    if any(is_sample_id(h) for h in header[1:]):
        return "column"
    if first and is_sample_id(first[0]):
        return "row"
    if first is None:
        if len(header) < 2:
            raise Unreadable(f"{os.path.basename(path)} holds no table: one line of text with no columns")
        return None                 # a header and no data lines: the header alone does not say which way round it is
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
    """The header line's cells. A file with no header line (zero bytes, or only blank lines) is not a table."""
    try:
        with _open_text(path) as fh:
            header = next(csv.reader(fh, delimiter="\t"), None)
    except (OSError, EOFError, UnicodeDecodeError, csv.Error) as e:
        raise Unreadable(f"{os.path.basename(path)} could not be read: {e}")
    if not header:
        raise Unreadable(f"{os.path.basename(path)} is empty")
    return header


def _row_name(line):
    """The first cell of a line. A row that is only its name has no tab, so the line ending must not stick to it."""
    return line.split("\t", 1)[0].rstrip("\r\n")


def row_names(path):
    """The first cell of every line after the header, in file order. Cheap: the rest of each line is not parsed."""
    names = []
    try:
        with _open_text(path) as fh:
            next(fh)
            for line in fh:
                if line.strip():
                    names.append(_row_name(line))
    except (OSError, EOFError, UnicodeDecodeError, StopIteration) as e:
        raise Unreadable(f"{os.path.basename(path)} could not be read: {e}")
    return names


def _lines(path, keep, in_order):
    """The data lines whose row name is in `keep`. Streamed when the file already lists them in the wanted order,
    otherwise held and sorted (the fallback for a release that shuffled its rows)."""
    if in_order:
        with _open_text(path) as fh:
            next(fh, None)
            for line in fh:
                if _row_name(line) in keep:
                    yield line.rstrip("\r\n").split("\t")
    else:
        with _open_text(path) as fh:
            next(fh, None)
            held = [line.rstrip("\r\n").split("\t") for line in fh if _row_name(line) in keep]
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
        next(fh, None)
        for line in fh:
            name = _row_name(line)
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
        next(fh, None)
        for line in fh:
            if _row_name(line) == name:
                cells = line.rstrip("\r\n").split("\t")
                return samples, {s: (cells[i + 1] if i + 1 < len(cells) else "") for i, s in enumerate(samples)}
    return samples, None
