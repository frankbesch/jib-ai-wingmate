# Synthetic pilot — author workspace

**BLOCKED: source artifacts exist; rendered corpus and layer A do not exist.**

Chrome repeatedly aborts with return code `-6`, including a blank-page probe.
The root cause is UNVERIFIED. This session cannot request elevated execution permissions.
No PDF-derived claim is certified by the source-only checks.

## Composition

| Component | Documents | Planned pages | Packets |
|---|---:|---:|---:|
| Field tickets | 12 | 12 | 8 shared ticket packets |
| Hauling logs | 3 | 3 | Ride in ticket packets 01, 05, 07 |
| Invoices | 2 | 2 | Ride in ticket packets 02, 08 |
| AFE covers | 2 | 2 | 2 shared AFE packets |
| AFEs | 2 | 4 | Same AFE packets |
| JIB statement | 1 | 2 | 1 JIB packet |
| Total | 22 | 25 | 11 |

Ticket packets 01–04 contain two tickets each. Packets 05–08 contain one ticket each.
Packets 01–03 have plain ticket layouts. Packet 04 has near-duplicate tickets.
Packets 05–06 carry reprints. Packets 07–08 use the permitted reprint-stamp option instead of extra pages.
The source includes three billing defects. These are extraction controls unless separately tagged in `traps.json`.

## Files and status

- `src/build.py`, `src/templates/page.html`, and 22 generated HTML documents define the corpus.
- `src/book.json` contains source values, not layer A truth.
- `src/key.py` keys rendered PDF text before opening source values for comparison.
- `src/check.py` checks the requested PDF, manifest, truth, and arithmetic gates.
- `src/audit_source.py` checks source structure only.
- `reference/` contains three reference JSON files with the authorized shapes.
- `planted.json` records the three intended billing defects.
- `traps.json` records trap locations, rules, and presence/class answers from the source design.
- `audit/` contains failure logs and source-check receipts.
- `clean/`, `scan/packets/`, and `truth/` contain no PDFs or truth keys.
- `manifest.json` is deliberately absent because no PDF hashes exist.

## Trap density

These counts describe the source design. Rendered trap execution remains UNVERIFIED.
A unit counts once even when multiple traps apply.
List-cell traps and page-specific field absences do not inflate document-level row 8.

| Row | Denominator per set | Clean mapped traps | Scan mapped traps |
|---|---:|---:|---:|
| 1 — document class | 22 | 3 (13.6%) | 7 (31.8%) |
| 4 — page topic | 25 | 6 (24.0%) | 9 (36.0%) |
| 5 — second distinct ticket | 11 | 5 (45.5%) | 5 (45.5%) |
| 8 — field presence | 191 | 75 (39.3%) | 78 (40.8%) |
| Total | 249 | 89 (35.7%) | 99 (39.8%) |

Four letter decoy traps are excluded from these counts until runner decoy selection is verified.
Those traps concern `wi_decimal` and `net_total`, versus the letter's stated share fields.
Their inclusion would produce 93/249 clean units and 103/249 scan units.
These are design counts, not evidence of model difficulty or extraction survival.

T1 targets six pages, or 24% of the planned pages.
The scan configuration uses 150 dpi grayscale, seeded noise, skew, JPEG compression, and stronger T1 degradation.
T1 adds a translucent stamp and clips paper margins. Stamp placement needs rendered inspection.
The six pages appear in `scan/README.md` and `REPORT.md`.

## Rules and keying

R1 counts a reprint with the same number as one ticket.
R2 treats labelled blank values as null.
R3 limits header-only presence to pages where the header appears.
R4 treats literal N/A and TBD as printed.
R5 treats a visible struck-out value as printed.
R6 preserves the first page's topic on continuation pages.
R7 keeps the table-bearing AFE letter classified as `afe_cover`.

The frozen schema field names are copied into `src/field_contract.json`.
Document labels vary; JSON field names do not.
The key script writes candidates from PDF extraction before reading `src/book.json`.
It then records each source disagreement in `uncertain` without replacing the candidate.
It writes document-local `page_of` locations and a separate `audit/page_presence.json`.
A labelled blank gets its label's page location. A wholly absent field gets a null location.
Signature blocks are intentionally empty and should key false after visual confirmation.

The source contains 147 REQUIRED non-boolean slots: 140 non-null and seven null.
The requested printed subtotal is 22 + 25 + 11 + 140 + 44 = 242.
The full presence task still has 249 questions because absent REQUIRED fields remain scored negatives.
Do not drop those seven questions from the eventual scorer.

## Rebuild and validation

Run from this folder in an environment where headless Chrome can launch:

```bash
python3 src/build.py
```

The build writes all HTML, renders Chrome PDFs, normalizes metadata, applies scans, and concatenates packets.
It then writes the manifest, keys layer A, compares source values, and runs the check script.
It should print 22 document hashes and 11 packet hashes for each of clean and scan.
This complete path remains UNVERIFIED because Chrome aborts before its first output.

Dependencies already found locally: Chrome, Python, pypdf, Pillow, magick, and pdftoppm.
Tesseract is also installed. No dependency installation or network request was attempted.

Source-only validation is available:

```bash
python3 src/build.py --source-only
python3 src/audit_source.py
```

After a successful render, inspect every clean and scan page at normal zoom.
Run local OCR and retain its outputs. OCR success alone does not certify field legibility.
Review all extracted candidates and `uncertain` entries before handing off PDFs for blind re-keying.
Verify PDF byte reproducibility with a second full build; only source reproducibility was checked here.

Run the requested fixture without live mode:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 ../typed/typed_questions.py --set synth-pilot --mode fixture
```

The fixture currently fails because this build has no manifest.
No runner workaround or live execution was attempted.

## UNVERIFIED

Rendered layout, page counts, PDF hashes, PDF byte reproducibility, packet concatenation, and table parsing remain UNVERIFIED.
Scan placement, normal-zoom legibility, OCR legibility, and document parser extraction survival remain UNVERIFIED.
Layer A values, blind agreement, runner integration, and model difficulty remain UNVERIFIED.
All names were invented locally. Accidental real-world name collisions were not checked because networking was prohibited.
The PDFs must not be scored or distributed as a finished corpus until these checks pass.
