# Blind re-key report

Keyed 71 documents from 80 page images: 45 field tickets, nine hauling logs, four invoices, four covers, four AFEs, and five JIB statements.

Keyed 1,588 scalar fields, including line-item cells, signature booleans, and 17 null values. This count excludes metadata and array containers.

Recorded 13 uncertain entries. Twelve tickets print conflicting well names: the Asset field says “Tressaline 9-VH”; the worksite note says “Tressaline 9V-H”. Values retain the Asset field; uncertain entries preserve the alternative. Ticket 44 retains the struck-out service date, 2026-09-29.

Nothing was unreadable. Blank fields remain null. Printed N/A and TBD remain strings. Blank ticket totals remain null despite printed subtotals. Reprint stamps do not create additional tickets.

Page references use one-based pages and zero-based array indices. Each non-null scalar has a page reference. Null fields have no page reference. Shared document fields reference their first printed occurrence; continuation rows reference page two. No header values were inferred onto continuation pages.

All printed totals equal their applicable line sums. JIB 01 retains the printed 0.24 line decimal and 1,872 net total; its header decimal is 0.20.

Validation confirmed all 71 document JSON files, required outer keys, page counts, scalar page references, and applicable arithmetic. All source reads stayed inside this folder. No network or PDF text extraction was used.
