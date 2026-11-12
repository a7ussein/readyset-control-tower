"""Compare two releases and build the findings document (docs/OUTPUT-CONTRACT.md).

    doc = compare("releases/A", "releases/B")

Cheapest work first: hash every file; open only the ones whose content differs; rerun only the analyses a finding
touches.
"""
import os
import re
import time
from datetime import datetime, timezone

from . import __version__, release
from .analyses import ER, PAM50, REGISTRY, BadQuestion, CannotRun, question
from .detect import compare_file
from .release import FILES, PROTEIN

PRODUCER = {"team": "Automyte", "product": "Cohort Control Tower", "track": "cohort-firewall"}
SAME_VALUES = ("The file's bytes differ but every value is the same (for example line endings, or the order of rows "
               "or columns), so there is nothing to report.")
WITNESS_SAMPLES = 12
SCOPE = ("Protects only the analyses named in the question. Reports what changed between two releases, not why. "
         "Research use only; no clinical claims.")

DETECTED_BY = {
    "sample_swap": "Every sample's whole profile is fingerprinted over the rows both releases share. These samples' "
                   "fingerprints in the new release equal each other's fingerprints in the trusted release.",
    "duplicate": "A sample id in the new release has a fingerprint identical to a different sample's, and the two were "
                 "not identical in the trusted release. An id that already existed counts as a copy only if at least "
                 "half of its informative cells changed.",
    "membership_change": "The set of sample ids in the file differs between the two releases. Ids that arrived as "
                         "copies of another sample are reported separately as duplicates.",
    "label_conflict": "The same sample holds a different value in the same clinical column in the two releases.",
    "missing_data": "A cell that held a value in the trusted release is blank or a missing-value marker in the new one.",
    "other": "The file's content differs in a way none of the specific rules explains, so the differing rows, columns "
             "or cells are reported as they are.",
}


def _names(folder_a, folder_b):
    a = os.path.basename(os.path.normpath(folder_a)) or "A"
    b = os.path.basename(os.path.normpath(folder_b)) or "B"
    return ("A", "B") if a == b else (a, b)


