# Expected results, written before any test release was built

| Test | Findings a correct tool reports | A1 | A2 | Verdict |
|---|---|---|---|---|
| t0 | none | not touched | not touched | Ready |
| t1 | one sample_swap in the protein file naming both samples | changed (an ER+ and an ER- sample trade values) | not touched | Conditional |
| t2 | one sample_swap in the protein file naming both samples | rerun, unchanged (both samples in one ER group) | not touched | Conditional |
| t3 | one duplicate naming 5 copies, each with its LumA source; one membership_change naming 5 Basal samples that left | affected; changed if any removed or added sample has ER Positive or Negative | not touched | Conditional |
| t4 | one label_conflict in clinical.tsv naming 10 samples | affected if any of the 10 is in the protein file, else not touched | not touched | Conditional |
| t5 | one label_conflict in clinical.tsv naming 10 samples | not touched | changed (10 samples move subtype) | Conditional |
| t6 | one sample_swap in the copy number file naming both samples | not touched | not touched | Conditional |
| t7 | one label_conflict in clinical.tsv naming 10 samples (PR_Status_nature2012) | not touched | not touched | Conditional |
| t8 | three findings: protein sample_swap, label_conflict on PAM50, RNA sample_swap | changed | changed | Conditional |
| t9 | one duplicate naming 3 copies, each with its LumA source; one membership_change naming 3 Her2 samples that left; all in the RNA file | not touched | not touched | Conditional |
| t10 | four sample_swap findings in the protein file, or fewer if swaps chain together (one finding naming every sample in the chain) | changed | not touched | Conditional |
| t11 | one label_conflict in clinical.tsv naming 10 samples | affected if any of the 10 is in the protein file: those samples drop out of A1, so its sample count shrinks | not touched | Conditional |
| t12 | one duplicate naming 3 copies, each with its LumA source; one membership_change naming 3 Basal samples that left; all in the mutation file | not touched | not touched | Conditional |

In every test: nothing reported that was not planted, and the output passes the organisers' validator.