"""Ask: questions in plain words about one comparison, answered from the findings document and nothing else.

    reply = ask(doc, "is it safe to use?")

No language model writes any answer. A question is matched to one of a fixed list of questions by the words in it, and the
answer is built from fields of the findings document by fixed sentence patterns, the same way the audit report is. So:

  - the same question about the same findings always gives the same answer, word for word (`fingerprint` proves it);
  - every answer carries a `trace`: how the question was understood, which fields were read, and the files, samples
    and numbers each statement rests on;
  - a question the findings cannot answer gets "I cannot answer that from this comparison", never a guess, and a
    clinical question is refused outright;
  - it works for a named person and has that person's rights and no more: it can prepare their decision on a change,
    and nothing is recorded until that person records it in their own name.
"""
import hashlib
import json
import re

from .report import KIND, MEANS, plural, shown

# The questions it can answer. Order matters only to break a tie, and the order is fixed.
# (id, the question in plain words, {word: weight}). A word matches a typed word that starts with it.
INTENTS = [
    ("verdict", "Can I use the new release?",
     {"use": 3, "safe": 3, "ready": 3, "verdict": 4, "trust": 2, "ok": 2, "okay": 2, "go": 1, "can": 1, "release": 1, "answer": 1}),
    ("changed", "What changed between the two releases?",
     {"change": 3, "differ": 3, "happen": 2, "found": 2, "finding": 3, "new": 1, "what": 1, "wrong": 2, "problem": 2, "issue": 2}),
    ("matters", "Why does it matter for my results?",
     {"matter": 4, "impact": 3, "affect": 3, "effect": 3, "result": 3, "important": 3, "significan": 3, "move": 2, "number": 2,
      "analys": 2, "why": 1, "paper": 2, "conclusion": 2}),
    ("do", "What should I do next?",
     {"do": 3, "fix": 4, "next": 3, "repair": 4, "action": 3, "should": 2, "recommend": 3, "resolve": 3, "handle": 2, "step": 2}),
    ("limits", "What can the tool not tell me?",
     {"cannot": 4, "cant": 4, "limit": 4, "unsure": 3, "sure": 3, "certain": 3, "confiden": 3, "not": 1, "tell": 1, "know": 1,
      "caveat": 4, "miss": 1, "uncertain": 4, "doubt": 3}),
    ("samples", "Which samples are involved?",
     {"sample": 4, "which": 1, "patient": 3, "id": 2, "ids": 2, "tumour": 2, "tumor": 2, "who": 1, "involved": 2}),
    ("severity", "How serious is each change, and why?",
     {"severity": 4, "serious": 4, "high": 3, "medium": 3, "low": 2, "rate": 2, "bad": 2, "risk": 3, "worst": 3, "severe": 4}),
    ("review", "Who has reviewed the changes, and what did they decide?",
     {"review": 4, "decision": 3, "decide": 3, "sign": 3, "approve": 3, "confirm": 3, "dismiss": 3, "who": 1}),
    ("how", "How do you work, and will you give the same answer next time?",
     {"how": 1, "work": 2, "method": 3, "detect": 3, "ai": 4, "model": 3, "llm": 4, "consisten": 4, "same": 2, "determin": 4,
      "hallucinat": 4, "chatgpt": 4, "gpt": 4, "agent": 3, "reproduc": 4, "again": 2, "fingerprint": 3}),
    ("files", "Which files were compared?",
     {"file": 4, "compared": 2, "rna": 3, "hash": 3, "checksum": 3, "data": 1, "opened": 2}),
]
TITLES = {i: t for i, t, _ in INTENTS}
TITLES["clinical"] = "A clinical question, which this tool does not answer"
TITLES["act"] = "Record my decision on a change"
# A question about patients' care is refused outright: the tool makes no clinical claims.
CLINICAL = ("treat", "therap", "diagnos", "prognos", "surviv", "die", "died", "death", "cure", "drug", "dose", "outcome",
            "prescri", "mortality", "chemo", "surgery")
