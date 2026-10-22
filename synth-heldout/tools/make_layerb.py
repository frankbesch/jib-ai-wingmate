#!/usr/bin/env python3
"""Build one layer-B keying set from a recorded Pulse run. Read-only toward the run and the corpus.

Writes <out>/pages/<doc_id>__p<N>.txt (N = page within the document, 1-based) from the Pulse extract, split
with typed_questions.pages_from_extract (the same text the arms read, before the MAX_PAGE_CHARS cut),
<out>/BRIEF.md (the pilot's layer-B brief, verbatim), and <out>/truth-a.sha256 over <corpus>/truth/ with the
freeze_hashes recipe, label relative to <corpus>/layerB (so the label is `../truth`, as in the pilot).

Usage: make_layerb.py --run runs/<pulse run id> --corpus <corpus dir> --out <layerB set dir>
"""
import argparse, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
DEMO = HERE.parent.parent
sys.path.insert(0, str(DEMO / 'typed')); sys.path.insert(0, str(DEMO)); sys.path.insert(0, str(HERE))
import typed_questions as tq  # noqa: E402
from freeze_hashes import dir_hash  # noqa: E402

BRIEF = DEMO / 'synth-pilot' / 'layerB' / 'clean' / 'BRIEF.md'   # clean and scan briefs are identical


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--run', required=True)
    ap.add_argument('--corpus', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    run, corpus, out = pathlib.Path(a.run), pathlib.Path(a.corpus), pathlib.Path(a.out)
    manifest = json.loads((corpus / 'manifest.json').read_text())
    packets = {p['packet_id']: p for p in manifest['packets']}
    pages_dir = out / 'pages'
    if pages_dir.exists() and any(pages_dir.iterdir()):
        raise SystemExit(f'{pages_dir} is not empty; refusing to overwrite')
    text = {}
    for pid, pk in packets.items():
        text[pid] = tq.pages_from_extract(json.loads((run / 'raw' / f'{pid}__extract.json').read_text()))
        if len(text[pid]) != pk['pages']:
            raise SystemExit(f'{pid}: extract has {len(text[pid])} pages, manifest says {pk["pages"]}')
    pages_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for d in manifest['documents']:
        for i, p in enumerate(d['pages'], 1):
            (pages_dir / f"{d['doc_id']}__p{i}.txt").write_text(text[d['packet']][p])
            n += 1
    (out / 'BRIEF.md').write_bytes(BRIEF.read_bytes())
    h, label = dir_hash(corpus / 'truth', corpus / 'layerB')
    (out / 'truth-a.sha256').write_text(h + '\n')
    print(f'{len(manifest["documents"])} documents, {n} pages -> {pages_dir}')
    print(f'truth-a {h}  (label {label})')


if __name__ == '__main__':
    main()
