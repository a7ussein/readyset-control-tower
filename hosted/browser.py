"""The comparison engine, driven from the online page. It runs inside the visitor's browser (Pyodide): the files they
choose are read into the browser's own memory and compared there by the same code the tool runs on a computer.
Nothing is uploaded to any server.

The page's script calls three functions, each returning JSON text: use(), current() and findings().
"""
import json
import os
import re

from control_tower.analyses import REGISTRY, BadQuestion
from control_tower.compare import compare
from control_tower.release import FILES
from control_tower.webserver import NotARelease, _label, release_folder, review_key, unzip_release

STAGING = "/staging"
state = {"trusted": None, "new": None}
cache = {}
AVAILABLE = [a.id for a in REGISTRY]
TITLES = {a.id: a.title for a in REGISTRY}


def current():
    trusted, new = state["trusted"], state["new"]
    return json.dumps({"trusted": trusted, "new": new, "files": list(FILES),
                       "trusted_name": _label(trusted) if trusted else None, "new_name": _label(new) if new else None})


def use(batch, name, as_trusted):
    """Take the files of one chosen release (already written under /staging/<batch>) as the trusted or the new release."""
    try:
        if not re.fullmatch(r"[A-Za-z0-9-]{8,64}", str(batch)):
            raise NotARelease("that selection is not known")
        label = re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.splitext(os.path.basename(str(name or "")))[0]).strip("-.")
        staged = os.path.join(STAGING, batch)
        target = os.path.join(staged, label or ("trusted" if as_trusted else "new-release"))
        os.makedirs(target, exist_ok=True)
        for f in FILES:
            if os.path.isfile(os.path.join(staged, f)):
                os.replace(os.path.join(staged, f), os.path.join(target, f))
        if os.path.isfile(os.path.join(staged, "upload.zip")):
            unzip_release(os.path.join(staged, "upload.zip"), target)
            os.remove(os.path.join(staged, "upload.zip"))
        folder = release_folder(target, STAGING)
        other = state["new"] if as_trusted else state["trusted"]
        if other and os.path.realpath(other) == os.path.realpath(folder):
            raise NotARelease("that is the same release twice. Choose the other one.")
    except NotARelease as e:
        return json.dumps({"status": 400, "body": {"detail": str(e)}})
    state["trusted" if as_trusted else "new"] = folder
    cache.clear()
    return json.dumps({"status": 200, "body": json.loads(current())})


def findings(wanted):
    """The findings for the question asked ("" = every registered analysis), as the tool's own page would get them."""
    trusted, new = state["trusted"], state["new"]
    if not (trusted and new):
        return json.dumps({"status": 404, "body": {"detail": "choose both releases first"}})
    ids = [x for x in str(wanted or "").split(",") if x] or list(AVAILABLE)
    unknown = [i for i in ids if i not in AVAILABLE]
    if unknown:
        return json.dumps({"status": 400, "body": {"detail": f"no analysis called {', '.join(unknown)}; choose from {', '.join(AVAILABLE)}"}})
    key = ",".join(ids)
    if key not in cache:
        try:
            cache[key] = compare(trusted, new, ids)
        except BadQuestion as e:
            return json.dumps({"status": 400, "body": {"detail": str(e)}})
        except Exception as e:                                  # say what went wrong instead of failing silently
            return json.dumps({"status": 500, "body": {"detail": f"The comparison failed ({type(e).__name__}). Check that both "
                                                                 f"selections hold the release's files, with the trusted one first."}})
    doc = json.loads(json.dumps(cache[key]))
    x = doc.setdefault("x_readyset", {})
    x["live"] = {"available": [{"id": i, "title": x.get("analysis_titles", {}).get(i) or TITLES.get(i, i)} for i in AVAILABLE]}
    name = str(doc["data"]["releases"][-1]["name"]) if doc.get("data", {}).get("releases") else ""
    x["review_keys"] = {f["id"]: review_key(f, name, doc) for f in doc.get("findings", []) if isinstance(f, dict) and "id" in f}
    return json.dumps({"status": 200, "body": doc})
