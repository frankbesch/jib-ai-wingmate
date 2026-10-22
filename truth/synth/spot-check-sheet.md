# Spot-check sheet — 30 fields to verify first

| # | Doc | Field | Keyed value | Page |
|---|-----|-------|-------------|------|
| 1 | jib | lines[2].owner_decimal (line 3, Stimulation and treating services) | 0.260000 | 1 |
| 2 | jib | wi_decimal (header, Working Interest) | 0.250000 | 1 |
| 3 | jib | lines[2].net_amount (line 3, tied to the 0.26 decimal) | 25074.40 | 1 |
| 4 | ticket_b | line_items[1].quantity (Fluid pumped, treated water) — handwritten | 240 | 1 |
| 5 | ticket_b | line_items[1].rate (Fluid pumped, treated water) | 4.75 | 1 |
| 6 | ticket_a | line_items[2].rate (Tool rental, packer assembly) | 425.00 | 1 |
| 7 | ticket_b | line_items[2].rate (Standby time) | 190.00 | 1 |
| 8 | afe_cover | wi_decimal_stated | 0.250000 | 1 |
| 9 | afe_cover | net_share_stated | 121700.00 | 1 |
| 10 | afe_cover | afe_number | AFE-2026-0417 | 1 |
| 11 | afe | afe_number | AFE-2026-0417 | 1 |
| 12 | afe | api_number | 42-389-41207 | 1 |
| 13 | afe | total_estimate | 486800.00 | 1 |
| 14 | afe | cost_lines[2].amount (line 3, Stimulation and treating services) | 142500.00 | 1 |
| 15 | ticket_a | ticket_number | PRW-88421 | 1 |
| 16 | ticket_a | total | 2830.00 | 1 |
| 17 | ticket_a | customer_signature_present | false | 1 |
| 18 | ticket_b | ticket_number | PRW-88437 | 1 |
| 19 | ticket_b | total | 3285.00 | 1 |
| 20 | ticket_b | customer_signature_present | false | 1 |
| 21 | hauling_log | log_number | SVT-4471 | 1 |
| 22 | hauling_log | loads[1].barrels (load 2, non-round value) | 122.5 | 1 |
| 23 | hauling_log | loads[3].barrels (load 4, non-round value) | 124.5 | 1 |
| 24 | hauling_log | total_barrels | 590 | 1 |
| 25 | invoice | invoice_number | INV-20260612-PRW | 1 |
| 26 | invoice | subtotal | 6115.00 | 1 |
| 27 | invoice | tax (non-round rate, ~8.249% of subtotal) | 504.49 | 1 |
| 28 | invoice | total | 6619.49 | 1 |
| 29 | jib | gross_total | 329570.00 | 1 |
| 30 | jib | net_total | 83356.90 | 1 |

Notes for the human reviewer:
- Row 1–3: the JIB's line 3 carries owner decimal 0.260000 against a header/every-other-line decimal of 0.250000 — the one planted oddity in the JIB, and its net amount follows the odd decimal, not the header one.
- Row 4: the only handwritten field in the whole packet (blue ink, ticket_b quantity). Everything else on that ticket is typeset.
- Rows 17 and 20: both field tickets (ticket_a, ticket_b) have blank signature lines in the clean PDFs — no signature mark visible in the rendered page image.
- Row 27: invoice tax is a non-round dollar figure implying a non-round tax rate; keyed as printed, not recomputed from subtotal.
