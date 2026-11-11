"""Compare two releases and build the findings document (docs/OUTPUT-CONTRACT.md).

    doc = compare("releases/A", "releases/B")

Cheapest work first: hash every file; open only the ones whose content differs; rerun only the analyses a finding
touches.
"""
import os
import time
from datetime import datetime, timezone

from . import __version__, release
from .analyses import ER, PAM50, REGISTRY, CannotRun
from .detect import compare_file
from .release import FILES, PROTEIN

PRODUCER = {"team": "Automyte", "product": "Cohort Control Tower", "track": "cohort-firewall"}
SCOPE = ("Protects only the analyses registered in the tool (A1, A2). Reports what changed between two releases, "
         "not why. Research use only; no clinical claims.")


def _names(folder_a, folder_b):
    a = os.path.basename(os.path.normpath(folder_a)) or "A"
    b = os.path.basename(os.path.normpath(folder_b)) or "B"
    return ("A", "B") if a == b else (a, b)


def _protein_samples(folder):
    path = release.path_of(folder, PROTEIN)
    if not path:
        return set()
    try:
        return set(release.header_of(path)[1:])
    except (OSError, EOFError, UnicodeDecodeError, StopIteration):
        return set()


def compare(folder_a, folder_b):
    started = time.time()
    rel_a, rel_b = _names(folder_a, folder_b)
    raw, files_info, hashes = [], [], {rel_a: [], rel_b: []}
    insufficient = False

    describe = _describer(folder_a, folder_b)
    for file in FILES:
        pa, pb = release.path_of(folder_a, file), release.path_of(folder_b, file)
        if not pa and not pb:
            files_info.append({"file": file, "status": "absent", "opened": False})
            continue
        if not pa or not pb:
            has, lacks = (rel_a, rel_b) if pa else (rel_b, rel_a)
            try:
                hashes[has].append({"file": file, "sha256": release.content_hash(pa or pb), "hash_of": "content"})
            except release.Unreadable:
                pass
            files_info.append({"file": file, "status": "missing_in_one", "opened": False})
            insufficient = True
            raw.append({
                "kind": "other", "file": file, "confidence": "high",
                "summary": f"{file} is in {has} but not in {lacks}, so the two releases cannot be compared for this file.",
                "evidence": [{"kind": "file", "id": file, "release": has, "note": f"present in {has}, absent from {lacks}"}],
                "changes": [{"scope": "file", "file": file}],
                "limitation": "Nothing can be said about what changed inside a file that one release does not have.",
                "repair": {"action": "flag_for_review", "targets": [{"kind": "file", "id": file, "release": lacks}],
                           "justification": f"{file} is missing from {lacks}. A person should obtain it before the "
                                            f"releases are compared."}})
            continue
        try:
            ha, hb = release.content_hash(pa), release.content_hash(pb)
        except release.Unreadable as e:
            files_info.append({"file": file, "status": "unreadable", "opened": False})
            insufficient = True
            raw.append(_unreadable(file, rel_b, str(e)))
            continue
        hashes[rel_a].append({"file": file, "sha256": ha, "hash_of": "content"})
        hashes[rel_b].append({"file": file, "sha256": hb, "hash_of": "content"})
        if ha == hb:
            files_info.append({"file": file, "status": "unchanged", "opened": False})
            continue
        try:
            raw += compare_file(file, pa, pb, rel_a, rel_b, describe)
            files_info.append({"file": file, "status": "changed", "opened": True})
        except release.Unreadable as e:
            files_info.append({"file": file, "status": "unreadable", "opened": True})
            insufficient = True
            raw.append(_unreadable(file, rel_b, str(e)))

    # Which analyses does each finding touch?
    used = {a.id: a.used(folder_a) | a.used(folder_b) for a in REGISTRY}
    protein_samples = _protein_samples(folder_a) | _protein_samples(folder_b)
    for f in raw:
        f["affects"] = [a.id for a in REGISTRY
                        if any(a.touched_by(ch, used[a.id], protein_samples) for ch in f["changes"])]

    # Rerun only the analyses a finding touches.
    analyses, status_of, blocked = [], {}, False
    for a in REGISTRY:
        because = [i for i, f in enumerate(raw) if a.id in f["affects"]]
        if not because:
            status_of[a.id] = "not_rerun"
            analyses.append({"id": a.id, "status": "not_rerun",
                             "note": f"Not rerun: no finding touches a file, column, row or sample that {a.id} "
                                     f"({a.title}) reads."})
            continue
        entry = {"id": a.id}
        try:
            before = a.run(folder_a)
            entry["before"] = _clean(before)
        except (CannotRun, release.Unreadable, OSError, EOFError, UnicodeDecodeError) as e:
            before = None
            entry["note"] = f"Could not be run on {rel_a}: {e}."
        try:
            after = a.run(folder_b)
        except (CannotRun, release.Unreadable, OSError, EOFError, UnicodeDecodeError) as e:
            status_of[a.id] = "blocked"
            blocked = True
            entry["status"] = "not_rerun"
            entry["note"] = f"Affected, but could not be rerun on {rel_b}: {e}."
            entry["_because"] = because
            analyses.append(entry)
            continue
        entry["after"] = _clean(after)
        entry["status"] = "unchanged" if before == after else "changed"
        status_of[a.id] = entry["status"]
        entry["_because"] = because
        analyses.append(entry)

    # Number the findings, set severity, attach repairs.
    findings, repairs = [], []
    for i, f in enumerate(raw, 1):
        fid = f"F{i}"
        moved = [a for a in f["affects"] if status_of[a] in ("changed", "blocked")]
        severity = "high" if moved else ("medium" if f["affects"] else "low")
        findings.append({
            "id": fid, "kind": f["kind"], "summary": f["summary"], "severity": severity,
            "confidence": f["confidence"], "evidence": f["evidence"],
            "affects_analyses": f["affects"],
            "not_affected_analyses": [a.id for a in REGISTRY if a.id not in f["affects"]],
            "limitation": f["limitation"], "needs_human_review": True})
        for r in (f.get("repair"), f.get("extra_repair")):
            if r:
                repairs.append({"id": f"R{len(repairs) + 1}", "action": r["action"], "targets": r["targets"],
                                "justification": r["justification"], "addresses": [fid]})
    for entry in analyses:
        because = entry.pop("_because", None)
        if because is not None and "note" not in entry:
            ids = ", ".join(f"F{i + 1}" for i in because)
            entry["note"] = (f"Rerun because {ids} touch{'es' if len(because) == 1 else ''} what {entry['id']} reads. "
                             + ("The result changed." if entry["status"] == "changed" else "The result is the same."))

    if insufficient:
        verdict = "Insufficient Evidence"
    elif blocked:
        verdict = "Blocked"
    elif findings:
        verdict = "Conditional"
    else:
        verdict = "Ready"

    return {
        "format_version": "0.2",
        "producer": dict(PRODUCER),
        "data": {"dataset": "TCGA-BRCA (event frozen release)",
                 "releases": [{"name": rel_a, "files": hashes[rel_a]}, {"name": rel_b, "files": hashes[rel_b]}]},
        "question": f"Did anything change between release {rel_a} and release {rel_b} that affects analysis "
                    + " or ".join(a.id for a in REGISTRY) + "?",
        "verdict": verdict,
        "findings": findings,
        "analyses": analyses,
        "repairs": repairs,
        "x_readyset": {
            "engine_version": __version__,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_seconds": round(time.time() - started, 2),
            "analyses_registered": [a.id for a in REGISTRY],
            "files": files_info,
            "scope": SCOPE},
    }


