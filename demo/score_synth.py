#!/usr/bin/env python3
"""Scorer for the joint-interest month (--set synth). Imported by score.py; the RRC scorer is untouched.

Scores runs/<id>/month.json against truth/synth/<doc_id>.json, one truth file per document
(shape: {doc_id, values, page_of, ...}; page_of is optional and only tightens the citation check).

Lines measured (each maps to a go/no-go row in the scorecard):
  classify_exact_per_document   predicted class == manifest class, over all seven documents
  critical_field_accuracy       the per-class critical set below, exact after normalization
  all_field_accuracy            every non-null scalar leaf in truth
  list_length_recall            predicted rows / truth rows, summed over every list in truth
  citation_coverage             scored values that carry a citation / scored values
  citation_text_contains_value  citations whose cited text contains the truth value / citations with text
  cycle_seconds                 per packet and total, as recorded by the pipeline
  credits and cost_per_page     as returned by the API and priced at documented list

Critical set per document class (the go/no-go definition):
  afe            afe_number, well_name, total_estimate, every cost_lines amount + account_code
  jib_statement  statement_period, property_number, wi_decimal, gross_total, net_total,
                 every line's afe_ref + gross_amount + owner_decimal + net_amount
  field_ticket   vendor_name, service_date, every line_item quantity + unit + rate
  hauling_log    total_barrels, every load's barrels
  invoice        total, every line's amount
  afe_cover      none declared in the go/no-go; scored in all-field accuracy only

If truth/synth does not exist the scorer prints "truth/synth absent — scoring skipped", writes a
counts-only scorecard from month.json, and exits 0. Nothing is guessed and no accuracy is reported.

Targets: copied from plan §2 (D-125) and never edited after the first live run. The reconcile lines read
runs/<id>/exceptions.json against the sealed synth/planted.json (opened only here, after the run).

Second corpus (--corpus <dir>, S2.0): a directory shaped like synth/ holding manifest.json and truth/<doc_id>.json.
corpus_paths() is the one resolver pipeline.py, make_fixtures.py, score.py, and this file share. --corpus synth
resolves to exactly the default paths (synth/manifest.json, truth/synth, fixtures/responses/synth).
  python3 score_synth.py --run runs/<id> [--corpus synth-pilot]   # --corpus defaults to the run record's corpus
"""
import argparse, json, math, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent


def corpus_paths(corpus=None):
    """Paths for a synth-shaped corpus dir (relative to demo/ or absolute).

    None or a dir that resolves to demo/synth -> the fixed paths every --set synth run has used. Any other dir ->
    <dir>/manifest.json, <dir>/truth/, and fixture responses under <dir>/fixtures/responses/ so a second corpus
    never overwrites the tracked synth fixtures. `label` is what the run record stores as `corpus`.
    """
    base = {'label': None, 'default': True, 'root': HERE / 'synth', 'manifest': HERE / 'synth' / 'manifest.json',
            'truth': HERE / 'truth' / 'synth', 'fixtures': HERE / 'fixtures' / 'responses' / 'synth'}
    if corpus is None:
        return base
    d = pathlib.Path(corpus)
    d = (d if d.is_absolute() else HERE / d).resolve()
    try:
        label = str(d.relative_to(HERE))
    except ValueError:
        label = str(d)
    if d == (HERE / 'synth').resolve():
        return dict(base, label=label)
    return {'label': label, 'default': False, 'root': d, 'manifest': d / 'manifest.json', 'truth': d / 'truth',
            'fixtures': d / 'fixtures' / 'responses'}


def reference_path(manifest, key):
    """HERE / manifest.references[key] (manifest paths are relative to demo/), or None when not declared."""
    p = (manifest.get('references') or {}).get(key)
    return HERE / p if p else None

