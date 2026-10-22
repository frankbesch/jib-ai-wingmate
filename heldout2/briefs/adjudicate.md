INPUTS: @compare/disagreements.json, @render/page-images/{variant}/, heldout2/inputs/rekey_fields.md
OUTPUTS: rulings.json
COPY_OUT: synth-heldout2/adjudication/

# Disagreement ruling, cold

Two earlier keyers disagree on some values. You have no other context and need none. Read only this folder. No network. Scratch files and helper scripts go in this folder too, never in /tmp or anywhere else on disk.

`disagreements.json` lists items: document, field, page. It does not say what either keyer answered. Each item names the page image file(s) to read in `images` (under `page-images/`, one rendering only). For each item, read those images and decide the value exactly as printed, or `null` when no value is printed, under the rules in `rekey_fields.md`. If the page cannot settle it, answer "undecidable".
Some items are not field values. An item that carries a `question` and `options` asks a choice about the document or page (its class, a page's topic, or whether a packet holds a second distinct field ticket): read the page images, answer with exactly one of the listed `options` as the `value`, or "undecidable". A reprint of a ticket (same number, a REPRINT stamp or a new time) is the same one ticket. A continuation page keeps the topic of its first page. A cover letter that contains an AFE table is still a cover.
Write `rulings.json`: [{"doc_id", "field", "value": <value|null>, "status": "decided"|"undecidable", "reason": "<one line>"}]. Final message under 100 words.
