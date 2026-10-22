# Scorer self-test (CHECK / EXPECT, declared before the scorer ran)

Two hand-written packets. Every expected value below was computed by hand from the counts, then the scorer was run.
If the scorer disagrees, the scorer is wrong until proven otherwise (lesson: the harness is the first suspect).

| Packet | Scalars scored | Correct | Critical scored | Critical correct | Lists | Table tp/fp/fn | Split tp/fp/fn | Exact | Classify | Cite scored/present/comparable/hits | Review |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P1 | 9 | 8 (total_depth 5100 vs 5000) | 8 | 7 | 1 of 2 (profile wrong) | 2 / 1 / 1 (completion_depth 4950 vs 4900) | 2 / 1 / 1 (page 3 → other) | no | 2 of 2 | 9 / 4 / 3 / 2 (county box IoU 0.33; operator_name cited with no truth box) | yes (pages split to other) |
| P2 | 8 | 8 | 8 | 8 | 2 of 2 | 4 / 0 / 0 | 2 / 0 / 0 | yes | 2 of 2 | 8 / 2 / 2 / 2 | no |

Aggregates: all-field 16/17 = 0.9412 · critical 15/16 = 0.9375 · list 3/4 = 0.75 · table F1 = 6/7 = 0.8571 · split F1 = 4/5 = 0.8 · split exact 1/2 = 0.5 · classify 4/4 = 1.0 · citation coverage 6/17 = 0.3529 · citation precision 4/5 = 0.8 · cycle p50 = median(10, 6) = 8.0, p95 = 10.0 · cost 0.50 / 5 pages = 0.1 · review 1/2 = 0.5.

Run: `python3 score.py --selftest`
