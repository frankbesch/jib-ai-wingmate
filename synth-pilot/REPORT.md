**Blocked: Chrome aborts before rendering; the corpus and layer A remain incomplete.**

- Created 22 HTML documents, the generator, validation scripts, references, and three planted defects.
- Source checks confirm 11 packets, 25 planned pages, and T1–T10 coverage; rendered behavior remains unverified.
- Chrome exits with signal 6; no PDFs, manifest, or truth keys were fabricated.
- [REPORT.md](synth-pilot/REPORT.md) records every gate failure and remaining check.

Next: run `python3 src/build.py` where headless Chrome can launch, then complete rendered keying and visual review.

## Counts and deliverables

| Item | Authored source | Verified rendered output |
|---|---:|---:|
| Documents | 22 | 0 |
| Packets | 11 | 0 |
| Pages per set | 25 planned | 0 |
| Billing defects | 3 | 0 PDF-confirmed |
| Layer A keys | 0 | 0 |
| PDF hash lines | 66 expected | 0 |

The source has 12 tickets, three hauling logs, two invoices, two covers, two AFEs, and one JIB.
The generator preserves the requested manifest shape and relative path convention when rendering succeeds.
It intentionally does not publish a manifest with missing or invented hashes.

Reference files and planted defects exist.
The planted-file SHA-256 is `c93084c5c6778aebaae468125d889835a9f873b630ba2a71b11c3494187f5d0b`.
The manifest seal is NOT COMPLETE because the manifest does not exist.

## Gate 1 — build

Command: `python3 src/build.py`

Result: FAIL, exit 1. Chrome subprocess exits `-6` before producing its first PDF.
The build prints zero SHA-256 lines instead of the required 66.
The Chrome version command succeeds. A separate blank-page render also returns `-6` without diagnostics.
The root cause is UNVERIFIED; a permissions or runtime failure is possible, not established.
This session's approval policy disallows elevation, so no elevated retry was attempted.

```text
Traceback (most recent call last):
  File "synth-pilot/src/build.py", line 245, in <module>
    run([CHROME,'--headless','--no-sandbox','--disable-gpu','--disable-background-networking','--disable-component-update','--disable-sync','--disable-extensions','--no-first-run','--no-default-browser-check','--disable-crash-reporter','--disable-breakpad','--metrics-recording-only','--host-resolver-rules=MAP * ~NOTFOUND','--user-data-dir='+str(ROOT/'tmp/chrome'),'--no-pdf-header-footer','--print-to-pdf='+str(raw),hp.as_uri()])
    ~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "synth-pilot/src/build.py", line 24, in run
    if cp.returncode:raise RuntimeError(f'{args[0]} failed ({cp.returncode}): {cp.stderr[-3000:]}')
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
RuntimeError: /Applications/Google Chrome.app/Contents/MacOS/Google Chrome failed (-6):
```

Blank-page probe receipt:

```json
{
  "returncode": -6,
  "stdout": "",
  "stderr": "",
  "pdf_exists": false
}
```

## Gate 2 — check script

Command: `python3 src/check.py`

Result: BLOCKED, exit 1.

```text
BLOCKED: manifest.json is absent; Chrome has not produced the corpus.
```

The implemented checks cover document and packet counts, page counts, hashes, split coverage, and concatenated page order.
They also cover required fields, list row keys, source plant locations, and all ten trap IDs.
These checks have not passed against PDFs or truth files.

Source-only check output:

```json
{
  "status": "SOURCE ONLY; not PDF gates",
  "documents": 22,
  "packets": 11,
  "planned_pages": 25,
  "classes": {
    "field_ticket": 12,
    "hauling_log": 3,
    "invoice": 2,
    "afe_cover": 2,
    "afe": 2,
    "jib_statement": 1
  },
  "source_nonnull_required_nonboolean": 140,
  "source_null_required_nonboolean": 7,
  "planned_units_all_required": 249,
  "requested_printed_subtotal": 242,
  "mapped_trap_units": {
    "clean": {
      "1": 3,
      "4": 6,
      "5": 5,
      "8": 75,
      "total_excluding_unmapped_decoy_traps": 89
    },
    "scan": {
      "1": 7,
      "4": 9,
      "5": 5,
      "8": 78,
      "total_excluding_unmapped_decoy_traps": 99
    }
  },
  "planted_sha256": "c93084c5c6778aebaae468125d889835a9f873b630ba2a71b11c3494187f5d0b"
}
```