def compare(folder_a, folder_b, analyses=None):
    """`analyses` is the question: the analyses this release is needed for, as registered ids or descriptions
    (see analyses.from_spec). None means every registered analysis."""
    chosen = question(analyses)
    # A question about a row, column or value that is not in the trusted release would always come back Ready. Refuse it.
    wrong = [w for w in (a.problem(folder_a) for a in chosen if a not in REGISTRY) if w]
    if wrong:
        raise BadQuestion("the question does not fit the trusted release. " + "; ".join(wrong))
    started = time.time()
    rel_a, rel_b = _names(folder_a, folder_b)
    notes = []
    if os.path.realpath(folder_a) == os.path.realpath(folder_b):
        notes.append("Both releases are the same folder, so there was nothing to compare.")
    elif os.path.isfile(os.path.join(folder_a, "CHANGES.json")) and not os.path.isfile(os.path.join(folder_b, "CHANGES.json")):
        notes.append(f"{rel_a} holds a CHANGES.json, which the organisers' script writes into a release it has altered. "
                     f"The two folders may be the wrong way round: the trusted release goes first.")
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
            found = compare_file(file, pa, pb, rel_a, rel_b, describe)
            raw += found
            info = {"file": file, "status": "changed", "opened": True}
            if not found:
                info["note"] = SAME_VALUES
            files_info.append(info)
        except release.Unreadable as e:
            files_info.append({"file": file, "status": "unreadable", "opened": True})
            insufficient = True
            raw.append(_unreadable(file, rel_b, str(e)))

    # Which analyses does each finding touch?
    used = {a.id: a.used(folder_a) | a.used(folder_b) for a in chosen}
    in_file = {a.id: a.file_samples(folder_a) | a.file_samples(folder_b) for a in chosen}
    for f in raw:
        f["affects"] = [a.id for a in chosen
                        if any(a.touched_by(ch, used[a.id], in_file[a.id]) for ch in f["changes"])]

    # Rerun only the analyses a finding touches.
    analyses, status_of, blocked = [], {}, False
    for a in chosen:
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
        if f["kind"] == "membership_change" and severity == "high":
            severity = "medium"                 # as in the organisers' reference output: lost coverage, not corrupted values
        findings.append({
            "id": fid, "kind": f["kind"], "summary": f["summary"], "severity": severity,
            "confidence": f["confidence"], "evidence": f["evidence"],
            "affects_analyses": f["affects"],
            "not_affected_analyses": [a.id for a in chosen if a.id not in f["affects"]],
            "limitation": f["limitation"], "needs_human_review": True})
        for r in (f.get("repair"), f.get("extra_repair")):
            if r:
                repairs.append({"id": f"R{len(repairs) + 1}", "action": r["action"], "targets": r["targets"],
                                "justification": r["justification"], "addresses": [fid]})
    effects, priority = _effects(raw, findings, repairs, chosen, folder_a, folder_b)
    witness = _witness(raw, folder_a, folder_b, rel_a, rel_b, chosen)
    rules = {}
    for f, raw_f in zip(findings, raw):
        reads = [f"{a.id} {'is touched' if a.id in raw_f['affects'] else 'is not touched'}: it reads {a.reads()}."
                 for a in chosen]
        why = {"high": "High: a protected analysis was rerun and its result changed.",
               "medium": "Medium: it touches samples a protected analysis reads, but the result held, or it is lost "
                         "coverage, which is never rated above medium.",
               "low": "Low: it touches nothing a protected analysis reads."}[f["severity"]]
        rules[f["id"]] = {"detected_by": DETECTED_BY.get(f["kind"], DETECTED_BY["other"]), "impact": reads, "severity": why}
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
    elif any(f["affects_analyses"] for f in findings):
        verdict = "Conditional"
    else:
        verdict = "Ready"                # nothing changed, or nothing that changed is read by the question's analyses

    return {
        "format_version": "0.2",
        "producer": dict(PRODUCER),
        "data": {"dataset": "TCGA-BRCA (event frozen release)",
                 "releases": [{"name": rel_a, "files": hashes[rel_a]}, {"name": rel_b, "files": hashes[rel_b]}]},
        "question": f"Did anything change between release {rel_a} and release {rel_b} that affects analysis "
                    + " or ".join(a.id for a in chosen) + "?",
        "verdict": verdict,
        "findings": findings,
        "analyses": analyses,
        "repairs": repairs,
        "x_readyset": {
            "engine_version": __version__,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_seconds": round(time.time() - started, 2),
            "analyses_registered": [a.id for a in REGISTRY],
            "analyses_in_question": [a.id for a in chosen],
            "analysis_titles": {a.id: a.title for a in list(REGISTRY) + [c for c in chosen if c not in REGISTRY]},
            "analysis_reads": {a.id: a.reads() for a in chosen},
            "unrelated_findings": sum(1 for f in findings if not f["affects_analyses"]),
            "notes": notes,
            "rules": rules,
            "effects": effects,
            "repair_priority": priority,
            "files": files_info,
            "witness": witness,
            "scope": SCOPE},
    }


SMALL = 0.005        # below half a percent on every headline number, a result moved only slightly


def _flat(result):
    out = {}
    for k, v in (result or {}).items():
        if isinstance(v, dict):
            out.update({f"{k}: {k2}": v2 for k2, v2 in v.items()})
        else:
            out[k] = v
    return out


def _headline(result):
    """The numbers a reader would quote from a result: the difference between groups if there is one, else the group
    means, else the shares. Sample counts are not headline numbers."""
    flat = _flat(result)
    for pick in (lambda k: k == "difference", lambda k: k.startswith("mean_"), lambda k: k.startswith("percent: ")):
        keys = [k for k in flat if pick(k)]
        if keys:
            return keys
    return list(flat)


def _most(b, a, keys):
    worst, most = None, 0.0
    for k in keys:
        x, y = b.get(k), a.get(k)
        if x == y:
            continue
        rel = abs(y - x) / abs(x) if isinstance(x, (int, float)) and isinstance(y, (int, float)) and x else 1.0
        if rel > most:
            worst, most = k, rel
    return worst, most


def _size(before, after):
    """('none' | 'small' | 'large', the measure that moved most, by how much as a fraction).

    Large: a headline number moved by half a percent or more. Small: the result changed, but no headline number moved
    that far (for example only the sample counts changed)."""
    b, a = _flat(before), _flat(after)
    if b == a:
        return "none", None, 0.0
    worst, most = _most(b, a, sorted(set(_headline(before)) | set(_headline(after))))
    if worst is not None and most >= SMALL:
        return "large", worst, round(most, 5)
    if worst is None:
        worst, most = _most(b, a, sorted(set(b) | set(a)))
    return "small", worst, round(most, 5)


