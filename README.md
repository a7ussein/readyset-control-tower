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

```bash
# 1. get the event data (from the organisers' challenge repo)
python data/tcga-brca/fetch.py

# 2. compare two releases: the trusted one first
python3 -m control_tower compare path/to/release-A path/to/release-B --out findings.json

# 3. look at the result in the page
./run.sh serve --findings findings.json        # http://localhost:8010  (run.bat on Windows)
```

`compare` prints the verdict, one line per file, each finding and which analyses were rerun. Its exit code is
0 Ready, 1 Conditional, 2 Blocked, 3 Insufficient Evidence.

Run the tests with `python3 -m unittest discover -s tests -t .`

## Data

The event's frozen TCGA-BRCA release, fetched with the organisers' `data/tcga-brca/fetch.py`. No data files are
committed to this repository. The data is de-identified but patient-derived: research use only, no re-identification,
no clinical claims.

## Team

Ordi (@ordibimvy) · James (@Bjay4910) · Ahmed Hussein (@a7ussein)

## Licence

Apache-2.0. Third-party code and its licences will be listed here.
