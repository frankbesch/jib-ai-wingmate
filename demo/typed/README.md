# typed/ — typed-question runner (rows 1, 4, 5, 8 of the 2026-09-28 decomposition)

_Built 2026-09-29 · Owner: Frank · Status: `claude -p` arm live PASS (G4, G5); Jev arm live PASS (J4). Replays a recorded parser run through typed questions with zero parser spend. Design: `../../artifacts/typed-questions-2026-09-28/02-typed-decomposition.md`._

## What it measures

| Node | Shape | Per | Label source | Fail-closed |
|---|---|---|---|---|
| row1 document class | choice over 7 classes + `needs_review` | document (7) | `synth/manifest.json` class | max p < 0.60 → `needs_review` |
| row4 page topic | choice over 7 topics + `needs_review` (one `field_ticket`; ordinal is software, collapsed 2026-09-29) | page (9) | manifest pages, document class | same |
| row5 second ticket | noul | packet (3) | count of field_ticket docs ≥ 2 | 0.35 < p < 0.65 → abstain |
| row8 field printed | noul, batched per document (7 calls, 66 units) or per field (66 calls) | required non-boolean field (`reconcile.REQUIRED`, 52) plus 2 decoy fields per document from another class (14 negatives, label False) | `truth/synth/<doc>.json` value not null; decoys False | same |

The report's headline is **wrong, not abstained**: what a silent pipeline would have passed through. `correct` requires a non-abstained answer equal to the label. Probabilities are the model's self-reported numbers and are **uncalibrated**; the report says so on every run. Thresholds are frozen in the file (declared before any live run).

## Gates (D-101), run 2026-09-29

| # | CHECK | EXPECT | Result |
|---|---|---|---|
| G1 | `python3 typed/typed_questions.py --run runs/live-synth-03 --mode fixture` | exit 0; 26 calls, 85 units, errors 0; row1 = 7 n / 5 correct / 1 abstain (ticket_b plant) / 1 wrong (afe_cover plant); row5 = 3 / 1 / 1 / 1 (day01 abstain, day30 wrong plants); report.md carries SYNTHETIC | PASS (`calls 26, units 85, errors 0, row1 {7,5,1,1,0}, row5 {3,1,1,1,0}`) |
| G2 | `python3 typed/typed_questions.py --mode dry-run` | 26 requests, `network_calls: 0`, exit 0 | PASS (`requests 26, approx_input_tokens 16058, network_calls 0`) |
| G3 | `python3 tests/test_typed_questions.py` | `OK 8 assertion groups` (labels, plants, thresholds, 10 malformed-reply shapes, 7 stubbed CLI failure envelopes, isolation flags, no plant reads) | PASS |
| G5 | live rerun after the row-4 collapse | row 4 abstains clear | PASS 2026-09-29, both runs: 85/85 correct, 0 abstain, 0 errors (`../../artifacts/typed-questions-2026-09-28/live-results/g5-row4-collapsed/`) |
| G4 | live run (FRANK-RUN, below) | 26 envelopes with `usage` logged; `errors 0`; report.md without SYNTHETIC | PASS 2026-09-29, both runs: 26 calls, 85 units, 0 errors, 0 wrong-not-abstained (`../../artifacts/typed-questions-2026-09-28/live-results/`) |

## Jev backend (`--backend jev`), built 2026-09-29

The second arm of the comparison: the same 26 calls and 85 units, sent to TypeSafe System One (`jev-1.13.0`, pinned) by `typed/jev_backend.py`. Labels, thresholds, and scoring are the same code as the `claude -p` arm. Jev arm status: live run done 2026-09-29 (J4).

