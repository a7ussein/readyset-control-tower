# ReadySet Control Tower

Team **Automyte** · OncoSys Cancer AI Lab, Nov 11–14 2026 · Track: Cohort Firewall · Product: Cohort Control Tower

**User:** a research engineer responsible for a dataset that gets new releases.

**The one workflow:** point the tool at two releases of the TCGA breast cancer data. It finds what silently changed
between them (swapped, copied, missing or relabelled samples), reruns only the analyses those changes touch, and
writes `findings.json` in the organisers' shared format.

## Status

Planning, plus the page's shell. No comparison engine yet: the team agrees the plan before anyone builds it.

- [`docs/PLAN-IN-SHORT.md`](docs/PLAN-IN-SHORT.md): the plan in two minutes.
- [`docs/OUTPUT-CONTRACT.md`](docs/OUTPUT-CONTRACT.md): the rules for `findings.json`.
- [`docs/example-findings.json`](docs/example-findings.json): a hand-written example that passes the organisers'
  validator. Every id and number in it is invented.
- [`docs/ENGINE-PLAN.md`](docs/ENGINE-PLAN.md): how the engine will work, with measurements on the real files.
- [`web/README.md`](web/README.md): the page, and how to work on it.

## Setup and run

You need Python 3.9 or newer and nothing else.

```bash
./run.sh          # the page at http://localhost:8010, showing the example findings (run.bat on Windows)
python3 -m unittest discover -s tests -t .
```

Today the page is a shell that shows the hand-written example. Running the tool on two real releases will be added
here once the engine exists.

## Data

The event's frozen TCGA-BRCA release, fetched with the organisers' `data/tcga-brca/fetch.py`. No data files are
committed to this repository. The data is de-identified but patient-derived: research use only, no re-identification,
no clinical claims.

## Team

Ordi (@ordibimvy) · James (@Bjay4910) · Ahmed Hussein (@a7ussein)

## Licence

Apache-2.0. Third-party code and its licences will be listed here.
