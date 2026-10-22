**FIX FIRST — audit evidence, P3 recomputation, blindness, and completion handling still have defects.**

### Prior findings

| Finding | Status | Current evidence |
|---|---|---|
| First-review 2: unknown charges | FIXED | `heldout2/run_heldout2.py:1879–1887` retains the reservation when cascade Jev errors occurred, including Claude-recovered failures. |
| First-review 6: build gates | PARTLY | `heldout2/run_heldout2.py:1456–1462` requires every gate ID; nonempty-text and earlier-name checks remain session attestations. |
| First-review 8: arm completeness | FIXED | `heldout2/run_heldout2.py:1984–1999` builds expected units; `heldout2/score_heldout2.py:570–589` checks inventory, errors, and coverage. |
| REVIEW-2: validation deadlines | FIXED | `heldout2/run_heldout2.py:1239,1486–1488` gives PDF validation the stage’s remaining time. |
| REVIEW-2: audit resume | FIXED | `heldout2/run_heldout2.py:794–805,1119` excludes the audit’s own outputs from input hashes. |
| REVIEW-2: baseline P3 failure | FIXED | `heldout2/score_heldout2.py:441–446` applies zero-flag restrictions per document, preventing mixed-baseline contamination. |
| REVIEW-2: clean evidence during scan adjudication | FIXED | `heldout2/run_heldout2.py:602,692` and `heldout2/briefs/adjudicate.md:1` restrict copied images to the audited variant. |

### New defects

- **An invalid score still completes successfully.** `heldout2/score_heldout2.py:647,726–737` writes INVALID but exits successfully. `heldout2/run_heldout2.py:1978–1982,1152` then marks scoring DONE and the run COMPLETE. For example, missing expected units trigger INVALID without stopping orchestration. Fix: return nonzero for INVALID and require the orchestrator to validate the verdict.

- **Launcher authentication can hang indefinitely.** `heldout2/run-heldout2.sh:42` runs `claude auth status` without a timeout, before orchestration starts. A stalled authentication process prevents every stage deadline and cleanup handler from starting. Fix: execute authentication under a bounded subprocess with process-group cleanup.

- **Packet adjudication receives document evidence.** `heldout2/run_heldout2.py:1730,1763` passes a row-5 packet ID into the document-image resolver at `:1712–1714`. Consider a two-ticket packet whose ID matches its first document. The adjudicator receives only that document’s images and can incorrectly rule that no second ticket exists. Unmatched packet IDs instead produce nonexistent image paths. Fix: resolve all packet documents and pages, preserving packet order, and validate every image path.

- **Audit corrections cannot update P3’s zero-flag restriction.** `heldout2/score_heldout2.py:441,628–629` always uses the original case flags across every truth layer. Suppose an audit changes an approval field from printed to absent, while K2 flags that document. With other thresholds satisfied, one false alarm leaves P1 passing and P3 unchanged, allowing an incorrect Overall PASS. Fix: derive each layer’s restriction from its corrected approval-presence labels and handle exclusions explicitly.

- **The blind layer-B keyer receives expected negative labels.** `heldout2/briefs/layerb.md:1,9` supplies `heldout2/inputs/layerb_fields.md:13`, which identifies specific fields as “DECOY” and normally absent. Every layer-B session therefore receives the negative-control list before examining extracted text. Fix: merge all queried fields into neutral lists and remove expected-presence wording.

No additional secret-exposure defect was established.

No additional cap, duplicate-submission, or paid stub/dry-run defect was established beyond accepted risks.

K1–K3 source selection, normalization, bounded matching, and missing-source handling match section 3.

No additional plausible-data crash defect was established.

Runtime behavior, sandbox enforcement, and default-request byte identity remain UNVERIFIED. No edits, project execution, API calls, or secret reads occurred.

FIX FIRST