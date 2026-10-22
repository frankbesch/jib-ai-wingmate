#!/usr/bin/env python3
"""Shared scorer for the well-file demo and for any customer PoC that reuses it.

One scorer, one normalization, run on every engine on the same day (bake-off fairness rules).
Metrics (definitions match the PoC charter in the packet):
  critical_field_accuracy   exact match after normalization on the critical set ÷ critical fields in truth
  all_field_accuracy        same over every scalar field in the truth (nested perpendiculars flattened)
  table_cell_f1             Field Information rows aligned by field_number; a cell is TP when normalized values match
  list_field_accuracy       purpose_of_filing and wellbore_profile scored as set equality
  split_page_f1             page-level F1 per class, micro-averaged; plus exact-range match rate per packet
  classify_accuracy         top-1 over published documents
  citation_coverage         scored string fields that carry a citation ÷ scored string fields
  citation_precision_iou50  cited boxes overlapping the truth box at IoU ≥ 0.5 ÷ cited boxes with a truth box
  cycle_time_p50/p95        seconds per packet (sum of step timings)
  cost_per_page_usd         at documented list rates as recorded by the pipeline
  review_rate               packets routed to a person ÷ packets (rule: any required field null, any failed page,
                            any page split to "other", or any document classified "unrecognized")

Truth boxes are normalized [x0, y0, x1, y1]. Predicted citations may be normalized 4-point, normalized 8-point,
or page-point 4-point (the /schema docs do not state the unit); the scorer normalizes by page size when values
exceed 1. That choice is recorded in the scorecard as citation_bbox_unit_assumed.

CHECK / EXPECT (D-101): `python3 score.py --selftest` scores tests/selftest/ and must reproduce tests/selftest/expect.json
exactly. Expected values were computed by hand and are explained in tests/selftest/README.md.
"""
import argparse, json, pathlib, re, statistics, sys

HERE = pathlib.Path(__file__).resolve().parent
CRITICAL = ['api_number', 'permit_number', 'operator_name', 'lease_name', 'well_number', 'county', 'district', 'total_depth']
LIST_FIELDS = ['purpose_of_filing', 'wellbore_profile']
SKIP = {'fields', 'data_validation_timestamp'}  # table scored separately; timestamp is RRC-internal, not a business field
REQUIRED = ['api_number', 'permit_number', 'operator_name', 'lease_name', 'well_number', 'county', 'district', 'total_depth']
TABLE_COLS = ['district', 'field_name', 'well_type', 'completion_depth', 'distance_to_nearest_well', 'wells_on_lease']


def norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return 'true' if v else 'false'
    s = str(v).strip().upper()
    s = re.sub(r'\s+', ' ', s)
    s = s.rstrip('.')
    try:
        f = float(s.replace(',', ''))
        return f"{f:.2f}"
    except ValueError:
        return s


def flatten(d, prefix=''):
    out = {}
    for k, v in (d or {}).items():
        if k in SKIP or k in LIST_FIELDS:
            continue
        if isinstance(v, dict):
            out.update(flatten(v, f'{prefix}{k}.'))
        else:
            out[f'{prefix}{k}'] = v
    return out


def to_norm_box(b, page_size):
    if not b:
        return None
    if len(b) == 8:
        xs, ys = b[0::2], b[1::2]
        b = [min(xs), min(ys), max(xs), max(ys)]
    if len(b) != 4:
        return None
    unit = 'normalized'
    if max(b) > 1.0:
        W, H = page_size
        b = [b[0] / W, b[1] / H, b[2] / W, b[3] / H]
        unit = 'page_points'
    return [float(x) for x in b], unit


