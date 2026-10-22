#!/usr/bin/env python3
"""Generate SYNTHETIC pipeline responses from the truth files so the demo runs end to end without an API key.

Every fixture is derived from truth plus labeled perturbations. The perturbation list is written into each
fixture under "perturbations" and printed, so nobody mistakes a fixture for a measurement. The shapes follow
the documented /classify, /extract, /split, /schema responses (the parser's API reference, 2026-09-04).

Perturbation plan (fixed, so the scorer's output is explainable in the room):
  918203  operator_name has a one-character typo; one plat page split to "other"
  917669  total_depth off by 100; lease_perpendiculars.feet_1 citation box shifted (IoU < 0.5)
  907829  county returned null (missing required field → routed to review); no citations for two fields
  918151  one plat classified "unrecognized" (catch-all fires; routing signal)
  all     fields table: one row loses its completion_depth in 918133
"""
import argparse, json, math, pathlib, random
from copy import deepcopy

HERE = pathlib.Path(__file__).resolve().parent
random.seed(7)


SYNTH_TOPIC = {'afe_cover': 'afe_cover', 'afe': 'afe', 'ticket_a': 'field_ticket_1', 'ticket_b': 'field_ticket_2',
               'hauling_log': 'hauling_log', 'invoice': 'invoice', 'jib': 'jib_statement'}
SYNTH_SCHEMA = {'afe_cover': 'afe_cover', 'afe': 'afe', 'ticket_a': 'field_ticket', 'ticket_b': 'field_ticket',
                'hauling_log': 'hauling_log', 'invoice': 'invoice', 'jib': 'jib_statement'}


def _keep(values, schema):
    """Drop any book key the published schema does not declare, so a fixture cannot invent a field."""
    props = schema.get('properties') or {}
    out = {}
    for k, v in values.items():
        if k not in props:
            continue
        sp = props[k]
        if isinstance(v, list) and (sp.get('items') or {}).get('properties'):
            ip = sp['items']['properties']
            out[k] = [{ik: iv for ik, iv in row.items() if ik in ip} for row in v]
        else:
            out[k] = v
    return out


def _leaves(values, prefix=''):
    """(path, value) for every scalar leaf, path in the month-record citation form lines[3].net_amount."""
    out = []
    for k, v in values.items():
        if isinstance(v, list):
            for i, row in enumerate(v):
                if isinstance(row, dict):
                    out += _leaves(row, f'{prefix}{k}[{i}].')
        elif isinstance(v, dict):
            out += _leaves(v, f'{prefix}{k}.')
        else:
            out.append((f'{prefix}{k}', v))
    return out


def _printed(v):
    if isinstance(v, bool):
        return 'Yes' if v else 'No'
    if isinstance(v, float) and (abs(v) >= 100 or round(v, 2) != v or v != int(v)):
        return f'{v:,.2f}' if abs(v) >= 100 or len(str(v).split('.')[-1]) <= 2 else str(v)
    return str(v)


def _nest_citations(flat):
    """{lines[3].net_amount: id} -> nested {lines: [{net_amount: id}, ...]}, the shape /schema returns."""
    out = {}
    for path, cid in flat.items():
        parts = path.split('.')
        cur = out
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            if '[' in part:
                name, idx = part[:-1].split('[')
                idx = int(idx)
                lst = cur.setdefault(name, [])
                while len(lst) <= idx:
                    lst.append({})
                if last:
                    lst[idx] = cid
                else:
                    cur = lst[idx]
            else:
                if last:
                    cur[part] = cid
                else:
                    cur = cur.setdefault(part, {})
    return out


