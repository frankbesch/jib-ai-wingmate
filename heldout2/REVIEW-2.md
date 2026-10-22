**FIX FIRST — cap enforcement, cleanup, validation, resume, and scoring still have blocking gaps.**

### First-review findings

| # | Status | File:line evidence |
|---|---|---|
| 1 | FIXED | `heldout2/run_heldout2.py:848` redacts subprocess output before logging, including secrets split across reads. |
| 2 | PARTLY | `heldout2/run_heldout2.py:1824` checks final errors, but Claude recovery can hide Jev failures. `typed/typed_questions.py:733,821` then permits understated settlement. |
| 3 | PARTLY | `heldout2/run_heldout2.py:1777` explicitly acknowledges enforcement after spending. The historical estimate at `:93` remains unenforceable. |
| 4 | FIXED | `heldout2/run_heldout2.py:2409` locks before reading resume state; `:490` rejects missing or unreadable ledgers. |
| 5 | PARTLY | `heldout2/run_heldout2.py:926` escalates group cleanup, but explicitly excludes detached descendants at `:928`. |
| 6 | PARTLY | `heldout2/run_heldout2.py:1409` accepts any nonempty list of passing gates. Missing mandatory gates remain undetected. |
| 7 | FIXED | `heldout2/run_heldout2.py:1847,1867,1287` validates registry hashes, identities, paths, and repeat assignments before audits and scoring. |
| 8 | PARTLY | `heldout2/score_heldout2.py:548,560` checks repeats and errors. `:562` compares coverage between runs, without establishing expected coverage. |
| 9 | FIXED | `heldout2/run_heldout2.py:1736,1740` enforces the primary exclusion limit against the combined unique set. |
| 10 | FIXED | `heldout2/run_heldout2.py:105,1024` freezes and verifies both `reconcile.py` and parsed REQUIRED. |
| 11 | PARTLY | `heldout2/run_heldout2.py:81–85` still allows shared user-temporary writes and Unix networking under default-allow permissions. |
| 12 | FIXED | `typed/typed_questions.py:539` now uses compatible quoting for the alias sentence. |

### New defects

- **Stage deadlines exclude validation.** `heldout2/run_heldout2.py:1328,1365,1440` gives Codex the full deadline, then performs PDF checks outside that deadline. Each check receives another timeout at `:239`. Slow PDFs can extend keying far beyond its advertised deadline. Fix: establish one stage deadline and pass its remaining time into every operation.

- **Successful audits break resume.** `heldout2/run_heldout2.py:722,1203` hashes the entire audit input directory before execution. `:1362` then adds the stage’s own answers inside that directory. `:750` excludes only later stages’ outputs. Consequently, restarting after a completed audit triggers `:1086` despite unchanged user inputs. Fix: hash explicit immutable audit inputs and checkpoint answers separately.

- **Baseline membership can falsely fail P3 and Overall.** `heldout2/briefs/generator.md:15` assigns one baseline class to documents without cases. This includes plain approval documents and documents without approval fields. `heldout2/score_heldout2.py:433` makes any true false-alarm designation constrain that entire class. A legitimate K2 catch on a plain baseline ticket therefore fails Overall at `:445`. Fix: separate baseline classes by field applicability and false-alarm semantics; validate class consistency.

- **Scan adjudication receives clean evidence.** `heldout2/briefs/adjudicate.md:1` supplies both image sets, including during scan-audit adjudication. `heldout2/run_heldout2.py:1667` supplies no variant restriction. When scanning obscures a value, the adjudicator can use the clean image to overturn the scan auditor. Fix: supply only the audited variant and identify its images explicitly.

No new secret-exposure defect was established; runtime secrecy remains UNVERIFIED.

No paid-call path was found in ordinary `--stub` or `--dry-run` execution.

K1–K3 source selection, normalization, bounded matching, and missing-source handling match section 3.

No additional plausible-data crash defect was established.

No files changed, project scripts ran, APIs were called, or secrets were read. Runtime behavior, sandbox enforcement, and request-byte identity remain UNVERIFIED.

FIX FIRST