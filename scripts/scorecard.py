"""Scorecard: build each test release, run our engine on it, and score the result against the answer key.

  python scripts/scorecard.py --challenge ../oncosys-hackathon-challenge
  python scripts/scorecard.py --challenge ../oncosys-hackathon-challenge tests/releases/t1.json
  python scripts/scorecard.py --challenge ../oncosys-hackathon-challenge --rescore tests/releases/t1.json
        (--rescore: score the saved output again without rebuilding or rerunning)
  python scripts/scorecard.py --challenge ../oncosys-hackathon-challenge --own
        (--own: also run Ahmed's 23 hand-made cases, tests/releases/own_changes.py)

Needs the challenge repo with fetch.py already run, and pandas and jsonschema installed in the active Python.
Exit code 0 when every test is clean, 1 otherwise.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # our repo: the folder above scripts/
NOT_RESULTS = {"analysis", "inputs", "n_ids_listed"}                    # keys in the organisers' output that are not numbers


def run(cmd, cwd):
    """Run a command in a folder. Return its exit code, its normal output and its error output."""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def expected_from(changes):
    """Turn the organisers' CHANGES.json into the findings a correct tool must report.
    Each is (kind, file, set of sample ids)."""
    out = []
    for ch in changes["changes"]:
        if ch["type"] == "swap_samples":
            out.append(("sample_swap", ch["file"], set(ch["samples"])))
        elif ch["type"] == "replace_with_duplicates":
            out.append(("duplicate", ch["file"], {d["new_id"] for d in ch["duplicates"]}))
            out.append(("membership_change", ch["file"], set(ch["removed"])))
        elif ch["type"] == "relabel_clinical":
            out.append(("label_conflict", ch["file"], set(ch["before"])))
    return out


def samples_in(finding):
    """The sample ids a finding names as evidence."""
    return {e["id"] for e in finding["evidence"] if e.get("kind") == "sample"}


def files_in(finding):
    """The files a finding points at."""
    return {e["file"] for e in finding["evidence"] if e.get("file")} | \
           {e["id"] for e in finding["evidence"] if e.get("kind") == "file"}


def score(expected, findings):
    """Match each planted change to a finding of the same kind, in the same file, naming at least its samples.
    One finding may cover several planted changes (chained swaps are reported as one finding).
    Return (number found, the misses, the findings no planted change explains)."""
    used, missed = set(), []
    for kind, file, ids in expected:
        hit = next((i for i, f in enumerate(findings)
                    if f["kind"] == kind and file in files_in(f) and ids <= samples_in(f)), None)
        if hit is None:
            missed.append((kind, file, sorted(ids)))
        else:
            used.add(hit)
    extra = [f for i, f in enumerate(findings) if i not in used]
    return len(expected) - len(missed), missed, extra


def sources_ok(changes, findings):
    """For every planted copy, the duplicate finding must name the sample it was copied from in that copy's note."""
    notes = {e["id"]: e.get("note", "") for f in findings if f["kind"] == "duplicate" for e in f["evidence"]}
    for ch in changes["changes"]:
        for d in ch.get("duplicates", []):
            if d["copied_from"] not in notes.get(d["new_id"], ""):
                return False
    return True


def reference(challenge, folder):
    """Run the organisers' own analysis script on one release folder. Return {"A1": {...}, "A2": {...}}."""
    code, out, err = run([sys.executable, "data/tcga-brca/reference_analyses.py", folder], challenge)
    if code != 0:
        raise RuntimeError(f"reference_analyses.py failed on {folder}: {err.strip()[-300:]}")
    return {a["analysis"]: a for a in json.loads(out)}


def analyses_ok(doc, ref_a, ref_b):
    """Check the engine's analyses against the organisers' numbers. Return a list of problems (empty is good)."""
    problems = []
    for a in doc["analyses"]:
        ra, rb = ref_a[a["id"]], ref_b[a["id"]]
        moved = {k: v for k, v in ra.items() if k not in NOT_RESULTS} != \
                {k: v for k, v in rb.items() if k not in NOT_RESULTS}
        if moved and a["status"] != "changed":
            problems.append(f"{a['id']} moved in the organisers' script but ours says {a['status']}")
        if not moved and a["status"] == "changed":
            problems.append(f"{a['id']} did not move in the organisers' script but ours says changed")
        for side, ref in (("before", ra), ("after", rb)):
            for k, v in (a.get(side) or {}).items():
                if k in ref and ref[k] != v:
                    problems.append(f"{a['id']} {side} {k}: ours {v}, organisers {ref[k]}")
    return problems


