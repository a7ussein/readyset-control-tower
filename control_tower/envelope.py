"""Opening a sealed envelope for the page: the same steps as the `envelope` command, with the organisers' own
`unseal.py` doing the opening. Returns what happened instead of printing it, so the page can show it."""
import os
import re
import shutil
import subprocess
import sys


class CannotOpen(Exception):
    """The envelope did not open. The message says why, in words a person can act on."""


def open_envelope(number, words, challenge=None):
    """(trusted release folder, the opened release folder). `words` is the four-word code."""
    from .__main__ import find_challenge
    number, words = str(number or "").strip(), [str(w).strip().lower() for w in (words or []) if str(w).strip()]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", number):
        raise CannotOpen("Type the envelope's number, for example 07.")
    if len(words) != 4 or not all(re.fullmatch(r"[a-z]{2,24}", w) for w in words):
        raise CannotOpen("The code is four words, for example: amber falcon river quartz.")
    repo = find_challenge(challenge)
    if not repo:
        raise CannotOpen("The organisers' folder (oncosys-hackathon-challenge) was not found next to this tool. "
                         "Put it beside this folder, or set the trusted release from inside it first.")
    trusted = os.path.join(repo, "data", "tcga-brca", "raw")
    if not os.path.isdir(trusted):
        raise CannotOpen("The trusted release has not been downloaded yet. In the organisers' folder, run their "
                         "data/tcga-brca/fetch.py once.")
    venv = os.path.join(repo, ".venv", "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")
    if os.path.isfile(venv):
        python = [venv]
    elif shutil.which("uv"):
        python = ["uv", "run", "-q", "--with", "pandas", "--with", "cryptography", "python3"]
    else:
        python = [sys.executable]
    root = os.path.join(repo, "envelopes", "opened")
    before = {d: os.path.getmtime(os.path.join(root, d)) for d in (os.listdir(root) if os.path.isdir(root) else [])}
    try:
        done = subprocess.run(python + [os.path.join("envelopes", "unseal.py"), number] + words, cwd=repo, capture_output=True,
                              text=True, timeout=300, env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    except (OSError, subprocess.TimeoutExpired) as e:
        raise CannotOpen(f"The organisers' script could not be run: {e}")
    if done.returncode != 0:
        said = [line.strip() for line in (done.stderr + "\n" + done.stdout).splitlines() if line.strip()]
        raise CannotOpen("The envelope did not open. Check the number and the four words. The organisers' script said: " +
                         (said[-1][:300] if said else "nothing"))
    folders = sorted((d for d in (os.listdir(root) if os.path.isdir(root) else []) if os.path.isdir(os.path.join(root, d, "release"))),
                     key=lambda d: (os.path.getmtime(os.path.join(root, d)) > before.get(d, 0), os.path.getmtime(os.path.join(root, d))))
    if not folders:
        raise CannotOpen("The envelope opened but holds no release folder.")
    return os.path.abspath(trusted), os.path.abspath(os.path.join(root, folders[-1], "release"))
