INPUTS: heldout2/inputs/composition.md, schemas/field_ticket.json, schemas/invoice.json, schemas/afe.json, schemas/afe_cover.json
OUTPUTS: coverage.json
COPY_OUT: synth-heldout2/design/

You are an independent test designer for a document-reading study. You have no other context and need none. Read only this folder. No network. Scratch files and helper scripts go in this folder too, never in /tmp or anywhere else on disk. Write only `coverage.json` in this folder.

Read `composition.md` and the schema files. A machine reader will be asked, per document, whether a value for `afe_number` is printed. Separately, an automated checker will review the reader's "not printed" answers and raise a flag when it believes the answer is wrong. You are not told how the reader or the checker works, and you must not guess at one mechanism and design only for it.

Your job: decide which document variations a fair test must contain so that (1) a reader that wrongly answers "not printed" is exposed, and (2) a checker that flags correct answers, or misses wrong ones, is exposed. Think about how real operators and vendors vary their paperwork: labels, formats, placement, missing or conflicting references, other reference numbers, documents that support or fail to support one another, and reading damage on scanned pages.

Write `coverage.json`:
{"classes": [{"class_id": "<short id>", "description": "<one or two sentences, concrete enough for someone else to build>", "afe_number_is_printed": true|false, "min_documents": <integer>, "why": "<one sentence>"}], "plain_controls_min": <integer>, "notes": ["..."]}

Rules:
- Between 6 and 12 classes. Include classes where the approval number is printed and classes where it is not.
- Set every quota yourself. Quotas must fit the composition: only 57 documents carry the field (45 tickets, 4 invoices, 4 covers, 4 AFEs), and a document may belong to more than one class only if you say so in `notes`.
- Keep a share of plain documents with an ordinary label and an ordinary number (`plain_controls_min`). Plain controls sit outside every class: do not define a class for them, and count them in addition to the class quotas.
- Classes must respect the field-presence rules in `composition.md`.
- Do not write document text. Do not name specific label words; a later session chooses the wording.
Final message: under 150 words, the class ids and quotas.
