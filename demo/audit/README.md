# audit/ — the pack a JV accountant hands to an auditor

`pack.py` turns one month record plus its exceptions and the decision log into a single
FEDS-styled PDF. Everything it reads is synthetic, and every page says so.

```
python3 audit/pack.py --run runs/fixture-synth-01
python3 audit/pack.py --run runs/fixture-synth-01 \
        --out runs/fixture-synth-01/audit-pack.pdf \
        --decisions audit/decisions.jsonl
```

Run `python3 reconcile.py --run runs/<id>` first; the pack refuses to build without
`exceptions.json`.

## What it reads

| input | owner | used for |
| --- | --- | --- |
| `runs/<id>/month.json` | pipeline | property, owner, period, credits, cost, extracted values, citations |
| `runs/<id>/exceptions.json` | `reconcile.py` | the exception list, routes, and clean-line count |
| `runs/<id>/scorecard.json` | `score_synth.py` | the go/no-go block on the cover, when present |
| `audit/decisions.jsonl` | a human in the queue | the decision and approver on each exception |
| `synth/caprock/packets/*.pdf` | corpus builder | the page images the citation crops come from |

Nothing in `runs/` or `synth/` is edited. The pack writes only `runs/<id>/audit-pack.html`,
`audit-pack.pdf`, `audit-pack-page-*.png`, `audit-pack.json`, and the crops under
`runs/<id>/audit-thumbs/`.

## What it writes

`runs/<id>/audit-pack.json` for the console:

```json
{ "pdf": "...", "pages": 6, "exceptions": 4, "decided": 0, "open": 4, "thumbnails": 14,
  "receipt": { "clean": true, "exit_code": 0, "flags": [], "text": "..." },
  "run_id": "fixture-synth-01", "html": "...", "synthetic": true }
```

## Page order

1. **Cover** — property, well, owner, period, run id, mode, a synthetic banner that reads
   "Synthetic documents; SYNTHETIC fixture responses" in fixture mode and
   "Synthetic documents; live document parser responses" otherwise, the go/no-go table, and packets with
   credits and list cost.
2. **Exceptions** — one row per exception: id, rule, document and field path, page, observed,
   expected, delta, route, and the decision. Then what each control checked and where each open
   exception goes. Ten exceptions fit a page; more paginate.
3. **Citations** — one crop per JIB line and per field-ticket line, five to a page, captioned
   `p<page> · <field_path> · <cited text>`. The crop is the packet page at the cited box, padded
   6 percent, scaled so the strip fills its frame.
4. **Approver trail** — every decision row for this run verbatim, the standing of each exception,
   what a decision row records, and the two honesty lines.

## Rules the pack keeps

- **A blank approver is not a signature.** A decision row whose `approver` is empty prints
  verbatim in the trail, marked "blank, unsigned", and the exception still counts as open. The
  pack never writes a decision row and never supplies a name.
- **A cited box over blank paper is reported, not hidden.** When the crop at the cited box
  catches no ink, the pack prints the cited text in a marked panel that says the value cannot be
  traced to the paper, and the page footer counts how many boxes on that page failed. This fires
  on `fixture-synth-01`: the fixture's citation geometry for JIB lines 2 to 8 and for several
  ticket lines points at blank regions, and lines 4 to 8 are cited to packet page 2 while the
  statement prints them on page 1. That is a fixture-geometry defect, not a pack defect; the pack
  reports it rather than papering over it.
- **The reconciliation is customer code.** The last page says so, next to the line that every
  number in the pack is synthetic.
- **The render is the ground truth.** The pack renders through
  the script named by `AUDIT_RENDER_SH` (an HTML-to-PDF renderer, not shipped), prints the receipt, stores it in
  `audit-pack.json`, and exits non-zero when the receipt flags a page.

## Layout knobs

`THUMBS_PER_PAGE` (5; the contract allows up to 8), `EXC_PER_PAGE` (8), `TAIL_INLINE_MAX` (4 —
above that many rows on the last exception page, the control summary moves to its own page),
`PAD` (0.06 citation padding), `DPI` (110, matching the receipt's rasterizer). Frame height is
derived per page from the number of crops so a page fills without a void; the crop is expanded
around the same centre to that frame's aspect and never cut inside the cited box.
