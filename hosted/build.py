#!/usr/bin/env python3
"""Assemble the hosted demo in hosted/out: the page, the recorded answers for the practice release, the tool's own
Python for the browser, and the one server function.   python3 hosted/build.py   (needs Node, for the page build)

The recorded answers in hosted/recorded were written by this tool comparing the organisers' practice release. They are
findings, not data files. The page runs the tool's report, change log and assistant code in the browser (Pyodide).
"""
import glob
import os
import shutil
import subprocess

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
out = os.path.join(here, "out")
kept = os.path.join(here, ".vercel-link")                       # the hosting project link survives a rebuild
if os.path.isdir(os.path.join(out, ".vercel")):
    shutil.rmtree(kept, ignore_errors=True)
    shutil.copytree(os.path.join(out, ".vercel"), kept)
shutil.rmtree(out, ignore_errors=True)
subprocess.run(["npx", "vite", "build", "--base=./", "--outDir", out], cwd=os.path.join(root, "web"), check=True)
for path in glob.glob(os.path.join(out, "assets", "*.js")):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace("`/brand/", "`./brand/").replace('"/brand/', '"./brand/'))
index = os.path.join(out, "index.html")
with open(index, encoding="utf-8") as fh:
    page = fh.read()
page = page.replace('<script type="module"', '<script src="./demo-shim.js"></script>\n    <script type="module"', 1)
page = page.replace("<title>ReadySet Control Tower</title>", "<title>ReadySet Control Tower: online demo</title>")
with open(index, "w", encoding="utf-8") as fh:
    fh.write(page)
shutil.copy(os.path.join(here, "demo-shim.js"), out)
shutil.copytree(os.path.join(here, "recorded"), os.path.join(out, "data"))
shutil.copytree(os.path.join(here, "api"), os.path.join(out, "api"))
package = os.path.join(out, "py", "control_tower")
os.makedirs(package)
for name in ("report.py", "ask.py", "changelog.py", "understand_ai.py"):
    shutil.copy(os.path.join(root, "control_tower", name), package)
with open(os.path.join(package, "__init__.py"), "w", encoding="utf-8") as fh:
    fh.write('"""ReadySet Control Tower: the report, change log and assistant code, as run by the online demo."""\n')
shutil.copytree(os.path.join(out, "py"), os.path.join(out, "api", "_lib"))      # the function's own copy of the package
if os.path.isdir(kept):
    shutil.copytree(kept, os.path.join(out, ".vercel"))
print("built", out)
