from pathlib import Path
import json,re
root=Path(__file__).resolve().parents[1]
def read(p):return (root/p).read_text()
m=json.loads(read('manifest.json'));design=json.loads(read('audit/design.json'))
brief=read('BRIEF-S3.1.md');gate_lines=[line for line in brief.splitlines() if re.match(r'^[1-4]\. ',line)]
assert len(gate_lines)==4
final='''**Completed the corpus and wrote [REPORT.md](synth-heldout/REPORT.md) with gates 1–4 pasted.**

- Each set contains 71 documents, 39 packets, and 80 pages; all 220 PDF hashes pass.
- All 71 PDF-derived keys pass field and list checks, with zero source differences.
- All scan pages passed Codex visual review; OCR legibility and independent human confirmation remain UNVERIFIED.
- Pilot-name checks pass, and nothing was committed.

Next: run the separate blind re-key using only PDFs and the frozen field list.
'''
report='''**The corpus is built, keyed, and checked; independent blind keying and human confirmation remain pending.**

## Counts and outcome

| Deliverable | Count or result |
|---|---:|
| Documents per set | 71 |
| Packets per set | 39 |
| Unique pages per set | 80 |
| Final clean PDFs | 110 |
| Final scan PDFs | 110 |
| Layer A truth files | 71 |
| Printed required non-boolean fields | 452 |
| Null required non-boolean fields | 13 |
| Decoys per set | 142 |
| Requested printed subtotal per set | 784 |
| Complete scored units per set | 797 |
| Billing plants | 3 |
| T1 scan pages | 20 |
| Source/key differences | 0 |

The 71 documents comprise 45 tickets, nine hauling logs, four invoices, four covers, four AFEs, and five JIB statements.
The 30 ticket packets contain 15 pairs and 15 singles.
Twelve carry T4/T5, with six pairs and six singles.
The remaining 18 lack ticket-count traps; some still carry field-label traps.
Four AFE packets and five JIB packets provide nine easy row-5 negatives.

Clean trap density is 288/797 (36.1%).
Scan trap density is 316/797 (39.6%).
Eight possible cover decoy traps remain excluded because downstream decoy selection is UNVERIFIED.
Every trap T1–T10 appears at least three times.
`README.md` contains composition, per-row density, rules, dependencies, and rebuild instructions.

## Gate 1 — build and all PDF hashes

'''+gate_lines[0]+'''

**PASS.** The command exited 0 after rendering, concatenation, keying, and checks.
Chrome aborted inside the sandbox; approved offline execution outside it succeeded.
The build keeps its profile inside this folder and disables background networking.

```text
'''+read('audit/gate1-summary.log')+'''```

Full command output, including all 220 SHA-256 lines:

```text
'''+read('audit/gate1.log')+'''```

## Gate 2 — structure, truth, and arithmetic

'''+gate_lines[1]+'''

**PASS.** The checker also verifies packet content order and the absence of scan text layers.
It verifies exactly 71 document PDFs and 39 packet PDFs in each set.
It verifies the sealed plant hash and each planted value in PDF-derived truth.

```text
$ python3 src/check.py
'''+read('audit/gate2.log')+'''exit=0
```

The requested subtotal omits 13 absent required fields.
Those fields remain scored negative answers, so the complete task totals 797 units per set.
The 142 decoys are the specified two-per-document allocation; the runner was not executed.

## Gate 3 — extraction and visual legibility

'''+gate_lines[2]+'''

**PASS for clean extraction and Codex visual review; OCR and independent human confirmation remain UNVERIFIED.**

I inspected all 80 scan pages, including every T1 page, at 850×1100 pixels per Letter page.
This corresponds to 100 pixels per inch.
The inspected images exactly match the JPEG pixels embedded in the scan PDFs.
Packet checks confirm that concatenation preserves those pixels and their order.
All scored text remained readable; no unreadable units were identified.
Clipped paper margins do not remove scored values.
Blank signature blocks, null cells, N/A, TBD, and struck dates retain their intended distinctions.

`audit/visual-review.json` binds each review result to the inspected image's SHA-256.
`audit/review/` contains the two-page visual review sheets.
This author review does not replace the required independent human normal-zoom decision.

```text
$ python3 audit/gate3.py
'''+read('audit/gate3.log')+'''exit=0
```

The stamp coordinates account for page-local position after skew.
All 20 T1 pages contain a stamp overlapping a printed value.
The scan pass retains the authorized noise, skew, opacity, compression, and margin-clipping settings.
No model result informed those settings.

## Gate 4 — pilot proper-noun exclusion

'''+gate_lines[3]+'''

**PASS.** Each grep returned no output and exit 1, the expected no-match result.
The pilot story omits vendor names, so the authorized generator supplied those two names.
The check also includes the disposal-location name and distinctive name roots.

```text
$ python3 audit/gate4.py
'''+read('audit/gate4.log')+'''exit=0
```

## Reproducibility and keying evidence

```text
$ python3 audit/repro_stamp.py
'''+read('audit/reproducibility.log')+'''exit=0
```

The final continuation-page stamp correction changed only its scan document and scan packet.
A separate repeat reproduced those two files byte-for-byte.
The other 218 PDF hashes matched the preceding complete build.
Cross-version byte identity remains UNVERIFIED.

The six frozen schemas exactly match `src/field_contract.json`.
The keyer writes rendered-PDF candidates before opening source values for comparison.
All 71 truth files identify `codex (author key, layer A)` and `rendered PDF`.
Every required field and every list row retains a document-local page location.
The source comparison contains zero differences, and every `uncertain` list is empty.

R3 has one explicit narrative repetition: AFE 02 repeats its AFE number in the declined-election note on page 2.
The page-presence key counts that occurrence as printed.
Its T6 metadata excludes that repeated field.
Other missing page headers remain absent on their continuation pages.

Plant seal: `'''+m['planted_sha256']+'''`.
The corpus uses September 2026, seed 931047, and new fictional names.
The final corpus contains no pilot document or pilot document reference.
Gate 4 records pilot names only as exclusion-test evidence.

No API key was read or set.
No service API, study runner, forbidden source directory, or git operation was used.
Existing files in `tools/` remain unchanged.
All authored deliverables and audit records remain inside this folder.

## Open questions and UNVERIFIED items

No unresolved question blocks the requested local build.
Independent blind layer A agreement and Frank's human adjudication remain pending.
OCR legibility, Pulse extraction survival, downstream integration, and measured model difficulty remain UNVERIFIED.
The clean density is 36.1%, below the approximate 40% target; scan density is 39.6%.
The unchanged layouts and limited class counts do not establish generalization beyond this synthetic corpus.

Next, provide only the PDFs and frozen field list to the separate blind keying session.
Hide the source, author truth, traps, and plants from that session.

## Final message

'''+final
(root/'REPORT.md').write_text(report)
(root/'audit/final-message.md').write_text(final)
print('REPORT.md written with four verbatim gate requirements, complete command receipts, all hashes, and final message.')
