**FIX FIRST — spending, process cleanup, validation, and confinement have blocking gaps.**

1. **Secret-bearing errors reach logs.** `heldout2/run_heldout2.py:1518` captures document parser output without redaction; `pipeline.py:415` includes raw HTTP error bodies. A service error that echoes the authentication header writes the key into the stage log. Actual service reflection is UNVERIFIED. Fix: redact secrets before persisting responses, exceptions, or subprocess output.

2. **Unknown charges become zero spend.** `heldout2/run_heldout2.py:1559` settles Jev reservations using reported totals, including failed runs. `typed/jev_backend.py:270` returns no cost for malformed successful responses or unreadable usage. A billed malformed response therefore releases its reservation, permitting additional spending. The document parser similarly treats missing credit fields as zero (`pipeline.py:328`). Fix: retain each uncertain call’s bound until its actual charge is known.

3. **The parser cap relies on an estimate.** `heldout2/run_heldout2.py:91` derives its five-credit page bound from historical consumption. `:1019` reserves that estimate, but `:1518` launches the entire pipeline without per-call budget enforcement. If 80 pages cost 450 credits, the second set cannot fit within 800 despite passing the reservation check. Fix: establish enforceable call bounds and reserve before each submission; current provider bounds are UNVERIFIED.

4. **Concurrent resumes can duplicate paid calls.** `heldout2/run_heldout2.py:906` loads state without acquiring an exclusive lock. Two resumes can read the same pending stage and independently submit it against identical remaining balances. Separately, missing or malformed ledger data silently resets spending (`:408`). Fix: lock the run before reading state and reject an unreadable existing ledger.

5. **Children can survive cleanup.** `heldout2/run_heldout2.py:781` calls cleanup with `graceful=False` after normal parent exit. `:805` then skips SIGKILL, leaving a SIGTERM-resistant descendant running after the stage becomes DONE. Resume cleanup also sends only SIGTERM (`:1003`). Fix: verify process-group termination and escalate regardless of the parent’s exit status; separately handle detached descendants.

6. **Failed build gates can pass orchestration.** `heldout2/run_heldout2.py:1242` checks only manifest totals and truth-file existence. A keying session can report failed PDF hashes, missing field keys, or case/truth contradictions while satisfying those checks. The runner then purchases extraction. Fix: require machine-readable gate results and independently validate every mandatory gate before the document parser runs.

7. **Resume does not protect repeat pairing.** `heldout2/run_heldout2.py:1583` writes `arms.json`, but arm outputs at `:628` include only the result directory. Change repeat assignments after stopping: resume accepts them, and scoring pairs different C/C-alias repeats. Fix: checkpoint the arm registry and validate its paths, identities, and repeat assignments before audit and scoring.

8. **Incomplete or failed arms can receive passing marks.** `heldout2/score_heldout2.py:124` accepts any directory containing reports and calls, without rejecting reported errors or validating unit completeness. `:309` checks for no C repeats, not missing required repeats. One surviving C repeat can therefore satisfy P1/P2 despite the second being absent. Fix: require the exact arm/repeat inventory, successful reports, and identical expected unit sets; restrict discovery to validated registry entries.

9. **Exclusion limits apply to fragments, not their union.** `heldout2/run_heldout2.py:1499` combines layer-A and audit exclusions, but `:1502` checks only audit exclusions. Six layer-A exclusions plus six distinct primary-audit exclusions produce twelve exclusions without triggering INVALID. Fix: enforce R6 against the combined unique exclusions for each set.

10. **K1’s effective rule is not frozen.** `heldout2/controls.py:33` loads REQUIRED from `reconcile.py` during scoring. `heldout2/run_heldout2.py:100` excludes that dependency from the freeze. Changing REQUIRED during the unattended run changes K1 and P2 while freeze verification passes. Fix: freeze and verify REQUIRED’s source or its parsed value before designing cases.

11. **Render confinement exceeds the accepted permissions.** `heldout2/run_heldout2.py:78` allows writes throughout `/private/var/folders` and `/dev`, rather than only the session folder. It denies outbound IP connections, not all network operations. Generated code can access unrelated temporary files and retains broader networking permissions. Fix: use default-deny permissions, session-local temporary storage, and a complete network denial; macOS enforcement remains UNVERIFIED.

12. **The typed change requires an undeclared Python upgrade.** `typed/typed_questions.py:539` reuses double quotes inside a double-quoted f-string expression. Python 3.11 and earlier reject the module during parsing. On such installations, the first arm fails after corpus generation and parser spending. Fix: use compatible quoting or require Python 3.12+ during initial preflight; the installed version is UNVERIFIED.

Static inspection found no paid-call path in ordinary `--stub` or `--dry-run` execution. K2 source selection, normalization, boundaries, and missing-source handling match the contract. Same-repeat catches, K1+K2 decisions, unique-person counting, and P3 blocking are implemented.

No files changed, project scripts ran, APIs were called, or secrets were read. Runtime tests and default-request byte identity remain UNVERIFIED.

FIX FIRST