The source implies 140 printed REQUIRED non-boolean fields and seven absent fields.
The requested arithmetic subtotal is 242 per set: 22 + 25 + 11 + 140 + 44.
The complete presence task remains 249 questions because seven absent REQUIRED fields still require answers.
The final count must be recomputed from rendered keys.

Planned trap density by row is recorded in README.md.
Mapped density is 89/249 clean units and 99/249 scan units, excluding unconfirmed decoy mappings.
These are source-design measurements, not rendered or model-performance results.

## Gate 3 — extraction and legibility

Result: NOT RUN. No clean or scan PDFs exist.
Clean-page text extraction, normal-zoom visual legibility, and OCR legibility are UNVERIFIED.
Tesseract is installed, but there are no rendered images to OCR.
No page was certified readable from HTML or source values.

T1 pages use document-local numbering:

| Document | Page | Skew |
|---|---:|---:|
| ticket_07 | 1 | +2.4 degrees |
| ticket_09 | 1 | -2.8 degrees |
| haul_02 | 1 | +3.1 degrees |
| cover_02 | 1 | -2.3 degrees |
| afe_02 | 1 | +2.6 degrees |
| jib_01 | 2 | -3.0 degrees |

The six T1 pages are 24% of the planned 25 pages.
Stamp alignment and clipped-margin safety require visual inspection before keying scan presence.
Unreadable units must be flagged for adjudication or dropped under the stated scan rule.

## Gate 4 — typed fixture

Command: `python3 ../typed/typed_questions.py --set synth-pilot --mode fixture`

Result: FAIL, exit 1. The actual error is a missing manifest, not a confirmed missing parser run.
No workaround, live run, pipeline call, network call, or credential access was attempted.
The final recorded invocation disabled Python bytecode writes.

```text
Traceback (most recent call last):
  File "synth-pilot/../typed/typed_questions.py", line 1108, in <module>
    sys.exit(main())
             ~~~~^^
  File "synth-pilot/../typed/typed_questions.py", line 887, in main
    manifest = load(manifest_path)
  File "synth-pilot/../typed/typed_questions.py", line 81, in load
    return json.loads(pathlib.Path(p).read_text())
                      ~~~~~~~~~~~~~~~~~~~~~~~~~^^
  File "/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/pathlib/__init__.py", line 787, in read_text
    with self.open(mode='r', encoding=encoding, errors=errors, newline=newline) as f:
         ~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/pathlib/__init__.py", line 771, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: 'synth-pilot/manifest.json'
```

## Layer A and reproducibility

`src/key.py` refuses to create keys without rendered PDFs.
Its candidate phase reads PDF text, field contracts, and manifest metadata only.
It opens source values only after writing all candidate keys.
Every discrepancy goes into `uncertain`; source values never overwrite candidates.
The parser and visual claims remain UNVERIFIED until actual rendering succeeds.

`python3 src/key.py` currently reports:

```text
BLOCKED: manifest.json is absent; build rendered PDFs before keying layer A.
```

Repeated source generation produced identical source bytes in the recorded check.
PDF byte reproducibility remains UNVERIFIED.
The author session is not blind. A separate PDF-only re-key is still required.

## Scope and access receipt

No prohibited existing corpus source, clean PDF, or scan PDF was opened.
One existing truth file was parsed solely to emit its structural shape; its values were not displayed or used.
The initial reads exceeded the requested spec-section scope and read the first 260 lines of reconcile.py.
That was an access-scope error; subsequent field extraction used only REQUIRED and LISTS.
The extra spec sections did not provide existing corpus document values or truth keys.

All authored paths remain within synth-pilot. No git command was run.
No dependency was downloaded. No API key was inspected or configured.

The current brief overrides the PDF skill's reportlab instruction at SKILL.md:28 and output directory instruction at SKILL.md:83.
The applicable skill path is the local Codex PDF skill (`pdf/SKILL.md`).
The implementation uses Chrome and the requested clean/scan directories.
The brief's ruled R1–R7 supersede the spec's older UNRULED status.

## Open questions and next action

1. Why does this Chrome binary abort in this execution environment?
2. Does a successful render preserve the planned 25-page layout and all table cells?
3. Are all scan fields readable at normal zoom, including stamped values?
4. Which two decoys will the runner select for each document?
5. Does a second complete build reproduce every PDF byte?

No scientific or scoring gate has passed.
Next: restore headless Chrome execution, run the full build, inspect every page, and finish layer A before blind re-keying.
