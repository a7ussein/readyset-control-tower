# The plan in short

For Ordi and James. Two minutes to read. The detail is in [`ENGINE-PLAN.md`](ENGINE-PLAN.md) and
[`OUTPUT-CONTRACT.md`](OUTPUT-CONTRACT.md).

## What we're building
Give the tool two versions of the breast cancer data. It tells you which samples changed, whether that moves either
of the two protected results, and writes one file, `findings.json`, that the judges' checker and another team's tool
read.

## How it works
1. **Hash every file.** If a file is the same in both versions it is never opened. All six files take about half a
   second.
2. **Fingerprint every sample** in the files that did change: one short hash of everything that sample holds.
3. **Compare fingerprints** to find what happened: two samples traded places, one was copied under a new name, one
   left, one arrived, a label changed, a value went blank. Anything left over is reported as "changed, can't classify".
4. **Ask which result each change touches.** We know exactly which columns and samples A1 and A2 read.
5. **Rerun only those results** and show before and after. The rest are marked "not rerun" with the reason.

## The one file that connects us
`findings.json`. Ahmed's engine writes it, James's screen shows it, Ordi's tests score it. A hand-written example is in
[`example-findings.json`](example-findings.json) and passes the organisers' validator. **James:** your screen should
need nothing that isn't in that file. If it does, tell Ahmed and the file gets a new field.

## What we learned from the real data
- The data is downloaded and all six files match the organisers' checksums.
- **The survival file has one sample per row**, not per column as the first plan assumed.
- **Some samples are already identical in the trusted release** (a tumour and a normal from one patient share a
  survival record). So "two samples look the same" is not automatically a copy. We only flag pairs that were different
  before.
- **Speed is fine.** The two files our results depend on take under a tenth of a second. Worst case, every large file
  changed, is about 24 seconds. No pandas needed; plain Python is fast enough.

## What exists today
- The output contract and the example file.
- The engine plan, with seven detectors described in one sentence each.
- 46 tests, 32 of which say exactly what the engine must report for each kind of change. They
  run on a tiny invented dataset of eight samples, so anyone can check an expected answer by eye.
- **A first working engine** (Ahmed got ahead of the Thursday start). It passes all the tests, gives the organisers'
  own A1 numbers on release A, and on a changed copy of the real data found exactly what was planted in under six
  seconds. **Run blind on the organisers' practice release, it matched the answer key exactly** (the swap, the five
  removed samples, the five copies and their sources, nothing extra) in under a second.
- **Ahmed's own checks of the engine**, run on his machine: releases built with the organisers' script, and changes
  their script cannot make, alone, combined and at scale. All passed, slowest under six seconds. These were to trust
  the engine, not to replace the team's testing. **The test releases and the scorecard are Ordi's to design and build.**

## Decisions we need from the team
1. **The verdict rule.** Ready = nothing changed. Conditional = things changed, we reran what was affected, a person
   reviews. Blocked = an affected result can't be rerun. Insufficient Evidence = a file is missing. Agree or change.
2. **Severity.** High = a result moved. Medium = a result's samples were touched but the number held. Low = no result
   touched. Agree or change.
3. **A copied sample is reported twice**, as a duplicate and as a membership change. Fine, or one finding?
4. **The interface.** Carry over the ReadySet page and design for James to re-point, or start fresh?

## Questions for the organisers at kickoff
1. What does the checker compare: just the kind of change and the sample ids, or also severity, verdict and repairs?
2. One finding per change, or one per sample?
3. How do we receive the hidden release, and which files can it change?
4. The seven-criterion rubric, which isn't in the repo.

Already answered (relayed by Ahmed, 10 Nov):
- Building on our October ReadySet work is allowed. We build here or copy things over as needed.
- Ordi's OncoSys internship does not affect eligibility.

## Who does what
- **Ahmed:** the engine. Built and merged; 46 tests pass. Next: whatever kickoff changes.
- **James:** the one screen and the fresh-clone setup. Builds against the example file first.
- **Ordi:** the test releases, the scorecard, the demo and the pitch.

## Rules we all keep
- Nobody opens the practice answer key or the organisers' reference output until our tool has run on the practice
  release.
- No data files in the repo. They are fetched.
- A test before the code it tests.
