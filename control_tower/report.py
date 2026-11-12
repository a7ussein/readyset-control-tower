"""The audit report: the findings document, written out in plain English as one self-contained page.

    html = render(doc)

Every sentence is built from a field of the findings document by a fixed pattern. Nothing is inferred and no model
writes any of it, so the same findings always give the same report, and each statement can be traced to the file.
"""
import html
import re

KIND = {"sample_swap": "Samples exchanged", "duplicate": "Copied samples", "membership_change": "Samples left or joined",
        "label_conflict": "Labels changed", "missing_data": "Values went missing", "other": "Other change"}
MEANS = {
    "Ready": "The new release can be used for the analyses in the question. Nothing those analyses read has changed.",
    "Conditional": "Something the analyses in the question read has changed. Each change below should be reviewed by a "
                   "person before the new release is used.",
    "Blocked": "The new release should not be used yet. A change left an analysis unable to run.",
    "Insufficient Evidence": "The two releases could not be fully compared, because a file is missing or unreadable.",
}
STATUS = {"changed": "was rerun and its result changed", "unchanged": "was rerun and its result is the same",
          "not_rerun": "was not rerun, because nothing it reads changed"}
FILE_STATUS = {"changed": "content differs", "unchanged": "identical, not opened", "absent": "in neither release",
               "missing_in_one": "missing in one release", "not_in_both": "in only one release; not needed, so not compared",
               "unreadable": "could not be read"}


def e(value):
    return html.escape("" if value is None else str(value))


def shown(value):
    if value is None:
        return "absent"
    if isinstance(value, float):
        return str(round(value, 3))
    text = str(value)
    if text.strip() == "":
        return "blank"
    if re.fullmatch(r"-?\d+\.\d{4,}(e-?\d+)?", text, re.I):
        return f"{float(text):.3f}"
    return text


