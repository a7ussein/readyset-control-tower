# ReadySet Control Tower

Team **Automyte** · OncoSys Cancer AI Lab, Nov 11–14 2026 · Track: Cohort Firewall · Product: Cohort Control Tower

## Start here: see it running in one minute

[![Try it in your browser](https://img.shields.io/badge/Try_it_now-in_your_browser-1F8A5B?style=for-the-badge)](https://readyset-control-tower.vercel.app/) [![Watch the demo video](https://img.shields.io/badge/Watch_the_demo-2_and_a_half_minutes-E0457B?style=for-the-badge)](https://a7ussein.github.io/readyset-control-tower/) [![Download the tool as a ZIP file](https://img.shields.io/badge/Download_the_tool-ZIP_file-3B2F8F?style=for-the-badge)](https://github.com/a7ussein/readyset-control-tower/archive/refs/heads/main.zip)

**To try it,** click Try it now. Nothing to install: the page opens in your browser on the organisers' practice release, as the tool compared it. Switch an analysis off and on, open a finding, sign it off, ask it a question in your own words, and download the report and the change log. It works on a phone too. The comparison itself was run beforehand; to compare your own data, run the tool on your own computer, where nothing is uploaded.

**To just watch,** click Watch the demo. **To run it on your own computer:**

1. Click Download the tool, then unzip the file. You get a folder called `readyset-control-tower-main`.
2. Start it:
   - **Windows:** open the folder and double-click `run.bat`.
   - **Mac:** open the folder and double-click `run.command`. The first time, macOS may refuse a downloaded file: right-click it, choose Open, then Open again.
   - **Linux, or if you prefer a terminal:** in the folder, run `./run.sh`.
3. Your browser opens the page at http://localhost:8010 with a worked example. To stop, close the Terminal or Command Prompt window.

**Everything is done on the page.** Open a sealed envelope by typing its number and four words, or drop a new release on the page. Switch your analyses on and off, read each change, sign your decision, ask questions in your own words, and download the report. No terminal is needed after the page is open; the command line is there for people who want it, under [Developer mode](#developer-mode-setup-and-the-command-line).

The only thing it needs is Python 3.9 or newer ([download Python](https://www.python.org/downloads/)). There is nothing else to install and no account to make. The example uses invented data; comparing real releases is covered under [Developer mode](#developer-mode-setup-and-the-command-line).

**What you are looking at:** when a research dataset gets a new release, this page answers one question: does the result you rely on still hold on the new release? It shows what changed, why each change matters, what to do next, and what the tool cannot tell you.

---

**User:** a research engineer responsible for a dataset that gets new releases.

**The one workflow:** point the tool at two releases of the TCGA breast cancer data. It finds what silently changed
between them (swapped, copied, missing or relabelled samples), reruns only the analyses those changes touch, and
writes `findings.json` in the organisers' shared format.

## Where each judging criterion is met

The Cohort Firewall track is scored on seven criteria. This is where to look for each, on the page and in the code.

| Criterion | On the page | In the repository |
|---|---|---|
| **Finding data problems**, without reporting problems the data does not support | The list of changes. On the organisers' practice release it reports exactly what was planted and nothing else. | `control_tower/detect.py`, `control_tower/compare.py`; `tests/test_detectors.py` states what must and must not be reported for each kind of change. |
| **Reasoning for the research question**: the result changes when the question changes | Switch an analysis off under "What I need it for": the verdict and each change's rating follow the question. | `control_tower/analyses.py` (what each analysis reads), `_severity` in `control_tower/compare.py`. |
| **Evidence and sources**: checks, data fields, decision rules, limitations | On each change: "The proof", "See the data in both files", "How the tool decided this", "What this cannot tell you". "How it works and how it was tested" under the verdict. | `control_tower/cells.py`, `x_readyset.rules` and `x_readyset.witness` in `findings.json`, `docs/ENGINE-PLAN.md`. |
| **Safety and uncertainty**: no clinical claims, uncertainty visible, human review required | Every change shows its confidence and its limit, and waits for a named person. Ask refuses clinical questions and says "I cannot answer that" when the findings do not hold the answer. | `needs_human_review` and `confidence` on every finding; the `clinical` and `limits` answers in `control_tower/ask.py`; `tests/test_ask.py`. |
| **Working tool and clear setup** | Press "Try it now" above, or unzip and double-click. | `run.sh`, `run.bat`, `run.command`; the tool needs only Python. `python3 -m unittest discover -s tests -t .` runs the tests. |
| **Useful next steps**: fixes that match the size of the problem | "So what?" and "Suggested fix" on each change, marked "before use" or "small effect". | `repairs` and `x_readyset.repair_priority` in `findings.json`. |
| **Communication**: understandable without specialist knowledge | The verdict in one sentence, the audit report in plain English, the change log as a spreadsheet. | `control_tower/report.py`, `control_tower/changelog.py`. |

## Status

The comparison engine and the page both work. The engine is tested, and the two together have been run on the organisers' practice release.

- [`docs/PLAN-IN-SHORT.md`](docs/PLAN-IN-SHORT.md): the plan in two minutes.
- [`docs/OUTPUT-CONTRACT.md`](docs/OUTPUT-CONTRACT.md): the rules for `findings.json`.
- [`docs/ENGINE-PLAN.md`](docs/ENGINE-PLAN.md): how the engine works, with measurements on the real files.
- [`web/README.md`](web/README.md): the page, and how to work on it.

## Developer mode: setup and the command line

The page does everything a researcher needs. This section is for people who want the terminal: fetching the data, scripting a comparison, running it in a pipeline.

Our tool needs Python 3.9 or newer and nothing else. Only the organisers' own scripts (fetching the data, building the practice release, validating the output) need two packages, covered below.

### Quick start, no data and no install needed beyond Python 3.9+

```bash
git clone https://github.com/a7ussein/readyset-control-tower.git
cd readyset-control-tower
./run.sh        # http://localhost:8010  (run.bat on Windows)
```

It opens http://localhost:8010 showing the hand-written example (`docs/example-findings.json`). Note that this example uses completely invented data.

If port 8010 is busy, pick another: `./run.sh serve --port 8123`.

### Comparing real releases

The event data is fetched with the organisers' `fetch.py` from their challenge repository (https://github.com/disleveK/oncosys-hackathon-challenge). No data files are committed to this repository.

Get the data and the practice release, in a folder next to this one (not inside it). The organisers' scripts need pandas, jsonschema and cryptography, installed below in a virtual environment; our tool needs none of them. If you already have their repository, run `git pull` in it first: their Windows fix for `make_release.py` (line endings) landed on 12 November. Starting from this repository's folder:

```bash
cd ..
git clone https://github.com/disleveK/oncosys-hackathon-challenge.git
cd oncosys-hackathon-challenge
python3 -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install pandas jsonschema cryptography  # cryptography is for envelopes/unseal.py
python data/tcga-brca/fetch.py             # the trusted release, into data/tcga-brca/raw/, checksums verified
python data/tcga-brca/make_release.py      # practice release B, into data/tcga-brca/releases/practice-B/
cd ../readyset-control-tower               # back to this repository; keep the virtual environment active
```

On a Mac with Python from python.org, `fetch.py` can fail with `SSL: CERTIFICATE_VERIFY_FAILED`. Run `/Applications/Python 3.x/Install Certificates.command` once (3.x is your Python version), then run `fetch.py` again.

The two folders can stay where they are: `compare` takes paths. `releases/practice-B/CHANGES.json` is the answer key, so do not open it until the tool has run.

Once you have the releases, compare them (the trusted release first):

```bash
# Compare two releases, from this repository's folder (RELEASE_A is the trusted one):
D=../oncosys-hackathon-challenge/data/tcga-brca
python3 -m control_tower compare $D/raw $D/releases/practice-B --out findings.json
# Windows (PowerShell) has no D=...; write the paths out:
#   python -m control_tower compare ..\oncosys-hackathon-challenge\data\tcga-brca\raw ..\oncosys-hackathon-challenge\data\tcga-brca\releases\practice-B --out findings.json

# Check the output with the organisers' validator (needs the virtual environment from above):
python ../oncosys-hackathon-challenge/format/validate.py findings.json

# Look at the result in the page:
./run.sh serve --findings findings.json        # http://localhost:8010  (run.bat on Windows)
```

Or let the page compare the two folders itself, which also lets you change the question on the page:

```bash
./run.sh serve $D/raw $D/releases/practice-B     # http://localhost:8010  (run.bat on Windows)
```

**Saturday's sealed envelope.** The organisers hand over an envelope number and a four-word code. On the page, press
"Compare a different release", type the number and the four words, and press "Open and compare". From a terminal, one command opens
it with their `unseal.py`, compares its release with the trusted one, writes `findings.json` and `audit-report.html`,
and shows the result on the page if the page is running (the practice envelope's code is public):

```bash
python3 -m control_tower envelope practice orange meadow pilot lantern
```

It looks for the organisers' repository next to this one; say `--challenge PATH` if it is somewhere else. Their
`unseal.py` needs `pandas` and `cryptography`: the `.venv` from "Comparing real releases" has both, or have `uv`
installed, and the command finds either. If the envelope does not open, their script says why and the command exits 70.

An envelope's release has five files and no RNA file. Neither registered analysis reads RNA, so the tool compares the
other five, says the RNA file was not compared, and raises no finding about it. To do the two steps by hand, run
their `python envelopes/unseal.py ...` and then `compare` on `envelopes/opened/<name>/release`.

**A release you have not seen.** Start the page with only the trusted release, then drop the new one on it:

```bash
./run.sh serve $D/raw            # then drop a folder or a zip on the page, choose one, or paste its path
```

The page compares it straight away, and "Compare a different release" takes the next one. It remembers the trusted
release, so after the first time plain `./run.sh` is enough.

**The audit report.** Besides `findings.json` for other tools, the page offers "Download the audit report": the
same findings in plain English as one page you can open, print or save as a PDF. From the command line add
`--report audit.html`. Every sentence in it is built from the findings by a fixed pattern; no language model writes it.

**The question.** The tool protects the analyses you say the release is needed for. On the page, switch them on and
off in the bar under the verdict. On the command line, `--for A2` asks about A2 alone, and `--question FILE` takes
your own analyses (see "The question" in [`docs/OUTPUT-CONTRACT.md`](docs/OUTPUT-CONTRACT.md)). For the practice
release the answer is Conditional when A1 is in the question and Ready when only A2 is.

On the page you can also press "Add an analysis of your own" and build one from the data's own files, rows and
columns, with no file to write.

**Ask.** Press "Ask about this release" on the page and ask in your own words, typed or spoken: can I use it, why
does it matter, what should I do, what can you not tell me. No language model writes any answer. A question is matched
to a fixed list by its words and the answer is built from the findings by fixed sentences, so the same question about
the same findings always gives the same answer, word for word. Every answer shows how it was reached (the words it
matched, the fields it read, the file, samples and numbers it rests on) and a fingerprint; "Ask it 100 more times"
asks again and shows the fingerprint did not change. A question the findings cannot answer gets "I cannot answer that",
and a clinical question is refused. It works for a named person with that person's rights on the page and no more:
say "confirm F1" and it prepares your decision, and nothing is recorded until you press the button in your own name.

Optional, and off unless you switch it on: "Understand any wording". When the word list does not recognise a wording,
a language model is asked one thing, which of the fixed questions is meant. It is sent the question and the list of
questions, never the findings or any data, and it writes none of the answer; the trace says when it was used. It
follows the event rule "use a local model or the user's own key": paste your own Anthropic API key into the Ask panel
(held in memory until you close the tool, never written to disk, never in this repository), or run a local model with
[Ollama](https://ollama.com) and the tool finds it. With neither, the switch does not exist and nothing is ever sent
anywhere.

**See the data.** Every change, and every source in an Ask answer, has "See the data in both files". It opens the two
files side by side for the samples involved: each row with the text in the trusted release beside the text in the new
one, exactly as written and unrounded, with every cell that differs marked. For a swap you can read down the columns
and see each sample holding the other's values.

**Review.** Every finding waits for a person. On its page, enter your name and role and confirm or dismiss it. The
review is saved in a small JSON file (`control-tower.reviews.json`, or beside the findings file) and is included
when you download `findings.json` from the page.

`compare` prints the verdict, one line per file, each finding and which analyses were rerun. Its exit code is
0 Ready, 1 Conditional, 2 Blocked, 3 Insufficient Evidence. An exit code of 1 is an answer, not a failure.
A run that gives no answer never uses those four: 64 means the command was wrong (a missing folder, a bad option),
and `envelope` exits 70 when the envelope did not open.

`$D` in these commands is only a shortcut for the organisers' data folder, set on the line above it (bash and zsh;
on Windows write the path out). The trusted
release always goes first and the new one second; the tool cannot tell if you swap them.

Run the tests with `python3 -m unittest discover -s tests -t .`

### Changing the page

Only needed by people who edit the frontend (requires Node.js):

```bash
cd web
npm install
npm run dev          # live reload on http://localhost:5173
```

After a change, run `npm run build` and commit `web/dist` so nobody needs Node to run the tool.

## Data

The event's frozen TCGA-BRCA release, fetched with the organisers' `data/tcga-brca/fetch.py`. No data files are
committed to this repository. The data is de-identified but patient-derived: research use only, no re-identification,
no clinical claims.

## Outputs to look at

The files the tool writes for the organisers' practice release, so you can see them without running anything:

- [`examples/practice-B.findings.json`](examples/practice-B.findings.json): the findings in the shared format (v0.2). It passes `format/validate.py`.
- [`examples/practice-B.audit-report.html`](examples/practice-B.audit-report.html): the same findings in plain English. Download it and open it in a browser.

Demo video (two and a half minutes): https://a7ussein.github.io/readyset-control-tower/

## Team

Ordi (@ordibimvy) · James (@Bjay4910) · Ahmed Hussein (@a7ussein)

## Licence

Apache-2.0.

Third-party code, all used only by the page in `web/` (the engine uses nothing but Python's standard library):

| What | Licence |
|---|---|
| React and React DOM | MIT |
| Red Hat Display, Red Hat Text and Red Hat Mono typefaces (via Fontsource) | SIL Open Font License 1.1 |
| Vite, TypeScript and their type packages (build tools only, not shipped) | MIT, Apache-2.0 |
