#!/usr/bin/env python3
"""Offline tests for the joint-interest month: --set synth pipeline, fixtures, and the synth scorer.

No network, no key, no truth needed: everything runs against runs/fixture-synth-01, which
`make_fixtures.py --set synth && pipeline.py --mode fixture --set synth --run-id fixture-synth-01` writes.

  1. month.json matches the MONTH RECORD CONTRACT (keys, packets, classify, documents, credits, timing).
  2. citation keys use the flattened list form  lines[3].net_amount.
  3. two field tickets in one packet map to two ordered split topics; the one-ticket fallback is explicit
     and copies nothing from the other ticket.
  4. the two planted defects survive the fixture, and the three fixture perturbations show up where declared.
  5. scorer math on a hand-built three-field truth, plus list-length recall and citation counting.
  6. --corpus <dir> (S2.0): a two-document temp corpus runs make_fixtures -> pipeline -> score_synth, the run
     record carries corpus, and the score reads <dir>/truth. Everything it writes stays in a temp dir.

Run: python3 tests/test_synth_pipeline.py
"""
import json, pathlib, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import pipeline as P
import score_synth as S

RUN = HERE / 'runs' / 'fixture-synth-01'
MANIFEST = json.loads((HERE / 'synth' / 'manifest.json').read_text())


def month():
    if not (RUN / 'month.json').exists():
        raise SystemExit('runs/fixture-synth-01/month.json is missing: run\n'
                         '  python3 make_fixtures.py --set synth && python3 pipeline.py --mode fixture --set synth --run-id fixture-synth-01')
    return json.loads((RUN / 'month.json').read_text())


def test_month_record_contract():
    m = month()
    for k in ['run_id', 'mode', 'set', 'synthetic_documents', 'synthetic_responses', 'started', 'finished',
              'packets', 'classify', 'documents', 'timing', 'credits', 'cycle_seconds', 'cost_usd_at_list']:
        assert k in m, f'month.json is missing {k}'
    assert m['set'] == 'synth' and m['mode'] == 'fixture'
    assert m['synthetic_documents'] is True and m['synthetic_responses'] is True
    assert set(m['packets']) == {'day01', 'day12', 'day30'}
    for pid, p in m['packets'].items():
        for k in ['file', 'pages', 'extract', 'split', 'schema']:
            assert k in p, f'{pid} packet block is missing {k}'
        for k in ['extraction_id', 'page_count', 'credits_used', 'failed_pages', 'seconds']:
            assert k in p['extract'], f'{pid} extract is missing {k}'
        assert set(p['split']) >= {'split_id', 'splits', 'credits_used', 'seconds'}
    assert len(m['classify']) == 7 and all(set(c) >= {'doc_id', 'file', 'predicted', 'credits_used', 'seconds'} for c in m['classify'])
    ids = {d['doc_id'] for d in MANIFEST['documents']}
    assert set(m['documents']) == ids
    for doc_id, d in m['documents'].items():
        for k in ['class', 'packet', 'pages', 'values', 'citations', 'credits_used', 'seconds', 'note']:
            assert k in d, f'{doc_id} is missing {k}'
        assert d['class'] == next(x['class'] for x in MANIFEST['documents'] if x['doc_id'] == doc_id)
        assert d['values'], f'{doc_id} came back with no values'
    assert m['credits']['total'] > 0 and m['cost_usd_at_list'] > 0 and m['cycle_seconds'] > 0


def test_classify_and_split_pages():
    m = month()
    truth_cls = {d['doc_id']: d['class'] for d in MANIFEST['documents']}
    assert all(truth_cls[c['doc_id']] == c['predicted'] for c in m['classify']), 'fixture classify should be exact'
    for pk in MANIFEST['packets']:
        got = m['packets'][pk['packet_id']]['split']['splits']
        pages = sorted(p for v in got.values() for p in v)
        assert pages == list(range(1, pk['pages'] + 1)), f"{pk['packet_id']} split does not cover every page once"