CRITICAL = {
    'afe': {'scalars': ['afe_number', 'well_name', 'total_estimate'], 'lists': {'cost_lines': ['amount', 'account_code']}},
    'jib_statement': {'scalars': ['statement_period', 'property_number', 'wi_decimal', 'gross_total', 'net_total'],
                      'lists': {'lines': ['afe_ref', 'gross_amount', 'owner_decimal', 'net_amount']}},
    'field_ticket': {'scalars': ['vendor_name', 'service_date'], 'lists': {'line_items': ['quantity', 'unit', 'rate']}},
    'hauling_log': {'scalars': ['total_barrels'], 'lists': {'loads': ['barrels']}},
    'invoice': {'scalars': ['total'], 'lists': {'line_items': ['amount']}},
    'afe_cover': {'scalars': [], 'lists': {}},
}

# Targets copied from plans/2026-09-05-pulse-ideal-demo-plan.md §2 (D-125). No target is edited after the first live run.
TARGET_SOURCE = 'plan §2 (D-125), declared before the first live run'
TARGETS = {
    'classify_exact_per_document': 1.0,      # 7 of 7 synthetic documents exact
    'critical_field_accuracy': 1.0,          # clean synthetic set; scanned set reported separately
    'all_field_accuracy': None,              # diagnostic, not a charter line
    'list_length_recall': 1.0,               # 6 AFE lines, 8 JIB lines, every ticket line present
    'citation_coverage': 1.0,                # every extracted value carries page and box
    'citation_text_contains_value': 0.9,     # cited text contains the value ≥ 0.9
    'reconcile_plants_caught': 1.0,          # both planted defects (2 of 2)
    'reconcile_false_catches': 0,            # zero false catches on the clean lines (lower is better)
    'clean_lines_to_a_person': 0,            # exceptions only; every clean line lands without a person
    'cycle_seconds_total': 480,              # full month under 8 minutes wall clock (lower is better)
    'cost_per_page_usd': None,               # metered on screen; list price stated per page
}
LOWER_IS_BETTER = {'reconcile_false_catches', 'clean_lines_to_a_person', 'cycle_seconds_total'}


def reconcile_lines(run_dir, planted_path=None):
    """Reconcile go/no-go inputs from runs/<id>/exceptions.json against the sealed synth/planted.json.

    Plants are read only here, after the run; the reconcile code never sees them. Extraction exceptions are not
    catches and are reported separately. Returns {} when exceptions.json is absent (reconcile not run yet).
    planted_path: None = synth/planted.json; a --corpus run passes its manifest's references.planted.
    Every top-level key P<n> is a plant (synth has P1, P2; H1 is not a billing plant and is not counted).
    """
    ex_path = run_dir / 'exceptions.json'
    planted_path = planted_path or HERE / 'synth' / 'planted.json'
    if not ex_path.exists() or not planted_path.exists():
        return {}
    ex = json.loads(ex_path.read_text()); planted = json.loads(planted_path.read_text())
    plants = {}
    for key in sorted(k for k in planted if re.fullmatch(r'P\d+', k)):
        pl = planted.get(key) or {}
        m = re.match(r'(\w+)\[(\d+)\]', pl.get('field_path') or '')
        if pl.get('doc_id') and m:
            plants[(pl['rule'], pl['doc_id'], m.group(1), int(m.group(2)))] = key
    caught, false_catches, fired_rule_lines = set(), [], 0
    for e in ex.get('exceptions') or []:
        if e.get('rule') == 'extraction':
            continue
        fired_rule_lines += 1
        m = re.match(r'(\w+)\[(\d+)\]', e.get('field_path') or '')
        k = (e.get('rule'), e.get('doc_id'), m.group(1) if m else None, int(m.group(2)) if m else None)
        if k in plants:
            caught.add(plants[k])
        else:
            false_catches.append({'id': e.get('id'), 'rule': e.get('rule'), 'doc_id': e.get('doc_id'), 'field_path': e.get('field_path')})
    summary = ex.get('summary') or {}
    return {
        'reconcile_plants_caught': pct(len(caught), len(plants)) if plants else None,
        'reconcile_plants_detail': {'planted': len(plants), 'caught': sorted(caught)},
        'reconcile_false_catches': len(false_catches),
        'reconcile_false_catch_detail': false_catches,
        'reconcile_extraction_exceptions': sum(1 for e in (ex.get('exceptions') or []) if e.get('rule') == 'extraction'),
        'clean_lines_to_a_person': len(false_catches),
        'reconcile_lines_checked': summary.get('checked') or summary.get('jib_lines'),
        'reconcile_fired_rule_lines': fired_rule_lines,
    }


