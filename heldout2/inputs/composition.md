# Corpus composition (fixed)

One synthetic month of joint-interest billing paperwork that an operator sends to a non-operating owner.
39 packets, 71 documents, 80 pages per set. Two sets: clean (text PDFs) and scan (image-only PDFs of the same pages).

| Class | Documents | Pages | Packets |
|---|---:|---:|---|
| field_ticket | 45 | 45 | 30 ticket packets: 15 with two tickets, 15 with one |
| hauling_log | 9 | 9 | riders in ticket packets |
| invoice | 4 | 4 | riders in ticket packets |
| afe_cover | 4 | 4 | one cover per AFE packet |
| afe | 4 | 8 | 4 AFE packets, two pages per AFE |
| jib_statement | 5 | 10 | 5 JIB packets, two pages each |

Document ids: ticket_01 to ticket_45, haul_01 to haul_09, invoice_01 to invoice_04, cover_01 to cover_04, afe_01 to afe_04, jib_01 to jib_05.
The field `afe_number` (an approval reference: the number of the Authorization for Expenditure that a cost belongs to) is a scored field on afe_cover, afe, field_ticket, and invoice documents.
A reader is asked, for each document: "Is a value for the field afe_number printed in this document?" The answer is yes or no.

Field-presence rules (ruled by the study owner):
- A wrong approval number is still printed. The question asks whether a value is printed, not whether it is right.
- An approval number in body text counts as printed.
- A reference that is not an approval number (a purchase order, a job number) does not make afe_number printed.
- A labelled field with a blank value is not printed. A printed "N/A" or "TBD" is printed. A struck-out value is printed.
