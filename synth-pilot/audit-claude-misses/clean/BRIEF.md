# Blind audit: is this field printed on this document?

You have page images of synthetic oil-and-gas paperwork in `pages/` and a list of questions in `items.json`. For each item, look at every page image listed and answer: is a value for `field` printed anywhere on that document? You have no other context and need none. Do not read anything outside this folder. No network.

Rules: a labelled field with a blank value is NOT printed. A value printed under a different label (for example "Ref" for an AFE number, "Bill To" for an operator name, a letterhead for a vendor name) IS printed if it is clearly that field. "N/A" or "TBD" printed in the field IS printed. A struck-out value IS printed. A "REPRINT" stamp does not change what is printed. A value that appears only on another document is NOT printed on this one.

Field meanings: ticket_number = the ticket's own number; afe_number = the AFE (authorization for expenditure) reference; well_name = the well; invoice_number = the invoice's own number; operator_name = the operating company; response_due_date = the date a reply is due; log_number = a hauling log number; total = the document's grand total.

Write `answers/answers.json`: a list of {"id": "<item id>", "printed": true|false, "value": "<as printed or null>", "page": <1-based page or null>, "where": "<the label or place on the page>", "confidence": "high|medium|low"}. Then `answers/REPORT.md` under 150 words: items answered, how many printed, how many not, anything unreadable.
