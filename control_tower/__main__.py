"""ReadySet Control Tower.

  python3 -m control_tower compare RELEASE_A RELEASE_B [--out findings.json]
        compare two release folders (the trusted one first) and write the findings
        exit code: 0 Ready, 1 Conditional, 2 Blocked, 3 Insufficient Evidence
  python3 -m control_tower serve [--findings FILE] [--port N] [--no-open]
        the page at http://localhost:8010, showing a findings file (the hand-written example by default)
"""
import json
import os
import sys

EXIT = {"Ready": 0, "Conditional": 1, "Blocked": 2, "Insufficient Evidence": 3}


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
    if len(args) != 2:
        print("usage: compare RELEASE_A RELEASE_B [--out findings.json]", file=sys.stderr)
        return 64
    for folder in args:
        if not os.path.isdir(folder):
            print(f"error: {folder} is not a folder", file=sys.stderr)
            return 64
    from .compare import compare
    doc = compare(args[0], args[1])
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    x = doc["x_readyset"]
    print(f"{doc['verdict']}   ({x['run_seconds']} s)")
    for f in x["files"]:
        print(f"  {f['status']:14} {f['file']}" + ("   (same values, different bytes)" if f.get("note") else ""))
    for f in doc["findings"]:
        hit = ", ".join(f["affects_analyses"]) or "no registered analysis"
        print(f"  {f['id']:4} {f['kind']:18} {f['severity']:6} affects {hit}: {f['summary']}")
    for a in doc["analyses"]:
        print(f"  {a['id']:4} {a['status']}")
    print(f"wrote {out}")
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