ACTIONS = {"confirm": "confirmed", "dismiss": "dismissed", "approve": "confirmed"}
STOP = {"the", "a", "an", "is", "it", "to", "of", "in", "on", "for", "and", "or", "this", "that", "me", "my", "i", "we", "you",
        "are", "was", "be", "does", "did", "with", "about", "please", "there", "any", "at", "by", "from", "so", "its"}
# Words that point at one finding kind or one analysis, so the answer can be narrowed to it.
KIND_WORDS = {"sample_swap": ("swap", "exchang", "trade", "mix"), "duplicate": ("duplicat", "copy", "copie", "copied"),
              "membership_change": ("left", "joined", "missing sample", "removed", "membership", "gone"),
              "label_conflict": ("label", "relabel"), "missing_data": ("blank", "missing value", "empty")}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def findings_fingerprint(doc):
    """One short code for everything an answer can depend on. If it is the same, every answer is the same."""
    x = doc.get("x_readyset") if isinstance(doc.get("x_readyset"), dict) else {}
    return _hash({k: doc.get(k) for k in ("verdict", "findings", "analyses", "repairs", "decisions", "data")} |
                 {"reviews": x.get("reviews"), "asked": x.get("analyses_in_question")})


def words_of(text):
    text = str(text or "").lower().replace("can't", "cant").replace("cannot", "cannot").replace("can not", "cannot")
    return [w for w in re.findall(r"[a-z0-9]+", text) if w not in STOP]


def understand(text):
    """(intent id or None, the words that decided it, every intent's score). Pure: no state, no randomness."""
    typed = words_of(text)
    scores, hits = {}, {}
    for intent, _, vocabulary in INTENTS:
        matched = sorted({w for w in typed for key in vocabulary if w.startswith(key)})
        scores[intent] = sum(max(weight for key, weight in vocabulary.items() if w.startswith(key)) for w in matched)
        hits[intent] = matched
    clinical = sorted({w for w in typed if any(w == c or (len(c) > 3 and w.startswith(c)) for c in CLINICAL)})
    if clinical:
        return "clinical", clinical, scores
    best = max(scores.values()) if scores else 0
    if best < 2:
        return None, [], scores
    intent = next(i for i, _, _ in INTENTS if scores[i] == best)          # the first in the fixed order wins a tie
    return intent, hits[intent], scores


def _focus(text, doc):
    """The findings and analyses the question names, if it names any."""
    low = " " + str(text or "").lower() + " "
    findings = [f for f in doc.get("findings", []) if isinstance(f, dict)]
    titles = (doc.get("x_readyset") or {}).get("analysis_titles") or {}
    named_f = [f for f in findings if re.search(rf"\b{re.escape(str(f.get('id')).lower())}\b", low)
               or any(w in low for w in KIND_WORDS.get(f.get("kind"), ()))]
    named_a = [a for a in titles if re.search(rf"\b{re.escape(a.lower())}\b", low)
               or any(w in low for w in words_of(titles[a]) if len(w) > 5)]
    return named_f, named_a


def _samples(finding):
    return [str(e.get("id")) for e in finding.get("evidence", []) if isinstance(e, dict) and e.get("kind") == "sample"]


def _file(finding):
    ev = [e for e in finding.get("evidence", []) if isinstance(e, dict)]
    return next((e.get("file") for e in ev if e.get("file")), None) or next((e.get("id") for e in ev if e.get("kind") == "file"), "")


def _name(finding):
    return f"{finding.get('id')} ({KIND.get(finding.get('kind'), 'Other change').lower()})"


def _source(finding, x):
    """What a statement about this finding rests on: the file, the samples, and one row of values a person can check."""
    out = {"finding": finding.get("id"), "file": _file(finding), "samples": _samples(finding)}
    w = (x.get("witness") or {}).get(finding.get("id"))
    if isinstance(w, dict) and w.get("values"):
        out["check"] = {"row": w.get("row"), "releases": w.get("releases"),
                        "values": [{"sample": v.get("sample"), "before": shown(v.get("before")), "after": shown(v.get("after"))}
                                   for v in w["values"][:4]]}
    return out


