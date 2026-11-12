"""ReadySet Control Tower.

  python3 -m control_tower compare RELEASE_A RELEASE_B [--out findings.json] [--report report.html] [--for A1,A2] [--question FILE]
        compare two release folders (the trusted one first) and write the findings
        --report     also write the audit report: the same findings in plain English, as one page to open or print
        --for        the question: which registered analyses this release is needed for (default: all of them)
        --question   a JSON file listing analyses, registered ids or new ones (docs/OUTPUT-CONTRACT.md, "The question")
        exit code: 0 Ready, 1 Conditional, 2 Blocked, 3 Insufficient Evidence
  python3 -m control_tower serve RELEASE_A RELEASE_B [--question FILE] [--port N] [--no-open]
        the page at http://localhost:8010, comparing the two folders live; the question can be changed on the page
  python3 -m control_tower serve [--findings FILE] [--port N] [--no-open]
        the page showing a findings file (the hand-written example by default)
"""
import json
import os
import sys

EXIT = {"Ready": 0, "Conditional": 1, "Blocked": 2, "Insufficient Evidence": 3}


def load_question(path):
    """A question file is a JSON list of analyses, or an object with an "analyses" list."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("analyses")
    if not isinstance(data, list):
        raise ValueError("expected a list of analyses")
    return data


def cmd_compare(args):
    args = list(args)
    out = "findings.json"
    if "--out" in args:
        i = args.index("--out")
        if i + 1 >= len(args):
            print("error: --out needs a file name", file=sys.stderr)
            return 64
        out = args[i + 1]
        del args[i:i + 2]
    specs, report = None, None
    if "--report" in args:
        i = args.index("--report")
        if i + 1 >= len(args):
            print("error: --report needs a file name", file=sys.stderr)
            return 64
        report = args[i + 1]
        del args[i:i + 2]
    try:
        if "--for" in args:
            i = args.index("--for")
            specs = [x for x in args[i + 1].split(",") if x]
            del args[i:i + 2]
        if "--question" in args:
            i = args.index("--question")
            specs = load_question(args[i + 1])
            del args[i:i + 2]
    except IndexError:
        print("error: --for needs a list such as A1,A2 and --question needs a file", file=sys.stderr)
        return 64
    except (OSError, ValueError) as e:
        print(f"error: the question file could not be read: {e}", file=sys.stderr)
        return 64
    if len(args) != 2:
        print("usage: compare RELEASE_A RELEASE_B [--out findings.json] [--for A1,A2] [--question FILE]", file=sys.stderr)
        return 64
    for folder in args:
        if not os.path.isdir(folder):
            print(f"error: {folder} is not a folder", file=sys.stderr)
            return 64
    from .analyses import BadQuestion
    from .compare import compare
    try:
        doc = compare(args[0], args[1], specs)
    except BadQuestion as e:
        print(f"error: {e}", file=sys.stderr)
        return 64
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    x = doc["x_readyset"]
    print(f"{doc['verdict']}   ({x['run_seconds']} s)   question: {', '.join(x['analyses_in_question'])}")
    for f in x["files"]:
        print(f"  {f['status']:14} {f['file']}" + ("   (same values, different bytes)" if f.get("note") else ""))
    for f in doc["findings"]:
        hit = ", ".join(f["affects_analyses"]) or "nothing in the question"
        print(f"  {f['id']:4} {f['kind']:18} {f['severity']:6} affects {hit}: {f['summary']}")
    for a in doc["analyses"]:
        print(f"  {a['id']:4} {a['status']}")
    print(f"wrote {out}")
    if report:
        from .report import render
        with open(report, "w", encoding="utf-8") as fh:
            fh.write(render(doc))
        print(f"wrote {report}")
    return EXIT[doc["verdict"]]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["compare"]:
        return cmd_compare(argv[1:])
    if argv[:1] == ["serve"]:
        from .webserver import main as serve
        return serve(argv[1:])
    print(__doc__, file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
