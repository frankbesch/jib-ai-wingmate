# S2.1 brief — build the pilot corpus and key layer A (Codex, author session)

You are building a SYNTHETIC test corpus for a document-extraction study. You are the author. A separate, blind Codex session will re-key your documents later, so key honestly from the rendered PDFs, not from your own source data. No network. No API key. Write only inside this folder (`synth-pilot/`). Nothing you write goes into git in this session.

## Why you, not Claude
The rule of this study: nothing Claude wrote may grade Claude. Claude wrote the existing corpus (`../synth/`) and its truth. So: do NOT open `../synth/src/`, `../synth/caprock/`, `../synth/caprock-scan/`, or the values in `../truth/synth/`. You may read, for SHAPE only: `../synth/manifest.json`, one file in `../truth/synth/` (structure, not values), `../reconcile.py` (REQUIRED and LISTS), `../schemas/*.json` (field names and descriptions; these are FROZEN and your documents must use these field names), `../typed/README.md`, and the spec `../../artifacts/typed-questions-2026-09-28/05-harder-corpus-spec.md` sections 2, 3, 4 (traps, sizes, keying rules R1–R7).

## Deliverables (all under this folder)
- `src/` your own generator: HTML templates + a build script. Render PDFs with headless Chrome (`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --headless --print-to-pdf=...`), no reportlab/fpdf (not installed). Seeded, reproducible; the build must run end to end with one command and print the sha256 of every PDF.
- `clean/NN_<doc_id>.pdf` (22 documents) and `clean/packets/<packet_id>.pdf` (11 packets, documents concatenated in packet order; `qpdf` or `pypdf` is available).
- `scan/` the same files after a scan pass with `magick` (150 dpi gray, skew, noise, JPEG). Spec trap T1: about 25% of scan pages get harder degradation (skew 2–4°, fax-grade noise, a stamp over one value, a clipped margin) but the text must stay legible at normal zoom. Keep a `scan/README.md` naming which pages got T1.
- `manifest.json` with the SAME shape as `../synth/manifest.json`: `documents[]` (doc_id, file, scan_file, class, packet, pages, page_count, sha256, scan_sha256), `packets[]` (packet_id, file, scan_file, pages, split_truth, sha256, scan_sha256), `references`, `planted_sha256`, `synthetic: true`, `story`, `built`. Paths relative to `demo/` like the existing manifest (`synth-pilot/clean/...`).
- `truth/<doc_id>.json` LAYER A, one per document, same shape as a `../truth/synth/*.json` file: `doc_id, source_file, keyed_by: "codex (author key, layer A)", keyed_from: "rendered PDF", values{...}, page_of{field: page}, uncertain[]`. Key every REQUIRED field and every LIST for the class. A field that is not printed is `null`. Key from the rendered PDF text/images (pdftotext via `pypdf`, or your eyes on the page images), not from your source data; then compare with your source and put every difference in `uncertain` with a reason.
- `traps.json`: for every document and every trapped field/page, the trap ID (T1–T10) it carries and what the correct answer is under rules R1–R7. Untrapped units are the clean controls.
- `planted.json`: the 3 planted billing defects (a wrong owner decimal on a JIB line, a ticket line billed above contract, a JIB line pointing at a non-elected AFE line), sealed by sha256 in the manifest.
- `reference/doi.json`, `reference/contract_rates.json`, `reference/afe_election.json` in the same shape as `../synth/reference/` (read those three small files; they are data, not Claude prose).
- `README.md`: composition table, trap density per row, the rules you applied, how to rebuild, and anything UNVERIFIED.
- `REPORT.md` (your final message also goes here): counts, gates, open questions.

## Composition (spec 05 §3, pilot column)
- 8 ticket packets: 4 with two field tickets, 4 with one; across them 12 field tickets, 3 hauling logs, 2 invoices (a hauling log or invoice rides in a ticket packet as in a real month). Of the 8: 3 plain, 3 carry T4 or T5 (near-duplicate or reprint), 2 carry a continuation page (T9) or a reprint stamp.
- 2 AFE packets: each a 1-page cover letter (`afe_cover`) + a 2-page AFE (`afe`); one of them carries T2 (cover letter with a cost table copied from the AFE, or an AFE with a transmittal paragraph).
- 1 JIB packet: a 2-page `jib_statement`, page 2 WITHOUT a "page N of M" banner (T9).
- Totals: 11 packets, 22 documents, 25 pages, 3 plants. Classes: `afe_cover`, `afe`, `field_ticket`, `hauling_log`, `invoice`, `jib_statement`.
- Trap density: about 40% of scored units carry at least one trap; the rest are clean controls in the same layouts. Use every trap T1–T10 at least once; T6 (field absent, e.g. AFE page 2 with no well name; a labelled blank), T8 (distractor numbers: only `subtotal` printed, no `total`; `wi_decimal_stated` but no `wi_decimal`), T10 (unusual labels: "Bill To" for operator_name, "Ref" for afe_number, "Serviced" for service_date) are the ones that attack the field-presence question, so spread them across documents.
- New fictional names for the operator, the non-operator, vendors, wells, county. No real company, person, or well. Layouts must NOT imitate the existing Caprock documents (you have not seen them; keep it that way).

## Keying rules (RULED, D-239 Q1): R1 a reprint of a ticket (same number, "REPRINT" stamp or new time) is one ticket. R2 a labelled field with a blank value is "not printed" (null). R3 a value printed only in a page header counts as printed for that page, and for later pages only if repeated there. R4 "N/A" or "TBD" printed in the field is "printed". R5 a struck-out value is "printed". R6 a continuation page keeps the topic of its first page. R7 a cover letter that contains an AFE table is still `afe_cover`.

## Gates you must run and paste into REPORT.md
1. `python3 src/build.py` (or your entry point) exits 0 and prints 22 + 11 clean and 22 + 11 scan sha256 lines.
2. A check script `src/check.py` that: loads manifest.json; asserts 22 documents, 11 packets, 25 pages, page_count matches `pypdf` for every clean and scan file, sha256 fields match the files, every split_truth covers every page of its packet exactly once; every truth file has every REQUIRED field key for its class and every LIST with the required row keys; prints the unit arithmetic per set: row1 = 22, row4 = 25, row5 = 11, row8 printed = count of non-null REQUIRED non-boolean fields (spec expects about 147) + decoys 2 per document = 44; total about 249.
3. `pdftotext`-style extraction (pypdf) of every clean page is non-empty; every scan page, when OCR is not available, is at least visually legible: state UNVERIFIED for OCR legibility, and list the T1 pages.
4. `python3 ../typed/typed_questions.py --set synth-pilot --mode fixture` may fail because no parser run exists for this corpus yet; if it errors, paste the error and say so. Do not try to work around it.

Do not run anything in `../typed/` or `../pipeline.py` in live mode. Do not read or set any API key. Report UNVERIFIED rather than guess. Keep your final message under 500 words, and put the full detail in REPORT.md.
