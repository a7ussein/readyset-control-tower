#!/bin/bash
# ReadySet Control Tower in one command. Needs Python 3.9+ and nothing else: no packages, no internet.
#   ./run.sh                       the page at http://localhost:8010 (opens your browser)
#   ./run.sh serve --findings F    show a findings file other than the example
# On Windows use:  run.bat   (or:  py -m control_tower serve)
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python || true)
[ -n "$PY" ] || { echo "Python was not found. Install Python 3.9 or newer from https://www.python.org/downloads/ and run this again."; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' || { echo "This needs Python 3.9 or newer; this is $("$PY" --version 2>&1)."; exit 1; }
[ $# -eq 0 ] && set -- serve
exec "$PY" -m control_tower "$@"
