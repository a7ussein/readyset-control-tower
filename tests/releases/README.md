# Test releases

How we prove the engine works on releases it has never seen.

| File | What it is |
|---|---|
| `t0.json` to `t12.json` | Configs for the organisers' `make_release.py`. Each plants a known change into release A. |
| `EXPECTED.md` | What a correct tool must report for each config, written and committed before any of them ran. |
| `own_changes.py` | 23 changes the organisers' script cannot make (blanked values, a renamed sample, a missing file, and more), checked against a known answer. |

## Build one test release

From the organisers' challenge repo, on a Mac or Linux (on Windows, `make_release.py` writes different line endings):

    python data/tcga-brca/make_release.py --config ../readyset-control-tower/tests/releases/t1.json

The release lands in `data/tcga-brca/releases/<name>/`, with its answer key in `CHANGES.json`.

## Run the hand-made cases

    python3 tests/releases/own_changes.py --challenge ../oncosys-hackathon-challenge

The scorecard that runs every config and scores it against the answer key is coming next (`scripts/scorecard.py`).
