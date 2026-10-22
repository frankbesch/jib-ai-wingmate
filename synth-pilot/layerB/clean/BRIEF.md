# Layer B keying, blind — is each field PRESENT in the extracted text?

You are keying from machine-extracted TEXT, not from images. Each file in `pages/` is the text a document-extraction service returned for one page of one document: `<doc_id>__p<N>.txt`. The doc_id tells the document type after the prefix: afe_cover, afe, ticket (field_ticket), haul (hauling_log), invoice, jib (jib_statement). Read only this folder. No network.

For EVERY document and EVERY field listed below for its type, decide: is a value for this field present in the text of that document (any of its pages)? Key the value as it appears in the text, or `null` when no value is present. A label with no value after it is `null`. A value that appears without a label (a letterhead name, a title line) counts as present if it is clearly that field. Do not infer a value from another document. Do not correct anything.

Field names per type:
- afe_cover: letter_date, operator_name, addressee, afe_number, well_name, response_due_date, wi_decimal_stated, net_share_stated
- afe: afe_number, operator_name, well_name, api_number, county, state, afe_date, afe_type, total_estimate
- field_ticket: ticket_number, vendor_name, service_date, well_name, afe_number, total
- hauling_log: log_number, hauler_name, log_date, well_name, total_barrels
- invoice: invoice_number, vendor_name, invoice_date, afe_number, well_name, subtotal, tax, total
- jib_statement: statement_period, operator_name, property_number, well_name, owner_name, owner_number, wi_decimal, gross_total, net_total, due_date

Also key these DECOY fields for every document, which should normally be absent: afe_cover: invoice_number, log_number; afe: ticket_number, statement_period; field_ticket: invoice_number, log_number; hauling_log: invoice_number, statement_period; invoice: log_number, statement_period; jib_statement: ticket_number, log_number.

Output one file per document to `truth-b/<doc_id>.json`:
{"doc_id": "<id>", "keyed_by": "codex blind layer-B key (extracted text)", "keyed_from": "extracted text", "values": {"<field>": <value or null>, ...}, "page_of": {"<field>": <page N or null>}, "notes": []}
Put an entry in `notes` for any page whose text is empty, garbled, or unreadable, and for any value you could not decide. Then write `truth-b/REPORT.md` (under 200 words): documents keyed, fields present, fields null, notes count.