def main():
    ap = argparse.ArgumentParser(description="Build each test release, run the engine, score it.")
    ap.add_argument("--challenge", required=True, help="path to the organisers' challenge repo")
    ap.add_argument("--rescore", action="store_true", help="score saved outputs again; do not build or run")
    ap.add_argument("--own", action="store_true", help="also run the hand-made cases in tests/releases/own_changes.py")
    ap.add_argument("configs", nargs="*", help="config files (default: tests/releases/t*.json)")
    args = ap.parse_args()

    challenge = os.path.abspath(args.challenge)
    raw = os.path.join(challenge, "data", "tcga-brca", "raw")
    configs = args.configs or sorted(glob.glob(os.path.join(ROOT, "tests", "releases", "t*.json")),
                                     key=lambda p: int(re.findall(r"\d+", os.path.basename(p))[0]))   # t2 before t10
    outdir = os.path.join(ROOT, "scorecard-out")
    os.makedirs(outdir, exist_ok=True)

    ref_a = reference(challenge, raw)
    print(f"{'test':26} {'verdict':22} {'found':7} {'false':6} {'sources':8} {'analyses':9} {'valid':6} {'secs':>5}")
    all_clean = True

    for cfg in configs:
        cfg = os.path.abspath(cfg)
        with open(cfg) as fh:
            spec = json.load(fh)
        name = spec["name"]

        rel = os.path.join(challenge, "data", "tcga-brca", "releases", name)
        result = os.path.join(outdir, name + ".json")
        secs = 0.0
        if not args.rescore:
            # 1. Build the release with the organisers' script. It also writes the answer key, CHANGES.json.
            code, out, err = run([sys.executable, "data/tcga-brca/make_release.py", "--config", cfg], challenge)
            if code != 0:
                print(f"{name:26} BUILD FAILED: {err.strip()[-300:]}")
                all_clean = False
                continue
            for f in spec.get("remove_files", []):          # Saturday's envelope comes without the RNA file
                os.remove(os.path.join(rel, f))

            # 2. Run our engine on release A and this release, and time it.
            start = time.time()
            code, out, err = run([sys.executable, "-m", "control_tower", "compare", raw, rel, "--out", result], ROOT)
            secs = time.time() - start
            if code not in (0, 1, 2, 3):
                print(f"{name:26} ENGINE FAILED (exit {code}): {err.strip()[-300:]}")
                all_clean = False
                continue

        # 3. Score it.
        with open(result) as fh:
            doc = json.load(fh)
        with open(os.path.join(rel, "CHANGES.json")) as fh:
            changes = json.load(fh)
        expected = expected_from(changes)
        found, missed, extra = score(expected, doc["findings"])
        src = sources_ok(changes, doc["findings"])
        problems = analyses_ok(doc, ref_a, reference(challenge, rel))
        vcode, vout, verr = run([sys.executable, "format/validate.py", result], challenge)

        clean = not missed and not extra and src and not problems and vcode == 0
        all_clean = all_clean and clean
        print(f"{name:26} {doc['verdict']:22} {f'{found}/{len(expected)}':7} {len(extra):<6} {'ok' if src else 'WRONG':8} "
              f"{'ok' if not problems else 'WRONG':9} {'ok' if vcode == 0 else 'NO':6} {secs:5.1f}")
        for m in missed:
            print(f"    missed:   {m}")
        for f in extra:
            print(f"    false:    {f['id']} {f['kind']}: {f['summary']}")
        for p in problems:
            print(f"    analysis: {p}")
        if vcode != 0:
            print(f"    invalid:  {(vout + verr).strip()[-300:]}")

    if args.own:
        # 4. Ahmed's hand-made cases: changes the organisers' script cannot make. It prints its own table.
        print("\nHand-made cases (tests/releases/own_changes.py):")
        code, out, err = run([sys.executable, os.path.join(ROOT, "tests", "releases", "own_changes.py"),
                              "--challenge", challenge], ROOT)
        print(out.rstrip() or err.strip()[-300:])
        all_clean = all_clean and code == 0

    print("CLEAN" if all_clean else "NOT CLEAN")
    return 0 if all_clean else 1


if __name__ == "__main__":
    sys.exit(main())