def norm(v):
    """Normalize for exact match. Decimals below 1 keep six places so 0.250000 and 0.260000 stay distinct."""
    if v is None:
        return None
    if isinstance(v, bool):
        return 'true' if v else 'false'
    s = str(v).strip().upper()
    s = re.sub(r'\s+', ' ', s).rstrip('.')
    try:
        f = float(s.replace(',', '').replace('$', ''))
    except ValueError:
        return s
    return f'{f:.6f}' if abs(f) < 1 else f'{f:.2f}'


def leaves(values, prefix=''):
    """(path, value) for every scalar leaf; list items use the month-record form lines[3].net_amount."""
    out = []
    for k, v in (values or {}).items():
        if isinstance(v, list):
            for i, row in enumerate(v):
                if isinstance(row, dict):
                    out += leaves(row, f'{prefix}{k}[{i}].')
                else:
                    out.append((f'{prefix}{k}[{i}]', row))
        elif isinstance(v, dict):
            out += leaves(v, f'{prefix}{k}.')
        else:
            out.append((f'{prefix}{k}', v))
    return out


def dig(values, path):
    """Read a leaf out of a predicted values dict by its flattened path. Missing -> None."""
    cur = values
    for part in path.split('.'):
        m = re.fullmatch(r'([^\[]+)(?:\[(\d+)\])?', part)
        if not m or not isinstance(cur, dict):
            return None
        cur = cur.get(m.group(1))
        if m.group(2) is not None:
            i = int(m.group(2))
            if not isinstance(cur, list) or i >= len(cur):
                return None
            cur = cur[i]
    return cur if not isinstance(cur, (dict, list)) else None


def critical_paths(cls, truth_values):
    spec = CRITICAL.get(cls) or {'scalars': [], 'lists': {}}
    paths = [k for k in spec['scalars'] if k in (truth_values or {})]
    for lname, cols in spec['lists'].items():
        rows = (truth_values or {}).get(lname) or []
        for i, row in enumerate(rows):
            if isinstance(row, dict):
                paths += [f'{lname}[{i}].{c}' for c in cols if c in row]
    return paths


def lists_of(values):
    return {k: v for k, v in (values or {}).items() if isinstance(v, list)}


