#!/usr/bin/env python3
"""Offline tests for typed/jev_backend.py and the runner's --backend jev path. No network, no key, no spend.

Asserts:
  1. Request shape: choice carries every option as a criteria key and needs_review has text; noul has
     no criteria; a row-8 batch carries one noul question per field; the body has state, model, questions only.
  2. parse_response returns the runner's answer contract for choice, noul, and batch.
  3. Malformed responses raise JevShape: not an object, missing usage, bool or negative tokens, wrong
     answer type, probability keys not equal to the option set, NaN, >1, bool, choice outside the set,
     noul out of range. A batch with one field missing parses, and the runner scores that field as an error.
  4. Fixture run with --backend jev: same plants as the claude fixture (row1 7/5/1/1, row5 3/1/1/1),
     85 units, errors 0, report.md carries SYNTHETIC and no dollar claim other than no spend.
  5. Dry-run with --backend jev and no key: exit 0, 26 requests, 85 questions, network_calls 0,
     socket guard on, key_ready false, 26 body files with no Bearer string.
  6. Live with no key exits 2. Dry-run over --max-spend exits 2. NaN --max-spend exits 2.
  7. The socket guard blocks a real connection attempt.
  8. ask() with a stubbed http: 200 returns an answer and metered cost = input_tokens * 0.042 / 1e6;
     401 and 422 return an error and no answer; 429 retries then succeeds; a shape mismatch keeps the
     billed tokens; the key never appears in the env record or the error string.
  9. redact scrubs the key and any Bearer token.
 10. Live loop in-process with a stubbed http and a fake key: a full run writes 26 calls with the raw
     redacted response and the sent body; a falsified bound, three 422s, and three dropped connections each
     stop the run with exit 3 and an INCOMPLETE report; dropped calls are charged at the bound; a run whose
     bound passes --max-spend makes no billed call; a 401 on the auth check exits 2 before any billed call;
     no output file holds the key.
 11. Parity hash across backends: with --parity settings (claude row 8 per field, jev per document) every one
     of the 85 units hashes equal on both sides; a changed document, option text, or field text changes the
     hash; `--mode parity-check --parity` prints `parity 85 of 85`, exit 0; without --parity it exits 1; the
     fixture runs of both backends record equal parity_sha256 per unit, 85 of 85.
 12. Disagree-off with Jev: a Jev choice that disagrees with its own top probability abstains by default
     and answers in parity mode.
 13. Default byte-identity: jev dry-run bodies match prompt_sha256 of the J4 run, 26 of 26 (skipped if the
     artifact is absent).
 14. Cascade live loop in-process, Jev http and the claude subprocess both stubbed, fake key: Jev answers
     row 1 at 0.70, row 5 at 0.60, and every row-8 `total` at 0.79 (escalate); all else at 0.90 (stays with Jev).
     report.json: 26 Jev requests, 13 Claude calls (row1 7, row5 3, row8 3), 39 calls, 6 escalated abstains,
     wrong split sums to the node total, served model logged, Jev cost = 26 x 100 tokens, latency sums per
     backend; every escalated unit carries equal parity hashes; no output file holds the key. Jev answers
     page day12:p3 with needs_review at 0.85: that unit is not escalated and goes to a person (abstain).
 15. Cascade cap counts both halves: a fixture run with --cap 28 stops at 28 calls (Jev + Claude), exit 3,
     INCOMPLETE; a live run whose Jev requests alone pass --cap exits 2 before any billed call.
 16. Cascade dry-run: exit 0, 26 requests, 85 questions, Jev estimate and bound, Claude upper bound 85,
     parity 85 of 85, network_calls 0, socket guard on, key not ready.
 17. Cascade Jev breaker (review finding 1): HTTP 500 on every POST while every Claude call succeeds. The
     Claude successes must not reset the Jev count: exit 3, stopped = 3 consecutive Jev errors, 3 Jev requests,
     jev_errors 3, escalated_by_reason jev_error; the unit whose Claude call was cut is an error unit.
 18. Cascade bound falsified: Jev bills 60000 tokens on call 1 -> exit 3, stopped 'bound falsified', 1 Jev request.
 19. Cascade Claude breaker: Jev answers every unit at 0.5 (all escalate) and every claude call fails ->
     exit 3, stopped = 3 consecutive Claude errors, 3 Claude calls.
 20. calls.jsonl is flushed per record: during Jev POST 3 the file on disk already holds the records of
     requests 1 and 2.
Run: python3 tests/test_jev_backend.py
"""
import json, math, os, pathlib, subprocess, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from typed import typed_questions as tq  # noqa: E402
from typed import jev_backend as jev  # noqa: E402

RUNNER = str(ROOT / 'typed' / 'typed_questions.py')
KEY = 'k' * 40
ENV = {k: v for k, v in os.environ.items() if k != jev.KEY_ENV}

def run(*args, env=ENV):
    return subprocess.run([sys.executable, RUNNER, '--backend', 'jev', *args], capture_output=True, text=True, env=env)

class FakeProc:
    def __init__(self, stdout='', stderr='', rc=0): self.stdout, self.stderr, self.returncode = stdout, stderr, rc