def test_citation_key_form():
    m = month()
    jib = m['documents']['jib']['citations']
    assert 'lines[3].net_amount' in jib, sorted(jib)[:8]
    c = jib['lines[3].net_amount']
    assert set(c) == {'page', 'bbox', 'text', 'ref'} and c['page'] in (1, 2) and c['ref']
    assert 'afe_number' in m['documents']['afe']['citations']
    assert 'cost_lines[5].amount' in m['documents']['afe']['citations']
    # F3: the invoice total citation is dropped on purpose, so coverage is measurably below 1.0
    assert 'total' not in m['documents']['invoice']['citations']


def test_two_tickets_in_one_packet():
    m = month()
    a, b = m['documents']['ticket_a'], m['documents']['ticket_b']
    assert a['topic'] == 'field_ticket_1' and b['topic'] == 'field_ticket_2'
    assert a['pages'] == [1] and b['pages'] == [2]
    assert a['values']['ticket_number'] != b['values']['ticket_number']
    assert a['note'] is None and b['note'] is None


def test_one_ticket_fallback_is_explicit():
    docs = [d for d in MANIFEST['documents'] if d['packet'] == 'day12']
    mapping, notes = P._ticket_topic_map(docs, {'field_ticket_1': [2], 'hauling_log': [3], 'invoice': [4]})
    assert mapping['field_ticket_1'] == 'ticket_b', 'the returned pages decide which ticket it is'
    assert 'ticket_a' in notes and 'no values' in notes['ticket_a']
    assert 'ticket_b' not in notes
    none_back, notes2 = P._ticket_topic_map(docs, {'invoice': [4]})
    assert set(notes2) == {'ticket_a', 'ticket_b'}
    assert 'field_ticket_1' not in none_back and 'field_ticket_2' not in none_back
    assert none_back == {'hauling_log': 'hauling_log', 'invoice': 'invoice'}


def test_planted_defects_and_perturbations_survive():
    m = month()
    jib = m['documents']['jib']['values']
    assert jib['lines'][2]['owner_decimal'] == 0.26, 'P1 must survive the fixture'
    assert jib['lines'][2]['net_amount'] == 25074.4
    assert all(l['owner_decimal'] == 0.25 for i, l in enumerate(jib['lines']) if i != 2)
    assert m['documents']['ticket_b']['values']['line_items'][0]['rate'] == 310.0, 'P2 must survive the fixture'
    assert m['documents']['invoice']['values']['line_items'][3]['rate'] == 310.0
    afe_codes = {c['account_code'] for c in m['documents']['afe']['values']['cost_lines']}
    assert all(l['afe_ref'] == 'AFE-2026-0417' and l['account_code'] in afe_codes for l in jib['lines']), 'rule 3 must fire on nothing'
    assert jib['lines'][7]['gross_amount'] == 9640.0, 'F1 retired 2026-09-05: the printed gross survives; no fixture-made false catch'
    assert m['documents']['hauling_log']['values']['loads'][4]['barrels'] is None, 'F2 null'