def _moved(analysis):
    before, after = analysis.get("before") or {}, analysis.get("after") or {}
    return [(k, before.get(k), after.get(k)) for k in before
            if not isinstance(before.get(k), dict) and before.get(k) != after.get(k) and k in after]


def ask(doc, text, actor=None, router=None):
    """Answer one question about one findings document. Same inputs, same output, always.

    `actor` is the person the assistant is working for: {"name": ..., "role": ...}. The assistant has that person's
    rights on the page and no more: it reads the findings, and it can prepare their decision on a change for them to
    record in their own name. With no named person it records nothing.

    `router` is optional help with unusual wording (see understand_ai.py): a function that names which fixed question
    a wording is closest to. It is consulted only when the word list understood nothing, it never sees `doc`, and the
    answer is built the same way whoever understood the question."""
    actor = actor if isinstance(actor, dict) else {}
    who, role = str(actor.get("name") or "").strip()[:200], str(actor.get("role") or "").strip()[:200]
    x = doc.get("x_readyset") if isinstance(doc.get("x_readyset"), dict) else {}
    findings = [f for f in doc.get("findings", []) if isinstance(f, dict)]
    analyses = [a for a in doc.get("analyses", []) if isinstance(a, dict)]
    repairs = [r for r in doc.get("repairs", []) if isinstance(r, dict)]
    titles = x.get("analysis_titles") or {}
    releases = [str(r.get("name")) for r in (doc.get("data") or {}).get("releases", []) if isinstance(r, dict)]
    old, new = (releases + ["the trusted release", "the new release"])[:2] if len(releases) < 2 else (releases[0], releases[-1])
    verdict = str(doc.get("verdict"))

    intent, matched, scores = understand(text)
    named_f, named_a = _focus(text, doc)
    low = str(text or "").lower()
    verb = next((v for v in ACTIONS if re.search(rf"\b{v}", low)), None)
    explicit = [f for f in findings if re.search(rf"\b{re.escape(str(f.get('id')).lower())}\b", low)]
    action = None
    if verb and len(explicit) == 1 and intent != "clinical":
        intent, matched = "act", [verb, str(explicit[0].get("id"))]
    elif intent is None and named_f:
        intent, matched = "changed", [str(f.get("id")) for f in named_f]       # a change was named and nothing else asked
    routed = False
    if intent is None and router is not None:
        choice = router(str(text or ""))
        if choice in {i for i, _, _ in INTENTS}:
            intent, matched, routed = choice, [], True
    about = named_f or findings
    answer, read, sources = [], [], []

    if intent is None:
        answer = ["I cannot answer that from this comparison. I only answer from what the tool found when it compared "
                  f"{old} with {new}, and I do not guess.", "Questions I can answer: " + " ".join(t for _, t, _ in INTENTS)]
        read = ["nothing: no question on my list matched"]

    elif intent == "clinical":
        answer = ["I cannot answer that. This tool says whether a research result still holds on a new release of the data. "
                  "It makes no clinical claims: nothing about treatment, diagnosis or what happens to a patient.",
                  str(x.get("scope") or "Research use only; no clinical claims.")]
        read = ["x_readyset.scope"]

    elif intent == "act":
        f = explicit[0]
        status = ACTIONS[verb]
        fix = "approved" if verb == "approve" else ""
        said = ("confirmed as a real problem" + (", with the suggested fix approved" if fix else "")) if status == "confirmed" \
            else "dismissed as an expected change"
        if not who or not role:
            answer = ["I act only in a named person's name. Tell me your name and your role first, then ask again.",
                      "I have the same rights you have on this page and no more: I can read the findings and record your "
                      "decision. I cannot decide for you."]
        else:
            action = {"finding": f.get("id"), "key": (x.get("review_keys") or {}).get(f.get("id")) or f.get("id"),
                      "status": status, "fix": fix, "reviewer": who, "role": role,
                      "note": "Recorded through the assistant, at this person's request."}
            answer = [f"Ready to record: {_name(f)} {said}, by {who}, {role}.",
                      f"What you are deciding on: {f.get('summary')}",
                      f"What this cannot tell you: {f.get('limitation')}",
                      "Nothing is recorded until you press the button. It is your decision, in your name."]
        read = ["findings (summary, limitation)", "x_readyset.review_keys"]
        sources = [_source(f, x)]

    elif intent == "verdict":
        waiting = [f for f in findings if f.get("needs_human_review")]
        answer.append({"Ready": f"Yes. {new} can be used for the analyses you chose.",
                       "Conditional": f"Not yet. {plural(len(findings), 'change')} in {new} "
                                      f"{'needs' if len(findings) == 1 else 'need'} a person's review first.",
                       "Blocked": f"No. {new} should not be used yet.",
                       "Insufficient Evidence": f"I cannot say. {old} and {new} could not be fully compared."}.get(verdict, f"The verdict is {verdict}."))
        answer.append(f"The verdict is {verdict}. {MEANS.get(verdict, '')}".strip())
        for a in analyses:
            moved = _moved(a)
            if a.get("status") == "changed" and moved:
                k, b, c = moved[-1]
                answer.append(f"{a.get('id')} ({titles.get(a.get('id'), 'analysis')}) was rerun and changed: {k.replace('_', ' ')} "
                              f"went from {shown(b)} to {shown(c)}.")
            elif a.get("status") == "not_rerun":
                answer.append(f"{a.get('id')} ({titles.get(a.get('id'), 'analysis')}) is untouched: nothing it reads changed.")
        if findings:
            answer.append(f"{len(waiting)} of {plural(len(findings), 'change')} still "
                          f"{'waits' if len(waiting) == 1 else 'wait'} for a person's review.")
        read = ["verdict", "analyses (status, before, after)", "findings (needs_human_review)"]
        sources = [_source(f, x) for f in findings]

    elif intent == "changed":
        if not findings:
            answer.append(f"Nothing that the tool compared differs between {old} and {new}.")
        else:
            answer.append(f"{plural(len(about), 'change')}" + (" you asked about:" if named_f else f" between {old} and {new}:"))
            answer += [f"{_name(f)}: {f.get('summary')}" for f in about]
        files = [f for f in x.get("files", []) if isinstance(f, dict)]
        same = [f.get("file") for f in files if f.get("status") == "unchanged"]
        if same and not named_f:
            answer.append(f"{plural(len(same), 'file')} {'is' if len(same) == 1 else 'are'} identical in both releases: {', '.join(same)}.")
        read = ["findings (kind, summary)", "x_readyset.files (status)"]
        sources = [_source(f, x) for f in about]

    elif intent == "matters":
        chosen = [a for a in analyses if not named_a or a.get("id") in named_a]
        for a in chosen:
            moved = _moved(a)
            title = titles.get(a.get("id"), "analysis")
            if a.get("status") == "changed" and moved:
                answer.append(f"{a.get('id')} ({title}) gives a different result on {new}: " + "; ".join(
                    f"{k.replace('_', ' ')} {shown(b)} to {shown(c)}" for k, b, c in moved) + ".")
            elif a.get("status") == "unchanged":
                answer.append(f"{a.get('id')} ({title}) was rerun and its result is the same.")
            elif a.get("status") == "not_rerun":
                answer.append(f"{a.get('id')} ({title}): {a.get('note', 'not rerun.')}")
        for f in about:
            why = ((x.get("rules") or {}).get(f.get("id")) or {}).get("severity")
            if why:
                answer.append(f"{_name(f)}. {why}")
        if not answer:
            answer.append("No change touches an analysis in your question, so no result moves.")
        read = ["analyses (before, after, status)", "x_readyset.rules (severity)", "x_readyset.effects"]
        sources = [_source(f, x) for f in about if f.get("affects_analyses")]

    elif intent == "do":
        ids = {f.get("id") for f in about}
        wanted = [r for r in repairs if ids & set(r.get("addresses") or [])]
        if not wanted:
            answer.append("There is nothing to fix: the tool suggests no repair for this comparison.")
        for r in wanted:
            level = ((x.get("repair_priority") or {}).get(r.get("id")) or {}).get("level")
            targets = [str(t.get("id")) for t in r.get("targets", []) if isinstance(t, dict)]
            answer.append(f"{r.get('id')}, for {', '.join(r.get('addresses') or [])}" + (f" ({level})" if level else "") +
                          f": {str(r.get('action')).replace('_', ' ')}. {r.get('justification')}" +
                          (f" Targets: {', '.join(targets[:6])}{' and others' if len(targets) > 6 else ''}." if targets else ""))
        if wanted:
            answer.append("The tool changes nothing itself. A person confirms or dismisses each change, and approving a fix is a separate decision.")
        read = ["repairs (action, targets, justification, addresses)", "x_readyset.repair_priority"]
        sources = [_source(f, x) for f in about]

    elif intent == "limits":
        answer += [f"{_name(f)}: {f.get('limitation')}" for f in about if f.get("limitation")]
        if x.get("scope"):
            answer.append(str(x["scope"]))
        answer.append("It also cannot tell whether the two releases were given in the wrong order: the trusted one must go first.")
        read = ["findings (limitation)", "x_readyset.scope"]
        sources = [_source(f, x) for f in about]

    elif intent == "samples":
        for f in about:
            ids = _samples(f)
            answer.append(f"{_name(f)}, in {_file(f)}: " + (", ".join(ids[:12]) + (f" and {len(ids) - 12} more" if len(ids) > 12 else "")
                                                        if ids else "no single sample is named; the whole file is involved") + ".")
        if not about:
            answer.append("No samples are involved: nothing changed.")
        read = ["findings (evidence: kind, id, file)"]
        sources = [_source(f, x) for f in about]

    elif intent == "severity":
        for f in about:
            why = ((x.get("rules") or {}).get(f.get("id")) or {}).get("severity")
            answer.append(f"{_name(f)} is rated {f.get('severity')}, with {f.get('confidence')} confidence." + (f" {why}" if why else ""))
        if not about:
            answer.append("There is nothing to rate: nothing changed.")
        read = ["findings (severity, confidence)", "x_readyset.rules (severity)"]
        sources = [_source(f, x) for f in about]

    elif intent == "review":
        reviews = {r.get("finding"): r for r in x.get("reviews", []) if isinstance(r, dict)}
        for f in about:
            r = reviews.get(f.get("id"))
            if not r:
                answer.append(f"{_name(f)}: nobody has reviewed it yet.")
                continue
            said = "confirmed as a real problem" if r.get("status") == "confirmed" else "dismissed as an expected change"
            who = r.get("reviewer") or "a reviewer who gave no name"
            answer.append(f"{_name(f)}: {said} by {who}" + (f", {r['role']}" if r.get("role") else "") +
                          (f", at {r['at']}" if r.get("at") else "") + "." +
                          (" The suggested fix was approved." if r.get("fix") == "approved" else "") +
                          (f" Note: {r['note']}" if r.get("note") else ""))
        if not about:
            answer.append("There is nothing to review: nothing changed.")
        read = ["x_readyset.reviews", "decisions"]

    elif intent == "how":
        answer = [
            "No language model writes my answers. I match your question to one of a fixed list of questions by the words in it, "
            "then fill fixed sentences from the findings file.",
            "So the same question about the same findings always gives the same answer, word for word. Each answer shows a "
            "fingerprint: ask again and the fingerprint is the same. It changes only if the findings or the reviews change.",
            "The findings come from an exact comparison: every sample in a changed file gets a fingerprint of everything it holds, "
            "and the tool looks for samples that traded, were copied, left, joined, were relabelled or went blank. Only the "
            "analyses a change touches are rerun."]
        answer += [f"{_name(f)} was found like this: {((x.get('rules') or {}).get(f.get('id')) or {}).get('detected_by')}"
                   for f in (named_f or []) if ((x.get("rules") or {}).get(f.get("id")) or {}).get("detected_by")]
        read = ["x_readyset.rules (detected_by)"]

    elif intent == "files":
        label = {"changed": "content differs", "unchanged": "identical: every byte was read and matches", "absent": "in neither release",
                 "missing_in_one": "missing in one release", "not_in_both": "in only one release, not needed, so not compared",
                 "unreadable": "could not be read"}
        files = [f for f in x.get("files", []) if isinstance(f, dict)]
        answer.append(f"{plural(len(files), 'file')} looked at, comparing {old} with {new}:")
        answer += [f"{f.get('file')}: {label.get(f.get('status'), f.get('status'))}." + (f" {f['note']}" if f.get("note") else "")
                   for f in files]
        read = ["x_readyset.files", "data.releases (content hashes)"]

    understood = TITLES.get(intent)
    trace = [
        {"step": "Read the question",
         "detail": ((f"My word list did not recognise this wording, so a language model was asked one thing: which of my "
                     f"fixed questions is this closest to? It chose \"{understood}\". It was sent your question and the "
                     f"list of questions. It was not sent the findings or any data, and it wrote none of this answer.")
                    if routed else
                    (f"Matched the words {', '.join(repr(w) for w in matched)} to the question \"{understood}\"."
                     if intent else "No question on the fixed list matched the words in it, so I did not answer."))},
    ]
    if intent and (named_f or named_a):
        trace.append({"step": "Narrowed it",
                      "detail": "The question names " + ", ".join([str(f.get("id")) for f in named_f] + list(named_a)) + "."})
    trace.append({"step": "Working for",
                  "detail": (f"{who}, {role}. I have this person's rights on the page and no more: I read the findings, and I can "
                             f"prepare their decision for them to record in their own name."
                             if who and role else "Nobody named yet, so I can read the findings and record nothing.")})
    trace.append({"step": "Read from the findings file", "detail": "; ".join(read) + "."})
    for s in sources:
        detail = f"{s['finding']} rests on {s['file']}" + (f", samples {', '.join(s['samples'][:6])}" +
                                                         (f" and {len(s['samples']) - 6} more" if len(s["samples"]) > 6 else "") if s["samples"] else "")
        if s.get("check"):
            c = s["check"]
            detail += ". Check it yourself, row " + str(c["row"]) + ": " + "; ".join(
                f"{v['sample']} was {v['before']} in {c['releases'][0]}, is {v['after']} in {c['releases'][-1]}" for v in c["values"][:2])
        trace.append({"step": "Evidence", "detail": detail + "."})
    trace.append({"step": "Wrote the answer", "detail": "By fixed sentence patterns. No language model, no randomness, nothing from outside the findings file."})

    based_on = findings_fingerprint(doc)
    reply = {"question": str(text or ""), "can_answer": intent is not None, "understood_as": understood, "intent": intent,
             "answer": answer, "trace": trace, "sources": sources, "suggestions": [t for _, t, _ in INTENTS],
             "understood_by": "a language model, for the wording only" if routed else "the fixed word list",
             "based_on": based_on, "action": action, "acting_for": {"name": who, "role": role} if who and role else None}
    reply["fingerprint"] = _hash({"intent": intent, "answer": answer, "based_on": based_on, "action": action,
                                  "focus": [f.get("id") for f in named_f] + list(named_a)})
    return reply


def consistency(doc, text, times=100, actor=None, router=None):
    """Ask the same question many times and count the different answers. The count must be 1."""
    times = max(2, min(int(times), 1000))
    seen = {json.dumps(ask(doc, text, actor, router), sort_keys=True) for _ in range(times)}
    return {"asked": times, "different_answers": len(seen), "fingerprint": ask(doc, text, actor, router)["fingerprint"]}
