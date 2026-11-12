# Output contract: `findings.json`

Status: **in use.** The engine writes exactly this, and its output passes the organisers' validator on the real data. The hand-written example below predates the engine and uses invented values.

One file ties our three roles together. The engine writes it, the screen shows it, the self-test scores it, and on
Saturday the organisers' checker and another team's Repair Review Desk read it. If it stays stable, nobody waits on
anybody.

- The example: [`example-findings.json`](example-findings.json). Hand-written. Every sample id, checksum and number in
  it is invented; it describes no real release. It passes the organisers' validator (shared format v0.2).
- Check any output: from the challenge repo, `python format/validate.py path/to/findings.json`
  (needs `pip install jsonschema`).

The example covers one finding of each kind we plan to detect, an analysis that changed, an analysis left alone, and a
repair for most findings.

## The rules the engine follows

### Top of the file
| Field | Rule |
|---|---|
| `format_version` | Always `"0.2"`. |
| `producer` | Always `{"team": "Automyte", "product": "Cohort Control Tower", "track": "cohort-firewall"}`. |
| `data.releases` | Two entries, the trusted release first. Each lists **all six files** with a SHA-256. |
| `files[].hash_of` | Always `"content"`: the hash of the decompressed content, on both releases, so the two are comparable and a re-gzipped file does not look changed. |
| `question` | One sentence naming both releases and the registered analyses. |
| `verdict` | One of our four words. The rule is below. The format marks it optional, and we do not know whether the checker reads it. |

### Sample ids
- Always the 15-character sample id (`TCGA-XX-XXXX-01`), exactly as it appears in the file. Never the 12-character
  patient id, never the longer aliquot barcode.
- Every sample a finding is about appears as **its own** evidence pointer with `"kind": "sample"`. We assume the
  checker matches findings to the answer key by kind and by these ids.

### Findings
Each finding is one thing that changed, of one kind.

| Field | Rule |
|---|---|
| `id` | `F1`, `F2`, … in the order found. Stable within a file. |
| `kind` | `sample_swap` · `duplicate` · `membership_change` · `label_conflict` · `missing_data` · `other`. Nothing else. |
| `summary` | One plain sentence a judge can read aloud. |
| `severity` | `high` if it changes a registered analysis's result. `medium` if it touches samples an analysis reads but the result is the same. `low` if it touches no registered analysis. One exception, to match the organisers' reference output: a `membership_change` is never above `medium`, because it is lost coverage, not corrupted values. |
| `confidence` | `high` when the pattern is exact (a profile matches another id's profile, a cell's text differs). `low` for the catch-all `other`. `medium` is reserved for partial matches. |
| `evidence` | At least one pointer. Each has `kind` and `id`, plus `release`, `file` and a `note` saying what was seen there. |
| `affects_analyses` / `not_affected_analyses` | Between them they name **every** registered analysis, each exactly once. Both are always present, even when one is empty. |
| `limitation` | Always present. What this finding cannot tell you. |
| `needs_human_review` | Always present. `true` for every finding that is not purely informational. |

One change, one kind. When a sample fits more than one pattern, the order of precedence is: swap, then duplicate, then
membership change, then relabel, then missing data, then `other`.

Which samples a finding lists, matching the organisers' own reference output:

- A `duplicate` finding lists the **copies** only. The sample each one copies is named in that pointer's `note`, not
  listed as a sample itself.
- A `membership_change` finding lists the samples that **left**, and any id that arrived with values of its own. A new
  id that is a copy appears only in the `duplicate` finding. Its summary says which clinical subgroups lost coverage
  ("by RNA subtype: Her2 5").

(The hand-written example file predates this rule and lists both; the engine follows the rule above.)

### Analyses
One entry per registered analysis, always. Today that is A1 and A2.

| `status` | Meaning | `before` / `after` |
|---|---|---|
| `changed` | Rerun; the result differs. | Both present. |
| `unchanged` | Rerun because a finding touched its inputs; the result is the same. | Both present and equal. |
| `not_rerun` | No finding touches a file, column, row or sample it reads. | Absent. |

- `before` and `after` hold the numbers the organisers' `reference_analyses.py` prints for that analysis on each
  release (`n_samples`, the group sizes, the means and the difference for A1; `n_samples`, `counts` and `percent` for
  A2), so anyone can reproduce them with one command.
- `note` (our addition) says in one sentence why it was or was not rerun, naming the findings.

### Repairs
| Field | Rule |
|---|---|
| `id` | `R1`, `R2`, … |
| `action` | `restore_from_previous_release` · `exclude` · `relabel` · `flag_for_review` · `other`. |
| `targets` | Pointers to exactly what would change. |
| `justification` | One or two sentences, using only facts stated in the findings it addresses. |
| `addresses` | Finding ids. Every id must exist in the file (the validator checks this). |

- Every repair addresses at least one finding. **We never propose a repair the findings do not support.** Review Desk
  teams are tested on spotting unsupported repairs, and ours must not be the one they reject.
- A finding may have no repair. In the example F4 has none: the label changed, no registered analysis reads that
  column, and we do not know which value is right.
- No repair is proposed for an analysis no finding affects.

### The verdict (proposal)
| Verdict | When |
|---|---|
| `Ready` | No findings. The two releases have identical content. |
| `Conditional` | Findings exist, every affected analysis was rerun, and before and after are shown. A person must review. |
| `Blocked` | An affected analysis cannot be rerun on the new release (its input row, column or file is gone). |
| `Insufficient Evidence` | A file is missing or unreadable in either release, so the comparison could not be made. |