def test_scorer_math_on_hand_built_truth():
    """Three scalar fields, one of them wrong; plus a two-row list where the model returned one row."""
    truth = {'doc_id': 'jib', 'values': {'statement_period': 'June 2026', 'property_number': 'TX-04412', 'gross_total': 111111.0},
             'page_of': {'statement_period': 1}}
    with tempfile.TemporaryDirectory() as td:
        troot = pathlib.Path(td)
        (troot / 'synth').mkdir()
        (troot / 'synth' / 'jib.json').write_text(json.dumps(truth))
        card, scored = S.score_month(RUN, troot, MANIFEST)
    assert scored is True
    a = card['summary']
    assert a['documents_scored'] == 1 and sorted(a['documents_missing_truth']) == ['afe', 'afe_cover', 'hauling_log', 'invoice', 'ticket_a', 'ticket_b']
    assert a['counts']['fields_scored'] == 3 and a['counts']['fields_correct'] == 2
    assert a['all_field_accuracy'] == 0.6667
    assert a['counts']['critical_scored'] == 3 and a['critical_field_accuracy'] == 0.6667
    assert a['classify_exact_per_document'] == 1.0
    assert a['citation_coverage'] == 1.0
    assert a['counts']['cite_text_hits'] == 2, 'the drifted gross_total is not in the cited text'
    assert a['citation_page_correct'] == 1.0
    gng = {r['line']: r for r in card['go_no_go']}
    assert gng['classify_exact_per_document']['verdict'] == 'pass'
    assert gng['critical_field_accuracy']['verdict'] == 'miss'
    assert gng['cost_per_page_usd']['verdict'] == 'report-only'


def test_scorer_list_length_recall_and_nulls():
    truth = {'doc_id': 'hauling_log', 'values': {'total_barrels': 590.0,
             'loads': [{'load_no': i + 1, 'barrels': b} for i, b in enumerate([118.0, 122.5, 115.0, 124.5, 110.0])]}}
    m = month()
    doc = m['documents']['hauling_log']
    d = S.score_document('hauling_log', 'hauling_log', truth, doc)
    assert d['list_truth_rows'] == 5 and d['list_pred_rows'] == 5
    assert d['critical_scored'] == 6, 'total_barrels + five load barrels'
    assert d['critical_correct'] == 5, 'the nulled fifth load barrels misses'
    assert 'loads[4].barrels' in d['nulls']
    # a model that returned three of five rows scores 0.6 recall
    short = {'total_barrels': 590.0, 'loads': (doc['values']['loads'] or [])[:3]}
    d2 = S.score_document('hauling_log', 'hauling_log', truth, {'values': short, 'citations': {}})
    assert d2['list_pred_rows'] == 3 and S.pct(d2['list_pred_rows'], d2['list_truth_rows']) == 0.6


def test_scorer_skips_when_truth_absent():
    with tempfile.TemporaryDirectory() as td:
        card, scored = S.score_month(RUN, pathlib.Path(td), MANIFEST)
    assert scored is False
    a = card['summary']
    assert a['scored'] is False and a['scoring_skipped_reason'] == 'truth/synth absent'
    assert a['documents'] == 7 and a['pages'] == 9 and a['cost_per_page_usd'] is not None
    # accuracy lines need truth; the reconcile and cycle lines come from exceptions.json and month.json and may be measured
    ACCURACY = {'classify_exact_per_document', 'critical_field_accuracy', 'all_field_accuracy', 'list_length_recall',
                'citation_coverage', 'citation_text_contains_value'}
    assert all(r['verdict'] in ('not-measurable', 'report-only') for r in card['go_no_go'] if r['line'] in ACCURACY)
    assert all(r['target_source'].startswith('plan §2') for r in card['go_no_go'])


def _cli(*args):
    """Run a demo script as the user would, offline: fixture mode only, PULSE_API_KEY removed from the env."""
    import os, subprocess
    env = {k: v for k, v in os.environ.items() if k != 'PULSE_API_KEY'}
    r = subprocess.run([sys.executable, *args], cwd=HERE, env=env, capture_output=True, text=True)
    assert r.returncode == 0, f'{args} exited {r.returncode}\n{r.stdout}\n{r.stderr}'
    return r.stdout


