# Engine plan

Status: **draft for the team to agree.** Written from the organisers' code and briefs. Nothing here has been run on
the real data yet, so every statement about file layout beyond the clinical and protein files is still to confirm.

The engine takes two release folders and writes `findings.json` as described in
[`OUTPUT-CONTRACT.md`](OUTPUT-CONTRACT.md). This page says how.

## 1. The analysis registry

The registry is the engine's knowledge of what each protected analysis reads. It is how a change gets mapped to
"affects A1" or "does not affect A2". These entries are read off the organisers' `reference_analyses.py`.

| | A1: ER-alpha protein by ER status | A2: RNA subtype mix |
|---|---|---|
| Files | `clinical.tsv`, `protein_rppa.tsv.gz` | `clinical.tsv` |
| Clinical columns | `sampleID`, `breast_carcinoma_estrogen_receptor_status` | `sampleID`, `PAM50Call_RNAseq` |
| Other rows | the `ERALPHA` row of the protein file | none |
| Samples it uses | protein-file columns that are primary tumours (characters 14–15 of the id are `01`) and whose ER status is exactly `Positive` or `Negative` | clinical rows that are primary tumours and have a non-blank `PAM50Call_RNAseq` |
| Result | counts and mean ER-alpha per group, and the difference | count and percent per subtype |

**A finding affects an analysis when a cell it changed is one the analysis reads, in either release.** Concretely:

- A1 is affected by: a change to the `ERALPHA` value of a sample A1 uses; a sample A1 uses entering or leaving the
  protein file; a change to ER status for a sample in the protein file; a clinical row for such a sample appearing or
  disappearing.
- A2 is affected by: a change to `PAM50Call_RNAseq` for a primary tumour; a primary tumour's clinical row appearing or
  disappearing.
- Everything else affects neither: any change in the survival, mutation, copy number or RNA files; a change to any
  other clinical column; a change to a protein row other than `ERALPHA`; a change to a sample that is not a primary
  tumour.

A swap of two whole protein columns affects A1 only if at least one of the two samples is one A1 uses. If both are in
the same ER group, A1 is rerun and comes out `unchanged`: the group means do not move when two members trade values.

**Rerunning.** An affected analysis is recomputed on both releases. Our own A1 and A2 must print exactly what the
organisers' script prints; a test compares the two on release A.

## 2. Fingerprints

A fingerprint is a short hash of everything one sample holds in one file.

- In a file with samples as columns: the hash of that column's cells, each paired with its row name (the protein or
  gene), so the order of rows does not matter.
- In `clinical.tsv` (one row per sample): the hash of that row's cells, each paired with its column name.
- Cells are read as their exact text. A blank and `NA` are different. Nothing is parsed as a number.
- A profile that is entirely blank gets no fingerprint. Otherwise every empty sample would look like a copy of every
  other.

Order of work, cheapest first:

1. Hash each file's decompressed content in both releases. **Same hash: the file is not opened again**, and it is
   recorded as unchanged.
2. For a changed file, fingerprint every sample in both releases.
3. Only for samples whose fingerprint differs, compare cell by cell.

## 3. The detectors

Each returns findings with the sample ids behind them. One sentence each, then the test that pins it down. The tests
use tiny hand-made releases (five samples, three rows), so they need no real data and run in milliseconds.

