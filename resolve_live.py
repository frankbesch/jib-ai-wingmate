#!/usr/bin/env python3
"""Resolve a live run's citation ids into page + box + text using the saved raw extract, and capture the
schema confidence block. Rewrites runs/<id>/<permit>.json in place. Idempotent; safe to re-run.

Why: the live /schema response (observed 2026-09-04) cites element ids such as `tbl-1-r0c1` or `txt-7`,
not {page, bbox}. The ids point into the /extract bounding_boxes (Tables cell_data, Text, Title, Header,
Footer). The docs' example shows {page, bbox}; the multi-extraction note mentions ids. Both shapes are handled.

  python3 resolve_live.py --run runs/live-clean-01
"""
import argparse, json, pathlib

HERE = pathlib.Path(__file__).resolve().parent


def index_extract(extract: dict) -> dict:
    """id → {page, bbox[4 normalized], text} from every bounding_boxes category that carries ids."""
    bb = extract.get('bounding_boxes') or {}
    idx = {}

    def box_from(coords):
        if not coords:
            return None
        if isinstance(coords[0], dict):
            xs = [p['x'] for p in coords]; ys = [p['y'] for p in coords]
        elif len(coords) == 8:
            xs, ys = coords[0::2], coords[1::2]
        elif len(coords) == 4:
            return [float(c) for c in coords]
        else:
            return None
        return [min(xs), min(ys), max(xs), max(ys)]

    for cat, items in bb.items():
        if cat in ('markdown_with_ids', 'Words'):
            continue
        for it in items or []:
            if cat == 'Tables':
                ti = it.get('table_info') or {}
                if ti.get('id'):
                    loc = ti.get('location') or {}
                    idx[ti['id']] = {'page': loc.get('page'), 'bbox': box_from(loc.get('coordinates')), 'text': None, 'kind': 'table', 'confidence': ti.get('confidence')}
                for c in it.get('cell_data') or []:
                    loc = c.get('location') or {}
                    idx[c['id']] = {'page': loc.get('page'), 'bbox': box_from(loc.get('coordinates')), 'text': (c.get('text') or ''), 'kind': 'cell', 'confidence': c.get('confidence')}
            elif isinstance(it, dict) and it.get('id'):
                idx[it['id']] = {'page': it.get('page_number'), 'bbox': box_from(it.get('bounding_box')), 'text': it.get('original_content') or it.get('content'), 'kind': cat, 'confidence': it.get('average_word_confidence')}
    return idx


def strip_prefix(t):
    """Pulse prefixes cell/text content with tags like '0t-' or '0a-'; strip one leading tag."""
    if isinstance(t, str) and len(t) > 3 and t[1] in 'ta' and t[2] == '-' and t[0].isdigit():
        return t[3:]
    return t


def resolve(cit, idx):
    """Return {page, bbox, text, ref} for a citation value of any documented shape."""
    if cit is None:
        return None
    if isinstance(cit, dict) and ('bbox' in cit or 'page' in cit) and not any(isinstance(v, (dict, list, str)) and k not in ('bbox',) for k, v in cit.items() if k != 'page'):
        return {'page': cit.get('page'), 'bbox': cit.get('bbox'), 'text': None, 'ref': None}
    if isinstance(cit, str):
        ref = cit.split('-', 1)[1] if cit.count('-') >= 2 and cit.split('-', 1)[0] and cit.split('-', 1)[1].startswith(('tbl', 'txt')) else cit
        el = idx.get(ref) or idx.get(cit)
        if el:
            return {'page': el['page'], 'bbox': el['bbox'], 'text': strip_prefix(el['text']), 'ref': cit, 'kind': el['kind'], 'element_confidence': el.get('confidence')}
        return {'page': None, 'bbox': None, 'text': None, 'ref': cit, 'unresolved': True}
    if isinstance(cit, list):
        return [resolve(c, idx) for c in cit]
    if isinstance(cit, dict):
        return {k: resolve(v, idx) for k, v in cit.items()}
    return None


def flatten_resolved(res, prefix=''):
    """Flatten nested resolved citations to dotted keys with {page,bbox,text,ref} leaves."""
    out = {}
    for k, v in (res or {}).items():
        key = f'{prefix}{k}'
        if isinstance(v, dict) and 'ref' in v:
            out[key] = v
        elif isinstance(v, dict):
            out.update(flatten_resolved(v, key + '.'))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict) and 'ref' in item:
                    out[f'{key}[{i}]'] = item
                elif isinstance(item, dict):
                    out.update(flatten_resolved(item, f'{key}[{i}].'))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--run', required=True)
    a = ap.parse_args()
    rd = pathlib.Path(a.run); rd = rd if rd.is_absolute() else HERE / rd
    run = json.loads((rd / 'run.json').read_text())
    for permit in run['permits']:
        recp = rd / f'{permit}.json'
        if not recp.exists():
            continue
        rec = json.loads(recp.read_text())
        ex = rd / 'raw' / f'{permit}__extract.json'
        if rec.get('error') or not ex.exists():
            continue
        idx = index_extract(json.loads(ex.read_text()))
        split_raw = rd / 'raw' / f'{permit}__schema_split.json'
        split_parsed = None
        if split_raw.exists():  # split-mode run (pipeline --schema-mode split): one raw file, results keyed by topic
            from pipeline import parse_split_schema, SCHEMA_TOPICS
            split_parsed = {SCHEMA_TOPICS[t][0]: v for t, v in parse_split_schema(json.loads(split_raw.read_text()), list(SCHEMA_TOPICS)).items()}
        for name in ('schema_w1', 'schema_plat'):
            rawp = rd / 'raw' / f'{permit}__{name}.json'
            if name not in rec:
                continue
            if split_parsed is not None:
                so = split_parsed.get(name) or {}
            elif rawp.exists():
                so = (json.loads(rawp.read_text()).get('schema_output') or {})
            else:
                continue
            raw_c = so.get('citations') or {}
            resolved = flatten_resolved(resolve(raw_c, idx))
            rec[name]['citation_refs'] = raw_c
            rec[name]['citations'] = {k: {'page': v.get('page'), 'bbox': v.get('bbox'), 'text': v.get('text'), 'ref': v.get('ref'), 'kind': v.get('kind')} for k, v in resolved.items()}
            rec[name]['confidence'] = so.get('confidence')
            unresolved = [k for k, v in resolved.items() if v.get('unresolved')]
            rec[name]['citation_note'] = f'{len(resolved)} citations resolved from element ids via /extract bounding boxes; {len(unresolved)} unresolved' + (f': {unresolved[:5]}' if unresolved else '')
        recp.write_text(json.dumps(rec, indent=1))
        print(f"{permit}: {rec.get('schema_w1', {}).get('citation_note')}")


if __name__ == '__main__':
    main()
