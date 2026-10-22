INPUTS: @render/clean/, @render/page-images/clean/, heldout2/inputs/rekey_fields.md
OUTPUTS: truth-blind/
COPY_OUT: synth-heldout2/blind/

# Truth keying, cold (blind re-key, layer A)

You are keying ground truth from documents by eye. You have no other context and need none. Everything you need is in this folder. Do not look anywhere else on disk. No network. Scratch files and helper scripts go in this folder too, never in /tmp.

Key every value exactly as printed, from the page images under `page-images/` (the PDFs under `clean/` are the same pages). Do not correct arithmetic. Follow `rekey_fields.md` for the field names per document type, the output shape, and the rules. Write one JSON file per document to `truth-blind/<doc_id>.json`, then `truth-blind/REPORT.md` under 150 words: documents keyed, values keyed, nulls, uncertain count.