| # | CHECK | EXPECT | Result |
|---|---|---|---|
| J1 | `python3 typed/typed_questions.py --backend jev --mode fixture` | exit 0; 26 calls, 85 units, errors 0; row1 7/5/1/1 and row5 3/1/1/1 (the planted results); report.md carries SYNTHETIC and "no spend" | PASS |
| J2 | `python3 typed/typed_questions.py --backend jev --mode dry-run` (no key set) | exit 0; 26 requests, 85 questions; `network_calls: 0`; `socket_guard: true`; 26 body files, no header, no key | PASS (est 23,713 tokens, $0.000996; bound 71,225 tokens, $0.002991; cap $0.01) |
| J3 | `python3 tests/test_jev_backend.py` | `OK 10 assertion groups`, including the live loop in-process with a stubbed `http` and a fake key | PASS |
| J4 | live run (FRANK-RUN, below) | 26 responses logged with `usage.input_tokens`; errors 0; report.md says METERED | PASS 2026-09-29, both runs: 26 calls, 85 units, 0 errors; clean 73/10/2, scan 70/14/1 (correct/abstain/wrong); $0.001308 and $0.001351 metered (`../../artifacts/typed-questions-2026-09-28/live-results/jev-arm/`) |

Cost receipts: price $0.042 per million input tokens, output free (docs.typesafe.ai/models, quoted in a private source review). The dry-run figures are an estimate (chars/3) and an upper bound (UTF-8 bytes), not a bill. The bill is `usage.input_tokens` from the live responses.

Safety: live refuses without a well-formed key; one `GET /v1/models` runs before any billed call; the run refuses if its whole bound passes `--max-spend`; it stops (exit 3, report marked INCOMPLETE) on three consecutive errors, on a call that bills more than its body bound, or on passing the cap; a dropped connection is charged at the bound; redirects are refused; the key is scrubbed from every stored response and error.

Fresh-context reviewer (2026-09-29) returned FIX FIRST: 1 blocker (error text was cut before it was redacted, so a key across byte 300 could leak a prefix), 5 material (the stored prompt was the claude prompt, and the raw response was dropped; no check that billing stays under the bound; live loop untested; redirects could carry the key; `HTTPException` uncaught), 3 nits. All applied.

### Row-8 field-description test (`--field-desc verbatim|short`)

Off by default; the default request bodies are byte-identical to the J4 run (26 of 26 hashes match). The hypothesis, variants, and pass mark are declared in `../../artifacts/typed-questions-2026-09-28/04-metrics-table.md`. Descriptions come from `schemas/<class>.json`. Claude control: 66 of 66 on both sets, both variants (2026-09-29). Jev result (2026-09-29): hypothesis SUPPORTED; `short` gives 65 of 66 on both sets (baseline 57 and 54), `verbatim` 63 and 64; decoys 14 of 14; $0.001710 billed for the four runs.

```bash
cd <repo root>
export TYPESAFE_API_KEY=... (see .env.example)
for m in verbatim short; do for r in live-synth-03 live-synth-scan-01; do python3 typed/typed_questions.py --backend jev --run runs/$r --rows 8 --field-desc $m --mode live --cap 10 --max-spend 0.005; done; done
```

Outputs: `runs/<id>/typed/live-jev-desc-<variant>-<stamp>/`.

### Rows 1 and 4 option-description test (`--option-desc verbatim|short`)

Off by default; default bodies still match the J4 run (26 of 26 hashes). Descriptions come from `schemas/synth_classify_config.json` and `schemas/synth_split_config.json`. The hypothesis, the one derived text, the prediction, and the pass mark are declared in the metrics table. Claude control: 16 of 16 on both sets, both variants (2026-09-29). Jev result (2026-09-29): hypothesis SUPPORTED, 16 of 16 on both sets with both variants (baseline 13 of 16); the verbatim-beats-short prediction was not confirmed; $0.003265 billed for the four runs.

```bash
cd <repo root>
export TYPESAFE_API_KEY=... (see .env.example)
for m in verbatim short; do for r in live-synth-03 live-synth-scan-01; do python3 typed/typed_questions.py --backend jev --run runs/$r --rows 1,4 --option-desc $m --mode live --cap 20 --max-spend 0.005; done; done
```

Outputs: `runs/<id>/typed/live-jev-opt-<variant>-<stamp>/`.

