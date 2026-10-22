# Truth keying, cold — held-out PDFs (blind re-key, layer A)

You are keying ground truth from PDF documents by eye. You have no other context and need none. Everything you need is in this folder. Do not look anywhere else on disk. No network.

## The files
Every `*.pdf` in `pdfs/`. The file name tells you the document type after the number prefix: `afe_cover`, `afe`, `field_ticket` (ticket), `hauling_log`, `invoice`, `jib_statement`. Some documents have two pages.

## What to do
Key every value exactly as printed. Do not correct arithmetic: if a printed total does not equal what you would compute, key what is printed and add the field to `uncertain` with one line saying why. Read a handwritten or struck-out value as written. Numbers as JSON numbers, text as printed, dates as printed.

Rules:
- R1 A reprint of a ticket (same number, "REPRINT" stamp, or a new time) is the same one ticket.
- R2 A labelled field with a blank value is not printed: key `null`.
- R3 A value printed only in a page header counts as printed on that page; on a later page only if it is repeated there. Record the page in `page_of`.
- R4 A printed "N/A" or "TBD" is printed: key the string.
- R5 A struck-out value is printed: key it and note "struck out" in `uncertain`.
- If a field is not on the page at all, key `null`.

## Output
Write one JSON object per document to `truth-blind/<doc_id>.json`, where `<doc_id>` is the file name without the number prefix and `.pdf`, in this exact shape:

```json
{"doc_id": "<id>", "source_file": "<file>", "keyed_by": "codex blind re-key (layer A, second session)",
 "keyed_from": "page images", "values": { ... }, "page_of": { "<field>": <page> }, "uncertain": []}
```

Field names for `values`:
- afe_cover: letter_date, operator_name, addressee, afe_number, well_name, response_due_date, wi_decimal_stated, net_share_stated
- afe: afe_number, operator_name, well_name, api_number, county, state, afe_date, afe_type, total_estimate, cost_lines[ line_no, account_code, description, category, amount ]
- field_ticket: ticket_number, vendor_name, service_date, well_name, afe_number, line_items[ description, quantity, unit, rate, amount ], total, customer_signature_present (true/false)
- hauling_log: log_number, hauler_name, log_date, well_name, loads[ load_no, time, fluid_type, barrels, destination ], total_barrels
- invoice: invoice_number, vendor_name, invoice_date, afe_number, well_name, line_items[ ticket_ref, description, quantity, unit, rate, amount ], subtotal, tax, total
- jib_statement: statement_period, operator_name, property_number, well_name, owner_name, owner_number, wi_decimal, gross_total, net_total, due_date, lines[ as printed: line_no, afe_ref, account_code, description, gross, owner_decimal, net ]

Also write `truth-blind/pages.json`: for every PDF, `{"<doc_id>": {"page_count": N, "class_by_eye": "<one of the six types, by what the page shows, not the file name>", "page_topics": ["<type of page 1>", ...]}}`. For a page that continues the previous page, write `"continuation"`.

When done, write `truth-blind/REPORT.md`: documents keyed, fields keyed, count of `uncertain` entries, and anything you could not read. Under 300 words.
