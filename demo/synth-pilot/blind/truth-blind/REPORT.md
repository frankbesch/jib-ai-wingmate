# Blind re-key report

- Keyed 22 documents from 25 page images: 12 tickets, three hauling logs, two invoices, two covers, two AFEs, and one JIB.
- Keyed 479 scalar fields, including row cells, eight nulls, and 12 signature booleans; the records contain 179 top-level fields.
- Recorded one uncertain entry: ticket_11.service_date is printed as 2026-08-10 and struck out.
- Nothing was unreadable. Printed line arithmetic and totals reconcile; no arithmetic corrections were made.
- Validated JSON structure, document coverage, required fields, page ranges, and arithmetic using the keyed values.

Blank fields remain null, including ticket_12.total and invoice_02.total. Their printed subtotals do not fill those blanks.
The printed N/A and TBD remain strings. All customer signature lines are blank.
Reprint stamps do not create additional tickets. The 12 printed ticket numbers are distinct.
The JIB preserves its printed 0.240000 line decimal separately from the 0.200000 statement decimal.

Page references use one-based page numbers and zero-based array indexes. Null values have null page references.
Document fields identify their first printed occurrence; row cells identify their own page.
Continuation pages do not inherit header fields. Cover_02 remains an afe_cover despite its copied estimate table.

No OCR, PDF text extraction, or network was used. The required PDF skill was the sole file read outside this folder.
