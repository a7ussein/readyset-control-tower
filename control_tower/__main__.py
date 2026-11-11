"""ReadySet Control Tower.

  python3 -m control_tower serve [--findings FILE] [--port N] [--no-open]
        the page at http://localhost:8010, showing a findings file (the hand-written example by default)

The comparison engine (`compare <release A> <release B> --out findings.json`) is not written yet.
"""
import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["serve"]:
        from .webserver import main as serve
        return serve(argv[1:])
    print(__doc__, file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
