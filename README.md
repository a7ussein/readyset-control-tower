# ReadySet Control Tower

Team **Automyte** · OncoSys Cancer AI Lab, Nov 11–14 2026 · Track: Cohort Firewall · Product: Cohort Control Tower

**User:** a research engineer responsible for a dataset that gets new releases.

**The one workflow:** point the tool at two releases of the TCGA breast cancer data. It finds what silently changed
between them (swapped, copied, missing or relabelled samples), reruns only the analyses those changes touch, and
writes `findings.json` in the organisers' shared format.

## Status

Planning. No engine code yet: the team agrees the plan before anyone builds.

- [`docs/OUTPUT-CONTRACT.md`](docs/OUTPUT-CONTRACT.md): the draft rules for `findings.json`.
- [`docs/example-findings.json`](docs/example-findings.json): a hand-written example that passes the organisers'
  validator. Every id and number in it is invented.

## Setup and run

To be written once the tool exists. It will work from a fresh clone using only the steps on this page.

## Data

The event's frozen TCGA-BRCA release, fetched with the organisers' `data/tcga-brca/fetch.py`. No data files are
committed to this repository. The data is de-identified but patient-derived: research use only, no re-identification,
no clinical claims.

## Team

Ordi (@ordibimvy) · James (@Bjay4910) · Ahmed Hussein (@a7ussein)

## Earlier work

This project builds on ReadySet, a tool Ahmed built in October 2026 for the first version of this challenge. The
team was told that building on that earlier work is allowed. This repository started empty on 10 November 2026;
everything carried over from ReadySet is listed here, file by file, as it is added.

Carried over so far: nothing. The approach is the same (every finding cites the samples behind it, "could not look" is
kept apart from "failed", and the tool never guesses).

## Licence

Apache-2.0. Third-party code and its licences will be listed here.
