#!/usr/bin/env python3
"""Build the two blind audit sets of held-out run 2 for one Pulse run (one set). Adapted from
synth-heldout/tools/make_audit.py. Read-only toward the run and the corpus; writes only under the two --out folders
and the --record file. No model call, no network.

Primary set (plan section 6, "Audit"): every unit that any A, B, or base C run missed (status against layer A is
wrong, abstain, or error), plus a random AUDIT_LUCKY units that all of those runs got right (random.Random(AUDIT_SEED),
sampled from the sorted list). Secondary set, separate folder: units that only an alias or batched run missed (missed
by a C-alias, B-alias, A-alias, or A-batched run and by no A, B, or base C run). Arm discovery and layer-A labels come
from score_heldout2 (out-dir tags, unit `label_a`).

Blinding: items are shuffled with the same seeded generator, and page images get opaque names (page-0001...) in
shuffled order, so neither the item order nor the folder listing shows which items were misses. Which item came
from which list is written only to --record, outside both audit folders. BRIEF.md holds the field definitions the
arms received (typed_questions.field_descriptions in the runs' field_desc mode, per document class) and the three
field-presence semantics of plan section 3, with no worked example and no answers.

Pages: clean = `pdftoppm -r 150 -png` of the document PDF (manifest `file`); scan = `pdfimages -j` of the scan PDF
(manifest `scan_file`). Rows 4 and 5 use the packet PDF.

Usage: make_audit2.py --run runs/<id> --corpus <corpus dir> --out <primary dir> --out-secondary <dir> --record <json>
"""
import argparse, json, os, pathlib, random, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
DEMO = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(DEMO / 'typed')); sys.path.insert(0, str(DEMO))
import score_heldout2 as sc  # noqa: E402

AUDIT_SEED = 20261002
AUDIT_LUCKY = 40
PRIMARY_ARMS, SECONDARY_ARMS = ('A', 'B', 'C'), ('A-batched', 'C-alias', 'B-alias', 'A-alias')
QUESTIONS = {'row1': 'Which document class is this document?', 'row4': 'Which topic does this page belong to?',
             'row5': 'Does this packet contain a second field ticket?'}
SEMANTICS = """- A wrong approval number is still printed. The question asks whether a value is printed, not whether it is right.
- An approval number in body text counts as printed.
- A reference that is not an approval number (a purchase order, a job number) does not make `afe_number` printed."""


def render(pdf, page, target_stem, variant):
    """One page of pdf -> target_stem.png (clean) or .jpg (scan). Returns the file name."""
    pdf = str(DEMO / pdf)
    if variant == 'clean':
        subprocess.run(['pdftoppm', '-r', '150', '-png', '-f', str(page), '-l', str(page), '-singlefile', pdf, str(target_stem)], check=True)
        return target_stem.name + '.png'
    subprocess.run(['pdfimages', '-j', '-f', str(page), '-l', str(page), pdf, str(target_stem)], check=True)
    made = sorted(target_stem.parent.glob(target_stem.name + '-*'))
    if [m.name for m in made] != [target_stem.name + '-000.jpg']:
        raise SystemExit(f'{pdf} page {page}: expected one embedded JPEG, got {[m.name for m in made]}')
    os.rename(made[0], str(target_stem) + '.jpg')
    return target_stem.name + '.jpg'


def select(arms):
    """(primary misses, lucky pool, secondary-only misses) as sets of (node, subject), against layer A."""
    label = {}
    for runs in arms.values():
        for r in runs:
            for k, u in r['units'].items():
                if u['la'] is not None:
                    label.setdefault(k, u['la'])

    def missed(names):
        out = set()
        for a in names:
            for r in arms.get(a, []):
                out |= {k for k, u in r['units'].items() if k in label and sc.status(u, k, label, set()) != 'correct'}
        return out
    prim = [r for a in PRIMARY_ARMS for r in arms.get(a, [])]
    pm = missed(PRIMARY_ARMS)
    right = {k for k in label if prim and all(k in r['units'] and sc.status(r['units'][k], k, label, set()) == 'correct'
                                               for r in prim)}
    return pm, right, missed(SECONDARY_ARMS) - pm, [r['name'] for r in prim]


def definitions(mode, docs, keys):
    """{(node, subject): definition} for row-8 keys, as the arms received them (None when field_desc is 'none')."""
    if mode in (None, 'none'):
        return {}
    import typed_questions as tq
    desc = tq.field_descriptions(mode)
    out = {}
    for node, subject in keys:
        if node == 'row8':
            doc, field = subject.split('.', 1)
            out[(node, subject)] = tq.describe(docs[doc]['class'], [field], desc)[field]
    return out