| # | Detector | It flags | Test case |
|---|---|---|---|
| 1 | **Unchanged file** | Nothing: a file whose content hash matches is skipped and listed as unchanged. | Two identical releases give no findings, verdict Ready, and no file is opened. |
| 2 | **Membership** | A sample id present in one release's file and absent from the other's. Reports who left and who arrived, and counts by sample type. | Remove one column and add one under a new id: both named, though the count is the same. |
| 3 | **Swap** | Sample X in the new release carries the old profile of Y, and Y carries the old profile of X. A chain of three or more is reported as one finding naming all of them. | Exchange two columns: one finding naming both. Exchange nothing but reorder the columns: no finding. |
| 4 | **Duplicate** | Two ids in the new release share a fingerprint that they did not share in the old release. | Copy column X under a new id: the new id is named with X as its source. Two ids that were already identical in the old release: no finding. |
| 5 | **Relabel** | The same sample and the same clinical column hold different non-blank text in the two releases. One finding per column, naming every sample. | Change ER status for two samples: one `label_conflict` finding, both values shown before and after. |
| 6 | **Missing data** | A cell that held a value in the old release is blank in the new one. | Blank one `ERALPHA` cell: one finding naming the sample and the protein. |
| 7 | **Catch-all** | Every remaining cell that differs and that detectors 2 to 6 did not explain. Low confidence, always flagged for a person. | Change one mutation cell from `0` to `1`: reported as `other`, not silently dropped. |

Structure changes are checked before any of these: a file missing from one release, a row (protein or gene) or a
clinical column that appeared or disappeared. If `ERALPHA` or a clinical column an analysis reads is gone, that analysis
cannot be rerun and the verdict is Blocked.

### When one sample fits two patterns
Decided in this order, and each changed sample-in-a-file is explained once:

1. **Swap** if the profile is some *other existing* sample's old profile and the exchange is mutual (or a closed chain).
2. **Duplicate** if the profile equals another id's profile *in the new release* and they were not equal before.
3. **Membership** for an id that exists in only one release. A new id that is a copy is reported under both 2 and 3.
4. **Relabel / missing data**, cell by cell, for a sample whose profile changed but matches nobody's.
5. **Catch-all** for whatever is left.

A new id that carries the profile of a sample that *left* is a rename. It is reported as one membership finding saying
so, not as a duplicate.

## 4. Speed

The hidden release is run live inside two minutes of questions.

- **Budget (proposal):** under 30 seconds on the demo laptop in the worst case, where the 64 MB RNA file changed.
- **How it stays fast:** unchanged files are never opened; fingerprints are computed in one streaming pass; cell
  comparison only happens for samples whose fingerprint differs.
- **Not measured yet.** The first thing to do with the real data is time the content hash and the fingerprint pass on
  each of the six files, and write the numbers here.

## 5. Choices to settle

| Choice | Recommendation | Why |
|---|---|---|
| pandas or the standard library for reading files | Standard library (`csv`, `gzip`, `hashlib`) | Exact-text reading is the default there; pandas turns blanks and `NA` into the same missing value unless told not to. It also keeps the fresh-clone start at zero installs for the engine. Revisit only if the measured time misses the budget. |
| Rerun A1 and A2 with our own code or by calling the organisers' script | Our own code, tested to print the same as theirs | No dependency on where the challenge repo sits on the judge's machine, and no pandas at run time. |
| RNA file absent from both releases | Compare the other five; list RNA as "not present" | Neither analysis reads it. `fetch.py --no-rna` makes this a normal case. |
| A file absent from only one release | A finding naming the file; verdict Insufficient Evidence | The comparison for that file cannot be made. |
| Command | `python -m control_tower compare <release A> <release B> --out findings.json` | Works with no interface. Exit code 0 Ready, 1 Conditional, 2 Blocked, 3 Insufficient Evidence. |

## 6. Build order

Each step has its test written first. Cut from the bottom if time runs out.

1. Release loader and content hashes; unchanged files skipped
2. Fingerprints
3. Membership
4. Duplicate
5. Swap
6. Relabel
7. Analysis registry and "affects / does not affect"
8. Rerun of affected analyses, before and after
9. `findings.json` writer, validated on every run; the command
10. Repair proposals
11. Missing data
12. Catch-all

## 7. Still to confirm on the real files

- That every file except `clinical.tsv` has samples as columns and one name per row.
- Whether sample ids in every file are the 15-character form.
- Whether release A already contains samples with identical profiles (the duplicate detector must not flag those).
- How a blank is written in each file: an empty cell, `NA`, or both.
- The timings in section 4.
