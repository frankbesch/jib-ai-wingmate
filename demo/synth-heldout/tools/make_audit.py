#!/usr/bin/env python3
"""Build a blind audit set (items.json + page images + BRIEF.md) from the redo arm runs of one Pulse run.
Read-only toward the runs and the corpus; writes only under --out.

Default: every DISCORDANT unit across the selected arm runs (--arms, default A,B,C): a unit whose correct /
not-correct status differs between any two arm runs. Pulse-dropped units are skipped (own column).
--misses-only reproduces the pilot: the union over the A repeats of row-8 units that are not correct.

Items (sorted by id). Row 8, same shape as the pilot: {"id": "<doc>.<field>", "document", "field", "pages"}.
Rows 1/4/5 add "node", "question", "options" (the arms' question text; options without needs_review, since the
auditor answers what is true): row1 id "row1.<doc>" (document pages), row4 id "row4.<packet>:p<N>" (that packet
page), row5 id "row5.<packet>" (every packet page).
Pages, byte-identical to the pilot's: clean = `pdftoppm -r 150 -png` of the document PDF (manifest `file`),
<doc>-p<N>.png; scan = `pdfimages -j` of the scan PDF (manifest `scan_file`; the embedded 150 dpi JPEG),
<doc>-p<N>.jpg. Packet pages (rows 4/5) are rendered from the packet PDF as packet_<packet>-p<N>.<ext>.
BRIEF.md is the pilot's audit brief for the run's variant, verbatim; when row 1/4/5 items exist an addendum
tells the auditor how to answer them (the pilot brief covers row 8 only).

Usage: make_audit.py --run runs/<id> --corpus <corpus dir> --out <audit set dir> [--arms A,B,C] [--misses-only]
"""
import argparse, json, os, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
DEMO = HERE.parent.parent
sys.path.insert(0, str(HERE))
import score_heldout as sh  # noqa: E402  (also puts typed/ on sys.path)
import typed_questions as tq  # noqa: E402

PILOT_BRIEF = DEMO / 'synth-pilot' / 'audit-claude-misses'
QUESTIONS = {'row1': 'Which document class is this document?', 'row4': 'Which topic does this page belong to?',
             'row5': 'Does this packet contain a second field ticket?'}
OPTIONS = {'row1': tq.CLASSES, 'row4': tq.TOPICS, 'row5': [True, False]}
ADDENDUM = """
## Items with a `question` (rows 1, 4, 5)

Some items carry `node`, `question`, and `options` instead of `field`. For each, look at every page image listed and pick the one option that is true of what is printed. Write it in the same `answers/answers.json` list as {"id": "<item id>", "answer": <one of options>, "page": <1-based page or null>, "where": "<what on the page decides it>", "confidence": "high|medium|low"}.
"""


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


def select(run, arms, misses_only):
    A, B, C = sh.arm_runs(run)
    if misses_only:
        keys = set()
        for p in A:
            keys |= {(u['node'], u['subject']) for u in sh.unit_records(p)
                     if u['node'] == 'row8' and not u.get('pulse_dropped') and sh.status(u) != 'correct'}
        return keys, [os.path.basename(p) for p in A]
    paths = [p for name, ps in zip('ABC', (A, B, C)) if name in arms for p in ps]
    seen = {}
    for p in paths:
        for u in sh.unit_records(p):
            if not u.get('pulse_dropped'):
                seen.setdefault((u['node'], u['subject']), set()).add(sh.status(u) == 'correct')
    return {k for k, v in seen.items() if len(v) == 2}, [os.path.basename(p) for p in paths]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--run', required=True)
    ap.add_argument('--corpus', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--arms', default='A,B,C')
    ap.add_argument('--misses-only', action='store_true')
    a = ap.parse_args()
    out, corpus = pathlib.Path(a.out), pathlib.Path(a.corpus)
    variant = json.loads((pathlib.Path(a.run) / 'run.json').read_text())['variant']
    if variant not in ('clean', 'scan'):
        raise SystemExit(f'run.json variant {variant!r}: expected clean or scan')
    if (out / 'items.json').exists() or ((out / 'pages').exists() and any((out / 'pages').iterdir())):
        raise SystemExit(f'{out} already holds an audit set; refusing to overwrite')
    manifest = json.loads((corpus / 'manifest.json').read_text())
    docs = {d['doc_id']: d for d in manifest['documents']}
    packets = {p['packet_id']: p for p in manifest['packets']}
    fkey = 'file' if variant == 'clean' else 'scan_file'
    keys, used = select(a.run, set(a.arms.split(',')), a.misses_only)
    (out / 'pages').mkdir(parents=True, exist_ok=True)
    done = {}

    def page(pdf, n, stem):
        if stem not in done:
            done[stem] = 'pages/' + render(pdf, n, out / 'pages' / stem, variant)
        return done[stem]

    def doc_pages(doc):
        d = docs[doc]
        return [page(d[fkey], i, f'{doc}-p{i}') for i in range(1, d['page_count'] + 1)]

    items = []
    for node, subject in keys:
        if node == 'row8':
            doc, field = subject.split('.', 1)
            items.append(dict(id=subject, document=doc, field=field, pages=doc_pages(doc)))
        elif node == 'row1':
            items.append(dict(id=f'row1.{subject}', node=node, document=subject, question=QUESTIONS[node],
                              options=OPTIONS[node], pages=doc_pages(subject)))
        elif node == 'row4':
            pid, p = subject.split(':p')
            items.append(dict(id=f'row4.{subject}', node=node, packet=pid, page=int(p), question=QUESTIONS[node],
                              options=OPTIONS[node], pages=[page(packets[pid][fkey], int(p), f'packet_{pid}-p{p}')]))
        elif node == 'row5':
            items.append(dict(id=f'row5.{subject}', node=node, packet=subject, question=QUESTIONS[node], options=OPTIONS[node],
                              pages=[page(packets[subject][fkey], i, f'packet_{subject}-p{i}') for i in range(1, packets[subject]['pages'] + 1)]))
        else:
            raise SystemExit(f'unknown node {node} for {subject}')
    items.sort(key=lambda x: x['id'])
    (out / 'items.json').write_text(json.dumps(items, indent=2) + '\n')
    brief = (PILOT_BRIEF / variant / 'BRIEF.md').read_text()
    (out / 'BRIEF.md').write_text(brief + (ADDENDUM if any('node' in x for x in items) else ''))
    by = {}
    for x in items:
        by[x.get('node', 'row8')] = by.get(x.get('node', 'row8'), 0) + 1
    print(f"{'misses-only (A row 8 not correct)' if a.misses_only else 'discordant'} over {used}")
    print(f'{len(items)} items {by}, {len(done)} page images ({variant}) -> {out}')


if __name__ == '__main__':
    main()
