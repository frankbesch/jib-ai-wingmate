#!/usr/bin/env python3
"""Offline test for the split-mode /schema path (no network, no key).

1. parse_split_schema on the documented example (the parser's API reference, /schema endpoint, 2026-09-04).
2. run_live end to end with a fake client: the fake serves the saved live-clean-02 raw classify/extract/split for
   917669 and answers /schema in split mode. Asserts the request shape (split_id + split_schema_config with only the
   topics that have pages), the record shape score.py/console read, and that citations resolve through the extract.
3. The 907829 case (1 page, no plat): plat topic must be omitted from the request and recorded as not run.
4. --schema-mode single still produces the live-clean-02 record shape.

Run: python3 tests/test_split_schema.py
"""
import json, pathlib, sys, tempfile
HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import pipeline as P

RAW = HERE / 'runs' / 'live-clean-02' / 'raw'
CFG = {'classify': P.load('schemas/classify_config.json'), 'split': P.load('schemas/split_config.json'), 'w1': P.load('schemas/w1_permit.json'), 'plat': P.load('schemas/plat.json')}

DOC_EXAMPLE = {"schema_id": "schema-uuid-789", "split_id": "split-uuid-123",
               "results": {"financial_statements": {"values": {"revenue": 5000000, "expenses": 3200000}, "citations": {"revenue": {"page": 15, "bbox": [100, 200, 300, 220]}}},
                           "signatures": {"values": {"signee_name": "Jane Doe", "date_signed": "2024-01-15"}, "citations": {}}}}


def test_parse_documented_example():
    out = P.parse_split_schema(DOC_EXAMPLE, ['financial_statements', 'signatures', 'missing'])
    assert out['financial_statements']['values']['revenue'] == 5000000
    assert out['financial_statements']['citations']['revenue']['page'] == 15
    assert out['signatures']['citations'] == {}
    assert out['missing'] is None
    wrapped = {'schema_output': {'results': DOC_EXAMPLE['results']}}
    assert P.parse_split_schema(wrapped, ['signatures'])['signatures']['values']['signee_name'] == 'Jane Doe'


class FakeClient:
    """Serves saved raw responses; records every /schema request."""
    base = 'fake://'

    def __init__(self, permit):
        self.permit = permit; self.schema_requests = []
        self.extract = json.loads((RAW / f'{permit}__extract.json').read_text())
        self.split = json.loads((RAW / f'{permit}__split.json').read_text())

    def resolve(self, r):
        return r

    def post_multipart(self, path, file_path, fields):
        if path == '/classify':
            return {'classify_output': {'classification': 'w1_permit'}, 'credits_used': 0.5}
        if path == '/extract':
            return self.extract
        raise AssertionError(path)

    def post_json(self, path, payload):
        if path == '/split':
            return self.split
        assert path == '/schema'
        self.schema_requests.append(payload)
        if 'split_id' in payload:
            # cite a real cell id from this packet's extract so the resolver has something to resolve
            cell = self.extract['bounding_boxes']['Tables'][0]['cell_data'][0]['id']
            res = {t: {'values': {'api_number': '42-000-00000'} if t == 'w1_permit' else {'surveyor': 'X'},
                       'citations': {'api_number': cell} if t == 'w1_permit' else {}} for t in payload['split_schema_config']}
            return {'schema_id': 'fake-split-schema', 'split_id': payload['split_id'], 'results': res, 'credits_used': 3.0}
        return {'schema_id': 'fake-single', 'schema_output': {'values': {'api_number': '42-000-00000'}, 'citations': {}}, 'credits_used': 2.0}


def run(permit, mode):
    client = FakeClient(permit)
    docs = [{'file': f'corpus/packets/clean/{permit}.pdf', 'permit': permit}]
    with tempfile.TemporaryDirectory() as td:
        rawdir = pathlib.Path(td)
        rec = P.run_live(client, permit, HERE / f'corpus/packets/clean/{permit}.pdf', docs, CFG, rawdir, mode)
        files = sorted(p.name for p in rawdir.iterdir())
    return client, rec, files


def test_split_mode_horizontal_packet():
    client, rec, files = run('917669', 'split')
    assert len(client.schema_requests) == 1, 'split mode is one /schema call'
    req = client.schema_requests[0]
    assert req['split_id'] == client.split['split_id']
    assert set(req['split_schema_config']) == {'w1_permit', 'plat'}
    w1 = req['split_schema_config']['w1_permit']
    assert w1['schema'] is CFG['w1'] and 'SURFACE location' in w1['schema_prompt']
    assert rec['schema_mode'] == 'split'
    assert rec['schema_w1']['pages'] == [1, 2, 3] and rec['schema_plat']['pages'] == [4]
    assert rec['schema_w1']['values']['api_number'] == '42-000-00000'
    c = rec['schema_w1']['citations']['api_number']
    assert c['page'] == 1 and c['bbox'] and c['ref'], c
    assert rec['credits']['schema_split'] == 3.0 and rec['credits']['total'] > 3.0
    assert rec['cycle_seconds'] is not None and rec['cost_usd_at_list'] > 0
    assert '917669__schema_split.json' in files and '917669__schema_w1.json' not in files


def test_split_mode_no_plat_pages():
    client, rec, files = run('907829', 'split')
    req = client.schema_requests[0]
    assert set(req['split_schema_config']) == {'w1_permit'}, 'plat has no pages → not sent'
    assert rec['schema_plat']['values'] == {} and 'no pages' in rec['schema_plat']['note']
    assert rec['schema_w1']['values']['api_number'] == '42-000-00000'


def test_single_mode_reproduces_old_shape():
    client, rec, files = run('917669', 'single')
    assert len(client.schema_requests) == 2 and all('extraction_id' in r for r in client.schema_requests)
    assert rec['schema_mode'] == 'single' and rec['schema_w1']['schema_mode'] == 'single'
    assert rec['credits']['schema_w1'] == 2.0 and rec['credits']['schema_plat'] == 2.0
    assert {'917669__schema_w1.json', '917669__schema_plat.json'} <= set(files)


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for t in tests:
        t(); print(f'PASS {t.__name__}')
    print(f'{len(tests)}/{len(tests)} passed')
