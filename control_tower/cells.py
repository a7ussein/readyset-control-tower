"""The data itself: for one finding, the cells of the samples involved, read straight from the two release files.

    view = cells(folder_a, folder_b, doc, "F1")

A person should not have to take a finding on trust. This returns what each file actually holds for the samples the
finding names: every row (or clinical column) with the text in the trusted release beside the text in the new one,
exactly as written, and which cells differ. Nothing is rounded or interpreted.
"""
from . import release

MAX_SAMPLES = 8
MAX_ROWS = 400


def _finding(doc, finding_id):
    return next((f for f in doc.get("findings", []) if isinstance(f, dict) and f.get("id") == finding_id), None)


def cells(folder_a, folder_b, doc, finding_id, max_rows=MAX_ROWS):
    f = _finding(doc, finding_id)
    if not f:
        return {"detail": f"there is no change called {finding_id}"}
    evidence = [e for e in f.get("evidence", []) if isinstance(e, dict)]
    file = next((e.get("file") for e in evidence if e.get("file")), None) or \
        next((e.get("id") for e in evidence if e.get("kind") == "file"), None)
    names = [str(r.get("name")) for r in (doc.get("data") or {}).get("releases", []) if isinstance(r, dict)]
    old, new = (names[0], names[-1]) if len(names) >= 2 else ("trusted", "new")
    samples = [str(e.get("id")) for e in evidence if e.get("kind") == "sample"]
    witness = ((doc.get("x_readyset") or {}).get("witness") or {}).get(finding_id) or {}
    samples += [str(v.get("sample")) for v in witness.get("values", []) if isinstance(v, dict)]
    samples = list(dict.fromkeys(samples))
    more_samples = max(0, len(samples) - MAX_SAMPLES)
    samples = samples[:MAX_SAMPLES]
    pa, pb = release.path_of(folder_a, file or ""), release.path_of(folder_b, file or "")
    if not file or not (pa or pb):
        return {"detail": "this change names no file that can be opened"}
    if not samples:
        return {"detail": "this change is about the whole file, not about named samples, so there are no cells to line up"}
    try:
        kinds = [release.layout(p) for p in (pa, pb) if p]
        kind = next((k for k in kinds if k), "column")
        before, after, order = {}, {}, []
        for path, into in ((pa, before), (pb, after)):
            if not path:
                continue
            if kind == "row":                                  # one sample per line: the rows shown are the file's columns
                columns, table = release.read_rows(path)
                order += [c for c in columns if c not in order]
                for s in samples:
                    if s in table:
                        into[s] = dict(table[s])
            else:                                               # one sample per column: the rows shown are the file's rows
                rows = release.row_names(path)
                order += [r for r in rows if r not in order]
                present = set(release.header_of(path)[1:])
                into.update(release.column_cells(path, {s for s in samples if s in present}, set(rows)))
    except (release.Unreadable, OSError, EOFError, UnicodeDecodeError) as e:
        return {"detail": f"{file} could not be read: {e}"}
    rows = []
    for name in order:
        line = []
        for s in samples:
            a = before.get(s, {}).get(name) if s in before else None
            b = after.get(s, {}).get(name) if s in after else None
            line.append({"before": a, "after": b, "changed": a != b})
        rows.append({"name": name, "cells": line, "changed": any(c["changed"] for c in line)})
    differing = [r for r in rows if r["changed"]]
    shown = (differing + [r for r in rows if not r["changed"]])[:max_rows]
    return {"finding": finding_id, "file": file, "releases": [old, new],
            "what_a_row_is": "a column of the clinical record" if kind == "row" else "a row of the file (one measurement)",
            "samples": [{"id": s, "in_trusted": s in before, "in_new": s in after} for s in samples],
            "more_samples": more_samples, "rows": shown, "rows_in_file": len(rows), "rows_that_differ": len(differing),
            "rows_left_out": len(rows) - len(shown)}
