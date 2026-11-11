"""Changes the organisers' script cannot make, tried on the real release.

    python3 tests/releases/own_changes.py --challenge PATH/TO/oncosys-hackathon-challenge

`make_release.py` makes swaps, copies and clinical relabels. The hidden release may hold other things. Each case here
takes the real release A, writes a changed copy with a known answer, runs the engine, and checks:
  - the findings: exactly the expected kind, file, samples and affected analyses, and nothing else;
  - the verdict;
  - where the organisers' `reference_analyses.py` can run on the changed copy, that our before and after equal it and
    that an analysis we did not rerun did not move.

Untouched files are symlinked, so a case costs only the one file it changes. Needs pandas for the organisers' script.
"""
import csv
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))          # the repository root
from control_tower import compare  # noqa: E402
from control_tower.release import FILES  # noqa: E402

CLINICAL, SURVIVAL, PROTEIN = "clinical.tsv", "survival.tsv", "protein_rppa.tsv.gz"
MUTATION, RNA = "mutation_gene_level.tsv.gz", "rna_hiseq.tsv.gz"
ER, PAM50 = "breast_carcinoma_estrogen_receptor_status", "PAM50Call_RNAseq"


def opener(path, mode):
    return gzip.open(path, mode + "t", newline="", encoding="utf-8", **({"compresslevel": 1} if mode == "w" else {})) \
        if path.endswith(".gz") else open(path, mode, newline="", encoding="utf-8")


def rewrite(src, dst, header=None, line=None, keep=None):
    """Copy a tab-separated file, optionally changing the header, each data line, or which lines are kept."""
    with opener(src, "r") as fi, opener(dst, "w") as fo:
        head = fi.readline().rstrip("\r\n").split("\t")
        fo.write("\t".join(header(head) if header else head) + "\n")
        for raw_line in fi:
            cells = raw_line.rstrip("\r\n").split("\t")
            if keep and not keep(cells):
                continue
            fo.write("\t".join(line(cells, head) if line else cells) + "\n")


def load(path):
    with opener(path, "r") as fh:
        return [row for row in csv.reader(fh, delimiter="\t")]


def save(path, rows):
    with opener(path, "w") as fh:
        csv.writer(fh, delimiter="\t", lineterminator="\n").writerows(rows)


class World:
    """What the cases need to know about the real release to pick their samples."""

    def __init__(self, raw):
        self.raw = raw
        rows = load(os.path.join(raw, CLINICAL))
        self.clin_head = rows[0]
        self.clin = {r[0]: dict(zip(rows[0], r)) for r in rows[1:]}
        self.protein = load(os.path.join(raw, PROTEIN))
        self.p_samples = self.protein[0][1:]
        self.p_rows = [r[0] for r in self.protein[1:]]
        with opener(os.path.join(raw, RNA), "r") as fh:
            self.rna_samples = fh.readline().rstrip("\n").split("\t")[1:]
        with opener(os.path.join(raw, MUTATION), "r") as fh:
            self.mut_samples = fh.readline().rstrip("\n").split("\t")[1:]
            self.mut_first_row = fh.readline().split("\t", 1)[0]
        self.surv = load(os.path.join(raw, SURVIVAL))

    def protein_with(self, er=None, pam50=None, n=1, skip=0):
        out = [s for s in self.p_samples if s[13:15] == "01" and s in self.clin
               and (er is None or self.clin[s][ER] == er) and (pam50 is None or self.clin[s][PAM50] == pam50)]
        return out[skip:skip + n]


