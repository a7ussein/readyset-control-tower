"""What changed in one file between two releases.

Given the old and new version of a file, `compare_file` returns a list of raw findings. Each names its kind, the
samples behind it, and the exact things that changed (`changes`), which is what lets the caller decide which
analyses it touches.

The order of explanation, so that each changed sample is explained once:
  1. swap (or a longer rotation): samples exchanged whole profiles
  2. rename: a new id carries the profile of a sample that left
  3. duplicate: an id carries a profile another id holds, and the two were not identical before
  4. membership: an id that exists in only one release
  5. cell by cell, for a sample whose profile changed but matches nobody: a value that went blank, a clinical label
     that changed, or a difference that fits no pattern
"""
from collections import Counter, defaultdict

from . import release
from .release import CLINICAL, EMPTY, PROTEIN, sample_type

TYPE_NAMES = {"01": "primary tumour", "11": "normal tissue", "06": "metastasis"}
MAX_DETAILED = 400          # beyond this many unexplained samples in one file, report them without cell detail
KEY_KIND = {PROTEIN: "protein"}


def _plural(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _by_type(samples):
    counts = Counter(TYPE_NAMES.get(sample_type(s), "other") for s in samples)
    return ", ".join(_plural(n, name) for name, n in counts.most_common())


def _key_kind(file):
    return KEY_KIND.get(file, "gene")


def classify(fp_a, fp_b):
    """Sort the samples of one file into swaps, renames, copies, departures, arrivals and the unexplained."""
    ids_a, ids_b = set(fp_a), set(fp_b)
    gone, new, common = ids_a - ids_b, ids_b - ids_a, ids_a & ids_b
    changed = {s for s in common if fp_a[s] != fp_b[s]}
    owners_a, holders_b = defaultdict(list), defaultdict(list)
    for s in sorted(fp_a):
        if fp_a[s] is not None:
            owners_a[fp_a[s]].append(s)
    for s in sorted(fp_b):
        if fp_b[s] is not None:
            holders_b[fp_b[s]].append(s)

    # 1. swaps and rotations: s now carries the old profile of another changed sample, and the chain closes.
    carries = {}
    for s in sorted(changed):
        donors = [t for t in owners_a.get(fp_b[s], []) if t != s and t in changed]
        if donors:
            carries[s] = donors[0]
    cycles, in_cycle = [], set()
    for start in sorted(carries):
        if start in in_cycle:
            continue
        path, node = [], start
        while node in carries and node not in path and node not in in_cycle:
            path.append(node)
            node = carries[node]
        if node == start and len(path) >= 2:
            cycles.append(path)
            in_cycle.update(path)

    # 2. renames: a new id holds, alone, the profile of a sample that left.
    renames, renamed_old, renamed_new = [], set(), set()
    for n in sorted(new):
        f = fp_b[n]
        if f is None or holders_b[f] != [n]:
            continue
        olds = [t for t in owners_a.get(f, []) if t in gone and t not in renamed_old]
        if olds:
            renames.append((olds[0], n))
            renamed_old.add(olds[0])
            renamed_new.add(n)

    # 3. copies: several ids hold one profile in the new release, and they did not all hold it before.
    copies = []                         # (the copy, the sample it copies)
    for f, holders in holders_b.items():
        if len(holders) < 2:
            continue
        kept = [s for s in holders if fp_a.get(s) == f]
        fresh = [s for s in holders if fp_a.get(s) != f and s not in in_cycle and s not in renamed_new]
        if not fresh:
            continue
        if kept:
            source = kept[0]
        else:
            source, fresh = fresh[0], fresh[1:]
        copies += [(c, source) for c in fresh]
    copied = {c for c, _ in copies}

    unexplained = sorted(changed - in_cycle - copied)
    return {"cycles": cycles, "renames": renames, "copies": sorted(copies), "gone": sorted(gone), "new": sorted(new),
            "unexplained": unexplained}


def _sample(sample, file, rel, note=None):
    p = {"kind": "sample", "id": sample, "release": rel, "file": file}
    if note:
        p["note"] = note
    return p


def _profile(file, sample):
    return {"scope": "profile", "file": file, "sample": sample}


def _subgroups(samples, describe):
    """'by RNA subtype: Her2 5; by ER status: Negative 3, Positive 2' for a set of samples, from their clinical record."""
    if not describe or not samples:
        return ""
    parts = []
    for label, values in describe(samples).items():
        counts = Counter(v for v in values if v)
        if counts:
            parts.append(f"by {label}: " + ", ".join(f"{k} {n}" for k, n in counts.most_common()))
    return "; ".join(parts)


def compare_file(file, path_a, path_b, rel_a, rel_b, describe=None):
    """Raw findings for one file whose content differs between the two releases.

    `describe(samples)` may return {label: [value per sample]} from the clinical record, used to say which
    subgroups lost coverage."""
    kind_a, kind_b = release.layout(path_a), release.layout(path_b)
    if kind_a != kind_b:
        raise release.Unreadable(f"{file} is laid out differently in the two releases")
    findings = []

    if kind_a == "row":
        cols_a, table_a = release.read_rows(path_a)
        cols_b, table_b = release.read_rows(path_b)
        shared = [c for c in cols_a if c in set(cols_b)]
        keys_gone, keys_new = [c for c in cols_a if c not in set(cols_b)], [c for c in cols_b if c not in set(cols_a)]
        fp_a, fp_b = release.row_fingerprints(table_a, shared), release.row_fingerprints(table_b, shared)

        def cells(samples):
            return ({s: table_a[s] for s in samples}, {s: table_b[s] for s in samples})
        key_word, scope = "column", "column"
    else:
        names_a, names_b = release.row_names(path_a), release.row_names(path_b)
        set_a, set_b = set(names_a), set(names_b)
        shared_set = set_a & set_b
        shared = [n for n in names_a if n in shared_set]
        keys_gone, keys_new = [n for n in names_a if n not in set_b], [n for n in names_b if n not in set_a]
        in_order = shared == [n for n in names_b if n in shared_set]
        fp_a = release.column_fingerprints(path_a, shared_set, in_order)
        fp_b = release.column_fingerprints(path_b, shared_set, in_order)

        def cells(samples):
            wanted = set(samples)
            return (release.column_cells(path_a, wanted, shared_set), release.column_cells(path_b, wanted, shared_set))
        key_word, scope = "row", "row"

    # A whole row or column that appeared or disappeared.
    if keys_gone or keys_new:
        parts = []
        if keys_gone:
            parts.append(f"{_plural(len(keys_gone), key_word)} from {rel_a} {'is' if len(keys_gone) == 1 else 'are'} "
                         f"missing in {rel_b} ({', '.join(keys_gone[:5])}{'…' if len(keys_gone) > 5 else ''})")
        if keys_new:
            parts.append(f"{_plural(len(keys_new), key_word)} appeared in {rel_b} "
                         f"({', '.join(keys_new[:5])}{'…' if len(keys_new) > 5 else ''})")
        evidence = [{"kind": "file", "id": file, "release": rel_b, "note": "; ".join(parts)}]
        if kind_a == "column":
            evidence += [{"kind": _key_kind(file), "id": k, "release": rel_a, "file": file, "note": f"not in {rel_b}"}
                         for k in keys_gone[:20]]
            evidence += [{"kind": _key_kind(file), "id": k, "release": rel_b, "file": file, "note": f"not in {rel_a}"}
                         for k in keys_new[:20]]
        findings.append({
            "kind": "other", "file": file, "confidence": "high",
            "summary": f"The shape of {file} changed: " + "; ".join(parts) + ".",
            "evidence": evidence,
            "changes": [{"scope": scope, "file": file, "key": k} for k in keys_gone + keys_new],
            "limitation": f"Samples were compared on the {key_word}s both releases share. Nothing can be said about values "
                          f"in a {key_word} that exists in only one release.",
            "repair": None})

    c = classify(fp_a, fp_b)

    # A sample that existed before only counts as a copy if most of what it holds changed. If a few cells changed and
    # the result happens to equal another sample, that is an edit, and it is explained cell by cell below.
    overwritten = [cp for cp, _ in c["copies"] if cp in fp_a]
    if overwritten:
        old, new_cells = cells(overwritten)
        for s in overwritten:
            informative = [k for k in shared if old[s].get(k, "") not in EMPTY or new_cells[s].get(k, "") not in EMPTY]
            differ = sum(1 for k in informative if old[s].get(k, "") != new_cells[s].get(k, ""))
            if not informative or differ / len(informative) < 0.5:
                c["copies"] = [(cp, src) for cp, src in c["copies"] if cp != s]
                c["unexplained"] = sorted(set(c["unexplained"]) | {s})

    for cycle in c["cycles"]:
        two = len(cycle) == 2
        evidence = [_sample(s, file, rel_b, f"its profile in {rel_b} equals {t}'s profile in {rel_a}")
                    for s, t in zip(cycle, cycle[1:] + cycle[:1])]
        evidence.append({"kind": "file", "id": file, "release": rel_b, "note": f"content differs from {rel_a}"})
        findings.append({
            "kind": "sample_swap", "file": file, "confidence": "high",
            "summary": (f"Two samples traded their whole profile in {file}: in {rel_b} each one carries the other's "
                        f"{rel_a} values." if two else
                        f"{len(cycle)} samples rotated their profiles in {file}: in {rel_b} each carries the {rel_a} "
                        f"values of another."),
            "evidence": evidence, "changes": [_profile(file, s) for s in cycle],
            "limitation": "An exchange is inferred from matching profiles. It shows the labels were exchanged, not "
                          "which release is correct.",
            "repair": {"action": "restore_from_previous_release", "targets": [_sample(s, file, rel_b) for s in cycle],
                       "justification": f"Each sample's {rel_b} profile is another sample's {rel_a} profile. Restoring "
                                        f"them from {rel_a} undoes the exchange."}})

    if c["copies"]:
        copies = c["copies"]
        # The copies are the evidence. The sample each one copies is named in its note, not listed as a sample of its
        # own: the source did nothing wrong, and listing it would look like a tenth changed sample.
        evidence = [_sample(copy, file, rel_b,
                            f"identical to {src} in {rel_b}; " + (f"this id is not in {rel_a}" if copy not in fp_a
                                                                 else f"it held different values in {rel_a}"))
                    for copy, src in copies]
        brand_new = [cp for cp, _ in copies if cp not in fp_a]
        overwritten = [cp for cp, _ in copies if cp in fp_a]
        targets, action, why = [], "exclude", []
        if brand_new:
            targets += [_sample(s, file, rel_b) for s in brand_new]
            why.append(f"{_plural(len(brand_new), 'id')} not in {rel_a} carry exact copies of other samples; excluding "
                       f"them removes the double-counted measurements")
        repair = {"action": action, "targets": targets, "justification": "; ".join(why) + "."} if brand_new else None
        findings.append({
            "kind": "duplicate", "file": file, "confidence": "high",
            "summary": f"{_plural(len(copies), 'sample id')} in {rel_b} carry a profile identical to another sample in "
                       f"{file}, and the two were not identical in {rel_a}.",
            "evidence": evidence, "changes": [_profile(file, s) for s, _ in copies],
            "limitation": "Identical profiles under different ids are treated as copies. Two real samples with "
                          "identical measurements would look the same.",
            "repair": repair,
            "extra_repair": ({"action": "restore_from_previous_release",
                              "targets": [_sample(s, file, rel_b) for s in overwritten],
                              "justification": f"{_plural(len(overwritten), 'sample')} that existed in {rel_a} now "
                                               f"hold a copy of another sample's values."} if overwritten else None)})

    renamed_old = {o for o, _ in c["renames"]}
    renamed_new = {n for _, n in c["renames"]}
    copied_ids = {cp for cp, _ in c["copies"]}
    arrivals = [s for s in c["new"] if s not in copied_ids]      # a new id that is a copy is in the duplicate finding
    if c["gone"] or arrivals:
        gone, new = c["gone"], arrivals
        evidence = [_sample(s, file, rel_a, f"in {rel_a}, absent from {rel_b}"
                            + (f"; its profile now appears under {dict(c['renames'])[s]}" if s in renamed_old else ""))
                    for s in gone]
        evidence += [_sample(s, file, rel_b, f"in {rel_b}, absent from {rel_a}"
                             + (f"; carries the {rel_a} profile of {dict((n, o) for o, n in c['renames'])[s]}"
                                if s in renamed_new else ""))
                     for s in new]
        lost = _subgroups(gone, describe)
        same_count = len(fp_a) == len(fp_b)
        if gone and same_count and not new:
            lead = (f"{file} has the same number of samples in both releases, but {_plural(len(gone), 'sample')} from "
                    f"{rel_a} {'is' if len(gone) == 1 else 'are'} gone, replaced by other ids")
        elif len(gone) == len(new) and gone:
            lead = (f"{file} has the same number of samples in both releases, but {_plural(len(gone), 'sample')} from "
                    f"{rel_a} {'is' if len(gone) == 1 else 'are'} gone and {_plural(len(new), 'new id')} appeared")
        else:
            bits = []
            if gone:
                bits.append(f"{_plural(len(gone), 'sample')} from {rel_a} {'is' if len(gone) == 1 else 'are'} "
                            f"missing from {rel_b} ({_by_type(gone)})")
            if new:
                bits.append(f"{_plural(len(new), 'sample id')} appeared in {rel_b} ({_by_type(new)})")
            lead = f"Who is in {file} changed: " + "; ".join(bits)
        if c["renames"]:
            lead += f". {_plural(len(c['renames']), 'new id')} carry the unchanged profile of a sample that left, " \
                    f"which looks like a rename"
        if lost:
            lead += f". Coverage lost, {lost}"
        truly_gone = [s for s in gone if s not in renamed_old]
        repair = None
        if truly_gone:
            repair = {"action": "restore_from_previous_release", "targets": [_sample(s, file, rel_a) for s in truly_gone],
                      "justification": f"{_plural(len(truly_gone), 'sample')} in {rel_a} {'is' if len(truly_gone) == 1 else 'are'} "
                                       f"missing from {rel_b}."}
        elif c["renames"]:
            repair = {"action": "flag_for_review", "targets": [_sample(n, file, rel_b) for _, n in c["renames"]],
                      "justification": "The same measurements appear under a different sample id. A person should "
                                       "confirm which id is right."}
        findings.append({
            "kind": "membership_change", "file": file, "confidence": "high", "summary": lead + ".",
            "evidence": evidence, "changes": [_profile(file, s) for s in gone + new],
            "limitation": "Reports which ids entered and left. It does not say why.", "repair": repair})

    # Samples whose values changed and match nobody: look at the cells.
    unexplained = c["unexplained"]
    if len(unexplained) > MAX_DETAILED:
        findings.append({
            "kind": "other", "file": file, "confidence": "low",
            "summary": f"{len(unexplained)} samples in {file} hold different values in {rel_b} and match no known "
                       f"pattern. There are too many to compare cell by cell in this run.",
            "evidence": [_sample(s, file, rel_b, "values differ") for s in unexplained]
                        + [{"kind": "file", "id": file, "release": rel_b, "note": f"content differs from {rel_a}"}],
            "changes": [_profile(file, s) for s in unexplained],
            "limitation": "The tool can show that these samples changed. It did not examine which cells.",
            "repair": {"action": "flag_for_review", "targets": [{"kind": "file", "id": file, "release": rel_b}],
                       "justification": "A large part of this file changed in a way the tool cannot classify."}})
    elif unexplained:
        old, new_cells = cells(unexplained)
        blanked, relabelled, other = defaultdict(list), defaultdict(list), []
        for s in unexplained:
            for key in shared:
                a, b = old[s].get(key, ""), new_cells[s].get(key, "")
                if a == b:
                    continue
                if a not in EMPTY and b in EMPTY:
                    blanked[key if kind_a == "row" else None].append((s, key, a, b))
                elif file == CLINICAL:
                    relabelled[key].append((s, key, a, b))
                else:
                    other.append((s, key, a, b))

        for key, hits in sorted(blanked.items(), key=lambda kv: str(kv[0])):
            who = sorted({s for s, *_ in hits})
            keys = sorted({k for _, k, *_ in hits})
            per = defaultdict(list)
            for s, k, a, b in hits:
                per[s].append(f"{k}: '{a}' in {rel_a}, blank in {rel_b}")
            evidence = [_sample(s, file, rel_b, "; ".join(per[s][:5]) + ("; …" if len(per[s]) > 5 else "")) for s in who]
            if kind_a == "column":
                evidence += [{"kind": _key_kind(file), "id": k, "release": rel_b, "file": file} for k in keys[:20]]
            where = f"the column {key}" if kind_a == "row" else (keys[0] if len(keys) == 1 else _plural(len(keys), "row"))
            findings.append({
                "kind": "missing_data", "file": file, "confidence": "high",
                "summary": f"{_plural(len(hits), 'value')} present in {rel_a} {'is' if len(hits) == 1 else 'are'} blank "
                           f"in {rel_b}: {where} of {file}, {_plural(len(who), 'sample')}.",
                "evidence": evidence,
                "changes": [{"scope": "cell", "file": file, "sample": s, "key": k} for s, k, *_ in hits],
                "limitation": "Only cells that differ between the two releases are compared. Values missing in both "
                              "are not reported.",
                "repair": {"action": "restore_from_previous_release", "targets": [_sample(s, file, rel_b) for s in who],
                           "justification": f"The values exist in {rel_a} and are blank in {rel_b}."}})

        for key, hits in sorted(relabelled.items()):
            who = sorted({s for s, *_ in hits})
            evidence = [_sample(s, file, rel_b, f"{k}: '{a}' in {rel_a}, '{b}' in {rel_b}") for s, k, a, b in sorted(hits)]
            findings.append({
                "kind": "label_conflict", "file": file, "confidence": "high",
                "summary": f"The clinical column {key} changed value for {_plural(len(who), 'sample')} between "
                           f"{rel_a} and {rel_b}.",
                "evidence": evidence,
                "changes": [{"scope": "cell", "file": file, "sample": s, "key": k} for s, k, *_ in hits],
                "limitation": "The two releases disagree. The tool cannot tell which value is correct.",
                "repair": {"action": "flag_for_review", "targets": [_sample(s, file, rel_b) for s in who],
                           "justification": f"The {key} value differs between releases for these samples, and the "
                                            f"data alone does not show which is right."}})

        if other:
            who = sorted({s for s, *_ in other})
            per = Counter(s for s, *_ in other)
            first = {}
            for s, k, a, b in other:
                first.setdefault(s, f"e.g. {k}: '{a}' in {rel_a}, '{b}' in {rel_b}")
            evidence = [_sample(s, file, rel_b, f"{_plural(per[s], 'cell')} differ; {first[s]}") for s in who]
            evidence.append({"kind": "file", "id": file, "release": rel_b, "note": f"content differs from {rel_a}"})
            findings.append({
                "kind": "other", "file": file, "confidence": "low",
                "summary": f"{_plural(len(other), 'cell')} in {file} differ between releases and match no known "
                           f"pattern (not an exchange, a copy, a relabel or a blank), across {_plural(len(who), 'sample')}.",
                "evidence": evidence,
                "changes": [{"scope": "cell", "file": file, "sample": s, "key": k} for s, k, *_ in other],
                "limitation": "The tool can show that these values changed. It cannot classify the change or say "
                              "whether it is an error.",
                "repair": {"action": "flag_for_review", "targets": [{"kind": "file", "id": file, "release": rel_b}],
                           "justification": "Values changed in a way the tool cannot classify. A person should decide "
                                            "whether the new values are corrections or errors."}})
    return findings