### Our own additions
The format allows extra keys. Ours all sit under one key, `x_readyset`, so another team's tool can ignore them:

| Key | For |
|---|---|
| `run_seconds`, `generated_at`, `engine_version` | The verdict banner. |
| `files[]` with `status` and `opened` | The per-file line on the screen. `status` is `changed`, `unchanged` (never opened), `absent` (in neither release), `missing_in_one`, or `unreadable`. A changed file with no findings also has a `note`: its bytes differ but every value is the same (line endings, or row or column order). |
| `witness` | Keyed by finding id, for findings about samples in a large file: one named `row` (ER-alpha in the protein file, otherwise the file's first row) and each sample's `before` and `after` value in it. A value is `null` where the sample is not in that release. A reader can open the two files and check the finding by eye. |
| `analysis_titles` | The plain name of each registered analysis, keyed by id, for the screen. |
| `analyses_in_question`, `analysis_reads`, `unrelated_findings` | The analyses this run was asked to protect, what each one reads in plain words, and how many findings touch none of them. |
| `rules` | Keyed by finding id: `detected_by` (the check that found it), `impact` (one line per analysis in the question: touched or not, and what it reads) and `severity` (why this level). |
| `effects`, `repair_priority` | `effects[finding][analysis]`: what that finding does to that analysis on its own, with `before`, `after` (the analysis recomputed on the trusted release with only that finding's changes applied), `size` (`large` when a headline number, meaning the difference between groups, a group mean or a share, moved by half a percent or more; `small` when the result changed less than that, for example only in its sample counts; `none` when it is identical), `measure` and `moved_by`. `repair_priority[repair]`: how urgent the fix is, sized by that effect (`before use`, `small effect`, `no effect on the result`, `for the record`). A swap or a copy that reaches an analysis is always `before use`, whatever its size, because the samples carry someone else's data. The shared `severity` field is unchanged by size, so it stays comparable with the organisers' reference output. |
| `review_keys`, `reviews`, `live` | Added by the page's server, never by `compare`: where a person's review attaches, the reviews recorded so far (`finding`, `status` of `confirmed` or `dismissed`, `reviewer`, `role`, `note`, `at`), and in live mode the analyses the page can switch between. |
| `analyses_registered` | States the tool's scope in data. |
| `scope` | The limitation sentence shown on screen. |
| `example_notice` | Only in the hand-written example. |

The screen must not need anything that is not in this file. If it does, the file gets a new key; the screen never
computes a number itself.

## Not decided yet
These need the organisers or the team. Each could change this contract.

1. **What does the checker compare?** Kinds and sample ids only, or also severity, verdict, analyses and repairs?
2. **Does the checker expect one finding per change or one per sample?** We group: one swap finding names both samples.
3. **How should a copied sample be reported?** We report it twice, as a duplicate and inside the membership change.
   If the checker counts findings, that may read as a false positive.
4. **Severity `none`.** The format has it. We do not use it. Should a change that touches no analysis be `none`
   instead of `low`?
5. **Evidence for large changes.** If 200 samples are relabelled, do we list all 200 pointers? This draft says yes.
6. **`hash_of`.** The organisers publish release A's checksums as hashes of the downloaded files. We report content
   hashes for both releases. Is that acceptable to the checker?
7. **The verdict rule** above is a proposal from the plan doc, not yet agreed.

## What I did and did not do
- Read the shared format's schema, the validator, `reference_analyses.py`, and the Control Tower and Review Desk briefs.
- Ran the organisers' validator on the example: valid. Ran it on a copy with a wrong `kind` and a repair pointing at a
  finding that does not exist: both rejected.
- Did **not** open the practice answer key (`CHANGES.json`), the organisers' reference output
  (`format/examples/control-tower-practice-B.json`), or the part of `make_release.py` that builds the practice release.
- Did not download or run anything on the real data. The `before` / `after` keys are copied from the analysis code;
  the values in the example are invented.


## The question

The question is which analyses the new release is needed for. It is an input, and the answer follows it.

- `compare A B` protects every registered analysis (A1 and A2).
- `compare A B --for A2` protects only A2. Findings that touch nothing A2 reads are still reported, at `low` severity,
  and the verdict is `Ready`: nothing that changed is read by this question.
- `compare A B --question q.json` takes a JSON list. Each entry is a registered id or a new analysis:

```json
[
  {"id": "A2"},
  {"id": "Q1", "type": "mean_by_group", "title": "HER2 protein by PR status",
   "file": "protein_rppa.tsv.gz", "row": "HER2", "column": "PR_Status_nature2012", "groups": ["Positive", "Negative"]},
  {"id": "Q2", "type": "category_mix", "title": "Histology mix", "column": "histological_type"}
]
```

`mean_by_group` is the mean of one row of a measurement file for primary tumours, split by the groups of a clinical
column (A1 is one of these). `category_mix` is how primary tumours divide among the values of a clinical column (A2 is
one of these). A new analysis gets the same treatment as A1 and A2: the tool works out which changes touch it, reruns
it only then, and reports before and after.

**Verdict rule, restated with the question in it.** `Ready`: nothing changed, or nothing that changed is read by the
question's analyses. `Conditional`: at least one finding touches an analysis in the question; it was rerun, and a person
reviews. `Blocked`: a touched analysis cannot be rerun. `Insufficient Evidence`: a file is missing or unreadable.