def score_document(doc_id, cls, truth, doc, page_offset=0):
    """Per-document counts. doc is the month.json documents[<doc_id>] block."""
    tv = truth.get('values') or {}
    pv = doc.get('values') or {}
    cites = doc.get('citations') or {}
    scored = [(p, v) for p, v in leaves(tv) if v is not None and v != '']
    correct = [p for p, v in scored if norm(dig(pv, p)) == norm(v)]
    crit = [p for p in critical_paths(cls, tv) if norm(dig(tv, p)) is not None]
    crit_ok = [p for p in crit if norm(dig(pv, p)) == norm(dig(tv, p))]
    tl, pl = lists_of(tv), lists_of(pv)
    list_truth_rows = sum(len(v) for v in tl.values())
    list_pred_rows = sum(len(pl.get(k) or []) for k in tl)
    cited = [p for p, _ in scored if isinstance(cites.get(p), dict) and (cites[p].get('bbox') or cites[p].get('text') or cites[p].get('ref'))]
    text_comparable = text_hits = 0
    page_of = truth.get('page_of') or {}
    page_comparable = page_hits = 0
    for p, v in scored:
        c = cites.get(p)
        if not isinstance(c, dict):
            continue
        if c.get('text') is not None:
            text_comparable += 1
            if norm(v) in norm(c['text']) or str(v).strip().upper() in str(c['text']).strip().upper():
                text_hits += 1
        if p in page_of and c.get('page') is not None:
            page_comparable += 1
            if c['page'] == page_of[p] + page_offset:  # truth page_of is document-relative; run citations are packet-relative
                page_hits += 1
    return {
        'doc_id': doc_id, 'class': cls, 'packet': doc.get('packet'), 'topic': doc.get('topic'),
        'pages_predicted': doc.get('pages'), 'note': doc.get('note'),
        'fields_scored': len(scored), 'fields_correct': len(correct),
        'critical_scored': len(crit), 'critical_correct': len(crit_ok),
        'list_truth_rows': list_truth_rows, 'list_pred_rows': list_pred_rows,
        'list_detail': {k: {'truth': len(v), 'predicted': len(pl.get(k) or [])} for k, v in tl.items()},
        'cite_scored': len(scored), 'cite_present': len(cited),
        'cite_text_comparable': text_comparable, 'cite_text_hits': text_hits,
        'cite_page_comparable': page_comparable, 'cite_page_hits': page_hits,
        'field_errors': [{'field': p, 'truth': v, 'predicted': dig(pv, p)} for p, v in scored if p not in correct],
        'nulls': [p for p, _ in scored if dig(pv, p) is None],
    }


def pct(n, d):
    return round(n / d, 4) if d else None


def go_no_go(summary):
    """Each measured line vs its plan §2 target: pass | miss | report-only | not-measurable."""
    rows = []
    for key, target in TARGETS.items():
        measured = summary.get(key)
        if measured is None:
            verdict = 'not-measurable'
        elif target is None:
            verdict = 'report-only'
        elif key in LOWER_IS_BETTER:
            verdict = 'pass' if measured <= target + 1e-9 else 'miss'
        else:
            verdict = 'pass' if measured >= target - 1e-9 else 'miss'
        rows.append({'line': key, 'measured': measured, 'target': target, 'verdict': verdict, 'target_source': TARGET_SOURCE})
    return rows


def counts_only(month, reason, run_dir=None, planted_path=None):
    run_dir = run_dir or pathlib.Path('.')
    """Scorecard when truth/synth is absent: month-derived counts, no accuracy, no invented numbers."""
    summary = {
        'run_id': month.get('run_id'), 'set': 'synth', 'mode': month.get('mode'),
        'variant': month.get('variant'), 'synthetic_documents': month.get('synthetic_documents'),
        'synthetic_responses': month.get('synthetic_responses'), 'scored': False, 'scoring_skipped_reason': reason,
        'documents': len(month.get('documents') or {}), 'packets': len(month.get('packets') or {}),
        'pages': month.get('pages'), 'credits_total': (month.get('credits') or {}).get('total'),
        'cost_usd_at_list': month.get('cost_usd_at_list'),
        'cost_per_page_usd': pct(month.get('cost_usd_at_list') or 0, month.get('pages') or 0),
        'cycle_seconds_total': month.get('cycle_seconds'),
        'cycle_seconds_by_packet': {k: v.get('cycle_seconds') for k, v in (month.get('packets') or {}).items()},
        'classify_predictions': {c['doc_id']: c['predicted'] for c in (month.get('classify') or [])},
    }
    summary.update(reconcile_lines(run_dir, planted_path))
    summary['go_no_go'] = go_no_go(summary)
    return {'summary': summary, 'documents': [], 'go_no_go': summary['go_no_go']}