def plural(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def flat(result):
    out = {}
    for k, v in (result or {}).items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                out[f"{k}: {k2}"] = v2
        else:
            out[k] = v
    return out


def table(headers, rows, mark=None):
    head = "".join(f"<th>{e(h)}</th>" for h in headers)
    body = ""
    for i, row in enumerate(rows):
        cells = "".join(f"<{'th' if j == 0 else 'td'}{' class=moved' if mark and mark(i, j) else ''}>{e(c)}</{'th' if j == 0 else 'td'}>"
                        for j, c in enumerate(row))
        body += f"<tr>{cells}</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def result_table(analysis, releases):
    before, after = flat(analysis.get("before")), flat(analysis.get("after"))
    if not before and not after:
        return ""
    keys = list(dict.fromkeys(list(before) + list(after)))
    rows, moved = [], []
    for k in keys:
        x, y = before.get(k), after.get(k)
        differs = x != y
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and differs:
            change = f"{y - x:+.3f}".rstrip("0").rstrip(".") if isinstance(x, float) or isinstance(y, float) else f"{y - x:+d}"
        else:
            change = "changed" if differs else "same"
        rows.append([k.replace("_", " "), shown(x), shown(y), change])
        moved.append(differs)
    return table(["", releases[0], releases[1], "change"], rows, lambda i, j: j == 2 and moved[i])


def render(doc):
    x = doc.get("x_readyset") or {}
    releases = [r.get("name", "") for r in (doc.get("data") or {}).get("releases", [])] + ["the trusted release", "the new release"]
    a_name, b_name = (releases[0] or "the trusted release"), (releases[1] or "the new release")
    findings = [f for f in doc.get("findings", []) if isinstance(f, dict)]
    analyses = [a for a in doc.get("analyses", []) if isinstance(a, dict)]
    repairs = [r for r in doc.get("repairs", []) if isinstance(r, dict)]
    titles, reads, rules, witness = x.get("analysis_titles") or {}, x.get("analysis_reads") or {}, x.get("rules") or {}, x.get("witness") or {}
    reviews = {r.get("finding"): r for r in x.get("reviews") or [] if isinstance(r, dict)}
    effects, priority = x.get("effects") or {}, x.get("repair_priority") or {}
    files = [f for f in x.get("files") or [] if isinstance(f, dict)]
    verdict = doc.get("verdict") or "No verdict"
    name = lambda i: f"{i} ({titles[i]})" if titles.get(i) else i
    reaching = [f for f in findings if f.get("affects_analyses")]

    out = []
    out.append(f"<h1>Release audit report</h1><p class=sub>{e(a_name)} (trusted) compared with {e(b_name)} (new). "
               f"{e((doc.get('producer') or {}).get('product', ''))}, team {e((doc.get('producer') or {}).get('team', ''))}. "
               f"Generated {e(x.get('generated_at', ''))}.</p>")

    # ---- the answer
    changed_files = [f["file"] for f in files if f.get("status") not in ("unchanged", "absent", "not_in_both")]
    files_compared = [f for f in files if f.get("status") not in ("absent", "not_in_both")]
    summary = [MEANS.get(verdict, "")]
    if files:
        summary.append(f"{len(changed_files)} of the {len(files_compared)} compared files {'differs' if len(changed_files) == 1 else 'differ'} between the releases"
                       + (f" ({', '.join(changed_files)})." if changed_files else "."))
    if findings:
        summary.append(f"{plural(len(findings), 'change')} {'was' if len(findings) == 1 else 'were'} found. "
                       f"{len(reaching)} of them reach the analyses in the question.")
    else:
        summary.append("No changes were found.")
    for a in analyses:
        line = f"{name(a['id'])} {STATUS.get(a.get('status'), a.get('status'))}."
        if a.get("status") == "not_rerun" and any(a["id"] in (f.get("affects_analyses") or []) for f in findings):
            line = f"{name(a['id'])} could not be rerun. {a.get('note', '')}"
        summary.append(line)
    decided = [f for f in findings if f.get("id") in reviews]
    if findings:
        summary.append(f"{len(decided)} of {plural(len(findings), 'change')} {'has' if len(decided) == 1 else 'have'} been reviewed by a person.")
    out.append(f"<section class='answer v-{e(verdict.lower().replace(' ', '-'))}'><p class=label>The question</p><p>{e(doc.get('question', ''))}</p>"
               f"<p class=label>The answer</p><p class=verdict>{e(verdict)}</p>" + "".join(f"<p>{e(s)}</p>" for s in summary if s)
               + "".join(f"<p{'' if 'not compared' in n else ' class=warn'}>{e(n)}</p>" for n in x.get("notes") or []) + "</section>")

    # ---- each change
    if findings:
        out.append("<h2>The changes</h2>")
    for f in findings:
        fid = f.get("id", "")
        samples = [p for p in f.get("evidence", []) if isinstance(p, dict) and p.get("kind") == "sample"]
        out.append(f"<section class=change><h3>{e(fid)}. {e(KIND.get(f.get('kind'), 'Change'))} <span class='sev s-{e(f.get('severity'))}'>{e(f.get('severity'))} severity</span></h3>")
        out.append(f"<p><b>What happened.</b> {e(f.get('summary', ''))}</p>")
        if samples:
            ids = ", ".join(p["id"] for p in samples[:12]) + (f", and {len(samples) - 12} more" if len(samples) > 12 else "")
            out.append(f"<p><b>Samples involved ({len(samples)}).</b> <span class=ids>{e(ids)}</span></p>")
        w = witness.get(fid)
        if w and w.get("values"):
            rows = [[v.get("sample"), shown(v.get("before")), shown(v.get("after"))] for v in w["values"]]
            moved = [v.get("before") != v.get("after") for v in w["values"]]
            out.append(f"<p><b>Proof you can check.</b> The {e(w.get('row'))} row of {e(w.get('file'))}, in each release. Numbers are rounded to three places.</p>"
                       + table(["sample", a_name, b_name], rows, lambda i, j: j == 2 and moved[i]))
        else:
            notes = [[p.get("id"), p.get("note", "")] for p in f.get("evidence", []) if isinstance(p, dict) and p.get("note")][:12]
            if notes:
                out.append("<p><b>Proof you can check.</b></p>" + table(["where", "what the files show"], notes))
        affected = f.get("affects_analyses") or []
        if affected:
            out.append(f"<p><b>What it does to the analyses.</b> It reaches {e(', '.join(name(i) for i in affected))}."
                       + (f" It does not reach {e(', '.join(f.get('not_affected_analyses') or []))}." if f.get("not_affected_analyses") else "") + "</p>")
            for aid in affected:
                own = (effects.get(fid) or {}).get(aid)
                if not own:
                    continue
                if own.get("size") == "none":
                    out.append(f"<p>On its own, this change leaves {e(aid)} exactly the same.</p>")
                else:
                    by = own.get("moved_by") or 0
                    pct = "more than 100%" if by >= 1 else f"{by * 100:.{2 if by < 0.01 else 1}f}%"
                    out.append(f"<p>On its own, this change moves {e(aid)} {'slightly' if own.get('size') == 'small' else 'clearly'}: "
                               f"{e(str(own.get('measure', '')).replace('_', ' '))} by {pct}.</p>"
                               + result_table({"before": own.get("before"), "after": own.get("after")}, [a_name, "this change alone"]))
        else:
            out.append("<p><b>What it does to the analyses.</b> Nothing. No analysis in the question reads what changed here.</p>")
        for r in repairs:
            if fid in (r.get("addresses") or []):
                targets = [t.get("id") for t in r.get("targets", []) if isinstance(t, dict)]
                urgency = priority.get(r.get("id")) or {}
                out.append(f"<p><b>Suggested fix ({e(r.get('id'))}).</b> "
                           + (f"<i>{e(str(urgency.get('level', '')).capitalize())}: {e(urgency.get('why', ''))}</i> " if urgency.get("level") else "")
                           + f"{e(str(r.get('action', '')).replace('_', ' ').capitalize())}. {e(r.get('justification', ''))}"
                           + (f" Applies to: <span class=ids>{e(', '.join(targets[:12]))}{' and more' if len(targets) > 12 else ''}</span>." if targets else "")
                           + " This is a suggestion only; the tool has changed nothing in the data.</p>")
        out.append(f"<p><b>What this cannot tell you.</b> {e(f.get('limitation', ''))}</p>")
        rule = rules.get(fid)
        if rule:
            out.append(f"<p><b>How it was found.</b> {e(rule.get('detected_by', ''))} {e(rule.get('severity', ''))}</p>")
        r = reviews.get(fid)
        if r:
            said = "Confirmed as a real problem" if r.get("status") == "confirmed" else "Dismissed as an expected change"
            out.append(f"<p class=reviewed><b>Reviewed.</b> {said} by {e(r.get('reviewer') or 'a reviewer who gave no name')}"
                       f"{', ' + e(r['role']) if r.get('role') else ''}{', ' + e(r['at']) if r.get('at') else ''}."
                       f"{' Note: ' + e(r['note']) if r.get('note') else ''}"
                       + (" The suggested fix was approved." if r.get("fix") == "approved" else
                          " The suggested fix has not been approved." if r.get("status") == "confirmed" else "") + "</p>")
        else:
            out.append("<p class=waiting><b>Not yet reviewed.</b> No person has confirmed or dismissed this change.</p>")
        out.append("</section>")

    # ---- the analyses
    if analyses:
        out.append("<h2>The analyses in the question</h2>")
    for a in analyses:
        out.append(f"<section class=change><h3>{e(name(a['id']))}</h3>")
        if reads.get(a["id"]):
            out.append(f"<p>It reads {e(reads[a['id']])}.</p>")
        out.append(f"<p>{e(a.get('note', ''))}</p>" + result_table(a, [a_name, b_name]) + "</section>")

    # ---- the files
    if files:
        hashes = {}
        for rel in (doc.get("data") or {}).get("releases", []):
            for fl in rel.get("files", []):
                hashes.setdefault(fl.get("file"), {})[rel.get("name")] = fl.get("sha256", "")
        rows = [[f.get("file"), FILE_STATUS.get(f.get("status"), f.get("status")) + (". " + f["note"] if f.get("note") else ""),
                 (hashes.get(f.get("file"), {}).get(a_name) or "")[:16], (hashes.get(f.get("file"), {}).get(b_name) or "")[:16]] for f in files]
        out.append("<h2>The files</h2><p>A file whose content hash is the same in both releases is identical and was not opened. "
                   "The first 16 characters of each SHA-256 content hash are shown; the full values are in findings.json.</p>"
                   + table(["file", "status", f"hash in {a_name}", f"hash in {b_name}"], rows))

    out.append(f"<h2>About this report</h2><p>{e(x.get('scope', ''))}</p>"
               "<p>Every sentence above is produced from the findings file by a fixed pattern. No language model wrote any part "
               "of it, so the same findings always give the same report. The machine-readable version is findings.json.</p>"
               f"<p class=sub>Engine {e(x.get('engine_version', ''))}. Compared in {e(x.get('run_seconds', ''))} s.</p>")

    return ("<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width, initial-scale=1'>"
            f"<title>Release audit report: {e(a_name)} and {e(b_name)}</title><style>{CSS}</style><body><main>" + "".join(out) + "</main></body></html>")


CSS = """
body{margin:0;background:#f3f3f9;color:#14122b;font:16px/1.55 -apple-system,'Helvetica Neue',Arial,sans-serif}
main{max-width:820px;margin:0 auto;padding:40px 24px 64px;background:#fff;min-height:100vh}
h1{font-size:30px;margin:0 0 6px;letter-spacing:-.4px}h2{font-size:21px;margin:34px 0 10px;padding-top:10px;border-top:2px solid #3b2f8f}
h3{font-size:17px;margin:0 0 8px}p{margin:0 0 9px}.sub{color:#5b5876;font-size:14px}
.answer{border:1px solid #e2e1ee;border-left:5px solid #5e6272;border-radius:10px;padding:16px 20px;margin:18px 0}
.answer.v-ready{border-left-color:#1b7f4b}.answer.v-conditional{border-left-color:#9a5b00}.answer.v-blocked{border-left-color:#bf272c}
.label{font-size:13px;color:#5b5876;margin:6px 0 2px;font-weight:600}.verdict{font-size:26px;font-weight:800;margin:0 0 8px}
.change{border:1px solid #e2e1ee;border-radius:10px;padding:16px 20px;margin:0 0 14px;break-inside:avoid}
.sev{font-size:12px;font-weight:600;border-radius:5px;padding:1px 7px;background:#f3f3f9;color:#5b5876;margin-left:6px}
.s-high{background:#fde8f0;color:#a8244f}.s-medium{background:#fff2dc;color:#9a5b00}
.ids{font:13px ui-monospace,Menlo,monospace;overflow-wrap:anywhere}
table{border-collapse:collapse;width:100%;margin:4px 0 12px;font:13px ui-monospace,Menlo,monospace}
th,td{border-bottom:1px solid #e2e1ee;padding:6px 8px;text-align:right;font-weight:400;overflow-wrap:anywhere}
th:first-child{text-align:left}thead th{font:600 12px -apple-system,Arial,sans-serif;color:#5b5876}
td.moved{background:#fde8f0;color:#a8244f;font-weight:600}
.reviewed{border-left:4px solid #1b7f4b;padding-left:10px}.waiting{border-left:4px solid #9a5b00;padding-left:10px}.warn{color:#bf272c;font-weight:600}
@media print{body{background:#fff}main{padding:0;max-width:none}h2{break-after:avoid}}
"""
