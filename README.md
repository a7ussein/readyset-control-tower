# ReadySet Control Tower

Team **Automyte** · OncoSys Cancer AI Lab, Nov 11–14 2026 · Track: Cohort Firewall · Product: Cohort Control Tower

**User:** a research engineer responsible for a dataset that gets new releases.

**The one workflow:** point the tool at two releases of the TCGA breast cancer data. It finds what silently changed
between them (swapped, copied, missing or relabelled samples), reruns only the analyses those changes touch, and
writes `findings.json` in the organisers' shared format.

## Status

The comparison engine and the page both work. The engine is tested, and the two together have been run on the organisers' practice release.

- [`docs/PLAN-IN-SHORT.md`](docs/PLAN-IN-SHORT.md): the plan in two minutes.
- [`docs/OUTPUT-CONTRACT.md`](docs/OUTPUT-CONTRACT.md): the rules for `findings.json`.
- [`docs/ENGINE-PLAN.md`](docs/ENGINE-PLAN.md): how the engine works, with measurements on the real files.
- [`web/README.md`](web/README.md): the page, and how to work on it.

## Setup and run

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

Get the data and the practice release, in a folder next to this one (not inside it). Starting from this repository's folder: The organisers' scripts need pandas and jsonschema, installed here in a virtual environment; our tool needs neither.

```bash
cd ..
git clone https://github.com/disleveK/oncosys-hackathon-challenge.git
cd oncosys-hackathon-challenge
python3 -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install pandas jsonschema
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

# Check the output with the organisers' validator (needs the virtual environment from above):
python ../oncosys-hackathon-challenge/format/validate.py findings.json

# Look at the result in the page:
./run.sh serve --findings findings.json        # http://localhost:8010  (run.bat on Windows)
```

Or let the page compare the two folders itself, which also lets you change the question on the page:

```bash
./run.sh serve $D/raw $D/releases/practice-B     # http://localhost:8010  (run.bat on Windows)
```

**The question.** The tool protects the analyses you say the release is needed for. On the page, switch them on and
off in the bar under the verdict. On the command line, `--for A2` asks about A2 alone, and `--question FILE` takes
your own analyses (see "The question" in [`docs/OUTPUT-CONTRACT.md`](docs/OUTPUT-CONTRACT.md)). For the practice
release the answer is Conditional when A1 is in the question and Ready when only A2 is.

**Review.** Every finding waits for a person. On its page, enter your name and role and confirm or dismiss it. The
review is saved in a small JSON file (`control-tower.reviews.json`, or beside the findings file) and is included
when you download `findings.json` from the page.

`compare` prints the verdict, one line per file, each finding and which analyses were rerun. Its exit code is
0 Ready, 1 Conditional, 2 Blocked, 3 Insufficient Evidence.

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

## Team

Ordi (@ordibimvy) · James (@Bjay4910) · Ahmed Hussein (@a7ussein)

## Licence

Apache-2.0. Third-party code and its licences will be listed here.