def score_month(run_dir: pathlib.Path, truth_root: pathlib.Path, manifest: dict, truth_dir=None, planted_path=None):
    """truth_dir None = truth_root/synth (the --set synth path). A --corpus run passes <dir>/truth directly."""
    month = json.loads((run_dir / 'month.json').read_text())
    reason = 'truth/synth absent' if truth_dir is None else f'{truth_dir} absent'
    truth_dir = truth_root / 'synth' if truth_dir is None else pathlib.Path(truth_dir)
    if not truth_dir.exists():
        return counts_only(month, reason, run_dir, planted_path), False
    classes = {d['doc_id']: d['class'] for d in manifest['documents']}
    per = []
    missing = []
    for doc_id, cls in classes.items():
        tp = truth_dir / f'{doc_id}.json'
        doc = (month.get('documents') or {}).get(doc_id)
        if not tp.exists() or doc is None:
            missing.append(doc_id)
            continue
        first = min((d.get('pages') or [1]) for d in manifest['documents'] if d['doc_id'] == doc_id)[0]
        per.append(score_document(doc_id, cls, json.loads(tp.read_text()), doc, page_offset=first - 1))
    if not per:
        return counts_only(month, 'truth/synth present but holds no document truth for this manifest', run_dir, planted_path), False
    s = lambda k: sum(p.get(k, 0) or 0 for p in per)
    cls_rows = month.get('classify') or []
    cls_ok = sum(1 for c in cls_rows if classes.get(c['doc_id']) == c.get('predicted'))
    pages = month.get('pages') or 0
    cost = month.get('cost_usd_at_list') or 0
    summary = {
        'run_id': month.get('run_id'), 'set': 'synth', 'mode': month.get('mode'), 'variant': month.get('variant'),
        'synthetic_documents': month.get('synthetic_documents'), 'synthetic_responses': month.get('synthetic_responses'),
        'scored': True, 'documents_scored': len(per), 'documents_missing_truth': missing,
        'classify_documents': len(cls_rows), 'classify_correct': cls_ok,
        'classify_exact_per_document': pct(cls_ok, len(cls_rows)),
        'critical_field_accuracy': pct(s('critical_correct'), s('critical_scored')),
        'all_field_accuracy': pct(s('fields_correct'), s('fields_scored')),
        'list_length_recall': pct(s('list_pred_rows'), s('list_truth_rows')),
        'citation_coverage': pct(s('cite_present'), s('cite_scored')),
        'citation_text_contains_value': pct(s('cite_text_hits'), s('cite_text_comparable')),
        'citation_page_correct': pct(s('cite_page_hits'), s('cite_page_comparable')),
        'cycle_seconds_total': month.get('cycle_seconds'),
        'cycle_seconds_by_packet': {k: v.get('cycle_seconds') for k, v in (month.get('packets') or {}).items()},
        'pages': pages, 'credits_total': (month.get('credits') or {}).get('total'),
        'credits_by_step': month.get('credits'), 'cost_usd_at_list': cost,
        'cost_per_page_usd': pct(cost, pages),
        'counts': {k: s(k) for k in ['fields_scored', 'fields_correct', 'critical_scored', 'critical_correct',
                                     'list_truth_rows', 'list_pred_rows', 'cite_scored', 'cite_present',
                                     'cite_text_comparable', 'cite_text_hits']},
    }
    summary.update(reconcile_lines(run_dir, planted_path))
    perts = month.get('fixture_perturbations') or []
    if perts:
        summary['fixture_perturbations'] = perts
        summary['fixture_note'] = 'SYNTHETIC responses: the misses below are the labelled perturbations, and cycle/credits are fixture values, not timings'
    summary['go_no_go'] = go_no_go(summary)
    return {'summary': summary, 'documents': per, 'go_no_go': summary['go_no_go']}, True


