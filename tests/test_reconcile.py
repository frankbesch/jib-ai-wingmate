#!/usr/bin/env python3
"""Offline tests for reconcile.py — the three customer rules plus extraction exceptions.

The sample month (tests/fixtures/month-sample.json) is hand-built from the values the synthetic
paper prints, with citation boxes lifted from the packet text layer. The test never reads the
planted-defect file: the rules have to find the overbilling from the documents and the customer's
own reference data, which is the only test worth running.

Asserts:
  1. rule_1_decimal fires on exactly one JIB line, routed jv_accountant, delta to the cent.
  2. rule_2_rate fires on exactly one ticket line, routed supply_chain, delta to the cent.
  3. rule_3_afe_ref fires on nothing (all 8 lines tie to the elected AFE and an AFE account code).
  4. Zero false catches: every other JIB line and ticket line lands in clean_lines.
  5. Every exception carries page, bbox and cited text, so the queue can draw the box.
  6. An extraction exception fires when a required field is nulled, routed by document class.
  7. A month with both defects corrected yields zero exceptions.
  8. reconcile never edits month.json and never writes an approver.

Run: python3 tests/test_reconcile.py
"""
import copy
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import reconcile as R  # noqa: E402

SAMPLE = HERE / 'fixtures' / 'month-sample.json'
REFS = ROOT / 'synth' / 'reference'

DOI = R.load(REFS / 'doi.json')
RATES = R.load(REFS / 'contract_rates.json')
ELECTION = R.load(REFS / 'afe_election.json')


def month():
    return json.loads(SAMPLE.read_text())


def run(m):
    out, counts = R.reconcile(m, DOI, RATES, ELECTION)
    return out, counts


def by_rule(out, rule):
    return [e for e in out['exceptions'] if e['rule'] == rule]


def test_sample_is_synthetic_and_shaped():
    m = month()
    assert m['synthetic_documents'] is True
    assert m['set'] == 'synth'
    assert set(m['documents']) == {'afe_cover', 'afe', 'ticket_a', 'ticket_b', 'hauling_log', 'invoice', 'jib'}
    assert len(m['documents']['jib']['values']['lines']) == 8
    assert len(m['documents']['afe']['values']['cost_lines']) == 6


def test_rule_1_fires_on_exactly_one_jib_line():
    out, counts = run(month())
    hits = by_rule(out, 'rule_1_decimal')
    assert len(hits) == 1, hits
    e = hits[0]
    assert e['doc_id'] == 'jib'
    assert e['approver_role'] == 'jv_accountant'
    assert e['status'] == 'open'
    # 96,440.00 gross at 0.26 instead of 0.25 = 964.40 of net overbilled
    assert e['observed']['owner_decimal'] == 0.26
    assert e['expected']['owner_decimal'] == 0.25
    assert e['observed']['net_amount'] == 25074.40
    assert e['expected']['net_amount'] == 24110.00
    assert e['delta_usd'] == 964.40
    assert counts['rule_1_decimal'] == [8, 1]


def test_rule_2_fires_on_exactly_one_ticket_line():
    out, counts = run(month())
    hits = by_rule(out, 'rule_2_rate')
    assert len(hits) == 1, hits
    e = hits[0]
    assert e['doc_id'] == 'ticket_b'
    assert e['approver_role'] == 'supply_chain'
    assert e['observed']['rate'] == 310.0
    assert e['expected']['contract_rate'] == 285.0
    # 25.00 over the sheet across 6 hours = 150.00
    assert e['delta_usd'] == 150.00
    assert counts['rule_2_rate'] == [6, 1]


def test_rule_3_fires_on_nothing():
    out, counts = run(month())
    assert by_rule(out, 'rule_3_afe_ref') == []
    assert counts['rule_3_afe_ref'] == [8, 0]


def test_no_false_catches():
    out, _ = run(month())
    assert len(out['exceptions']) == 2
    assert by_rule(out, 'extraction') == []
    clean_1 = [c for c in out['clean_lines'] if c['rule'] == 'rule_1_decimal']
    clean_2 = [c for c in out['clean_lines'] if c['rule'] == 'rule_2_rate']
    clean_3 = [c for c in out['clean_lines'] if c['rule'] == 'rule_3_afe_ref']
    assert len(clean_1) == 7 and len(clean_2) == 5 and len(clean_3) == 8
    # no line is both fired and clean under the same rule (extraction may call a field present
    # while a money rule calls it wrong — that is two different questions about the same box)
    fired = {(e['doc_id'], e['field_path'], e['rule']) for e in out['exceptions']}
    assert not fired & {(c['doc_id'], c['field_path'], c['rule']) for c in out['clean_lines']}
    assert out['summary'] == {'jib_lines': 8, 'ticket_lines': 6, 'fired': 2, 'clean': len(out['clean_lines'])}