Confirming run with both options on (`--field-desc short --option-desc verbatim`, 2026-09-29, Frank-run): 84 correct, 1 abstain, 0 wrong of 85 on both sets; $0.001521 and $0.001564 billed.

### Items 2 and 3 (`--unlabelled generic|targeted`, `--continuation software`)

Both off by default; default and confirming request bodies still match the earlier runs (26 of 26 hashes each). Hypotheses, the one hand-written text, and both pass marks are declared in the metrics table. With `--continuation software` a page whose header says "page N of M" (N of 2 or more) gets no model call and takes the decision of the page before it; `calls.jsonl` marks it `software: true`. Claude control: 85 of 85 and 66 of 66 on both sets (2026-09-29). Jev result (2026-09-29): `--continuation software` SUPPORTED; `--unlabelled generic` NOT SUPPORTED and harmful (row 8 fell to 22 of 66; do not use); `--unlabelled targeted` scored 66 of 66 but missed the declared margin on clean (0.68 against 0.72), NOT SUPPORTED.

```bash
cd <repo root>
export TYPESAFE_API_KEY=... (see .env.example)
for r in live-synth-03 live-synth-scan-01; do python3 typed/typed_questions.py --backend jev --run runs/$r --field-desc short --option-desc verbatim --unlabelled generic --continuation software --mode live --cap 30 --max-spend 0.01; python3 typed/typed_questions.py --backend jev --run runs/$r --rows 8 --field-desc short --unlabelled targeted --mode live --cap 10 --max-spend 0.005; done
```

### Generic sentence, join fixed (`--unlabelled generic-fixed`)

Same sentence as `generic`, with a full stop closing the description first. The mark and the reading of the result are declared in the metrics table. Claude control: 66 of 66 on both sets (2026-09-29). Jev result (2026-09-29): NOT SUPPORTED; row 8 stayed at 22 of 66 on both sets, so the sentence and not the join causes the collapse. Do not use either generic option with Jev.

```bash
cd <repo root>
export TYPESAFE_API_KEY=... (see .env.example)
for r in live-synth-03 live-synth-scan-01; do python3 typed/typed_questions.py --backend jev --run runs/$r --rows 8 --field-desc short --unlabelled generic-fixed --mode live --cap 10 --max-spend 0.005; done
```

### Redo flags (S1.1, 2026-09-30; private source plan, sections 2 to 4)

All flags are off by default. Default request bodies still match G5 (claude) and J4 (jev), 26 of 26 hashes each (`--compare-hashes`).