def rejects(r, body):
    try:
        jev.parse_response(r, body)
    except jev.JevShape:
        return True
    return False

def main():
    run_dir = ROOT / 'runs' / 'live-synth-03'
    if not run_dir.exists():
        print('SKIP: runs/live-synth-03 not present (gitignored run output)'); return 0
    manifest = tq.load(ROOT / 'synth' / 'manifest.json')
    docs, packets, page_text, truth = tq.build_inputs(run_dir, manifest, ROOT / 'truth' / 'synth')
    reqs = tq.make_requests({1, 4, 5, 8}, docs, packets, page_text, truth, 'per-document')
    ch = next(r for r in reqs if r['node'] == 'row4')
    no = next(r for r in reqs if r['node'] == 'row5')
    ba = next(r for r in reqs if r['node'] == 'row8')

    b = jev.build_request(ch)                                                                             # 1
    assert sorted(b) == ['model', 'questions', 'state'] and b['model'] == 'jev-1.13.0' and b['state'] == ch['text']
    q = b['questions'][jev.QID]
    assert q['type'] == 'choice' and list(q['criteria']) == ch['options'] and q['criteria']['needs_review']
    assert not any(o.startswith('field_ticket_') for o in q['criteria'])
    assert jev.build_request(no)['questions'][jev.QID] == {'type': 'noul', 'instructions': jev.DOMAIN + no['question']}
    bq = jev.build_request(ba)['questions']
    assert list(bq) == ba['fields'] and all(v['type'] == 'noul' for v in bq.values())

    usage = {'input_tokens': 100, 'output_tokens': 0}                                                     # 2
    probs = {o: 0.0 for o in ch['options']}; probs[ch['label']] = 0.9; probs['needs_review'] = 0.1
    good_c = {'model': 'jev-1.13.0', 'usage': usage,
              'answers': {'q': {'type': 'choice', 'choice': ch['label'], 'probabilities': probs, 'confidence': 0.88}}}
    ans, toks, _ = jev.parse_response(ch, good_c)
    assert toks == 100 and tq.score(ch, ans)['correct']
    for mode in ('verbatim', 'short'):                                                                    # 1b field descriptions
        dr = tq.make_requests({8}, docs, packets, page_text, truth, 'per-document', mode)
        assert len(dr) == 7 and sum(len(r['fields']) for r in dr) == 66
        for r in dr:
            assert list(r['descriptions']) == r['fields'] and all(r['descriptions'].values())
            qs = jev.build_request(r)['questions']
            assert all(' The field means: ' + r['descriptions'][f] in qs[f]['instructions'] for f in r['fields'])
            assert 'with what each one means' in tq.prompt_for(r)
        inv = next(r for r in dr if r['subject'] == 'invoice')
        if mode == 'short':
            assert inv['descriptions']['total'] == 'Invoice total as printed', inv['descriptions']['total']
            assert inv['descriptions']['log_number'] == 'Log or manifest number printed in the header'      # decoy: home schema
        else:
            assert 'never sum' in inv['descriptions']['total']
    assert all('descriptions' not in r or r['descriptions'] is None for r in reqs), 'descriptions must be off by default'
    assert all(not r.get('option_descriptions') for r in reqs), 'option descriptions must be off by default'
    for mode in ('verbatim', 'short'):                                                                    # 1c option descriptions
        orq = tq.make_requests({1, 4}, docs, packets, page_text, truth, 'per-document', 'none', mode)
        assert len(orq) == 16
        for r in orq:
            crit = jev.build_request(r)['questions'][jev.QID]['criteria']
            assert list(crit) == r['options'] and all(isinstance(v, str) and v for v in crit.values())
            assert crit['needs_review'] == 'The evidence is thin.' and 'with what each one means' in tq.prompt_for(r)
            assert not any('FIRST' in v or 'SECOND' in v for v in crit.values()), 'ordinal text leaked into row 4'
        c1 = jev.build_request(next(r for r in orq if r['node'] == 'row1'))['questions'][jev.QID]['criteria']
        c4 = jev.build_request(next(r for r in orq if r['node'] == 'row4'))['questions'][jev.QID]['criteria']
        assert c4['field_ticket'].startswith('A field ticket has')
        if mode == 'verbatim':
            assert c1['afe_cover'].endswith('it is afe_cover, not afe.')
        else:
            assert c1['afe_cover'] == 'A one-page LETTER on operator letterhead addressed to a working-interest owner'
    base = tq.make_requests({1, 4, 5, 8}, docs, packets, page_text, truth, 'per-document', 'short', 'verbatim')   # 1d items 2 and 3
    gen = tq.make_requests({8}, docs, packets, page_text, truth, 'per-document', 'short', 'none', 'generic')
    for r in gen:
        qs = jev.build_request(r)['questions']
        assert all(v['instructions'].endswith(tq.UNLABELLED_GENERIC) for v in qs.values()) and tq.UNLABELLED_GENERIC in tq.prompt_for(r)
    fix = tq.make_requests({8}, docs, packets, page_text, truth, 'per-document', 'short', 'none', 'generic-fixed')
    for r, g in zip(fix, gen):
        qf, qg = jev.build_request(r)['questions'], jev.build_request(g)['questions']
        for f in r['fields']:
            d = r['descriptions'][f]
            assert qf[f]['instructions'].endswith(d + '.' + tq.UNLABELLED_GENERIC), qf[f]['instructions']
            assert qg[f]['instructions'].endswith(d + tq.UNLABELLED_GENERIC) and '..' not in qf[f]['instructions']
            assert qf[f]['instructions'].replace(d + '.', d, 1) == qg[f]['instructions'], 'the full stop must be the only difference'
    fv = tq.make_requests({8}, docs, packets, page_text, truth, 'per-document', 'verbatim', 'none', 'generic-fixed')
    assert all('..' not in v['instructions'] for r in fv for v in jev.build_request(r)['questions'].values())
    tgt = tq.make_requests({8}, docs, packets, page_text, truth, 'per-document', 'short', 'none', 'targeted')
    b8 = {r['subject']: r for r in base if r['node'] == 'row8'}
    changed = [(r['subject'], f) for r in tgt for f in r['fields'] if r['descriptions'][f] != b8[r['subject']]['descriptions'][f]]
    assert changed == [('invoice', 'vendor_name')], changed
    assert 'letterhead' in next(r for r in tgt if r['subject'] == 'invoice')['descriptions']['vendor_name']
    assert not any(r.get('hint') for r in tgt)
    cont = tq.make_requests({4}, docs, packets, page_text, truth, 'per-document', 'none', 'verbatim', 'none', 'software')
    soft = [(r['subject'], r['inherit'], r['label']) for r in cont if r.get('software')]
    assert soft == [('day01:p3', 'day01:p2', 'afe'), ('day30:p2', 'day30:p1', 'jib_statement')], soft
    assert len([r for r in cont if not r.get('software')]) == 7
    assert tq.is_continuation('AFE-1 — page 2 of 2\n\nbody') and tq.is_continuation('Page 3 of 5')
    assert not tq.is_continuation('page 1 of 2') and not tq.is_continuation('x' * 300 + ' page 2 of 2') and not tq.is_continuation('page 3 of 2')
    assert not any(r.get('software') for r in reqs) and not any(r.get('hint') for r in reqs)
    with tempfile.TemporaryDirectory() as td:
        o = run('--mode', 'fixture', '--rows', '4', '--option-desc', 'verbatim', '--continuation', 'software', '--out', td)
        assert o.returncode == 0, o.stderr
        rep = json.loads((pathlib.Path(td) / 'report.json').read_text())
        assert (rep['calls'], rep['model_calls'], rep['software_units'], rep['units'], rep['errors']) == (9, 7, 2, 9, 0), rep
        assert rep['nodes']['row4']['correct'] == 9
        recs = [json.loads(l) for l in (pathlib.Path(td) / 'calls.jsonl').read_text().splitlines()]
        inh = [r for r in recs if r.get('software')]
        assert [r['score']['inherited'] for r in inh] == ['day01:p2', 'day30:p1'] and all(r['cost_usd'] is None for r in inh)
    good_n = {'model': 'jev-1.13.0', 'usage': usage, 'answers': {'q': {'type': 'noul', 'noul': 0.5}}}
    ans, _, _ = jev.parse_response(no, good_n)
    assert ans == {'answer': True, 'p_true': 0.5} and tq.score(no, ans)['abstain']
    good_b = {'model': 'jev-1.13.0', 'usage': usage,
              'answers': {f: {'type': 'noul', 'noul': 0.97 if v else 0.02} for f, v in ba['label'].items()}}
    ans, _, _ = jev.parse_response(ba, good_b)
    assert all(u['correct'] for u in tq.score(ba, ans)['fields'].values())

    def c(**kw):                                                                                          # 3
        a = dict(good_c['answers']['q'], **kw)
        return dict(good_c, answers={'q': a})
    bad = [
        (ch, 'x'), (ch, {'model': 'm', 'answers': {}}), (ch, dict(good_c, usage={'input_tokens': True})),
        (ch, dict(good_c, usage={'input_tokens': -1})), (ch, dict(good_c, answers=[])), (ch, c(type='noul')),
        (ch, c(probabilities={'afe': 1.0})), (ch, c(probabilities=dict(probs, afe=math.nan))),
        (ch, c(probabilities=dict(probs, afe=1.7))), (ch, c(probabilities=dict(probs, afe=True))),
        (ch, c(choice='field_ticket_9')), (no, dict(good_n, answers={'q': {'type': 'noul', 'noul': 1.2}})),
        (no, dict(good_n, answers={'q': {'type': 'noul', 'noul': '0.9'}})), (no, dict(good_n, answers={})),
        (ba, dict(good_b, answers=dict(good_b['answers'], **{ba['fields'][0]: {'type': 'choice'}}))),
    ]
    for r, body in bad:
        assert rejects(r, body), f'accepted {body!r}'
    short = dict(good_b, answers={f: a for f, a in good_b['answers'].items() if f != ba['fields'][0]})
    ans, _, _ = jev.parse_response(ba, short)
    s = tq.score(ba, ans)['fields']
    assert s[ba['fields'][0]]['error'] and sum(1 for u in s.values() if u['error']) == 1

    with tempfile.TemporaryDirectory() as td:                                                             # 4
        out = run('--mode', 'fixture', '--out', td)
        assert out.returncode == 0, out.stderr
        rep = json.loads((pathlib.Path(td) / 'report.json').read_text())
        assert rep['synthetic'] is True and rep['calls'] == 26 and rep['units'] == 85 and rep['errors'] == 0, rep
        assert rep['backend'].startswith('jev') and rep['cost_usd'] == 0
        r1, r5 = rep['nodes']['row1'], rep['nodes']['row5']
        assert (r1['n'], r1['correct'], r1['abstain'], r1['wrong_not_abstained'], r1['error']) == (7, 5, 1, 1, 0), r1
        assert (r5['n'], r5['correct'], r5['abstain'], r5['wrong_not_abstained'], r5['error']) == (3, 1, 1, 1, 0), r5
        md = (pathlib.Path(td) / 'report.md').read_text()
        assert 'SYNTHETIC' in md and 'no spend' in md and 'METERED' not in md

    with tempfile.TemporaryDirectory() as td:                                                             # 5
        out = run('--mode', 'dry-run', '--out', td)
        assert out.returncode == 0, out.stderr
        d = json.loads(out.stdout)
        assert (d['requests'], d['questions'], d['network_calls'], d['socket_guard'], d['key_ready']) == (26, 85, 0, True, False), d
        assert 0 < d['est_cost_usd'] <= d['bound_cost_usd'] <= d['max_spend']
        files = sorted((pathlib.Path(td) / 'requests').glob('*.json'))
        assert len(files) == 26 and not any('Bearer' in f.read_text() for f in files)

    assert run('--mode', 'live').returncode == 2                                                          # 6
    short_key = run('--mode', 'live', env=dict(ENV, **{jev.KEY_ENV: 'abc'}))
    assert short_key.returncode == 2 and 'abc' not in short_key.stderr.replace('(3 chars', '')
    assert run('--mode', 'dry-run', '--max-spend', '0.000001').returncode == 2
    assert run('--mode', 'dry-run', '--max-spend', 'nan').returncode == 2

    guard = subprocess.run([sys.executable, '-c',                                                         # 7
                            'import sys; sys.path.insert(0, %r)\n'
                            'from typed import jev_backend as j\nj.install_socket_guard()\n'
                            'try:\n    j.http("GET", j.MODELS_URL, "k" * 40)\n'
                            'except RuntimeError as e:\n'
                            '    assert "SOCKET GUARD" in str(e) and j.GUARD["blocked"] >= 1\n    print("BLOCKED")' % str(ROOT)],
                           capture_output=True, text=True)
    assert guard.returncode == 0 and 'BLOCKED' in guard.stdout, guard.stderr

    real = jev.http                                                                                       # 8
    try:
        seen = []
        def stub(seq):
            it = iter(seq)
            def h(method, url, key, payload=None, timeout=30):
                seen.append((method, url, payload))
                st, body = next(it)
                return st, json.dumps(body).encode() if not isinstance(body, bytes) else body, 12.0
            return h
        jev.http = stub([(200, good_n)])
        ans, env, err = jev.ask(no, KEY)
        assert err is None and ans['p_true'] == 0.5 and env['usage']['input_tokens'] == 100
        assert abs(env['total_cost_usd'] - 100 * 0.042 / 1e6) < 1e-15 and seen[-1][1] == jev.API_URL
        for st, needle in ((401, 'HTTP 401'), (422, 'HTTP 422')):
            jev.http = stub([(st, ('echo Bearer %s and %s' % (KEY, KEY)).encode())])
            ans, env, err = jev.ask(no, KEY)
            assert ans is None and needle in err and KEY not in err and KEY not in json.dumps(env), err
        naps = []
        jev.http = stub([(429, {}), (529, {}), (200, good_n)])
        ans, env, err = jev.ask(no, KEY, sleep=naps.append)
        assert err is None and naps == [1, 2]
        jev.http = stub([(429, {})] * 5)
        ans, env, err = jev.ask(no, KEY, sleep=naps.append)
        assert ans is None and 'HTTP 429' in err
        jev.http = stub([(200, dict(good_n, answers={'q': {'type': 'noul', 'noul': 7}, 'echo': KEY}))])
        ans, env, err = jev.ask(no, KEY)
        assert ans is None and 'SHAPE' in err and env['usage']['input_tokens'] == 100 and KEY not in json.dumps(env)
        jev.http = stub([(200, b'not json')])
        ans, env, err = jev.ask(no, KEY)
        assert ans is None and 'not JSON' in err
        jev.http = stub([(200, dict(good_n, model='jev-2.0.0'))])
        ans, env, err = jev.ask(no, KEY)
        assert ans is None and 'pinned' in err and env['total_cost_usd'] > 0
        jev.http = stub([(422, ('x' * 290 + ' invalid key ' + KEY).encode())])      # key straddles byte 300
        ans, env, err = jev.ask(no, KEY)
        assert KEY[:8] not in err, err
        jev.http = stub([(0, b'timed out')])
        ans, env, err = jev.ask(no, KEY)
        assert ans is None and env['total_cost_usd'] == jev.usd(jev.max_tokens(jev.build_request(no)))

        # 10. live loop end to end, in-process, stubbed http, fake key
        def answer_for(payload, tokens=100):
            out = {}
            for qid, q in payload['questions'].items():
                if q['type'] == 'choice':
                    opts = list(q['criteria']); pr = {o: 0.0 for o in opts}; pr[opts[0]] = 1.0
                    out[qid] = {'type': 'choice', 'choice': opts[0], 'probabilities': pr, 'confidence': 1.0}
                else:
                    out[qid] = {'type': 'noul', 'noul': 0.9}
            return {'model': payload['model'], 'answers': out, 'usage': {'input_tokens': tokens, 'output_tokens': 0}, 'echo': KEY}
        def live(handler, *extra):
            jev.http = handler
            td = tempfile.mkdtemp()
            old_argv, old_key = sys.argv, os.environ.get(jev.KEY_ENV)
            sys.argv = ['typed_questions.py', '--backend', 'jev', '--mode', 'live', '--out', td, *extra]
            os.environ[jev.KEY_ENV] = KEY
            try:
                code = tq.main()
            finally:
                sys.argv = old_argv
                os.environ.pop(jev.KEY_ENV, None) if old_key is None else os.environ.__setitem__(jev.KEY_ENV, old_key)
            text = ''.join(f.read_text() for f in pathlib.Path(td).rglob('*') if f.is_file())
            assert KEY not in text, 'key written to an output file'
            rep = pathlib.Path(td) / 'report.json'
            return code, (json.loads(rep.read_text()) if rep.exists() else None), pathlib.Path(td)
        def ok(method, url, key, payload=None, timeout=30):
            return 200, json.dumps({'data': []} if method == 'GET' else answer_for(payload)).encode(), 5.0
        code, rep, td = live(ok)
        assert code == 0 and rep['calls'] == 26 and rep['stopped'] is None and rep['errors'] == 0, rep
        assert abs(rep['cost_usd'] - 26 * jev.usd(100)) < 1e-12
        first = json.loads((td / 'calls.jsonl').read_text().splitlines()[0])
        assert first['http_status'] == 200 and first['served_model'] == 'jev-1.13.0' and first['response']['echo'] == '[REDACTED]'
        sent = json.loads(json.loads((td / 'prompts.jsonl').read_text().splitlines()[0])['prompt'])
        assert sorted(sent) == ['model', 'questions', 'state']
        def pricey(method, url, key, payload=None, timeout=30):
            return 200, json.dumps({'data': []} if method == 'GET' else answer_for(payload, 60000)).encode(), 5.0
        code, rep, _ = live(pricey)      # 60000 tokens > the body bound: the bound is falsified on call 1
        assert code == 3 and rep['calls'] == 1 and 'bound falsified' in rep['stopped'], rep
        def no_post(method, url, key, payload=None, timeout=30):
            assert method == 'GET', 'a billed call was made although the bound passes the cap'
            return 200, b'{"data": []}', 5.0
        code, rep, _ = live(no_post, '--max-spend', '0.001')    # whole-run bound $0.0028 > cap: refuse before any call
        assert code == 2 and rep is None
        def dropped(method, url, key, payload=None, timeout=30):
            return (200, b'{"data": []}', 5.0) if method == 'GET' else (0, b'timed out', 5.0)
        code, rep, _ = live(dropped)                             # no response: each call is charged at its bound
        assert code == 3 and rep['calls'] == 3 and rep['cost_usd'] > 0 and 'circuit breaker' in rep['stopped'], rep
        def broken(method, url, key, payload=None, timeout=30):
            return (200, b'{"data": []}', 5.0) if method == 'GET' else (422, b'{"error": "validation"}', 5.0)
        code, rep, _ = live(broken)
        assert code == 3 and rep['calls'] == 3 and rep['errors'] == 3 and 'circuit breaker' in rep['stopped'], rep
        def denied(method, url, key, payload=None, timeout=30):
            assert method == 'GET', 'a billed call was made after a failed auth check'
            return 401, b'{"error": "invalid key"}', 5.0
        code, rep, _ = live(denied)
        assert code == 2 and rep is None
    finally:
        jev.http = real

    assert jev.redact({'a': ['x ' + KEY, 'Bearer abcdefgh12345']}, KEY) == {'a': ['x [REDACTED]', 'Bearer [REDACTED]']}  # 9
    src = (ROOT / 'typed' / 'jev_backend.py').read_text()
    assert 'planted' not in src and 'print(' not in src

    rq = lambda row8: [r for r in tq.make_requests({1, 4, 5, 8}, docs, packets, page_text, truth, row8, 'short', 'verbatim') if not r.get('software')]   # 11
    hc, hj = {}, {}
    for r in rq('per-field'):
        hc.update(tq.parity_hashes(r, 'claude'))
    jr = rq('per-document')
    for r in jr:
        hj.update(tq.parity_hashes(r, 'jev'))
    assert len(hc) == len(hj) == 85 and hc == hj, sum(1 for k in hc if hc[k] != hj.get(k))
    r0 = next(r for r in jr if r['node'] == 'row1')
    b0 = jev.build_request(r0)
    parts = jev.parity_parts(r0, b0)[r0['subject']]
    assert parts[0] == r0['question'] and parts[1] == r0['options'] and parts[3] == r0['text']
    assert tq.parity_sha256(parts) == hc[r0['subject']]
    moved = dict(b0, state=b0['state'] + ' ')
    assert tq.parity_sha256(jev.parity_parts(r0, moved)[r0['subject']]) != hc[r0['subject']], 'document text not covered'
    crit = dict(b0['questions'][jev.QID]['criteria'], afe='changed')
    q2 = dict(b0, questions={jev.QID: dict(b0['questions'][jev.QID], criteria=crit)})
    assert tq.parity_sha256(jev.parity_parts(r0, q2)[r0['subject']]) != hc[r0['subject']], 'option text not covered'
    b8 = next(r for r in jr if r['node'] == 'row8')
    f0 = b8['fields'][0]
    q8 = jev.build_request(b8)
    q8['questions'][f0] = dict(q8['questions'][f0], instructions=q8['questions'][f0]['instructions'] + 'x')
    assert tq.parity_sha256(jev.parity_parts(b8, q8)[f'{b8["subject"]}.{f0}']) != hc[f'{b8["subject"]}.{f0}'], 'field text not covered'
    o = subprocess.run([sys.executable, RUNNER, '--mode', 'parity-check', '--parity'], capture_output=True, text=True, env=ENV)
    assert o.returncode == 0 and o.stdout.splitlines()[0] == 'parity 85 of 85' and json.loads(o.stdout.splitlines()[-1])['network_calls'] == 0, o
    o = subprocess.run([sys.executable, RUNNER, '--mode', 'parity-check'], capture_output=True, text=True, env=ENV)
    assert o.returncode == 1 and o.stdout.startswith('parity ') and 'mismatch' in o.stdout, o
    def recorded(backend):
        td = tempfile.mkdtemp()
        o = subprocess.run([sys.executable, RUNNER, '--backend', backend, '--mode', 'fixture', '--parity', '--out', td],
                           capture_output=True, text=True, env=ENV)
        assert o.returncode == 0, o.stderr
        h = {}
        for c in map(json.loads, open(pathlib.Path(td) / 'calls.jsonl')):
            p = c['parity_sha256']
            h.update({f"{c['subject']}.{f}": v for f, v in p.items()} if isinstance(p, dict) else {c['subject']: p})
        return h, json.loads((pathlib.Path(td) / 'report.json').read_text())
    (rc, repc), (rj, repj) = recorded('claude'), recorded('jev')
    assert rc == rj == hc and repc['calls'] == 85 and repj['calls'] == 26 and repc['units'] == repj['units'] == 85
    assert repc['errors'] == repj['errors'] == 0 and repj['row8_mode'] == 'per-document' and repj['model_requested'] == 'jev-1.13.0'

    pr = {o: 0.0 for o in ch['options']}; pr[ch['label']] = 0.9; pr['needs_review'] = 0.1                 # 12
    other = next(o for o in ch['options'] if o not in (ch['label'], 'needs_review'))
    dis = {'model': 'jev-1.13.0', 'usage': usage, 'answers': {'q': {'type': 'choice', 'choice': other, 'probabilities': pr, 'confidence': 0.8}}}
    ans, _, _ = jev.parse_response(ch, dis)
    assert tq.score(ch, ans)['abstain'] and tq.score(ch, ans)['disagree']
    s = tq.score(ch, ans, disagree_abstain=False)
    assert not s['abstain'] and s['disagree'] and s['final'] == ch['label'] and s['correct'], s

    nr_page = page_text['day12'][3][:tq.MAX_PAGE_CHARS]         # row-4 page Jev will answer needs_review at 0.85
    def cas_http(method, url, key, payload=None, timeout=30):                                             # 14
        if method == 'GET':
            return 200, b'{"data": []}', 5.0
        out = {}
        for qid, q in payload['questions'].items():
            if q['type'] == 'choice' and payload['state'] == nr_page and 'topic' in q['instructions']:
                pr = {o: 0.0 for o in q['criteria']}; pr['needs_review'] = 0.85; pr[next(iter(q['criteria']))] = 0.15
                out[qid] = {'type': 'choice', 'choice': 'needs_review', 'probabilities': pr, 'confidence': 0.8}
            elif q['type'] == 'choice':
                opts = list(q['criteria']); top = 0.7 if 'document class' in q['instructions'] else 0.9
                pr = {o: 0.0 for o in opts}; pr[opts[0]] = top; pr['needs_review'] = round(1 - top, 2)
                out[qid] = {'type': 'choice', 'choice': opts[0], 'probabilities': pr, 'confidence': 0.5}
            else:
                p = 0.6 if 'second field ticket' in q['instructions'] else 0.79 if qid == 'total' else 0.9
                out[qid] = {'type': 'noul', 'noul': p}
        return 200, json.dumps({'model': payload['model'], 'answers': out, 'usage': {'input_tokens': 100, 'output_tokens': 0}, 'echo': KEY}).encode(), 5.0
    def cas_cli(cmd, **kw):
        if cmd[:3] == ['claude', 'auth', 'status']:
            return FakeProc(json.dumps({'loggedIn': True}))
        prompt = kw['input']
        res = ('{"answer": "afe", "probabilities": {"afe": 1.0}}' if 'Options (unordered)' in prompt
               else '{"answer": true, "p_true": 0.5}')
        return FakeProc(json.dumps({'result': res, 'num_turns': 1, 'duration_ms': 7, 'total_cost_usd': 0.01,
                                    'usage': {'input_tokens': 5, 'output_tokens': 2}, 'modelUsage': {'claude-pin-full': {}}}))
    def cascade(handler, cli, *extra):
        real_run = subprocess.run
        jev.http, subprocess.run = handler, cli
        td = tempfile.mkdtemp()
        old_argv, old_key = sys.argv, os.environ.get(jev.KEY_ENV)
        sys.argv = ['typed_questions.py', '--backend', 'cascade', '--mode', 'live', '--model', 'claude-pin', '--out', td, *extra]
        os.environ[jev.KEY_ENV] = KEY
        try:
            code = tq.main()
        finally:
            jev.http, subprocess.run, sys.argv = real, real_run, old_argv
            os.environ.pop(jev.KEY_ENV, None) if old_key is None else os.environ.__setitem__(jev.KEY_ENV, old_key)
        text = ''.join(f.read_text() for f in pathlib.Path(td).rglob('*') if f.is_file())
        assert KEY not in text, 'key written to an output file'
        rp = pathlib.Path(td) / 'report.json'
        return code, (json.loads(rp.read_text()) if rp.exists() else None), pathlib.Path(td)
    code, rep, td = cascade(cas_http, cas_cli, '--cap', '60')
    c = rep['cascade']
    assert code == 0 and rep['stopped'] is None and rep['errors'] == 0, rep
    assert (c['jev_requests'], c['claude_calls'], rep['calls']) == (26, 13, 39) and c['escalated_by_node'] == {'row1': 7, 'row5': 3, 'row8': 3}, c
    assert c['escalated_abstain'] == 6 and c['wrong_not_abstained_by']['claude'] == 6, c
    assert sum(c['wrong_not_abstained_by'].values()) == sum(v['wrong_not_abstained'] for v in rep['nodes'].values())
    assert c['units_answered_by_jev'] == 85 - 13 and c['units_to_person'] == c['units_to_person_abstain'] >= 6
    assert c['latency_ms_sum'] == {'jev': 26 * 5, 'claude': 13 * 7} and abs(c['jev_billed_usd'] - 26 * jev.usd(100)) < 1e-12
    assert c['jev_billed_tokens'] == 2600 and '$0 billed' in c['claude_cost_basis'] and abs(c['claude_cost_estimate_usd'] - 0.13) < 1e-9
    assert rep['model_requested'] == 'claude-pin' and rep['served_models'] == ['claude-pin-full'] and c['h4'].endswith('= 13, Claude-alone calls would be 85')
    units = [json.loads(l) for l in (td / 'calls.jsonl').read_text().splitlines()]
    esc = [u for u in units if u.get('kind') == 'unit' and u['jev']['escalated']]
    assert len(esc) == 13 and all(u['parity_sha256']['jev'] == u['parity_sha256']['claude'] for u in esc)
    assert all(u['claude']['served_model'] == 'claude-pin-full' and u['claude']['latency_ms'] == 7 for u in esc)
    assert sum(1 for u in units if u.get('kind') == 'jev_request') == 26 and 'METERED' in (td / 'report.md').read_text()
    nr = next(u for u in units if u.get('kind') == 'unit' and u['subject'] == 'day12:p3')
    assert (nr['answered_by'], nr['jev']['escalated'], nr['jev']['decision'], nr['jev']['p_top'], nr['score']['abstain']) == ('jev', False, 'abstain', 0.85, True), nr
    assert c['units_to_person_abstain'] == 7 and rep['model_mismatches'] == 0, c   # 6 escalated abstains + the needs_review unit

    with tempfile.TemporaryDirectory() as td:                                                             # 15
        o = run('--backend', 'cascade', '--mode', 'fixture', '--cap', '28', '--out', td)
        rep = json.loads((pathlib.Path(td) / 'report.json').read_text())
        c = rep['cascade']
        assert o.returncode == 3 and rep['calls'] == 28 == c['jev_requests'] + c['claude_calls'] and 'cap' in rep['stopped'], rep
        assert c['claude_calls'] >= 1 and 'INCOMPLETE' in (pathlib.Path(td) / 'report.md').read_text()
    def get_only(method, url, key, payload=None, timeout=30):
        assert method == 'GET', 'a billed call was made although the Jev requests pass --cap'
        return 200, b'{"data": []}', 5.0
    code, rep, _ = cascade(get_only, cas_cli, '--cap', '20')
    assert code == 2 and rep is None

    o = run('--backend', 'cascade', '--mode', 'dry-run', '--escalate-below', '0.80')                       # 16
    d = json.loads(o.stdout)
    assert o.returncode == 0 and (d['requests'], d['questions'], d['claude_calls_upper_bound'], d['parity']) == (26, 85, 85, '85 of 85'), d
    assert (d['network_calls'], d['socket_guard'], d['key_ready']) == (0, True, False) and 0 < d['est_cost_usd'] <= d['bound_cost_usd'], d

    def fail_post(method, url, key, payload=None, timeout=30):                                            # 17
        return (200, b'{"data": []}', 5.0) if method == 'GET' else (500, b'{"error": "boom"}', 5.0)
    good_cli = lambda cmd, **kw: (FakeProc(json.dumps({'loggedIn': True})) if cmd[:3] == ['claude', 'auth', 'status'] else
                                  FakeProc(json.dumps({'result': '{"answer": "afe", "probabilities": {"afe": 1.0}}' if 'Options (unordered)' in kw['input']
                                                       else '{"answer": true, "p_true": 0.9}', 'num_turns': 1, 'duration_ms': 7, 'modelUsage': {'m': {}}})))
    code, rep, td = cascade(fail_post, good_cli, '--cap', '200')
    c = rep['cascade']
    assert code == 3 and rep['stopped'] == 'circuit breaker: 3 consecutive Jev errors', rep['stopped']
    assert (c['jev_requests'], c['jev_errors'], c['escalated_by_reason'], c['claude_calls']) == (3, 3, {'jev_error': 3}, 2), c
    recs = [json.loads(l) for l in (td / 'calls.jsonl').read_text().splitlines()]
    assert sum(1 for r in recs if r.get('kind') == 'jev_request' and r['error']) == 3
    cut = [r for r in recs if r.get('kind') == 'unit' and not (r.get('claude') or {}).get('asked', True)]
    assert len(cut) == 1 and cut[0]['score']['error'] and rep['errors'] == 1 and '| Jev requests that errored | 3 |' in (td / 'report.md').read_text()

    def over_bill(method, url, key, payload=None, timeout=30):                                            # 18
        if method == 'GET':
            return 200, b'{"data": []}', 5.0
        st, body, ms = cas_http(method, url, key, payload)
        b = json.loads(body); b['usage']['input_tokens'] = 60000
        return st, json.dumps(b).encode(), ms
    code, rep, _ = cascade(over_bill, good_cli, '--cap', '200')
    assert code == 3 and 'bound falsified' in rep['stopped'] and rep['cascade']['jev_requests'] == 1, rep['stopped']

    def unsure(method, url, key, payload=None, timeout=30):                                               # 19
        if method == 'GET':
            return 200, b'{"data": []}', 5.0
        out = {}
        for qid, q in payload['questions'].items():
            if q['type'] == 'choice':
                opts = list(q['criteria']); pr = {o: 0.0 for o in opts}; pr[opts[0]] = 0.5; pr['needs_review'] = 0.5
                out[qid] = {'type': 'choice', 'choice': opts[0], 'probabilities': pr, 'confidence': 0.1}
            else:
                out[qid] = {'type': 'noul', 'noul': 0.5}
        return 200, json.dumps({'model': payload['model'], 'answers': out, 'usage': {'input_tokens': 100, 'output_tokens': 0}}).encode(), 5.0
    bad_cli = lambda cmd, **kw: (FakeProc(json.dumps({'loggedIn': True})) if cmd[:3] == ['claude', 'auth', 'status'] else
                                 FakeProc(json.dumps({'is_error': True, 'result': 'overloaded'})))
    code, rep, _ = cascade(unsure, bad_cli, '--cap', '200')
    c = rep['cascade']
    assert code == 3 and rep['stopped'] == 'circuit breaker: 3 consecutive Claude errors' and c['claude_calls'] == 3 and c['jev_errors'] == 0, (rep['stopped'], c)

    mid = tempfile.mkdtemp(); peek = []                                                                   # 20
    def peeking(method, url, key, payload=None, timeout=30):
        if method == 'POST':
            f = pathlib.Path(mid) / 'calls.jsonl'
            peek.append(sum(1 for l in f.read_text().splitlines() if '"kind": "jev_request"' in l) if f.exists() else 0)
        return cas_http(method, url, key, payload)
    code, rep, _ = cascade(peeking, cas_cli, '--cap', '60', '--out', mid)
    assert code == 0 and peek[:3] == [0, 1, 2], peek[:3]

    j4 = ROOT.parent / 'artifacts' / 'typed-questions-2026-09-28' / 'live-results' / 'jev-arm' / 'live-synth-03' / 'calls.jsonl'   # 13
    if j4.exists():
        with tempfile.TemporaryDirectory() as td:
            o = run('--mode', 'dry-run', '--compare-hashes', str(j4), '--out', td)
            d = json.loads(o.stdout)
            assert o.returncode == 0 and d['hash_match'] == '26 of 26' and d['socket_guard'] and d['network_calls'] == 0, (o.stdout, o.stderr)
        n = 20
    else:
        print('SKIP group 13: J4 artifact absent'); n = 19
    print(f'OK {n} assertion groups')
    return 0

if __name__ == '__main__':
    sys.exit(main())
