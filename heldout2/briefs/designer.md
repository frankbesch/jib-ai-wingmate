INPUTS: @critic/coverage.json, heldout2/inputs/composition.md, heldout2/inputs/run1_labels.txt
OUTPUTS: case_spec.json
COPY_OUT: synth-heldout2/design/

You are designing the cases for a synthetic document corpus. You have no other context and need none. Read only this folder. No network. Scratch files and helper scripts go in this folder too, never in /tmp or anywhere else on disk. Write only `case_spec.json` in this folder.

`coverage.json` lists case classes with quotas, set by an independent critic. `composition.md` fixes the documents. `run1_labels.txt` lists label words already used in an earlier corpus.

Write `case_spec.json`:
{"seed": <new integer>, "entities": {"operator": "...", "owner": "...", "vendors": ["...", "..."], "wells": ["...", "..."], "county": "..."},
 "documents": [{"doc_id": "<id from composition.md>", "packet": "<packet id>", "class_ids": ["<class_id>", ...] or [], "label_variant": "<the exact label text this document uses for the approval reference, or null>", "afe_number_is_printed": true|false, "placement": "<where and how it appears, one sentence>", "notes": "<anything the builder needs>"}]}

Rules:
- Every one of the 71 documents appears once. Meet or exceed every class quota and the plain-control minimum, and say in a top-level `"quota_check"` object how many documents each class received.
- Spread each class over several packets and over both ticket vendors. Use at least four different alternate label wordings across the classes that call for an unusual label, none of them in `run1_labels.txt`.
- All names are fictional and new. Approval numbers follow one house format of your choosing, except where a class calls for a changed format.
- `afe_number_is_printed` must agree with the class definitions and the field-presence rules in `composition.md`.
- A plain control belongs to no class: give it `class_ids: []` and `afe_number_is_printed: true`.
- Hauling logs and JIB statements do not carry the field; give them `class_ids: []` and `label_variant: null`.
Final message: under 150 words, the quota check.
