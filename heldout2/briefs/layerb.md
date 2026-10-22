INPUTS: @make_layerb/pages/, heldout2/inputs/layerb_fields.md
OUTPUTS: truth-b/
COPY_OUT: synth-heldout2/layerB/

# Layer B keying, blind: is each field PRESENT in the extracted text?

You are keying from machine-extracted TEXT, not from images. Each file in `pages/` is the text a document-extraction service returned for one page of one document: `<doc_id>__p<N>.txt`. Read only this folder. No network. Scratch files and helper scripts go in this folder too, never in /tmp or anywhere else on disk. You have no other context and need none.

Follow `layerb_fields.md` for the field names per document type, the output shape, and the rules. Write one file per document to `truth-b/<doc_id>.json`, then `truth-b/REPORT.md` under 200 words.