def print_card(card):
    a = card['summary']
    tag = 'SYNTHETIC DOCUMENTS + SYNTHETIC RESPONSES — not a Pulse measurement' if a.get('synthetic_responses') else 'synthetic documents, live responses'
    print(f"\nSynth month scorecard {a.get('run_id')}  [{tag}]  variant={a.get('variant')}")
    if not a.get('scored'):
        print(f"  {a.get('scoring_skipped_reason')}: no accuracy reported")
        rows = [('Documents', a['documents']), ('Packets', a['packets']), ('Pages', a['pages']),
                ('Credits', a['credits_total']), ('Cost per page ($)', a['cost_per_page_usd']),
                ('Cycle seconds total', a['cycle_seconds_total'])]
    else:
        rows = [('Classify exact (per document)', f"{a['classify_correct']}/{a['classify_documents']}"),
                ('Critical-field accuracy', a['critical_field_accuracy']),
                ('All-field accuracy', a['all_field_accuracy']),
                ('List-length recall', a['list_length_recall']),
                ('Citation coverage', a['citation_coverage']),
                ('Cited text contains value', a['citation_text_contains_value']),
                ('Cycle seconds total', a['cycle_seconds_total']),
                ('Credits / cost per page ($)', f"{a['credits_total']} / {a['cost_per_page_usd']}")]
    for k, v in rows:
        print(f"  {k:30} {v}")
    print('  cycle seconds by packet: ' + json.dumps(a.get('cycle_seconds_by_packet') or {}))
    for d in card['documents']:
        if d['field_errors'] or d['note']:
            print(f"  {d['doc_id']}: errors={[(e['field'], e['predicted']) for e in d['field_errors']][:6]} note={d['note']}")
    print('  go/no-go:')
    for r in card['go_no_go']:
        print(f"    {r['line']:30} measured={r['measured']} target={r['target']} {r['verdict'].upper()}")


def score_and_write(run_dir: pathlib.Path, truth_root: pathlib.Path, corpus=None, out=None):
    """Score one synth-set run and write scorecard.json. score.py and the CLI below both call this.

    corpus None -> the run record's `corpus` if it carries one, else the fixed synth paths (unchanged behaviour).
    For a non-default corpus, truth is <dir>/truth/<doc_id>.json and --truth is not consulted.
    """
    run_meta = json.loads((run_dir / 'run.json').read_text())
    if corpus is None:
        corpus = run_meta.get('corpus')
    elif run_meta.get('corpus') and corpus_paths(corpus)['label'] != corpus_paths(run_meta['corpus'])['label']:
        print(f"WARNING: --corpus {corpus} differs from the run record's corpus {run_meta['corpus']}; scoring against --corpus", file=sys.stderr)
    paths = corpus_paths(corpus)
    manifest = json.loads(paths['manifest'].read_text())
    if paths['default']:
        card, scored = score_month(run_dir, truth_root, manifest)
    else:
        card, scored = score_month(run_dir, truth_root, manifest, truth_dir=paths['truth'],
                                   planted_path=reference_path(manifest, 'planted'))
    out = pathlib.Path(out) if out else run_dir / 'scorecard.json'
    out.write_text(json.dumps(card, indent=1))
    if not scored:
        print('truth/synth absent — scoring skipped' if paths['default'] else f"{card['summary'].get('scoring_skipped_reason')} — scoring skipped")
    print_card(card)
    print(f"\nscorecard: {out}")
    return card, scored


def main():
    ap = argparse.ArgumentParser(description='Score a synth-set run (month.json) against a corpus truth dir.')
    ap.add_argument('--run', required=True, help='runs/<id> (relative to demo/ or absolute)')
    ap.add_argument('--corpus', help='corpus dir holding manifest.json and truth/ (default: the run record, else synth)')
    ap.add_argument('--truth', default=str(HERE / 'truth'), help='truth root for the default synth corpus (truth/synth)')
    ap.add_argument('--out')
    a = ap.parse_args()
    run_dir = pathlib.Path(a.run)
    run_dir = run_dir if run_dir.is_absolute() else HERE / run_dir
    score_and_write(run_dir, pathlib.Path(a.truth), a.corpus, a.out)


if __name__ == '__main__':
    main()