def containment(truth_box, cited_box):
    """Share of the truth box covered by the cited box (1.0 = the cited region fully contains the value)."""
    ix0, iy0, ix1, iy1 = max(truth_box[0], cited_box[0]), max(truth_box[1], cited_box[1]), min(truth_box[2], cited_box[2]), min(truth_box[3], cited_box[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    area = (truth_box[2] - truth_box[0]) * (truth_box[3] - truth_box[1])
    return inter / area if area > 0 else 0.0


def iou(a, b):
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def score_packet(truth_w1, truth_split, truth_classes, rec):
    """Return per-packet counts. truth_classes: {filename: class}."""
    out = {'permit': rec.get('permit'), 'error': rec.get('error')}
    if rec.get('error'):
        return out
    pv = (rec.get('schema_w1') or {}).get('values') or {}
    pc = (rec.get('schema_w1') or {}).get('citations') or {}
    tv = truth_w1['values']
    tf, pf = flatten(tv), flatten(pv)
    fields_scored = [k for k, v in tf.items() if v is not None and v != '']
    correct = [k for k in fields_scored if norm(pf.get(k)) == norm(tf[k])]
    crit = [k for k in fields_scored if k in CRITICAL]
    crit_ok = [k for k in crit if k in correct]
    out['fields_scored'] = len(fields_scored); out['fields_correct'] = len(correct)
    out['critical_scored'] = len(crit); out['critical_correct'] = len(crit_ok)
    out['field_errors'] = [{'field': k, 'truth': tf[k], 'predicted': pf.get(k)} for k in fields_scored if k not in correct]
    # list fields
    out['list_scored'] = 0; out['list_correct'] = 0
    for k in LIST_FIELDS:
        if tv.get(k) is not None:
            out['list_scored'] += 1
            if set(map(norm, tv[k] or [])) == set(map(norm, pv.get(k) or [])):
                out['list_correct'] += 1
    # table
    trows = {norm(r.get('field_number')): r for r in (tv.get('fields') or [])}
    prows = {norm(r.get('field_number')): r for r in (pv.get('fields') or [])}
    tp = fp = fn = 0
    for key, tr in trows.items():
        pr = prows.get(key)
        for col in TABLE_COLS:
            if tr.get(col) is None:
                continue
            if pr is not None and norm(pr.get(col)) == norm(tr.get(col)):
                tp += 1
            else:
                fn += 1
                if pr is not None and pr.get(col) is not None:
                    fp += 1
    for key, pr in prows.items():
        if key not in trows:
            fp += sum(1 for col in TABLE_COLS if pr.get(col) is not None)
    out['table_tp'], out['table_fp'], out['table_fn'] = tp, fp, fn
    # split
    ts = truth_split['splits']; ps = (rec.get('split') or {}).get('splits') or {}
    stp = sfp = sfn = 0
    classes = set(ts) | set(ps)
    for c in classes:
        t, p = set(ts.get(c, [])), set(ps.get(c, []))
        stp += len(t & p); sfp += len(p - t); sfn += len(t - p)
    out['split_tp'], out['split_fp'], out['split_fn'] = stp, sfp, sfn
    out['split_exact'] = all(sorted(ts.get(c, [])) == sorted(ps.get(c, [])) for c in set(ts) | set(ps))
    # classify
    cls = rec.get('classify') or []
    out['classify_n'] = len(cls); out['classify_correct'] = sum(1 for c in cls if truth_classes.get(c['file']) == c.get('predicted'))
    out['classify_unrecognized'] = sum(1 for c in cls if c.get('predicted') == 'unrecognized')
    # citations
    str_fields = [k for k in fields_scored if isinstance(tf[k], str)]
    def cite_of(k):
        c = pc.get(k)
        if isinstance(c, dict) and (c.get('bbox') or c.get('text') or c.get('ref')):
            return c
        if isinstance(c, str):  # unresolved element id (run resolve_live.py to attach page/box/text)
            return {'ref': c, 'bbox': None, 'text': None, 'page': None}
        return None
    cited = [k for k in str_fields if cite_of(k)]
    out['cite_scored'] = len(str_fields); out['cite_present'] = len(cited)
    page_size = truth_w1.get('page_size_pt') or [792.0, 612.0]
    tb = truth_w1.get('citation_truth') or {}
    hits = 0; comparable = 0; units = set(); contain_hits = 0; text_hits = 0; text_comparable = 0
    for k in cited:
        c = cite_of(k)
        if k in tb and c.get('bbox'):
            comparable += 1
            nb = to_norm_box(c['bbox'], page_size)
            if nb:
                b, u = nb; units.add(u)
                same_page = c.get('page') == tb[k]['page']
                if same_page and iou(b, tb[k]['bbox']) >= 0.5:
                    hits += 1
                if same_page and containment(tb[k]['bbox'], b) >= 0.9:
                    contain_hits += 1
        if c.get('text') is not None:
            text_comparable += 1
            if norm(tf[k]) in norm(c['text']) and (c.get('page') is None or c.get('page') == tb.get(k, {}).get('page', c.get('page'))):
                text_hits += 1
    out['cite_comparable'] = comparable; out['cite_hits'] = hits; out['cite_contain_hits'] = contain_hits
    out['cite_text_comparable'] = text_comparable; out['cite_text_hits'] = text_hits; out['cite_units'] = sorted(units)
    # timing and cost
    out['cycle_seconds'] = rec.get('cycle_seconds')
    out['pages'] = (rec.get('extract') or {}).get('page_count')
    out['cost_usd'] = rec.get('cost_usd_at_list')
    # review routing
    reasons = []
    if any(pv.get(k) in (None, '') for k in REQUIRED):
        reasons.append('required field null')
    if (rec.get('extract') or {}).get('failed_pages'):
        reasons.append('failed pages')
    if ps.get('other'):
        reasons.append('pages split to other')
    if out['classify_unrecognized']:
        reasons.append('document classified unrecognized')
    if out['field_errors'] and any(e['field'] in CRITICAL for e in out['field_errors']):
        reasons.append('critical field mismatch vs truth (visible only with truth; in production use word/table confidence and rules)')
    out['review_reasons'] = reasons
    out['routed_to_review'] = bool([r for r in reasons if not r.startswith('critical field mismatch')])
    return out


def f1(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return round(2 * p * r / (p + r), 4) if p + r else 0.0, round(p, 4), round(r, 4)


def pct(n, d):
    return round(n / d, 4) if d else None


def aggregate(per):
    ok = [p for p in per if not p.get('error')]
    agg = {'packets': len(per), 'packets_scored': len(ok), 'packets_errored': [p['permit'] for p in per if p.get('error')]}
    s = lambda k: sum(p.get(k, 0) or 0 for p in ok)
    agg['critical_field_accuracy'] = pct(s('critical_correct'), s('critical_scored'))
    agg['all_field_accuracy'] = pct(s('fields_correct'), s('fields_scored'))
    agg['list_field_accuracy'] = pct(s('list_correct'), s('list_scored'))
    agg['table_cell_f1'], agg['table_cell_precision'], agg['table_cell_recall'] = f1(s('table_tp'), s('table_fp'), s('table_fn'))
    agg['split_page_f1'], agg['split_page_precision'], agg['split_page_recall'] = f1(s('split_tp'), s('split_fp'), s('split_fn'))
    agg['split_exact_rate'] = pct(sum(1 for p in ok if p.get('split_exact')), len(ok))
    agg['classify_accuracy'] = pct(s('classify_correct'), s('classify_n'))
    agg['citation_coverage'] = pct(s('cite_present'), s('cite_scored'))
    agg['citation_precision_iou50'] = pct(s('cite_hits'), s('cite_comparable'))
    agg['citation_precision_contain90'] = pct(s('cite_contain_hits'), s('cite_comparable'))
    agg['citation_precision_text'] = pct(s('cite_text_hits'), s('cite_text_comparable'))
    agg['citation_bbox_unit_assumed'] = sorted({u for p in ok for u in p.get('cite_units', [])})
    times = [p['cycle_seconds'] for p in ok if p.get('cycle_seconds') is not None]
    if times:
        agg['cycle_time_p50_s'] = round(statistics.median(times), 2)
        agg['cycle_time_p95_s'] = round(sorted(times)[max(0, int(round(0.95 * len(times))) - 1)], 2)
    pages = s('pages'); cost = sum(p.get('cost_usd') or 0 for p in ok)
    agg['pages'] = pages; agg['cost_usd_total_at_list'] = round(cost, 4); agg['cost_per_page_usd'] = pct(cost, pages)
    agg['review_rate'] = pct(sum(1 for p in ok if p.get('routed_to_review')), len(ok))
    agg['counts'] = {k: s(k) for k in ['fields_scored', 'fields_correct', 'critical_scored', 'critical_correct', 'table_tp', 'table_fp', 'table_fn', 'split_tp', 'split_fp', 'split_fn', 'classify_n', 'classify_correct', 'cite_scored', 'cite_present', 'cite_comparable', 'cite_hits', 'cite_contain_hits', 'cite_text_comparable', 'cite_text_hits']}
    return agg


def score_run(run_dir: pathlib.Path, truth_root: pathlib.Path):
    run = json.loads((run_dir / 'run.json').read_text())
    per = []
    for permit in run['permits']:
        rec = json.loads((run_dir / f'{permit}.json').read_text())
        tw = json.loads((truth_root / 'w1' / f'{permit}.json').read_text())
        tsp = json.loads((truth_root / 'split' / f'{permit}.json').read_text())
        tcls = {}
        for f in (truth_root / 'classify').glob(f'{permit}__*.json'):
            j = json.loads(f.read_text()); tcls[j['file']] = j['class']
        per.append(score_packet(tw, tsp, tcls, rec))
    agg = aggregate(per)
    agg['run_id'] = run.get('run_id'); agg['synthetic'] = run.get('synthetic', False); agg['mode'] = run.get('mode'); agg['set'] = run.get('set')
    return {'summary': agg, 'packets': per}


def print_table(card):
    a = card['summary']
    tag = 'SYNTHETIC FIXTURE — not a Pulse measurement' if a.get('synthetic') else f"{a.get('mode')} run"
    print(f"\nScorecard {a.get('run_id')}  [{tag}]  set={a.get('set')}  packets={a['packets_scored']}/{a['packets']}")
    rows = [('Critical-field accuracy', a['critical_field_accuracy']), ('All-field accuracy', a['all_field_accuracy']),
            ('List-field accuracy', a['list_field_accuracy']), ('Table cell F1', a['table_cell_f1']), ('Split page F1', a['split_page_f1']),
            ('Split exact-range rate', a['split_exact_rate']), ('Classify accuracy', a['classify_accuracy']),
            ('Citation coverage', a['citation_coverage']), ('Citation precision @IoU 0.5', a['citation_precision_iou50']), ('Citation precision, contains value (geom)', a.get('citation_precision_contain90')), ('Citation precision, cited text has value', a.get('citation_precision_text')),
            ('Cycle time p50 / p95 (s)', f"{a.get('cycle_time_p50_s')} / {a.get('cycle_time_p95_s')}"),
            ('Cost per page at list ($)', a['cost_per_page_usd']), ('Review rate', a['review_rate'])]
    for k, v in rows:
        print(f"  {k:30} {v}")
    for p in card['packets']:
        if p.get('error'):
            print(f"  {p['permit']}: ERROR {p['error']}")
        elif p['field_errors'] or p['review_reasons']:
            print(f"  {p['permit']}: errors={[(e['field'], e['predicted']) for e in p['field_errors']]} review={p['review_reasons']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run')
    ap.add_argument('--truth', default=str(HERE / 'truth'))
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--out')
    ap.add_argument('--corpus', help='synth-set runs only: corpus dir with manifest.json and truth/ (default: the run record, else synth)')
    a = ap.parse_args()
    if a.selftest:
        st = HERE / 'tests' / 'selftest'
        card = score_run(st / 'run', st / 'truth')
        expect = json.loads((st / 'expect.json').read_text())
        got = {k: card['summary'].get(k) for k in expect}
        bad = {k: (got[k], expect[k]) for k in expect if got[k] != expect[k]}
        print_table(card)
        if bad:
            print('\nSELFTEST FAIL — got vs expected:')
            for k, (g, e) in bad.items():
                print(f'  {k}: got {g} expected {e}')
            sys.exit(1)
        print(f'\nSELFTEST PASS — {len(expect)} expected values reproduced exactly')
        return
    if not a.run:
        sys.exit('give --run runs/<id> or --selftest')
    run_dir = pathlib.Path(a.run)
    if not run_dir.is_absolute():
        run_dir = HERE / run_dir
    run_meta = json.loads((run_dir / 'run.json').read_text())
    if run_meta.get('set') == 'synth':  # joint-interest month: different documents, different lines, own scorer
        import score_synth  # --corpus (or the run record's corpus) picks manifest + truth; none = synth/, truth/synth
        score_synth.score_and_write(run_dir, pathlib.Path(a.truth), a.corpus, a.out)
        return
    card = score_run(run_dir, pathlib.Path(a.truth))
    out = pathlib.Path(a.out) if a.out else run_dir / 'scorecard.json'
    out.write_text(json.dumps(card, indent=1))
    print_table(card)
    print(f"\nscorecard: {out}")


if __name__ == '__main__':
    main()