def test_corpus_flag_on_temp_corpus():
    """S2.0: --corpus <dir> runs make_fixtures -> pipeline (fixture) -> score_synth on a tiny temp corpus.

    Two documents in one packet (day01: afe_cover + afe) copied from synth/, a manifest in the synth shape with no
    references.book (so the fixture replays the temp truth), and truth/<doc_id>.json copied from truth/synth. One
    temp truth value is changed after the run, so the scorer can only report that error if it reads the temp truth.
    """
    src = [d for d in MANIFEST['documents'] if d['packet'] == 'day01']
    pk = next(p for p in MANIFEST['packets'] if p['packet_id'] == 'day01')
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td).resolve()
        (root / 'pdf').mkdir(); (root / 'truth').mkdir()
        docs = []
        for d in src:
            f = root / 'pdf' / pathlib.Path(d['file']).name
            f.write_bytes((HERE / d['file']).read_bytes())
            docs.append(dict(d, file=str(f), scan_file=str(f)))
            (root / 'truth' / f"{d['doc_id']}.json").write_text((HERE / 'truth' / 'synth' / f"{d['doc_id']}.json").read_text())
        pf = root / 'pdf' / 'day01.pdf'
        pf.write_bytes((HERE / pk['file']).read_bytes())
        manifest = {'built': 'test', 'synthetic': True, 'story': 'S2.0 temp corpus', 'documents': docs,
                    'packets': [dict(pk, file=str(pf), scan_file=str(pf))], 'references': {}}
        (root / 'manifest.json').write_text(json.dumps(manifest))
        run = root / 'run'  # absolute run id: pipeline writes HERE/runs/<abs> == <abs>, so nothing lands in demo/runs

        out = _cli('make_fixtures.py', '--corpus', str(root))
        assert 'perturbations: none' in out, out
        fx = json.loads((root / 'fixtures' / 'responses' / 'day01.json').read_text())
        assert fx['perturbations'] == [] and 'replay layer-A truth' in fx['source']
        assert set(fx['schema']['results']) == {'afe_cover', 'afe'}

        _cli('pipeline.py', '--mode', 'fixture', '--corpus', str(root), '--run-id', str(run))
        rj = json.loads((run / 'run.json').read_text())
        mj = json.loads((run / 'month.json').read_text())
        assert rj['set'] == 'synth' and rj['corpus'] == str(root) and rj['mode'] == 'fixture'
        assert mj['set'] == 'synth' and mj['corpus'] == str(root)
        assert rj['documents'] == ['afe_cover', 'afe'] and rj['packets'] == ['day01']
        assert set(mj['documents']) == {'afe_cover', 'afe'} and all(v['values'] for v in mj['documents'].values())
        assert 'fixture_perturbations' not in mj

        t = json.loads((root / 'truth' / 'afe.json').read_text())
        t['values']['afe_number'] = 'AFE-S20-TEMP'
        (root / 'truth' / 'afe.json').write_text(json.dumps(t))

        _cli('score_synth.py', '--run', str(run), '--corpus', str(root))
        card = json.loads((run / 'scorecard.json').read_text())
        a = card['summary']
        assert a['scored'] is True and a['documents_scored'] == 2 and a['documents_missing_truth'] == []
        assert a['classify_correct'] == 2 and a['classify_documents'] == 2
        afe = next(d for d in card['documents'] if d['doc_id'] == 'afe')
        assert {'field': 'afe_number', 'truth': 'AFE-S20-TEMP', 'predicted': 'AFE-2026-0417'} in afe['field_errors']
        assert [e['field'] for e in afe['field_errors']] == ['afe_number'], afe['field_errors']

        # score.py with no --corpus takes the corpus from the run record and must produce the same card
        _cli('score.py', '--run', str(run), '--out', str(root / 'scorecard-via-score.json'))
        assert json.loads((root / 'scorecard-via-score.json').read_text()) == card

        # --corpus synth resolves to exactly the fixed synth paths
        p = S.corpus_paths('synth')
        assert p['default'] and p['label'] == 'synth' and p['truth'] == HERE / 'truth' / 'synth'
        assert p['fixtures'] == HERE / 'fixtures' / 'responses' / 'synth' and S.corpus_paths(None)['label'] is None


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for t in tests:
        t(); print(f'PASS {t.__name__}')
    print(f'{len(tests)}/{len(tests)} passed')