def test_every_exception_carries_a_citation():
    out, _ = run(month())
    for e in out['exceptions']:
        assert e['page'] is not None, e['id']
        assert e['bbox'] is not None and len(e['bbox']) == 4, e['id']
        assert all(0.0 <= v <= 1.0 for v in e['bbox']), e['bbox']
        assert e['cited_text'], e['id']
    ids = [e['id'] for e in out['exceptions']]
    assert ids == sorted(ids) and ids[0] == 'EX-001'


def test_extraction_exception_on_a_nulled_required_field():
    m = month()
    m['documents']['jib']['values']['due_date'] = None
    out, _ = run(m)
    hits = [e for e in by_rule(out, 'extraction') if e['field_path'] == 'due_date']
    assert len(hits) == 1
    assert hits[0]['doc_id'] == 'jib' and hits[0]['approver_role'] == 'jv_accountant'

    m = month()
    m['documents']['ticket_b']['values']['line_items'][1]['quantity'] = None
    out, _ = run(m)
    hits = [e for e in by_rule(out, 'extraction') if e['field_path'] == 'line_items[1].quantity']
    assert len(hits) == 1
    assert hits[0]['doc_id'] == 'ticket_b' and hits[0]['approver_role'] == 'field'


def test_extraction_exception_on_a_short_list():
    m = month()
    m['documents']['jib']['values']['lines'] = m['documents']['jib']['values']['lines'][:6]
    out, _ = run(m)
    hits = [e for e in by_rule(out, 'extraction') if e['field_path'] == 'lines']
    assert len(hits) == 1 and hits[0]['observed'] == 6 and hits[0]['expected'] == 8

    m = month()
    m['documents']['hauling_log']['values']['loads'] = m['documents']['hauling_log']['values']['loads'][:2]
    out, _ = run(m)
    hits = [e for e in by_rule(out, 'extraction') if e['field_path'] == 'loads']
    assert len(hits) == 1 and hits[0]['approver_role'] == 'field'


def test_clean_month_yields_zero_exceptions():
    m = month()
    line = m['documents']['jib']['values']['lines'][2]
    line['owner_decimal'] = 0.25
    line['net_amount'] = round(line['gross_amount'] * 0.25, 2)
    for doc_id in ('ticket_b', 'invoice'):
        for it in m['documents'][doc_id]['values']['line_items']:
            if it['description'] == 'Pump truck, hourly':
                it['rate'] = 285.0
                it['amount'] = round(285.0 * it['quantity'], 2)
    out, counts = run(m)
    assert out['exceptions'] == [], out['exceptions']
    assert out['summary']['fired'] == 0
    assert counts['rule_1_decimal'][1] == 0 and counts['rule_2_rate'][1] == 0


def test_reconcile_never_edits_the_month_and_never_types_an_approver():
    before = hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
    m = month()
    snapshot = copy.deepcopy(m)
    out, _ = run(m)
    assert m == snapshot, 'reconcile mutated the month record it was handed'
    assert hashlib.sha256(SAMPLE.read_bytes()).hexdigest() == before
    blob = json.dumps(out).lower()
    assert 'approver"' not in blob.replace(' ', '')
    for e in out['exceptions']:
        assert 'approver' not in e or e.get('approver') is None
        assert set(e) == {'id', 'rule', 'doc_id', 'field_path', 'page', 'bbox', 'cited_text',
                          'observed', 'expected', 'delta_usd', 'approver_role', 'status', 'message'}
    assert out['synthetic'] is True and out['rules_version'] == '1'


def test_missing_reference_owner_does_not_crash():
    """A DOI with no matching owner number still resolves through the single WI owner."""
    m = month()
    m['documents']['jib']['values']['owner_number'] = 'OW-00000'
    out, _ = run(m)
    assert len(by_rule(out, 'rule_1_decimal')) == 1


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS  {t.__name__}')
        except AssertionError as e:
            failed += 1
            print(f'FAIL  {t.__name__}: {e}')
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f'ERROR {t.__name__}: {type(e).__name__}: {e}')
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
