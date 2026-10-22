# synth-heldout tools (session 3, full held-out run)

Four read-only-toward-sources tools that replace the pilot's ad-hoc commands. Run every command from the repo root. Each tool reproduces the pilot's committed outputs when pointed at `synth-pilot/` (CHECK output below). None of them calls the document parser, Jev, or Claude.

**`make_layerb.py`** builds one layer-B keying set from a recorded parser run. It writes `pages/<doc_id>__p<N>.txt` from `raw/<packet>__extract.json`, split with `typed_questions.pages_from_extract`. That is the same text the arms read, before the 12000-character cut. N is the page within the document. It copies the pilot's layer-B `BRIEF.md` verbatim and writes `truth-a.sha256` over `<corpus>/truth/`. It refuses to write into a non-empty `pages/`.
`python3 synth-heldout/tools/make_layerb.py --run runs/<parser run id> --corpus synth-heldout --out synth-heldout/layerB/clean`

**`freeze_hashes.py`** freezes a truth dir as one sha256. Recipe, reproduced from the pilot's committed values: run from the layer-B root (`<corpus>/layerB`), `shasum -a 256 <label>/*.json | shasum -a 256`. Only `*.json` files are hashed, sorted by name; `REPORT.md` is excluded. The label is the dir relative to the layer-B root: `../truth` for layer A, `<set>/truth-b` for layer B. The default root is the dir's grandparent; `--root` overrides it. The tool prints one hash per `--dir`; `--out` writes a file (one dir) or `<dir name>.sha256` into an existing dir.
`python3 synth-heldout/tools/freeze_hashes.py --dir synth-heldout/layerB/clean/truth-b --out synth-heldout/layerB/clean/truth-b.sha256`

**`make_audit.py`** builds a blind audit set: `items.json`, `pages/`, `BRIEF.md`. By default it selects every discordant unit across the selected arm runs (`--arms`, default `A,B,C`), where discordant means correct in one arm run and not correct in another. Parser-dropped units are skipped. `--misses-only` reproduces the pilot: the union over the A repeats of row-8 units that are not correct. Row-8 items keep the pilot shape. Row 1/4/5 items add `node`, `question` (the arms' question text) and `options` (without `needs_review`). Pages are byte-identical to the pilot's. Clean pages come from `pdftoppm -r 150 -png` on the document PDF, as `<doc>-p<N>.png`. Scan pages come from `pdfimages -j` on the scan PDF, which extracts the embedded 150 dpi JPEG, as `<doc>-p<N>.jpg`. Rows 4/5 use the packet PDF, as `packet_<packet>-p<N>`. `BRIEF.md` is the pilot audit brief for the run's variant, verbatim. An addendum for question items is appended only when row 1/4/5 items exist.
`python3 synth-heldout/tools/make_audit.py --run runs/<id> --corpus synth-heldout --out synth-heldout/audit/clean`

**`score_heldout.py`** generalises `synth-pilot/score_pilot.py`. It prints per-arm-run rows with the same fields and arithmetic. It compares A r1 against each B repeat and prints the discordant units, with count and `by_field` per repeat, min, max, mean, and the union. It then prints H1 (every B repeat has at least 10 discordant units on more than one field name). H2, H3, and H4 are read per C repeat against the mean of the A repeats: wrong <= mean + 5, person-reviews <= mean + 10, Claude calls <= 50% of the mean. It also prints `pulse_dropped` and `extract_invented` from report.json. Each verdict reads `SUPPORTED` or `NOT SUPPORTED`. A set holds Hn only if every C repeat present holds; the output names how many repeats were present (2 planned). With two `--run`, `overall` is SUPPORTED only if H2, H3, and H4 hold in every C repeat on both sets. `--audit answers.json --changed N` (one pair per `--run`) adds the audit counts and the changed-truth count. The tool exits 0 whatever the verdicts.
`python3 synth-heldout/tools/score_heldout.py --run runs/<clean id> --run runs/<scan id> [--audit a-clean.json --changed N --audit a-scan.json --changed M]`

## CHECK output (2026-09-30, against synth-pilot)

C1 (pages diff empty; truth-a and BRIEF byte-identical):
```
22 documents, 25 pages -> /tmp/lb-clean/pages
truth-a 75e076805ae9f2cb07723398ac2426bd5e72635ce1d2c44e359af698b0900aa3  (label ../truth)
pages diff clean: empty (rc=0)
truth-a clean identical
brief clean identical
22 documents, 25 pages -> /tmp/lb-scan/pages
truth-a 75e076805ae9f2cb07723398ac2426bd5e72635ce1d2c44e359af698b0900aa3  (label ../truth)
pages diff scan: empty (rc=0)
truth-a scan identical
brief scan identical
```
C2 (tool output, then the committed file):
```
synth-pilot/layerB/clean/truth-b: label clean/truth-b
32e66a123b731a1508451f36ea0a19d213322900a2b72fedf84355c04f2a84f2
32e66a123b731a1508451f36ea0a19d213322900a2b72fedf84355c04f2a84f2
synth-pilot/layerB/scan/truth-b: label scan/truth-b
07c7c70b58f91e7e0771f94568e7e4fd4ac20ebc8757dc65e188e26e2c29a62c
07c7c70b58f91e7e0771f94568e7e4fd4ac20ebc8757dc65e188e26e2c29a62c
```
C3 (`--misses-only`; items equal the pilot's including order; pages byte-identical):
```
misses-only (A row 8 not correct) over ['redo-claude-20260930T212307Z-r1', 'redo-claude-20260930T212307Z-r2']
17 items {'row8': 17}, 10 page images (clean) -> /tmp/au-clean
clean ids equal as sets: True 17 17 | items equal incl pages and order: True
pages byte-identical clean
brief identical clean
misses-only (A row 8 not correct) over ['redo-claude-20260930T215656Z-r1', 'redo-claude-20260930T215656Z-r2']
17 items {'row8': 17}, 10 page images (scan) -> /tmp/au-scan
scan ids equal as sets: True 17 17 | items equal incl pages and order: True
pages byte-identical scan
brief identical scan
```
C4 (exit=0; per-arm rows equal `pilot-gates.json` arm rows; discordant 29 / 31; excerpt):
```
clean arm rows equal pilot-gates.json: True | union by_field equals pilot by_field: True
scan arm rows equal pilot-gates.json: True | union by_field equals pilot by_field: True
clean H2 wrong-not-abstained 11 vs A mean 10 + 5 = 15 SUPPORTED; H3 2 vs 15.5 SUPPORTED; H4 53 vs 124.5 SUPPORTED
scan  H2 wrong-not-abstained 17 vs A mean 11.5 + 5 = 16.5 NOT SUPPORTED; H3 3 vs 13.5 SUPPORTED; H4 50 vs 124.5 SUPPORTED
note: rule reads over the 1 C repeat(s) present (planned 2)
overall: {"rule": "goal SUPPORTED only if H2, H3, H4 hold in every C repeat on every set", ..., "verdict": "NOT SUPPORTED"}
```
C5: `pyflakes` is not installed; `python3 -m py_compile synth-heldout/tools/*.py` exit 0.

Not verified against a committed output: the default discordant mode of `make_audit.py` (no pilot counterpart). It runs on the pilot: clean 35 items (row8 32, row1 1, row5 2), scan 36 (row8 34, row1 1, row5 1). The row-4 path has not run, because no pilot row-4 unit is discordant.