def cases(w):
    """(name, what it is, changed file, function writing that file, expected) for each case."""
    P = os.path.join(w.raw, PROTEIN)
    C = os.path.join(w.raw, CLINICAL)
    out = []

    def add(name, what, file, write, findings, verdict, statuses=None):
        out.append({"name": name, "what": what, "file": file, "write": write, "findings": findings,
                    "verdict": verdict, "statuses": statuses})

    def f(kind, file, samples, affects):
        return (kind, file, frozenset(samples), tuple(affects))

    def protein_edit(change):
        def write(dst):
            rows = [list(r) for r in w.protein]
            change(rows)
            save(dst, rows)
        return write

    col = {s: i + 1 for i, s in enumerate(w.p_samples)}
    era = w.p_rows.index("ERALPHA") + 1
    other_row_name = next(r for r in w.p_rows if r != "ERALPHA")
    other_row = w.p_rows.index(other_row_name) + 1

    three = w.protein_with(er="Positive", n=3)

    def blank_era(rows):
        for s in three:
            rows[era][col[s]] = ""
    add("o1-blank-er-alpha", "ER-alpha value blanked for three samples", PROTEIN, protein_edit(blank_era),
        [f("missing_data", PROTEIN, three, ["A1"])], "Conditional", {"A1": "changed", "A2": "not_rerun"})

    two = w.protein_with(er="Negative", n=2)

    def blank_other(rows):
        for s in two:
            rows[other_row][col[s]] = ""
    add("o2-blank-other-protein", f"{other_row_name} value blanked for two samples", PROTEIN, protein_edit(blank_other),
        [f("missing_data", PROTEIN, two, [])], "Conditional", {"A1": "not_rerun", "A2": "not_rerun"})

    one = w.protein_with(er="Positive", n=1, skip=5)

    def nudge(rows):
        rows[era][col[one[0]]] = str(round(float(rows[era][col[one[0]]]) + 1.5, 6))
    add("o3-edit-er-alpha-number", "one ER-alpha number edited", PROTEIN, protein_edit(nudge),
        [f("other", PROTEIN, one, ["A1"])], "Conditional", {"A1": "changed", "A2": "not_rerun"})

    old = w.protein_with(er="Positive", n=1, skip=9)[0]
    new_id = "TCGA-ZZ-9999-01"

    def rename(rows):
        rows[0][col[old]] = new_id
    add("o4-rename-sample", "one protein sample renamed to an id found nowhere else", PROTEIN, protein_edit(rename),
        [f("membership_change", PROTEIN, [old, new_id], ["A1"])], "Conditional", {"A1": "changed", "A2": "not_rerun"})

    add("o5-drop-er-alpha-row", "the ER-alpha row removed from the protein file", PROTEIN,
        protein_edit(lambda rows: rows.pop(era)), [f("other", PROTEIN, [], ["A1"])], "Blocked", None)

    add("o6-drop-other-row", f"the {other_row_name} row removed from the protein file", PROTEIN,
        protein_edit(lambda rows: rows.pop(other_row)), [f("other", PROTEIN, [], [])], "Conditional",
        {"A1": "not_rerun", "A2": "not_rerun"})

    def shuffle(rows):
        body = rows[1:]
        body.reverse()
        order = [0] + list(range(len(rows[0]) - 1, 0, -1))
        rows[:] = [[r[i] for i in order] for r in [rows[0]] + body]
    add("o7-reorder-rows-and-columns", "protein rows and columns reordered, no value changed", PROTEIN,
        protein_edit(shuffle), [], "Ready", {"A1": "not_rerun", "A2": "not_rerun"})

    m2 = w.mut_samples[3:5]

    def mut(dst):
        idx = None

        def line(cells, head):
            nonlocal idx
            if idx is None:
                idx = [head.index(s) for s in m2]
            if cells[0] == w.mut_first_row:
                for i in idx:
                    cells[i] = "1" if cells[i] == "0" else "0"
            return cells
        rewrite(os.path.join(w.raw, MUTATION), dst, line=line)
    add("o8-edit-mutation-cells", "one mutation cell flipped for two samples", MUTATION, mut,
        [f("other", MUTATION, m2, [])], "Conditional", {"A1": "not_rerun", "A2": "not_rerun"})

    normals = [s for s in w.rna_samples if s[13:15] == "11"][:2]

    def rna(dst):
        idx = None

        def line(cells, head):
            nonlocal idx
            if idx is None:
                idx = [head.index(s) for s in normals]
            cells[idx[0]], cells[idx[1]] = cells[idx[1]], cells[idx[0]]
            return cells
        rewrite(os.path.join(w.raw, RNA), dst, line=line)
    add("o9-swap-normal-tissue-rna", "two normal-tissue samples swapped in the RNA file", RNA, rna,
        [f("sample_swap", RNA, normals, [])], "Conditional", {"A1": "not_rerun", "A2": "not_rerun"})

    x = w.protein_with(er="Positive", pam50="LumA", n=1, skip=2)[0]
    y = w.protein_with(er="Negative", pam50="Basal", n=1, skip=2)[0]

    def clinical_swap(dst):
        rows = load(C)
        at = {r[0]: i for i, r in enumerate(rows)}
        rx, ry = rows[at[x]], rows[at[y]]
        rows[at[x]], rows[at[y]] = [x] + ry[1:], [y] + rx[1:]
        save(dst, rows)
    add("o10-swap-clinical-records", "two patients' whole clinical records exchanged", CLINICAL, clinical_swap,
        [f("sample_swap", CLINICAL, [x, y], ["A1", "A2"])], "Conditional", {"A1": "changed", "A2": "unchanged"})

    gone = w.protein_with(er="Positive", pam50="LumA", n=1, skip=7)[0]
    add("o11-delete-clinical-record", "one sample's clinical record deleted", CLINICAL,
        lambda dst: rewrite(C, dst, keep=lambda cells: cells[0] != gone),
        [f("membership_change", CLINICAL, [gone], ["A1", "A2"])], "Conditional", {"A1": "changed", "A2": "changed"})

    add("o12-add-clinical-column", "a new column added to the clinical file", CLINICAL,
        lambda dst: rewrite(C, dst, header=lambda h: h + ["site_audit_flag"], line=lambda cells, h: cells + ["ok"]),
        [f("other", CLINICAL, [], [])], "Conditional", {"A1": "not_rerun", "A2": "not_rerun"})

    er2 = w.protein_with(er="Positive", n=2, skip=12)
    k = w.clin_head.index(ER)

    def blank_er(cells, head):
        if cells[0] in er2:
            cells[k] = ""
        return cells
    add("o13-blank-er-status", "ER status blanked for two samples", CLINICAL, lambda dst: rewrite(C, dst, line=blank_er),
        [f("missing_data", CLINICAL, er2, ["A1"])], "Conditional", {"A1": "changed", "A2": "not_rerun"})

    s2 = [r[0] for r in w.surv[1:] if r[0][13:15] == "01"][20:22]
    t = w.surv[0].index("OS.time")

    def surv(dst):
        rows = [list(r) for r in w.surv]
        for r in rows[1:]:
            if r[0] in s2:
                r[t] = str(int(float(r[t] or 0)) + 400)
        save(dst, rows)
    add("o14-edit-survival-time", "survival time edited for two samples", SURVIVAL, surv,
        [f("other", SURVIVAL, s2, [])], "Conditional", {"A1": "not_rerun", "A2": "not_rerun"})

    def corrupt(dst):
        with open(dst, "wb") as fh:
            fh.write(b"this is not a gzip file")
    add("o15-corrupt-protein-file", "the protein file replaced by something unreadable", PROTEIN, corrupt,
        None, "Insufficient Evidence", None)

    add("o16-protein-file-missing", "the protein file absent from the new release", PROTEIN, None,
        None, "Insufficient Evidence", None)

    # ---- several changes at once ---------------------------------------------------------------------------------
    def both(*changes):
        def change(rows):
            for ch in changes:
                ch(rows)
        return change

    add("o17-four-own-kinds-three-files",
        "ER-alpha blanked, a sample renamed, mutation cells flipped and a clinical record deleted, together",
        [PROTEIN, MUTATION, CLINICAL],
        {PROTEIN: protein_edit(both(blank_era, rename)), MUTATION: mut,
         CLINICAL: lambda dst: rewrite(C, dst, keep=lambda cells: cells[0] != gone)},
        [f("missing_data", PROTEIN, three, ["A1"]), f("membership_change", PROTEIN, [old, new_id], ["A1"]),
         f("other", MUTATION, m2, []), f("membership_change", CLINICAL, [gone], ["A1", "A2"])],
        "Conditional", {"A1": "changed", "A2": "changed"})

    unused = next(s for s, r in w.clin.items() if s[13:15] == "01" and s not in col and r[ER] == "Positive")
    donor = w.protein_with(er="Negative", n=1, skip=15)[0]
    z = w.protein_with(er="Negative", n=1, skip=6)
    lum = [s for s, r in w.clin.items() if s[13:15] == "01" and r[PAM50] == "LumA"][30:33]
    pk = w.clin_head.index(PAM50)

    def script_like(rows):
        for r in rows[1:]:                                   # a swap: x and y trade every value
            r[col[x]], r[col[y]] = r[col[y]], r[col[x]]
        rows[0].append(unused)                               # a copy: the donor's values under an id that has a clinical record
        for r in rows[1:]:
            r.append(r[col[donor]])
        rows[era][col[z[0]]] = ""                            # and one ER-alpha value blanked

    def pam_relabel(cells, head):
        if cells[0] in lum:
            cells[pk] = "LumB"
        return cells
    add("o18-script-kinds-mixed-with-ours",
        "a swap, a copy onto an id with a clinical record, a blanked ER-alpha value and a subtype relabel, together",
        [PROTEIN, CLINICAL], {PROTEIN: protein_edit(script_like), CLINICAL: lambda dst: rewrite(C, dst, line=pam_relabel)},
        [f("sample_swap", PROTEIN, [x, y], ["A1"]), f("duplicate", PROTEIN, [unused], ["A1"]),
         f("missing_data", PROTEIN, z, ["A1"]), f("label_conflict", CLINICAL, lum, ["A2"])],
        "Conditional", {"A1": "changed", "A2": "changed"})

    # ---- changes at scale ----------------------------------------------------------------------------------------
    many_er = [s for s, r in w.clin.items() if s[13:15] == "01" and r[ER] == "Positive"][:300]
    many_set = set(many_er)

    def er_many(cells, head):
        if cells[0] in many_set:
            cells[k] = "Negative"
        return cells
    add("o19-relabel-er-300-samples", "ER status relabelled for 300 samples", CLINICAL,
        lambda dst: rewrite(C, dst, line=er_many), [f("label_conflict", CLINICAL, many_er, ["A1"])], "Conditional",
        {"A1": "changed", "A2": "not_rerun"})

    hk = w.clin_head.index("histological_type")
    many_h = [s for s, r in w.clin.items() if r["histological_type"]][:700]
    many_h_set = set(many_h)

    def hist_many(cells, head):
        if cells[0] in many_h_set:
            cells[hk] = "Recoded"
        return cells
    add("o20-relabel-unread-column-700", "a column neither analysis reads relabelled for 700 samples", CLINICAL,
        lambda dst: rewrite(C, dst, line=hist_many), [f("label_conflict", CLINICAL, many_h, [])], "Conditional",
        {"A1": "not_rerun", "A2": "not_rerun"})

    def shift_era(rows):
        for i in range(1, len(rows[era])):
            rows[era][i] = str(round(float(rows[era][i]) + 0.5, 6))
    add("o21-shift-whole-er-alpha-row", "every sample's ER-alpha value shifted by 0.5", PROTEIN, protein_edit(shift_era),
        [f("other", PROTEIN, w.p_samples, ["A1"])], "Conditional", {"A1": "changed", "A2": "not_rerun"})

    add("o22-rewrite-whole-rna-file", "every value in the 180 MB RNA file rewritten with an extra digit (25 million cells)",
        RNA, lambda dst: rewrite(os.path.join(w.raw, RNA), dst, line=lambda cells, h: [cells[0]] + [v + "0" for v in cells[1:]]),
        [f("other", RNA, w.rna_samples, [])], "Conditional", {"A1": "not_rerun", "A2": "not_rerun"})

    by_patient = {}
    for r in w.surv[1:]:
        by_patient.setdefault(r[0][:12], []).append(r)
    twins = next([a[0], b[0]] for rows in by_patient.values() if len(rows) == 2
                 for a, b in [rows] if a[1:] == b[1:] and {a[0][13:15], b[0][13:15]} == {"01", "11"})

    def surv_twins(dst):
        rows = [list(r) for r in w.surv]
        for r in rows[1:]:
            if r[0] in twins:
                r[t] = str(int(float(r[t] or 0)) + 90)
        save(dst, rows)
    add("o23-update-shared-survival-record", "one patient's survival record updated; its tumour and normal rows change together",
        SURVIVAL, surv_twins, [f("other", SURVIVAL, twins, [])], "Conditional", {"A1": "not_rerun", "A2": "not_rerun"})
    return out


