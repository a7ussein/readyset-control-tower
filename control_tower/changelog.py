"""The change log: every affected sample as one row of a spreadsheet (CSV), built from the findings document.

    text = to_csv(doc)

One row per sample a finding names (or one row for the finding when it names none). Each row says which change it
belongs to, where it is, the value before and after when the findings carry one, which analyses it touches, the
suggested fix, and the person's decision. Nothing is inferred: every cell is a field of the findings document.
"""
import csv
import io

from .report import KIND, shown

COLUMNS = ["change", "kind", "severity", "file", "sample", "measure", "value_in_trusted", "value_in_new", "what_changed",
           "affects_analyses", "suggested_fix", "fix_priority", "decision", "decided_by", "role", "decided_at", "note",
           "what_this_cannot_tell_you"]


def rows(doc):
    x = doc.get("x_readyset") if isinstance(doc.get("x_readyset"), dict) else {}
    reviews = {r.get("finding"): r for r in x.get("reviews", []) if isinstance(r, dict)}
    out = []
    for f in (f for f in doc.get("findings", []) if isinstance(f, dict)):
        fid = f.get("id")
        evidence = [e for e in f.get("evidence", []) if isinstance(e, dict)]
        file = next((e.get("file") for e in evidence if e.get("file")), None) or \
            next((e.get("id") for e in evidence if e.get("kind") == "file"), "")
        witness = (x.get("witness") or {}).get(fid) or {}
        values = {v.get("sample"): v for v in witness.get("values", []) if isinstance(v, dict)}
        repair = next((r for r in doc.get("repairs", []) if isinstance(r, dict) and fid in (r.get("addresses") or [])), {})
        targets = {str(t.get("id")) for t in repair.get("targets", []) if isinstance(t, dict)}
        priority = ((x.get("repair_priority") or {}).get(repair.get("id")) or {}).get("level", "")
        r = reviews.get(fid) or {}
        decision = {"confirmed": "confirmed as a real problem", "dismissed": "dismissed as an expected change"}.get(r.get("status"), "waiting for review")
        if r.get("status") == "confirmed" and r.get("fix") == "approved":
            decision += "; suggested fix approved"
        base = {"change": fid, "kind": KIND.get(f.get("kind"), "Other change"), "severity": f.get("severity", ""), "file": file,
                "affects_analyses": ", ".join(f.get("affects_analyses") or []) or "none",
                "decision": decision, "decided_by": r.get("reviewer", ""), "role": r.get("role", ""), "decided_at": r.get("at", ""),
                "note": r.get("note", ""), "what_this_cannot_tell_you": f.get("limitation", "")}
        samples = [e for e in evidence if e.get("kind") == "sample"]
        if not samples:
            out.append({**base, "sample": "", "what_changed": f.get("summary", ""),
                        "suggested_fix": str(repair.get("action", "")).replace("_", " "), "fix_priority": priority})
            continue
        for e in samples:
            sid = str(e.get("id"))
            v = values.get(sid)
            fixed = sid in targets or not targets
            out.append({**base, "sample": sid, "file": e.get("file") or file,
                        "measure": witness.get("row", "") if v else "",
                        "value_in_trusted": shown(v.get("before")) if v else "", "value_in_new": shown(v.get("after")) if v else "",
                        "what_changed": e.get("note") or f.get("summary", ""),
                        "suggested_fix": str(repair.get("action", "")).replace("_", " ") if fixed else "",
                        "fix_priority": priority if fixed else ""})
    return out


def to_csv(doc):
    releases = [str(r.get("name")) for r in (doc.get("data") or {}).get("releases", []) if isinstance(r, dict)]
    head = list(COLUMNS)
    if len(releases) >= 2:                                   # name the two value columns after the releases themselves
        head[head.index("value_in_trusted")] = f"value_in_{releases[0]}"
        head[head.index("value_in_new")] = f"value_in_{releases[-1]}"
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(head)
    for row in rows(doc):
        writer.writerow(["" if row.get(c) is None else row.get(c, "") for c in COLUMNS])
    return "﻿" + buffer.getvalue()                      # the mark makes Excel read it as UTF-8
