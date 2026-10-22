# S3.1 brief — build the held-out corpus and key layer A (Codex, author session)

You are building the SECOND, larger part of a SYNTHETIC test corpus for a document-extraction study. You built the pilot part in `../synth-pilot/` (11 packets). A separate, blind Codex session will re-key your documents later, so key honestly from the rendered PDFs, not from your own source data. No network. No API key. Write only inside this folder (`synth-heldout/`). Nothing you write goes into git in this session.

## Why you, not Claude
The rule of this study: nothing Claude wrote may grade Claude. Do NOT open `../synth/src/`, `../synth/caprock/`, `../synth/caprock-scan/`, or the values in `../truth/synth/`. You MAY reuse your own pilot generator: copy `../synth-pilot/src/` into `src/` and extend it. Read `../synth-pilot/README.md`, `../synth-pilot/traps.json`, and `../synth-pilot/manifest.json` for shape. Field names come from `../schemas/*.json` (FROZEN). Rules and traps: `../../artifacts/typed-questions-2026-09-28/05-harder-corpus-spec.md` sections 2, 3, 4.

## What is different from the pilot
- New seed. New month (September instead of August). New fictional operator, non-operator, vendors, wells, county. No name from the pilot reappears. Keep the same page layouts and the same trap catalogue T1 to T10; the pilot did not tune traps (ruling G1, D-243), so nothing about trap strength changes.
- Held-out by construction: this corpus is scored on its own. Do not include or reference any pilot document.
- Composition below is the spec-05 full corpus MINUS the pilot PLUS eight more ticket packets (ruling Q6, D-239).

## Deliverables (all under this folder)
- `src/` generator (headless Chrome via `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --headless --print-to-pdf=...`; `qpdf` or `pypdf` for concatenation; `magick` for the scan pass). Seeded, reproducible; one command builds end to end and prints the sha256 of every PDF.
- `clean/NN_<doc_id>.pdf` (71 documents) and `clean/packets/<packet_id>.pdf` (39 packets, documents concatenated in packet order).
- `scan/` the same after the scan pass (150 dpi gray, skew, noise, JPEG, no text layer). T1: about 25% of scan pages get harder degradation (skew 2–4°, fax-grade noise, a stamp over one value, a clipped margin), text legible at normal zoom. `scan/README.md` names the T1 pages.
- `manifest.json` in the SAME shape as `../synth-pilot/manifest.json` (paths relative to `demo/`, like `synth-heldout/clean/...`).
- `truth/<doc_id>.json` LAYER A, one per document, same shape as `../synth-pilot/truth/*.json`, `keyed_by: "codex (author key, layer A)"`, `keyed_from: "rendered PDF"`. Key every REQUIRED field and every LIST for the class. Not printed is `null`. Key from the rendered PDF, then compare with your source and put every difference in `uncertain` with a reason.
- `traps.json`, `planted.json` (3 plants, sealed by sha256 in the manifest), `reference/{doi,contract_rates,afe_election}.json` (same shapes as the pilot).
- `README.md`: composition table, trap density per row, rules applied, how to rebuild, anything UNVERIFIED.
- `REPORT.md` (your final message also goes here): counts, gates, open questions.

## Composition
- 30 ticket packets: 15 with two field tickets, 15 with one. Across them 45 field tickets, 9 hauling logs, 4 invoices (a hauling log or invoice rides in a ticket packet as in a real month; the eight extra ticket packets may be plain, with no rider). Of the 30: 18 plain (9 two-ticket, 9 one-ticket); 12 carry T4 or T5 (6 two-ticket near-duplicate or reprint, 6 one-ticket with a reprint stamp or a continuation page T9).
- 4 AFE packets: each a 1-page cover (`afe_cover`) + a 2-page AFE (`afe`); two carry T2 (cover with a cost table copied from the AFE, or an AFE with a transmittal paragraph).
- 5 JIB packets: a 2-page `jib_statement`; at least two with page 2 WITHOUT a "page N of M" banner (T9).
- Totals: 39 packets, 71 documents (45 ticket, 9 hauling, 4 invoice, 4 cover, 4 AFE, 5 JIB), 80 pages (45 + 9 + 4 + 4 + 8 + 10), 3 plants.
- Trap density: about 40% of scored units carry at least one trap; the rest are clean controls in the same layouts. Every trap T1–T10 at least three times. T6 (labelled blank), T8 (distractor numbers), T10 (unusual labels: "Bill To", "Ref", "Serviced", "Dispatch docket", "Account request") spread across documents and classes, in about the pilot's proportion.

## Keying rules (RULED, D-239 Q1)
R1 a reprint of a ticket (same number, "REPRINT" stamp or new time) is one ticket. R2 a labelled field with a blank value is "not printed" (null). R3 a value printed only in a page header counts as printed for that page, and for later pages only if repeated there. R4 "N/A" or "TBD" printed in the field is "printed". R5 a struck-out value is "printed". R6 a continuation page keeps the topic of its first page. R7 a cover letter that contains an AFE table is still `afe_cover`.

## Gates you must run and paste into REPORT.md
1. `python3 src/build.py` exits 0 and prints 71 + 39 clean and 71 + 39 scan sha256 lines.
2. `python3 src/check.py`: 71 documents, 39 packets, 80 pages; page_count matches `pypdf` for every clean and scan file; sha256 fields match the files; every split_truth covers every page of its packet exactly once; every truth file has every REQUIRED field key for its class and every LIST with the required row keys; prints the unit arithmetic per set: row1 = 71, row4 = 80, row5 = 39, row8 printed = count of non-null REQUIRED non-boolean fields (at most 465) + decoys 2 per document = 142; total at most 797.
3. Extraction (pypdf) of every clean page is non-empty; every scan page visually legible; state UNVERIFIED for OCR legibility; list the T1 pages.
4. `grep -ril` for every pilot proper noun (operator, non-operator, vendors, wells, county from `../synth-pilot/manifest.json` `story`) over `src/` and `truth/` returns nothing.

Do not run anything in `../typed/` or `../pipeline.py`. Do not read or set any API key. Report UNVERIFIED rather than guess. Keep your final message under 500 words; full detail in REPORT.md.