def describe(doc):
    def samples(fd):
        return frozenset(e["id"] for e in fd["evidence"] if e["kind"] == "sample")

    def file_of(fd):
        return next((e.get("file") for e in fd["evidence"] if e.get("file")), None) or \
            next((e["id"] for e in fd["evidence"] if e["kind"] == "file"), None)
    return sorted(((fd["kind"], file_of(fd), samples(fd), tuple(fd["affects_analyses"])) for fd in doc["findings"]),
                  key=str)


def main(argv):
    if "--challenge" not in argv:
        print(__doc__, file=sys.stderr)
        return 64
    challenge = os.path.abspath(argv[argv.index("--challenge") + 1])
    data = os.path.join(challenge, "data", "tcga-brca")
    raw = os.path.join(data, "raw")
    ref = os.path.join(data, "reference_analyses.py")
    w = World(raw)
    before = json.loads(subprocess.run([sys.executable, ref, raw], capture_output=True, text=True, check=True).stdout)
    work = tempfile.mkdtemp(prefix="own-changes-")
    failures, slowest, n = 0, 0.0, 0
    try:
        for c in cases(w):
            n += 1
            rel = os.path.join(work, c["name"])
            os.makedirs(rel)
            writers = c["write"] if isinstance(c["write"], dict) else {c["file"]: c["write"]}
            for file in FILES:
                if file not in writers:
                    os.symlink(os.path.join(raw, file), os.path.join(rel, file))
            for file, write in writers.items():
                if write:
                    write(os.path.join(rel, file))
            started = time.time()
            doc = compare(raw, rel)
            seconds = time.time() - started
            slowest = max(slowest, seconds)
            problems = []
            if doc["verdict"] != c["verdict"]:
                problems.append(f"verdict {doc['verdict']}, expected {c['verdict']}")
            if c["findings"] is not None:
                got, want = describe(doc), sorted(c["findings"], key=str)
                if got != want:
                    for item in want:
                        if item not in got:
                            problems.append(f"missing: {item[0]} in {item[1]}, {len(item[2])} samples, affects {list(item[3])}")
                    for item in got:
                        if item not in want:
                            problems.append(f"unexpected: {item[0]} in {item[1]}, {sorted(item[2])[:3]}, affects {list(item[3])}")
            elif not any(e["kind"] == "file" and e["id"] == c["file"] for fd in doc["findings"] for e in fd["evidence"]):  # noqa: E501
                problems.append("no finding names the file")
            if c["statuses"]:
                got = {a["id"]: a["status"] for a in doc["analyses"]}
                if got != c["statuses"]:
                    problems.append(f"analyses {got}, expected {c['statuses']}")
                r = subprocess.run([sys.executable, ref, rel], capture_output=True, text=True)
                if r.returncode == 0:
                    after = json.loads(r.stdout)
                    for a in doc["analyses"]:
                        rb = next(x for x in before if x["analysis"] == a["id"])
                        ra = next(x for x in after if x["analysis"] == a["id"])
                        if a["status"] == "not_rerun":
                            if rb != ra:
                                problems.append(f"{a['id']} not rerun, but the organisers' script shows it moved")
                        else:
                            for side, refd in (("before", rb), ("after", ra)):
                                for key, v in a[side].items():
                                    if refd.get(key) != v:
                                        problems.append(f"{a['id']} {side}.{key}: ours {v}, organisers' {refd.get(key)}")
                else:
                    problems.append("the organisers' script could not run on this release")
            failures += 1 if problems else 0
            kinds = ", ".join(f"{fd['kind']}→{'+'.join(fd['affects_analyses']) or 'none'}" for fd in doc["findings"]) or "no findings"
            print(f"{'PASS' if not problems else 'FAIL'}  {c['name']:30} {seconds:5.1f}s  {doc['verdict']:22} {kinds}")
            print(f"        {c['what']}")
            for p in problems:
                print(f"        problem: {p}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"\n{n - failures} of {n} cases pass.  Slowest run: {slowest:.1f}s")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