def _describer(folder_a, folder_b):
    """A function that says which clinical subgroups a set of samples belongs to, from the trusted release's clinical
    record (falling back to the new one). Used to report which subgroup lost coverage."""
    table = {}
    for folder in (folder_b, folder_a):                    # the trusted release wins where both have the sample
        path = release.path_of(folder, release.CLINICAL)
        if path:
            try:
                table.update(release.read_rows(path)[1])
            except release.Unreadable:
                pass
    if not table:
        return None

    def describe(samples):
        return {"RNA subtype": [table.get(s, {}).get(PAM50, "") for s in samples],
                "ER status": [table.get(s, {}).get(ER, "") for s in samples]}
    return describe


def _clean(result):
    """Before and after hold the result's numbers only, as in the organisers' own output."""
    return {k: v for k, v in result.items() if k not in ("analysis", "inputs", "n_ids_listed")}


def _unreadable(file, rel, why):
    return {"kind": "other", "file": file, "confidence": "high",
            "summary": f"{file} could not be read, so the two releases cannot be compared for this file. {why}",
            "evidence": [{"kind": "file", "id": file, "release": rel, "note": why}],
            "changes": [{"scope": "file", "file": file}],
            "limitation": "Nothing can be said about what changed inside a file that cannot be read.",
            "repair": {"action": "flag_for_review", "targets": [{"kind": "file", "id": file, "release": rel}],
                       "justification": f"{file} could not be read. A person should check the file."}}