def build(keys, out, variant, docs, packets, defs, opts):
    """Write items.json, opaque page images, and BRIEF.md under out. Returns (items, {item id: unit}, page count)."""
    fkey = 'file' if variant == 'clean' else 'scan_file'
    rng = random.Random(AUDIT_SEED)
    order = sorted(keys)
    rng.shuffle(order)
    needed = []                                   # (pdf, page) in first-use order of the shuffled items

    def pages_of(node, subject):
        if node in ('row8', 'row1'):
            d = docs[subject.split('.', 1)[0]]
            return [(d[fkey], i) for i in range(1, d['page_count'] + 1)]
        if node == 'row4':
            pid, p = subject.split(':p')
            return [(packets[pid][fkey], int(p))]
        return [(packets[subject][fkey], i) for i in range(1, packets[subject]['pages'] + 1)]
    for k in order:
        needed += [pp for pp in pages_of(*k) if pp not in needed]
    slots = list(range(1, len(needed) + 1))
    rng.shuffle(slots)
    (out / 'pages').mkdir(parents=True, exist_ok=True)
    name = {pp: 'pages/' + render(pp[0], pp[1], out / 'pages' / f'page-{slots[i]:04d}', variant) for i, pp in enumerate(needed)}
    items = []
    for n, (node, subject) in enumerate(order, 1):
        it = dict(id=f'item-{n:03d}', pages=[name[pp] for pp in pages_of(node, subject)])
        if node == 'row8':
            doc, field = subject.split('.', 1)
            it.update(document=doc, field=field)
            if (node, subject) in defs:
                it['definition'] = defs[(node, subject)]
        else:
            it.update(node=node, question=QUESTIONS[node], options=opts.get(node))
        items.append(it)
    (out / 'items.json').write_text(json.dumps(items, indent=2) + '\n')
    (out / 'BRIEF.md').write_text(brief(items))
    return items, {it['id']: f'{k[0]}:{k[1]}' for it, k in zip(items, order)}, len(needed)


def brief(items):
    fields = {}
    for it in items:
        if 'field' in it:
            fields.setdefault(it['field'], set()).add(it.get('definition'))
    lines = []
    for f in sorted(fields):
        ds = sorted(d for d in fields[f] if d)
        lines.append(f'- `{f}`: ' + (' / '.join(ds) if ds else '(no definition was given to the arms)'))
    q = any('node' in it for it in items)
    return f"""# Blind audit: what is printed on these pages?

`items.json` lists questions; `pages/` holds the page images each item names. For each item, look at every page image it lists. Do not read anything outside this folder. No network.

For an item with `document` and `field`: answer whether a value for `field` is printed anywhere on that document's pages.

Field-presence rules:
{SEMANTICS}

Field definitions (each item also carries the `definition` the answering systems received):
{chr(10).join(lines) if lines else '- (no field items)'}
{chr(10) + 'For an item with `node`, `question`, and `options`: pick the one option that is true of what is printed on the listed pages.' + chr(10) if q else ''}
Write `answers/answers.json`: a list of {{"id": "<item id>", "printed": true|false (field items), "answer": <one of options> (question items), "page": <1-based page within the item's list, or null>, "where": "<the label or place on the page>", "confidence": "high|medium|low"}}. Then `answers/REPORT.md` under 150 words: items answered, how many printed, how many not, anything unreadable.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--run', required=True)
    ap.add_argument('--corpus', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--out-secondary', required=True)
    ap.add_argument('--record', required=True, help='selection record; must lie outside both audit folders')
    a = ap.parse_args()
    run, corpus = pathlib.Path(a.run), pathlib.Path(a.corpus)
    outs = [pathlib.Path(a.out), pathlib.Path(a.out_secondary)]
    rec = pathlib.Path(a.record).resolve()
    if any(o.resolve() in rec.parents for o in outs):
        raise SystemExit('--record must lie outside both audit folders')
    variant = json.loads((run / 'run.json').read_text())['variant']
    if variant not in ('clean', 'scan'):
        raise SystemExit(f'run.json variant {variant!r}: expected clean or scan')
    for o in outs:
        if (o / 'items.json').exists() or ((o / 'pages').exists() and any((o / 'pages').iterdir())):
            raise SystemExit(f'{o} already holds an audit set; refusing to overwrite')
    man = json.loads((corpus / 'manifest.json').read_text())
    docs = {d['doc_id']: d for d in man['documents']}
    packets = {p['packet_id']: p for p in man['packets']}
    arms, incomplete = sc.discover(run)
    pm, right, sec, used = select(arms)
    lucky = set(random.Random(AUDIT_SEED).sample(sorted(right), min(AUDIT_LUCKY, len(right))))
    reps = [json.loads((run / 'typed' / n / 'report.json').read_text()) for n in used]
    modes = {r.get('field_desc') for r in reps}
    if len(modes) > 1:
        raise SystemExit(f'primary runs disagree on field_desc: {modes}')
    mode = modes.pop() if modes else None
    opts = {}
    if any(k[0] != 'row8' for k in pm | lucky | sec):
        import typed_questions as tq
        opts = {'row1': tq.CLASSES, 'row4': tq.TOPICS, 'row5': [True, False]}
    record = dict(run=str(run), variant=variant, seed=AUDIT_SEED, primary_runs=used, incomplete_runs=incomplete,
                  field_desc=mode)
    for tag, keys, out in (('primary', pm | lucky, outs[0]), ('secondary', sec, outs[1])):
        items, idmap, npages = build(keys, out, variant, docs, packets, definitions(mode, docs, keys), opts)
        record[tag] = dict(out=str(out), items=len(items), pages=npages, id_to_unit=idmap,
                           misses=sorted(f'{k[0]}:{k[1]}' for k in (pm if tag == 'primary' else sec)),
                           **(dict(random_right=sorted(f'{k[0]}:{k[1]}' for k in lucky), right_pool=len(right)) if tag == 'primary' else {}))
        print(f'{tag}: {len(items)} items, {npages} page images ({variant}) -> {out}')
    rec.write_text(json.dumps(record, indent=1) + '\n')
    print(f'primary misses {len(pm)}, random right {len(lucky)} of {len(right)}, secondary-only misses {len(sec)}; record -> {rec}')


if __name__ == '__main__':
    main()