def _page_words(pdf: pathlib.Path):
    """{page: (W, H, [(text, x0, y0, x1, y1), ...])} from pdftotext -bbox-layout, reading order preserved."""
    import subprocess, re, html
    xml = subprocess.run(['pdftotext', '-bbox-layout', str(pdf), '-'], capture_output=True, text=True).stdout
    pages = {}
    for pn, block in enumerate(re.findall(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', xml, re.S), start=1):
        W, H, body = float(block[0]), float(block[1]), block[2]
        words = [(html.unescape(m.group(5)), float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
                 for m in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', body)]
        pages[pn] = (W, H, words)
    return pages


def _candidates(val, printed):
    """Strings the value could print as, most specific first."""
    c = [printed, str(val)]
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        f = float(val)
        c += [f'{f:,.2f}', f'{f:.2f}', f'{f:.6f}', f'{f:,.0f}', f'{f:g}']
    seen, out = set(), []
    for x in c:
        if x and x not in seen:
            seen.add(x); out.append(x)
    return out


def _find_box(pages, allowed_pages, used, val, printed):
    """First unused occurrence of the value on the document's own pages, as (page, normalized bbox), or None.

    Multi-word values match a run of consecutive words on one line. Reading order plus the used-set means the
    seven 0.250000 decimals on a JIB land on seven different rows.
    """
    for cand in _candidates(val, printed):
        toks = cand.split()
        if not toks:
            continue
        for pn in allowed_pages:
            if pn not in pages:
                continue
            W, H, words = pages[pn]
            for i in range(len(words) - len(toks) + 1):
                if all(words[i + j][0] == toks[j] for j in range(len(toks))) and (pn, i) not in used:
                    used.add((pn, i))
                    xs0 = min(w[1] for w in words[i:i + len(toks)]); ys0 = min(w[2] for w in words[i:i + len(toks)])
                    xs1 = max(w[3] for w in words[i:i + len(toks)]); ys1 = max(w[4] for w in words[i:i + len(toks)])
                    return pn, [round(xs0 / W, 4), round(ys0 / H, 4), round(xs1 / W, 4), round(ys1 / H, 4)]
    return None


def synth_topics(manifest):
    """{doc_id: split topic} from the manifest: the class name, except field tickets, which take field_ticket_1 and
    field_ticket_2 by first page within their packet (the pipeline's two-ticket rule). For synth this reproduces
    SYNTH_TOPIC exactly. A packet the frozen split config cannot express (three tickets, or two documents of one
    other class) stops with a message instead of guessing a topic."""
    out = {}
    for pk in manifest['packets']:
        pdocs = [d for d in manifest['documents'] if d['packet'] == pk['packet_id']]
        tickets = sorted((d for d in pdocs if d['class'] == 'field_ticket'), key=lambda d: min(d['pages']))
        if len(tickets) > 2:
            raise SystemExit(f"{pk['packet_id']}: {len(tickets)} field tickets; the frozen split config has two ticket topics")
        for i, d in enumerate(tickets):
            out[d['doc_id']] = f'field_ticket_{i + 1}'
        others = [d['class'] for d in pdocs if d['class'] != 'field_ticket']
        dup = sorted({c for c in others if others.count(c) > 1})
        if dup:
            raise SystemExit(f"{pk['packet_id']}: more than one {dup} document; one split topic per class")
        for d in pdocs:
            if d['class'] != 'field_ticket':
                out[d['doc_id']] = d['class']
    return out


def build_synth(corpus=None):
    """SYNTHETIC /classify, /extract, /split, /schema responses for the joint-interest month.

    Derived from synth/src/book.json (the author's source, never truth) with three LABELLED perturbations, so a
    fixture run exercises the scorer, the extraction-exception path, and citation coverage:
      F1  retired 2026-09-05 (see the note in the body)
      F2  hauling_log.loads[4].barrels -> null          (extraction exception, routes to field)
      F3  invoice.total citation dropped                (citation coverage < 1.0)
    Neither planted defect is touched: P1 (jib.lines[2].owner_decimal 0.26) and P2 (ticket_b.line_items[0].rate 310)
    survive the fixture exactly as printed, so reconcile fires on the story, not on fixture noise.

    corpus (--corpus <dir>): another synth-shaped corpus. Values come from the manifest's references.book when it
    declares one, else from <dir>/truth/<doc_id>.json (the fixture then replays layer-A truth, labelled in
    `source`). F2/F3 are keyed to synth doc ids, so a non-synth corpus gets no perturbations, said in the output.
    Fixtures go to <dir>/fixtures/responses/; --corpus synth writes exactly what --set synth writes.
    """
    from score_synth import corpus_paths
    HEREP = HERE
    paths = corpus_paths(corpus)
    manifest = json.loads(paths['manifest'].read_text())
    book_ref = (manifest.get('references') or {}).get('book')
    docs = {d['doc_id']: d for d in manifest['documents']}
    if paths['default'] or book_ref:
        book = json.loads((HEREP / (book_ref or 'synth/src/book.json')).read_text())
        source = f"{book_ref or 'synth/src/book.json'} (author source, not truth)"
    else:
        book = {'documents': {did: json.loads((paths['truth'] / f'{did}.json').read_text())['values'] for did in docs}}
        source = f"{paths['label']}/truth (no references.book in the manifest; fixture values replay layer-A truth)"
    topic_of = synth_topics(manifest)
    schemas = {did: json.loads((HEREP / f"schemas/{d['class']}.json").read_text()) for did, d in docs.items()}
    out = paths['fixtures']
    out.mkdir(parents=True, exist_ok=True)

    values = {did: _keep(deepcopy(book['documents'][did]), schemas[did]) for did in docs}
    perts = []
    drop_citation = set()
    if paths['default']:
        # F1 (a digit drift on jib.lines[7].gross_amount) was retired 2026-09-05: it made rule_1 fire a third time in
        # fixture mode, so the rehearsal showed a false catch the story does not have. Live runs show what Pulse does.
        values['hauling_log']['loads'][4]['barrels'] = None
        perts.append('F2 hauling_log.loads[4].barrels: null (extraction exception)')
        drop_citation = {('invoice', 'total')}
        perts.append('F3 invoice.total: citation dropped (citation coverage < 1.0)')

    printed = {did: {p: _printed(v) for p, v in _leaves(_keep(deepcopy(book['documents'][did]), schemas[did]))} for did in docs}

    for pk in manifest['packets']:
        pid = pk['packet_id']
        pdocs = [d for d in manifest['documents'] if d['packet'] == pid]
        pages = pk['pages']
        elements, results, flat_by_doc = [], {}, {}
        n = 0
        # Citation geometry comes from the packet PDF's own text layer (pdftotext -bbox-layout), so a fixture box
        # sits over the printed value the way a live citation would; a value not found on the page falls back to a
        # labelled strip. Geometry is still SYNTHETIC: it shows the overlay's shape, never Pulse's precision.
        page_words = _page_words(HEREP / pk['file'])
        used = set(); unplaced = 0
        for d in pdocs:
            did = d['doc_id']
            leaves = _leaves(values[did])
            npages = len(d['pages'])
            per = max(1, math.ceil(len(leaves) / npages))
            flat = {}
            for i, (path, val) in enumerate(leaves):
                if (did, path) in drop_citation or val is None:
                    continue
                n += 1
                cid = f'txt-{pid}-{n}'
                shown = printed[did].get(path, _printed(val))
                hit = _find_box(page_words, d['pages'], used, val, shown)
                if hit:
                    page, box = hit
                else:
                    unplaced += 1
                    page = d['pages'][min(i // per, npages - 1)]
                    y = 0.08 + 0.82 * ((i % per) / max(1, per))
                    box = [0.12, round(y, 4), 0.88, round(y + 0.02, 4)]
                elements.append({'id': cid, 'page_number': page, 'bounding_box': box, 'original_content': shown,
                                 'synthetic': True, 'geometry': 'text-layer' if hit else 'fallback-strip'})
                flat[path] = cid
            flat_by_doc[did] = flat
            results[topic_of[did]] = {'values': values[did], 'citations': _nest_citations(flat)}
        splits = {}
        for d in pdocs:
            splits[topic_of[d['doc_id']]] = list(d['pages'])
        rec = {
            'packet_id': pid, 'synthetic': True, 'synthetic_responses': True, 'perturbations': perts,
            'source': source,
            'classify': {pathlib.Path(d['file']).name: {'classify_output': {'classification': d['class']},
                                                        'credits_used': 0.5 * d['page_count'], 'synthetic': True,
                                                        '_fixture_seconds': round(random.uniform(0.8, 1.6), 3)} for d in pdocs},
            'extract': {'extraction_id': f'fixture-synth-{pid}', 'page_count': pages, 'credits_used': float(pages),
                        'failed_pages': [], 'bounding_boxes': {'Text': elements, 'Tables': [], 'Words': []},
                        'synthetic': True, '_fixture_seconds': round(2.5 + 1.1 * pages, 3)},
            'split': {'split_id': f'fixture-synth-split-{pid}', 'split_output': {'splits': splits},
                      'credits_used': 2.0 * pages, 'synthetic': True, '_fixture_seconds': round(1.5 + 0.4 * pages, 3)},
            'schema': {'schema_id': f'fixture-synth-schema-{pid}', 'split_id': f'fixture-synth-split-{pid}',
                       'results': results, 'credits_used': 1.0 * pages, 'synthetic': True,
                       '_fixture_seconds': round(3.0 + 0.6 * pages, 3)},
        }
        (out / f'{pid}.json').write_text(json.dumps(rec, indent=1))
        print(f"{pid}: synth fixture written ({len(pdocs)} documents, {len(elements)} citation elements, {unplaced} without a text-layer box)")
    print('perturbations: ' + ('; '.join(perts) if perts else f"none (F2/F3 are keyed to synth doc ids; corpus {paths['label']})"))
    if not paths['default']:
        print(f'fixtures: {out}  source: {source}')


def main():
    manifest = json.loads((HERE / 'corpus/manifest.json').read_text())
    out = HERE / 'fixtures' / 'responses'; out.mkdir(parents=True, exist_ok=True)
    for pk in manifest['packets']:
        permit = pk['permit']
        w1 = json.loads((HERE / pk['w1_truth']).read_text())
        sp = json.loads((HERE / pk['split_truth']).read_text())
        docs = [d for d in manifest['documents'] if d['permit'] == permit]
        perts = []
        values = deepcopy(w1['values'])
        citations = {k: {'page': v['page'], 'bbox': v['bbox']} for k, v in w1['citation_truth'].items()}
        splits = deepcopy(sp['splits'])
        classify = [{'file': pathlib.Path(d['file']).name, 'predicted': d['class'], 'seconds': round(random.uniform(0.8, 1.6), 3)} for d in docs]

        if permit == '918203':
            values['operator_name'] = values['operator_name'].replace('O', '0', 1); perts.append('operator_name: one-character OCR-style substitution')
            if splits.get('plat'):
                last = splits['plat'].pop(); splits.setdefault('other', []).append(last); perts.append(f'split: plat page {last} routed to other')
        if permit == '917669':
            values['total_depth'] = str(int(values['total_depth']) + 100); perts.append('total_depth: +100 ft')
            k = 'lease_perpendiculars.feet_1'
            if k in citations:
                b = citations[k]['bbox']; citations[k]['bbox'] = [round(b[0] + 0.12, 4), b[1], round(b[2] + 0.12, 4), b[3]]; perts.append('citation lease_perpendiculars.feet_1 shifted right 0.12 (IoU < 0.5)')
        if permit == '907829':
            values['county'] = None; perts.append('county: null (required field missing → review)')
            for k in ['nearest_town', 'abstract_number']:
                citations.pop(k, None)
            perts.append('citations dropped: nearest_town, abstract_number')
        if permit == '918151':
            for c in classify:
                if c['predicted'] == 'plat':
                    c['predicted'] = 'unrecognized'; perts.append(f"classify: {c['file']} → unrecognized (catch-all)"); break
        if permit == '918133' and values.get('fields'):
            values['fields'][1]['completion_depth'] = None; perts.append('fields[1].completion_depth: null')

        pages = pk['pages']
        rec = {
            'permit': permit, 'synthetic': True, 'perturbations': perts,
            'classify': classify,
            'extract': {'extraction_id': f'fixture-{permit}', 'page_count': pages, 'credits_used': float(pages), 'failed_pages': [],
                        'seconds': round(2.5 + 1.1 * pages + random.uniform(-0.5, 0.5), 3), 'words': None, 'tables': None, 'selection_marks': None},
            'split': {'split_id': f'fixture-split-{permit}', 'splits': splits, 'seconds': round(1.5 + 0.4 * pages, 3)},
            'schema_w1': {'schema_id': f'fixture-schema-{permit}', 'values': values, 'citations': citations, 'seconds': round(3.0 + 0.6 * pages, 3)},
            'schema_plat': {'schema_id': f'fixture-plat-{permit}', 'values': {}, 'citations': {}, 'seconds': round(2.0 + 0.5 * pages, 3), 'note': 'plat truth is PLANNED (human keying); fixture returns nothing so no plat number can be quoted'},
            'timing': {}, 'credits': {'extract': float(pages)},
        }
        rec['timing'] = {'extract': rec['extract']['seconds'], 'split': rec['split']['seconds'], 'schema_w1': rec['schema_w1']['seconds'], 'schema_plat': rec['schema_plat']['seconds']}
        rec['cycle_seconds'] = round(sum(rec['timing'].values()) + sum(c['seconds'] for c in classify), 3)
        rec['cost_usd_at_list'] = round(pages * (0.5 + 1 + 2 + 1 + 1) * 0.015, 4)
        rec['cost_note'] = 'documented list rates: classify 0.5 + extract 1 + split 2 + schema 1 + schema 1 credits per page at $0.015'
        (out / f'{permit}.json').write_text(json.dumps(rec, indent=1))
        print(f"{permit}: fixture written, perturbations={perts or ['none']}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--set', choices=['clean', 'synth'], default='clean',
                    help='clean = the RRC well-file fixtures (default, unchanged); synth = the joint-interest month')
    ap.add_argument('--corpus', help='synth-shaped corpus dir (relative to demo/ or absolute) with manifest.json and truth/; implies --set synth')
    a = ap.parse_args()
    if a.corpus is not None:
        build_synth(a.corpus)
    else:
        build_synth() if a.set == 'synth' else main()
