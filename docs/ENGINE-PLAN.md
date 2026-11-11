# Engine plan

Status: **built.** The engine in `control_tower/` follows this plan; 41 tests pass. Section 8 says how it did on the
real files. The rules below are still open to change by the team.

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

- In a file with samples as columns (mutation, protein, copy number, RNA): the hash of that column's cells, each
  paired with its row name (the protein or gene), so the order of rows does not matter.
- In a file with one row per sample (`clinical.tsv` and `survival.tsv`): the hash of that row's cells, each paired
  with its column name.
- The loader works out which way round a file is by where the `TCGA-` ids are (the header, or the first column). It
  does not assume.
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

- **Budget:** under 30 seconds on the demo laptop in the worst case, where every file changed.
- **How it stays fast:** unchanged files are never opened; fingerprints are computed in one streaming pass; cell
  comparison only happens for samples whose fingerprint differs.

Measured on release A, standard library only, one pass per file (Apple-silicon laptop, 10 Nov):

| File | Size unpacked | Shape | Content hash | Fingerprint every sample |
|---|---|---|---|---|
| `clinical.tsv` | 1.7 MB | 1,247 samples × 194 columns | under 0.01 s | 0.04 s |
| `survival.tsv` | 0.1 MB | 1,236 samples × 11 columns | under 0.01 s | under 0.01 s |
| `protein_rppa.tsv.gz` | 1.7 MB | 131 proteins × 747 samples | 0.01 s | 0.03 s |
| `mutation_gene_level.tsv.gz` | 64.5 MB | 40,543 genes × 791 samples | 0.03 s | 3.9 s |
| `copy_number_gistic.tsv.gz` | 59.9 MB | 24,776 genes × 1,080 samples | 0.03 s | 3.7 s |
| `rna_hiseq.tsv.gz` | 180.4 MB | 20,530 genes × 1,218 samples | 0.22 s | 4.4 s |

What this means:

- Hashing all six files in both releases takes about half a second. Deciding "nothing changed" is nearly instant.
- The two files A1 and A2 read (clinical and protein) fingerprint in well under a tenth of a second.
- The worst case, all three large files changed, is about 12 seconds per release, so about 24 seconds for the
  fingerprint pass before cell comparison. That is inside the budget with little to spare, on this laptop. It must be
  re-timed on the demo laptop, and the cell comparison still has to be measured once it exists.
- The standard library is fast enough. There is no speed case for pandas.

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

## 8. How the engine did on the real release

Run on 10 Nov on the event's frozen release, standard library only.

- **A1 matches the organisers' numbers.** Ours gives 529 ER-positive tumours with mean 2.179 and 169 ER-negative with
  mean -0.872. Their starter shows 2.18 and -0.87.
- **Release A against itself:** Ready in 0.64 seconds; no file opened.
- **Release A against a copy we changed ourselves** (two protein samples swapped, two RNA samples swapped, one RNA
  subtype relabelled): 5.75 seconds, including the 180 MB RNA file. It reported exactly those three changes: the
  relabel affecting A2, the protein swap affecting A1, and the RNA swap affecting neither. Both analyses were rerun.
- **Both outputs pass the organisers' validator.**
- Not yet run: the organisers' practice release B. That is the blind test, to be done with the team.

Two things the build added to this plan:

- **A copy needs most of the sample to have changed.** In a small file, editing one cell can make a sample equal to
  another by coincidence. An existing sample is only called a copy when at least half of its cells differ from before.
- **An unreadable file is never a crash.** A file that cannot be read as a table gives a finding and the verdict
  Insufficient Evidence.

## 7. What the real files showed

Checked on release A on 10 Nov, with our own read-only script.

| Question | Answer |
|---|---|
| Does every file except `clinical.tsv` have samples as columns? | **No.** `survival.tsv` has one sample per row, like the clinical file. The other four have samples as columns. |
| Are sample ids always the 15-character form? | Yes, in all six files. No id is repeated within a file. |
| Which sample types are in each file? | Clinical: 1,101 primary, 139 normal, 7 metastasis. Protein: 742 primary, 5 metastasis, no normals. Mutation and copy number: primary only. |
| Does release A already contain identical profiles? | **Yes.** `survival.tsv` has 135 groups of samples with identical rows (a tumour and a normal from the same patient share one survival record). `copy_number_gistic.tsv.gz` has one group of four. The other files have none. So "two ids share a profile" is normal in some files, and the duplicate detector must only flag pairs that were **not** identical in the old release. |
| How is a blank written? | As an empty cell, in the clinical and survival files (116,445 and 1,626 of them). The four molecular files have no blanks at all in release A, so a blank appearing there is itself a change. |
| Are row names unique in the molecular files? | Yes. No protein or gene name is repeated. |

Still not known:

- How the hidden release is delivered, and which files it can change (a question for the organisers).
- Timings on the demo laptop.
- The cost of the cell-by-cell comparison, which does not exist yet.