def _effects(raw, findings, repairs, chosen, folder_a, folder_b):
    """What each finding does to each analysis on its own: the analysis recomputed on the trusted release with only
    that finding's changes applied. Also how urgently each suggested fix is needed, sized by that effect."""
    inputs = {}
    for a in chosen:
        try:
            inputs[a.id] = (a.inputs(folder_a), a.inputs(folder_b))
        except (CannotRun, release.Unreadable, OSError, EOFError, UnicodeDecodeError):
            inputs[a.id] = None
    wrap = lambda v: v if isinstance(v, tuple) else (v,)
    effects = {}
    for f, raw_f in zip(findings, raw):
        for a in chosen:
            if a.id not in raw_f["affects"] or not inputs[a.id]:
                continue
            before_in, after_in = inputs[a.id]
            try:
                before = _clean(a.compute(*wrap(before_in)))
                alone = _clean(a.compute(*wrap(a.with_only(before_in, after_in, raw_f["changes"]))))
            except (CannotRun, ValueError, KeyError, TypeError):
                continue
            size, measure, by = _size(before, alone)
            effects.setdefault(f["id"], {})[a.id] = {"before": before, "after": alone, "size": size,
                                                     "measure": measure, "moved_by": by}
    priority = {}
    for r in repairs:
        fid = r["addresses"][0]
        f = next(x for x in findings if x["id"] == fid)
        sizes = [e["size"] for e in effects.get(fid, {}).values()]
        if not f["affects_analyses"]:
            priority[r["id"]] = {"level": "for the record", "why": "Nothing in the question reads what this finding touches."}
        elif not sizes:
            priority[r["id"]] = {"level": "before use", "why": "An analysis you rely on cannot be rerun until this is resolved."}
        elif "large" in sizes:
            priority[r["id"]] = {"level": "before use", "why": "On its own this finding clearly moves a result you rely on."}
        elif f["kind"] in ("sample_swap", "duplicate"):
            priority[r["id"]] = {"level": "before use", "why": "These samples carry another sample's data. The effect on this "
                                 "result is small or none, but anything else computed from them is wrong too."}
        elif "small" in sizes:
            priority[r["id"]] = {"level": "small effect", "why": "On its own this finding moves a result by less than half a "
                                 "percent. Fix it, or accept it and say so in your methods."}
        else:
            priority[r["id"]] = {"level": "no effect on the result", "why": "It touches samples a result reads, but on its own "
                                 "the result is the same. Fix it when convenient."}
    return effects, priority


def _witness(raw, folder_a, folder_b, rel_a, rel_b, chosen):
    """For each finding about samples in a large file: one named row, with each sample's value in both releases.

    A reader can open the two files, find that row, and check the finding by eye. The row is the one an analysis
    in the question reads when the file has one (ER-alpha in the protein file for A1), otherwise the file's first row."""
    out, rows = {}, {}
    for i, f in enumerate(raw, 1):
        file = f.get("file")
        ids = [e["id"] for e in f["evidence"] if e["kind"] == "sample"]
        for e in f["evidence"]:                          # a copy's source is named in its note
            m = re.match(r"identical to (TCGA-\S+)", e.get("note", "")) if e["kind"] == "sample" else None
            if m and m.group(1) not in ids:
                ids.append(m.group(1))
        pa, pb = release.path_of(folder_a, file or ""), release.path_of(folder_b, file or "")
        if not ids or not pa or not pb:
            continue
        try:
            if file not in rows:
                if release.layout(pa) != "column" or release.layout(pb) != "column":
                    rows[file] = None
                else:
                    names = release.row_names(pa)
                    wanted = [a.row for a in chosen if a.file == file and a.row in names]
                    name = wanted[0] if wanted else (names[0] if names else None)
                    rows[file] = name and (name, release.one_row(pa, name)[1], release.one_row(pb, name)[1])
            if not rows[file] or rows[file][1] is None or rows[file][2] is None:
                continue
        except (release.Unreadable, OSError, EOFError, UnicodeDecodeError, StopIteration):
            rows[file] = None
            continue
        name, in_a, in_b = rows[file]
        out[f"F{i}"] = {"file": file, "row": name, "releases": [rel_a, rel_b],
                        "values": [{"sample": s, "before": in_a.get(s), "after": in_b.get(s)}
                                   for s in ids[:WITNESS_SAMPLES]]}
    return out


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
