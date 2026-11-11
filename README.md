# ReadySet Control Tower

Team **Automyte** · OncoSys Cancer AI Lab, Nov 11–14 2026 · Track: Cohort Firewall · Product: Cohort Control Tower

**User:** a research engineer responsible for a dataset that gets new releases.

**The one workflow:** point the tool at two releases of the TCGA breast cancer data. It finds what silently changed
between them (swapped, copied, missing or relabelled samples), reruns only the analyses those changes touch, and
writes `findings.json` in the organisers' shared format.

## Status

The comparison engine works and is tested. The page is still a shell that shows one findings file.

- [`docs/PLAN-IN-SHORT.md`](docs/PLAN-IN-SHORT.md): the plan in two minutes.
- [`docs/OUTPUT-CONTRACT.md`](docs/OUTPUT-CONTRACT.md): the rules for `findings.json`.
- [`docs/ENGINE-PLAN.md`](docs/ENGINE-PLAN.md): how the engine works, with measurements on the real files.
- [`web/README.md`](web/README.md): the page, and how to work on it.

## Setup and run

You need Python 3.9 or newer and nothing else: no packages to install.

### Quick start, no data and no install needed beyond Python 3.9+

Clone the repository, then run:

```bash
./run.sh        # http://localhost:8010  (run.bat on Windows)
```

It opens http://localhost:8010 showing the hand-written example (`docs/example-findings.json`). Note that this example uses completely invented data.

### Comparing real releases

The event data is fetched with the organisers' `fetch.py` from their challenge repository (https://github.com/disleveK/oncosys-hackathon-challenge). No data files are committed to this repository.

Get the data and the practice release, in a folder next to this one (the organisers' scripts need pandas; our tool does not):

```bash
git clone https://github.com/disleveK/oncosys-hackathon-challenge.git
cd oncosys-hackathon-challenge
pip install -r requirements.txt
python data/tcga-brca/fetch.py             # the trusted release, into data/tcga-brca/raw/, checksums verified
python data/tcga-brca/make_release.py      # practice release B, into data/tcga-brca/releases/practice-B/
```

The two folders can stay where they are: `compare` takes paths. `releases/practice-B/CHANGES.json` is the answer key, so do not open it until the tool has run.

Once you have the releases, compare them (the trusted release first):

```bash
# Compare two releases, from this repository's folder (RELEASE_A is the trusted one):
D=../oncosys-hackathon-challenge/data/tcga-brca
python3 -m control_tower compare $D/raw $D/releases/practice-B --out findings.json

# Look at the result in the page:
./run.sh serve --findings findings.json        # http://localhost:8010  (run.bat on Windows)
```

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
