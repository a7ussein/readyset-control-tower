"""ReadySet Control Tower.

  python3 -m control_tower compare RELEASE_A RELEASE_B [--out findings.json] [--report report.html] [--for A1,A2] [--question FILE]
        compare two release folders (the trusted one first) and write the findings
        --report     also write the audit report: the same findings in plain English, as one page to open or print
        --for        the question: which registered analyses this release is needed for (default: all of them)
        --question   a JSON file listing analyses, registered ids or new ones (docs/OUTPUT-CONTRACT.md, "The question")
        exit code: 0 Ready, 1 Conditional, 2 Blocked, 3 Insufficient Evidence; 64 the command was wrong
  python3 -m control_tower envelope NUMBER WORD WORD WORD WORD [--challenge PATH] [--port N]
        Saturday in one step: open the organisers' sealed envelope with their unseal.py, compare its release with the
        trusted one, write findings.json and audit-report.html, and show it on the page if the page is running
        exit code: the verdict's, as for compare; 70 the envelope did not open, so there is no answer
  python3 -m control_tower serve RELEASE_A RELEASE_B [--question FILE] [--port N] [--no-open]
        the page at http://localhost:8010, comparing the two folders live; the question can be changed on the page
  python3 -m control_tower serve [--findings FILE] [--port N] [--no-open]
        the page showing a findings file (the hand-written example by default)
"""
import json
import os
import sys

EXIT = {"Ready": 0, "Conditional": 1, "Blocked": 2, "Insufficient Evidence": 3}
NO_ANSWER = 70          # the envelope did not open: never one of the verdict codes, so a script cannot mistake it for an answer


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
        print(f"  {f['status']:14} {f['file']}" + ("   (not needed by any analysis; not compared)" if f["status"] == "not_in_both"
                                                    else "   (same values, different bytes)" if f.get("note") else ""))
    for f in doc["findings"]:
        hit = ", ".join(f["affects_analyses"]) or "nothing in the question"
        print(f"  {f['id']:4} {f['kind']:18} {f['severity']:6} affects {hit}: {f['summary']}")
    for a in doc["analyses"]:
        print(f"  {a['id']:4} {a['status']}")
    for note in x.get("notes", []):
        print(f"  note: {note}")
    print(f"wrote {out}")
    if report:
        from .report import render
        with open(report, "w", encoding="utf-8") as fh:
            fh.write(render(doc))
        print(f"wrote {report}")
    return EXIT[doc["verdict"]]


def find_challenge(given=None):
    """The organisers' repository: where it was said to be, where the trusted release was last taken from, or next to
    this one as the README says."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    guesses = [given] if given else []
    try:
        with open("control-tower.settings.json", encoding="utf-8") as fh:
            trusted = json.load(fh).get("trusted") or ""
        guesses.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.normpath(trusted)))))
    except (OSError, ValueError, AttributeError):
        pass
    guesses += [os.path.join(os.path.dirname(here), "oncosys-hackathon-challenge"),
                os.path.join(os.getcwd(), "..", "oncosys-hackathon-challenge")]
    for g in guesses:
        if g and os.path.isfile(os.path.join(g, "envelopes", "unseal.py")):
            return os.path.abspath(g)
    return None


def cmd_envelope(args):
    import shutil
    import subprocess
    import urllib.request
    args = list(args)
    challenge, port = None, int(os.environ.get("PORT") or 8010)
    try:                                                    # the page says which port it is on when it starts
        with open("control-tower.settings.json", encoding="utf-8") as fh:
            port = int(json.load(fh).get("port") or port)
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    for flag in ("--challenge", "--port"):
        if flag in args:
            i = args.index(flag)
            if i + 1 >= len(args):
                print(f"error: {flag} needs a value", file=sys.stderr)
                return 64
            if flag == "--challenge":
                challenge = args[i + 1]
            else:
                port = int(args[i + 1])
            del args[i:i + 2]
    if len(args) < 2:
        print("usage: envelope NUMBER WORD WORD WORD WORD   (for example: envelope 07 amber falcon river quartz)", file=sys.stderr)
        return 64
    repo = find_challenge(challenge)
    if not repo:
        print("error: cannot find the organisers' repository (the folder with envelopes/unseal.py).\n"
              "Say where it is:  --challenge PATH/TO/oncosys-hackathon-challenge", file=sys.stderr)
        return 64
    trusted = os.path.join(repo, "data", "tcga-brca", "raw")
    if not os.path.isdir(trusted):
        print(f"error: the trusted release is not at {trusted}.\n"
              "Download it first, in the organisers' repository:  python data/tcga-brca/fetch.py", file=sys.stderr)
        return NO_ANSWER
    venv = os.path.join(repo, ".venv", "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")
    if os.path.isfile(venv):
        python = [venv]
    elif shutil.which("uv"):
        python = ["uv", "run", "-q", "--with", "pandas", "--with", "cryptography", "python3"]
    else:
        python = [sys.executable]
    started = __import__("time").time()
    before = {d: os.path.getmtime(os.path.join(repo, "envelopes", "opened", d))
              for d in (os.listdir(os.path.join(repo, "envelopes", "opened")) if os.path.isdir(os.path.join(repo, "envelopes", "opened")) else [])}
    opened = subprocess.run(python + [os.path.join("envelopes", "unseal.py")] + args, cwd=repo)
    if opened.returncode != 0:
        print("\nThe envelope did not open, so nothing was compared. The organisers' script says why, just above.\n"
              "If it says the code is wrong, check the number and the four words. Otherwise do what it asks, then run this again.",
              file=sys.stderr)
        return NO_ANSWER
    root = os.path.join(repo, "envelopes", "opened")
    folders = sorted((d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d, "release"))),
                     key=lambda d: (os.path.getmtime(os.path.join(root, d)) > before.get(d, 0), os.path.getmtime(os.path.join(root, d))))
    if not folders:
        print("error: the envelope opened but holds no release folder", file=sys.stderr)
        return NO_ANSWER
    new = os.path.join(root, folders[-1], "release")
    code = cmd_compare([trusted, new, "--out", "findings.json", "--report", "audit-report.html"])
    try:
        body = json.dumps({"trusted": os.path.abspath(trusted), "path": os.path.abspath(new)}).encode()
        with urllib.request.urlopen(urllib.request.Request(f"http://localhost:{port}/api/release", data=body, method="POST"), timeout=5):
            print(f"The page now shows this envelope: http://localhost:{port}")
    except OSError:
        print(f"The page is not running on port {port}. To see this on the page:  ./run.sh serve {trusted} {new}")
    print(f"Envelope to findings in {__import__('time').time() - started:.1f} s.")
    return code


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["compare"]:
        return cmd_compare(argv[1:])
    if argv[:1] == ["envelope"]:
        return cmd_envelope(argv[1:])
    if argv[:1] == ["serve"]:
        from .webserver import main as serve
        return serve(argv[1:])
    if argv[:1] in (["--help"], ["-h"], ["help"]):
        print(__doc__)
        return 0
    print(__doc__, file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