| Flag | Effect |
|---|---|
| `--set <dir>` | Corpus dir with its own `manifest.json` and `truth/`. No flag (or `--set synth`) keeps `synth/manifest.json` and `truth/synth`. |
| `--truth-b <dir>` | Layer-B truth, keyed from the parser extract, same JSON shape. Row 8 is scored against B. A present and B absent is parser-dropped: its own column, out of correct, abstain, wrong, error, top = label, and every person count (`scored` = n − parser-dropped). A absent and B present is listed as extract-invented. |
| `--parity` | Both backends get `--field-desc short --option-desc verbatim`. Claude asks row 8 one field per call; Jev keeps its request shape. `disagree` no longer forces an abstain; the thresholds are unchanged. Each unit records `parity_sha256` over question text, ordered options, definitions, and document text, read back from what each backend sends. |
| `--mode parity-check` | Builds every unit for both backends with no network and prints `parity N of N`, then any mismatch. With `--parity` on the current set: `parity 85 of 85`. |
| `--model` | Required in `--mode live` with the claude backend; without it the run exits 2 before any call. `calls.jsonl` logs `model_requested` and `served_model` (the keys of the envelope's `modelUsage`); `report.json` records `model_requested` and `served_models`. |
| `--compare-hashes <calls.jsonl>` | Dry-run only: compares every request hash with `prompt_sha256` in a recorded run and prints `hash_match`. |

```bash
cd <repo root>
A=../artifacts/typed-questions-2026-09-28/live-results
python3 typed/typed_questions.py --mode dry-run --compare-hashes $A/g5-row4-collapsed/live-synth-03/calls.jsonl
python3 typed/typed_questions.py --backend jev --mode dry-run --compare-hashes $A/jev-arm/live-synth-03/calls.jsonl
python3 typed/typed_questions.py --mode parity-check --parity
```

### Cascade backend (`--backend cascade --escalate-below 0.80`, S1.2, 2026-09-30)

Arm C runs as one run. Jev answers every unit first. A unit goes to Claude as one per-field call when its Jev top probability is strictly under the line, or when its Jev answer is an error. Claude's frozen thresholds then decide answer or abstain. An abstain or an error goes to a person. Top probability is the highest option probability for a choice and max(p, 1 − p) for a yes/no. The cascade always runs in parity mode. Each escalated unit records both parity hashes, and the run refuses to start unless they are equal. `--cap` counts Jev requests plus Claude calls. `--max-spend` covers the Jev half. Live mode needs `--model`, the Jev key, and a logged-in `claude`. `calls.jsonl` holds one `jev_request` record per request. It also holds one `unit` record per unit: `answered_by`, the Jev probability and decision, and, when escalated, Claude's answer, probability, model, and latency. The report adds a cascade table and the H4 line. The fixture escalates `ticket_b`, `afe_cover`, `day01`, and `invoice.vendor_name`, and Claude abstains on two of them. `invoice.total` sits on the line at 0.80 and stays with Jev.

Review fixes (2026-09-30):
- Each half has its own circuit breaker. Three Jev errors in a row stop the run with exit 3, even when Claude answers the escalated units. Three Claude errors in a row also stop it.
- The report counts `jev_errors` and splits escalations by reason (`below_line`, `jev_error`).
- Every report now has a `top = label` column, the threshold-free headline: the top answer equals the label. The cascade reports it for the Jev half and the Claude half.
- The `claude -p` child never receives `TYPESAFE_API_KEY`.
- `calls.jsonl` is flushed after every record.
- A Jev `needs_review` answer at a top probability of 0.80 or more is not escalated. It abstains and goes to a person. This follows the frozen definition, and it cannot lower the H3 count.
- Each Claude call record compares `served_model` with `model_requested` loosely: case is ignored, a date suffix such as `-20251001` is dropped, and either string may contain the other. A mismatch sets `model_mismatch: true` on the record, and `report.json` counts `model_mismatches`. A mismatch is logged, never an error, because an alias may differ from the served id.

```bash
python3 typed/typed_questions.py --backend cascade --mode fixture --escalate-below 0.80
python3 typed/typed_questions.py --backend cascade --mode dry-run --escalate-below 0.80
```

UNVERIFIED: whether the `claude -p` envelope carries `modelUsage` in these runs. The G5 records kept only `usage`, so no recorded envelope shows it; the first live run with `--model` settles it (`served_model` null means absent).

### Known differences between the two arms (report these with any comparison)

Under parity mode (`--parity`, and always in `--backend cascade`):

- The question text, the ordered options, the definitions, and the document text are identical. `parity_sha256` checks this for every unit (`--mode parity-check`: 85 of 85).
- Row 8 is one field per call for Claude. Jev answers each field as an independent question within one request.
- The disagree route is off for both arms. A disagreeing answer keeps its `disagree` flag and no longer forces an abstain.
- The residual difference is the wrapper. Claude receives a system prompt and a JSON output contract. The contract includes the choice-prompt line `Use "needs_review" when the evidence is thin.` (`typed_questions.py`, `prompt_for`). Jev receives neither. Its output shape is fixed by the API, and it gets that sentence only as the `needs_review` criteria text ("The evidence is thin."). The parity hash does not cover this wrapper.
- The thresholds (0.60 floor, 0.35–0.65 band) were declared for self-reported Claude numbers. They are applied unchanged to Jev.

Before parity, the 2026-09-29 runs (G4, G5, J4, and the description tests):

- Row 8: Claude saw all fields of a document in one prompt. Jev answered each field as an independent question in one request.
- Claude saw option and field names only, unless a `--field-desc` or `--option-desc` flag was set. Jev's criteria map carried text for `needs_review` only.
- Claude reports an answer and probabilities, so an answer that disagreed with its own top probability abstained. Jev's noul answer is derived from its probability, so that route could not fire for Jev.
- `needs_review` was the only option with criteria text ("The evidence is thin."), mirroring the one sentence the Claude prompt gives it.
- Claude also received a system prompt and a JSON output contract. Jev received neither.
- The same thresholds applied to both arms.

### Live run, Jev arm (Frank starts it; D-218; metered)

```bash
cd <repo root>
export TYPESAFE_API_KEY=... (see .env.example)
python3 typed/typed_questions.py --backend jev --run runs/live-synth-03 --mode dry-run
python3 typed/typed_questions.py --backend jev --run runs/live-synth-03 --mode live --cap 30 --max-spend 0.01
python3 typed/typed_questions.py --backend jev --run runs/live-synth-scan-01 --mode live --cap 30 --max-spend 0.01
```

Outputs: `runs/<id>/typed/live-jev-<stamp>/{calls.jsonl,prompts.jsonl,report.json,report.md}`. `prompts.jsonl` holds the request bodies.

## Review receipt

Fresh-context reviewer (opus, 2026-09-29) returned FIX FIRST: 1 blocker (a choice reply without probabilities scored correct), 6 material (unvalidated probabilities, silent answer/argmax disagreement, all-positive row-8 labels with the signature boolean mislabelled, `claude -p` running with tools and repo settings in the demo cwd, crash on timeout or non-dict envelope, errors folded into the abstain column), 3 nits. All applied: `Malformed` fail-closed scoring with a validated probability contract; `disagree` flag abstains; boolean fields excluded and 14 decoy negatives added; CLI runs with `--tools ''`, `--setting-sources ''`, `--no-session-persistence`, a fixed system prompt, and an empty temp cwd, and `num_turns > 1` is an error; timeout, missing CLI, and non-dict envelopes return errors; per-node `error` column and headline count; 3-consecutive-error circuit breaker; prompts logged to `prompts.jsonl`; report states oracle segmentation for row 1.

## Live run (Frank starts it; D-218)

Backend is `claude -p --output-format json` (the CLI is logged in; no Anthropic SDK or API key exists on this machine, checked 2026-09-29). The envelope's `total_cost_usd` is logged per call; G4 reported non-zero amounts. Billing basis RESOLVED 2026-09-29: the CLI is signed in with a Max subscription (`claude auth status`: `authMethod claude.ai`, `subscriptionType max`), so the envelope amount is an API-equivalent estimate at list price and is not billed per call (code.claude.com/docs/en/costs). Residual: usage credits past the plan limit, not checked. Cap refuses more calls than `--cap`.

```bash
cd <repo root>
echo hi | claude -p >/dev/null && echo "AUTH OK" || echo "RE-LOGIN NEEDED: claude auth login"
python3 typed/typed_questions.py --run runs/live-synth-03 --mode dry-run          # 26 requests, 0 calls
python3 typed/typed_questions.py --run runs/live-synth-03 --mode live --cap 30    # clean set
python3 typed/typed_questions.py --run runs/live-synth-scan-01 --mode live --cap 30   # scan set, reported apart
```

Outputs: `runs/<id>/typed/live-<stamp>/{calls.jsonl,report.json,report.md}`. Per-field row 8 (`--row8 per-field`, 85 calls) is the second experiment, not the first.

## What this does not do

- No calibration claim. Whether p=0.9 means 90% is a later measurement over n≥30 per node.
- Rows 9, 24, 32 are not here: no labeled set exists (02 §D).
- The runner never reads `synth/planted.json`; labels come from the manifest and truth only (test 6).
- Not a document parser feature. The typed calls sit beside the document parser's outputs, as the decomposition draws them.
