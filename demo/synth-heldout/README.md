# Synthetic held-out corpus

**The corpus contains 71 documents, 39 packets, and 80 pages per set.**

September 2026 records use seed `931047` and new fictional entities.
The operator is Darsenne Basin Operations LLC.
The owner is Ultraven Fold Interests LLC.
Brelquor Field Services LLC and Sovarek Fluid Transit LLC provide services.
Tressaline 9-VH and Ostrand 4-KH sit in fictional Lumereth County.
All amounts and entities are synthetic.

## Composition

| Class | Documents | Pages | Packet arrangement |
|---|---:|---:|---|
| field_ticket | 45 | 45 | 15 pairs and 15 singles |
| hauling_log | 9 | 9 | Riders in ticket packets |
| invoice | 4 | 4 | Riders in ticket packets |
| afe_cover | 4 | 4 | One cover per AFE packet |
| afe | 4 | 8 | Two pages per AFE |
| jib_statement | 5 | 10 | Two pages per JIB packet |
| Total | 71 | 80 | 39 packets |

Ticket packets 01–09 contain ordinary pairs with different dates and quantities.
Packets 10–15 contain near-duplicate pairs that differ only in ticket number and one charge description.
Packets 16–24 contain ordinary single tickets.
Packets 25–30 contain one ticket with a REPRINT stamp.
Thus, 18 packets lack T4/T5, and 12 carry T4/T5.
Some ordinary packets carry field-label traps; “plain” describes their ticket-count treatment.

AFE packets 02 and 04 carry both table-bearing covers and forms with transmittal paragraphs.
These provide four T2 instances across two packets.
All five JIB continuation pages omit page-count banners.
All four AFE cost schedules also omit those banners.

## Trap density

The denominator includes absent required fields because absence remains a scored answer.
Counts deduplicate overlapping traps on each scored unit.

| Row | Units per set | Clean trapped | Scan trapped |
|---|---:|---:|---:|
| 1: document class | 71 | 8 (11.3%) | 21 (29.6%) |
| 4: page topic | 80 | 17 (21.2%) | 29 (36.2%) |
| 5: second distinct ticket | 39 | 12 (30.8%) | 12 (30.8%) |
| 8: field presence | 607 | 251 (41.4%) | 254 (41.8%) |
| Total | 797 | 288 (36.1%) | 316 (39.6%) |

Eight cover decoy traps remain outside these density counts because runner decoy selection remains UNVERIFIED.
Their inclusion would give 296/797 clean and 324/797 scan.
The clean density is below 40%; the scan density is approximately 40%.
Trap parameters and page layouts retain the authorized generator's settings.
Label traps appear across all six classes.
T1 covers exactly 20/80 pages, with locations in `scan/README.md`.
The stamp follows a rendered value's position to ensure overlap.
Noise, skew range, stamp opacity, JPEG quality, and margin clipping remain fixed.
These counts describe design, not measured model difficulty.

## Rules and layer A

| Rule | Applied interpretation |
|---|---|
| R1 | A stamped reprint remains one ticket. |
| R2 | A labelled blank has a null value. |
| R3 | A header field counts on later pages only when repeated. |
| R4 | Literal N/A and TBD count as printed. |
| R5 | A visible struck-out value counts as printed. |
| R6 | A continuation retains the first page's topic. |
| R7 | A cover with an AFE cost table remains afe_cover. |

`src/field_contract.json` matches the frozen schemas without changing descriptions.
Its REQUIRED and LISTS definitions retain the study's scoring contract.
The schema's minimal `required` arrays alone do not define this study's complete field inventory.

`src/key.py` reads rendered PDF text and writes candidates before opening source values.
It keys every required field and each list row, including blank cells and zero-dollar rows.
It records page locations and page-specific presence separately.
It compares candidates with source values and retains differences in `uncertain`.
The comparison currently contains zero differences.
All signature blocks remain visibly empty and key false.

The 465 required non-boolean slots include 452 printed values and 13 nulls.
Two decoys per document add 142 questions.
The requested printed subtotal is `71 + 80 + 39 + 452 + 142 = 784`.
The complete presence task includes nulls and totals `797` units per set.
Row 5 contains 15 positives, 15 one-ticket negatives, and nine easy negatives.
The scan set uses the same layer A values, subject to separate visual legibility review.

Three billing plants appear in `planted.json`.
The manifest seals that file with SHA-256.
Reference files provide ownership, contract rates, and the declined AFE election.

## Rebuild and verify

Run from this folder:

```bash
python3 src/build.py
python3 src/check.py
python3 src/audit.py
python3 audit/gate4.py
```

The build renders HTML through headless Google Chrome and concatenates PDFs with pypdf.
Poppler renders each page at 150 dpi.
ImageMagick adds grayscale noise, skew, clipping, and JPEG compression.
The scan PDFs contain JPEG images without text layers.
The command writes layer A, checks the corpus, and prints all 220 PDF SHA-256 lines.
It overwrites generated outputs inside this folder.

Dependencies are locally installed Python, pypdf, Pillow, Chrome, pdftoppm, and magick.
Chrome uses `tmp/chrome-profile` and disables background networking.
In this session, sandboxed Chrome aborted; approved execution outside the sandbox rendered successfully.
The build stops its own Chrome process after receiving a complete PDF.
No API key or service call is required.

`python3 src/build.py --source-only` regenerates source artifacts without rendering PDFs.
That option does not certify existing manifests or keys after source changes.

`audit/` retains rendered pages, extracted text, candidate keys, comparisons, and gate receipts.
`REPORT.md` contains the four requested gates and final status.
Existing files in `tools/` were left unchanged.
No git command or study runner was executed.

## UNVERIFIED and next action

OCR legibility, document parser extraction survival, model difficulty, and downstream runner integration remain UNVERIFIED.
Independent blind key agreement and Frank's human adjudication remain pending.
Codex visual review cannot substitute for that independent human decision.
Cross-version PDF byte reproducibility remains UNVERIFIED.

Next, give a separate blind session only the PDFs and frozen field list.
Keep `truth/`, `src/`, `traps.json`, and `planted.json` hidden from that session.
