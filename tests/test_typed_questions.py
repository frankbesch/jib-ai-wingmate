#!/usr/bin/env python3
"""Offline tests for typed/typed_questions.py — fixture mode and stubbed CLI only, no network.

Asserts:
  1. Page split matches the manifest (3, 4, 2) and the afe document text carries both of its pages.
  2. Request counts for rows 1,4,5,8 per-document: 7, 9, 3, 7 = 26 calls; row 8 = 66 units (52 required
     non-boolean fields + 14 decoy negatives), with 14 False labels.
  3. Row-4 labels: day12 pages 1..4 -> field_ticket, field_ticket, hauling_log, invoice (no ordinal option).
  4. Fixture run: row1 7/5/1/1 (planted abstain ticket_b, planted wrong afe_cover); row5 3/1/1/1
     (planted abstain day01, planted wrong day30); errors 0; report.md carries SYNTHETIC.
  5. Thresholds are the declared values and sit on the declared side (0.60 passes, 0.35 and 0.65 are confident).
  6. Malformed replies raise Malformed, never score: no probabilities, empty, NaN, >1, bool, string,
     sum 1.8, key outside the set, answer disagreeing with argmax (abstain + disagree), noul answer
     not boolean, noul answer disagreeing with p_true (abstain).
  7. ask_model with a stubbed subprocess: is_error envelope, nonzero exit, unparseable stdout, JSON array,
     timeout, missing CLI, num_turns > 1 -> all return an error string and no answer; a good envelope
     returns the parsed JSON and its usage. The command carries --tools '' and --setting-sources ''.
  8. The runner never reads synth/planted.json.
  9. --set: no flag and `--set synth` resolve to the fixed paths; a copied corpus dir (manifest.json + truth/)
     gives the same fixture report as the default.
 10. --truth-b: row 8 is scored against layer B; a unit with A present and B absent is Pulse-dropped (own
     column, out of correct/abstain/wrong); a unit with A absent and B present is listed as extract-invented;
     per-document and per-field agree; without --truth-b the report has no Pulse-dropped column.
 11. --model pin: live with the claude backend and no --model exits 2 with a one-line message before any
     subprocess; with --model and a stubbed CLI, calls.jsonl logs model_requested and the served model from
     the envelope's modelUsage keys, and report.json records model_requested.
 12. Disagree-off (parity): a disagreeing answer keeps its flag but no longer abstains; the floor and the
     band still abstain.
 13. Default byte-identity: dry-run prompts match prompt_sha256 of the G5 run, 26 of 26 (skipped if the
     artifact is absent).
 14. Cascade line: top probability is the max option probability (choice) and max(p, 1-p) (noul); 0.79
     escalates, 0.80 does not, on both shapes; the line is declared at 0.80.
 15. Cascade --model pin: live cascade without --model exits 2 with the one-line message before any
     subprocess or socket.
 16. Cascade fixture: escalations on rows 1 (2), 5 (1), 8 (1); 2 escalated units abstained by Claude; 26 Jev
     requests + 4 Claude calls; wrong split 1 Jev / 1 Claude; 2 units to a person; the 0.80 plant is answered by
     Jev; every escalated unit records equal Jev and Claude parity hashes; H4 line; $0 billed.
 17. Threshold-free headline: every scored unit carries `top` (best option; p >= 0.5) and `top_correct`; an
     abstained unit keeps its top answer; report.json and report.md sum top_correct per node for the claude,
     jev, and cascade fixtures (cascade: 6/9/1/66, Jev half 82 of 85, Claude half 2 of 4); jev_errors 0.
 18. Cascade + --truth-b: the Pulse-dropped unit (invoice.vendor_name, escalated) leaves correct, abstain, wrong,
     error, top_correct, and every person count; scored = n - pulse_dropped (json and md); an errored dropped
     unit keeps its reason under dropped_error and error is False.
 19. Cascade fixture starts no subprocess: subprocess.run raises for the whole in-process run, exit 0.
 20. ask_model passes an env without TYPESAFE_API_KEY to the claude child (the key is set in this process).
 22. Subject collisions (synth-pilot defect, 2026-09-30): a copy of the set whose packet ids equal document ids
     (day01 -> afe_cover, day12 -> ticket_a, day30 -> jib) still gives parity 85 of 85 and a cascade with 85
     Claude-alone calls; the escalated row-1 unit afe_cover goes to Claude with the row-1 question (a choice
     reply, parity hashes equal), not the row-5 question of packet afe_cover.
 21. Served-model check, log only: exact match, alias contained, and date suffix are not mismatches; a different
     model is; a stubbed live run with a different served model exits 0, marks each call model_mismatch,
     and report.json counts model_mismatches 3; the matching run counts 0.
 23. --alias afe_number (held-out run 2, BUILD-SPEC H1): the constant is the declared sentence; it is appended to
     every afe_number description (per-field question, per-document listing, Jev body) and nothing else changes;
     alias with no field descriptions exits; parity stays 85 of 85; report.json, the dry-run tag (claude, jev,
     cascade), and report.md carry it; default requests are unchanged by the new parameter.
 24. --claude-row8 per-document: under --parity claude runs 26 calls (row 8 = 7 batches, 66 units) with the same
     short descriptions and disagree-abstain off; report.json and the dry-run tag carry it; without --parity it
     exits 2; cascade and jev ignore it (same requests, no tag, cascade report says per-field).
Run: python3 tests/test_typed_questions.py
"""
import io, json, math, os, pathlib, shutil, subprocess, sys, tempfile, contextlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from typed import typed_questions as tq  # noqa: E402

class FakeProc:
    def __init__(self, stdout='', stderr='', rc=0): self.stdout, self.stderr, self.returncode = stdout, stderr, rc

def stub(monkey):
    calls = []
    def run(cmd, **kw):
        calls.append(cmd)
        r = monkey(cmd, kw)
        if isinstance(r, Exception): raise r
        return r
    return run, calls

def main():
    run_dir = ROOT / 'runs' / 'live-synth-03'
    if not run_dir.exists():
        print('SKIP: runs/live-synth-03 not present (gitignored run output)'); return 0
    manifest = tq.load(ROOT / 'synth' / 'manifest.json')
    docs, packets, page_text, truth = tq.build_inputs(run_dir, manifest, ROOT / 'truth' / 'synth')
    assert [len(page_text[p]) for p in ('day01', 'day12', 'day30')] == [3, 4, 2], 'page split'          # 1
    afe = next(d for d in docs if d['doc_id'] == 'afe')
    t = tq.doc_text(afe, page_text)
    assert page_text['day01'][2][:40] in t and page_text['day01'][3][-40:] in t, 'afe spans pages 2-3'
    reqs = tq.make_requests({1, 4, 5, 8}, docs, packets, page_text, truth, 'per-document')
    by = {}
    for r in reqs: by[r['node']] = by.get(r['node'], 0) + 1
    assert by == {'row1': 7, 'row4': 9, 'row5': 3, 'row8': 7}, by                                          # 2
    r8 = [r for r in reqs if r['node'] == 'row8']
    assert sum(len(r['fields']) for r in r8) == 66 and sum(1 for r in r8 for v in r['label'].values() if not v) == 14
    assert all('customer_signature_present' not in r['fields'] for r in r8)
    tl = tq.topic_labels(docs)
    assert [tl[('day12', p)] for p in (1, 2, 3, 4)] == ['field_ticket', 'field_ticket', 'hauling_log', 'invoice']  # 3
    assert not any(o.startswith('field_ticket_') for o in tq.TOPICS)
    with tempfile.TemporaryDirectory() as td:
        out = subprocess.run([sys.executable, str(ROOT / 'typed' / 'typed_questions.py'), '--run', str(run_dir),
                              '--mode', 'fixture', '--out', td], capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        rep = json.loads((pathlib.Path(td) / 'report.json').read_text())
        assert rep['synthetic'] is True and rep['calls'] == 26 and rep['units'] == 26 - 7 + 66 and rep['errors'] == 0, rep
        r1, r5 = rep['nodes']['row1'], rep['nodes']['row5']
        assert (r1['n'], r1['correct'], r1['abstain'], r1['wrong_not_abstained'], r1['error']) == (7, 5, 1, 1, 0), r1     # 4
        assert (r5['n'], r5['correct'], r5['abstain'], r5['wrong_not_abstained'], r5['error']) == (3, 1, 1, 1, 0), r5
        assert 'SYNTHETIC' in (pathlib.Path(td) / 'report.md').read_text()
        assert (pathlib.Path(td) / 'prompts.jsonl').read_text().count('\n') == 26
    assert (tq.CHOICE_FLOOR, tq.NOUL_LO, tq.NOUL_HI) == (0.60, 0.35, 0.65)                                # 5
    opts = tq.CLASSES + ['needs_review']
    ok = tq.score_choice({'answer': 'afe', 'probabilities': {'afe': 0.6, 'afe_cover': 0.4}}, opts, 'afe')
    assert ok['correct'] and not ok['abstain'], ok
    assert not tq.score_noul({'answer': False, 'p_true': 0.35}, False)['abstain']
    assert not tq.score_noul({'answer': True, 'p_true': 0.65}, True)['abstain']
    bad = [                                                                                               # 6
        {'answer': 'afe'}, {'answer': 'afe', 'probabilities': {}}, {'probabilities': {'afe': math.nan, 'afe_cover': 0.0}},
        {'probabilities': {'afe': 1.7}}, {'probabilities': {'afe': True}}, {'probabilities': {'afe': '0.9'}},
        {'probabilities': {'afe': 0.9, 'afe_cover': 0.9}}, {'probabilities': {'field_ticket_9': 1.0}}, 'not an object', None,
    ]
    for b in bad:
        try:
            tq.score_choice(b, opts, 'afe'); raise AssertionError(f'accepted {b!r}')
        except tq.Malformed:
            pass
    d = tq.score_choice({'answer': 'afe_cover', 'probabilities': {'afe': 0.9, 'afe_cover': 0.1}}, opts, 'afe')
    assert d['abstain'] and d['disagree'] and not d['correct'] and not d['wrong_not_abstained'], d
    for b in [{'answer': 'yes', 'p_true': 0.9}, {'answer': True, 'p_true': 1.2}, {'answer': True}, {'p_true': 0.9}]:
        try:
            tq.score_noul(b, True); raise AssertionError(f'accepted {b!r}')
        except tq.Malformed:
            pass
    d = tq.score_noul({'answer': False, 'p_true': 0.9}, True)
    assert d['abstain'] and d['disagree'], d
    s = tq.score(dict(shape='noul-batch', label={'a': True, 'b': False}), {'fields': {'a': {'answer': True, 'p_true': 0.9}}})
    assert s['fields']['b']['error'] and s['fields']['a']['correct']
    real = subprocess.run                                                                                 # 7
    good_env = json.dumps({'result': '```json\n{"answer": true, "p_true": 0.9}\n```', 'usage': {'input_tokens': 5, 'output_tokens': 2}, 'num_turns': 1})
    cases = [
        (FakeProc(json.dumps({'is_error': True, 'result': 'Not logged in'})), 'Not logged in'),
        (FakeProc('{"result": "auth expired"}', rc=1), 'auth expired'), (FakeProc('garbage'), 'unparseable'), (FakeProc('[1,2]'), 'unparseable'),
        (subprocess.TimeoutExpired('claude', 180), 'timeout'), (FileNotFoundError(), 'not found'),
        (FakeProc(json.dumps({'result': '{}', 'num_turns': 2})), 'num_turns'),
    ]
    try:
        for proc, needle in cases:
            subprocess.run, calls = stub(lambda cmd, kw, p=proc: p)
            ans, env, err = tq.ask_model('q', cwd='/tmp')
            assert ans is None and err and needle in err, (needle, err)
        subprocess.run, calls = stub(lambda cmd, kw: FakeProc(good_env))
        ans, env, err = tq.ask_model('q', cwd='/tmp')
        assert err is None and ans == {'answer': True, 'p_true': 0.9} and env['usage']['input_tokens'] == 5
        cmd = calls[0]
        assert '--tools' in cmd and cmd[cmd.index('--tools') + 1] == '' and '--setting-sources' in cmd and '--no-session-persistence' in cmd
    finally:
        subprocess.run = real
    src = (ROOT / 'typed' / 'typed_questions.py').read_text().splitlines()                                # 8
    reads = [l for l in src if 'planted' in l and any(k in l for k in ('load(', 'open(', 'read_text', 'Path('))]
    assert not reads, f'runner must not read the plants: {reads}'

    runner = str(ROOT / 'typed' / 'typed_questions.py')                                                  # 9
    def fixture(*extra):
        td = tempfile.mkdtemp()
        o = subprocess.run([sys.executable, runner, '--run', str(run_dir), '--mode', 'fixture', '--out', td, *extra],
                           capture_output=True, text=True)
        assert o.returncode == 0, o.stderr
        return json.loads((pathlib.Path(td) / 'report.json').read_text()), pathlib.Path(td)
    fixed = (ROOT / 'synth' / 'manifest.json', ROOT / 'truth' / 'synth')
    assert tq.set_paths(None) == fixed and tq.set_paths('synth') == fixed and tq.set_paths(str(ROOT / 'synth')) == fixed
    def corpus(edits=None):
        d = pathlib.Path(tempfile.mkdtemp())
        shutil.copy(ROOT / 'synth' / 'manifest.json', d / 'manifest.json')
        (d / 'truth').mkdir()
        for doc in manifest['documents']:
            t = tq.load(ROOT / 'truth' / 'synth' / f"{doc['doc_id']}.json")
            for (doc_id, f), v in (edits or {}).items():
                if doc_id == doc['doc_id']:
                    t['values'][f] = v
            (d / 'truth' / f"{doc['doc_id']}.json").write_text(json.dumps(t))
        return d
    base, _ = fixture()
    copied, _ = fixture('--set', str(corpus()))
    assert copied['nodes'] == base['nodes'] and copied['units'] == 85 and copied['corpus_set'] != 'synth', copied
    assert 'pulse_dropped' not in base and all('pulse_dropped' not in v for v in base['nodes'].values())

    set_a = corpus({('invoice', 'tax'): None})                                                            # 10
    set_b = corpus({('invoice', 'vendor_name'): None})
    for row8 in ('per-document', 'per-field'):
        rep, td = fixture('--set', str(set_a), '--truth-b', str(set_b / 'truth'), '--row8', row8)
        r8 = rep['nodes']['row8']
        assert (r8['n'], r8['correct'], r8['abstain'], r8['wrong_not_abstained'], r8['error'], r8['pulse_dropped']) == (66, 65, 0, 0, 0, 1), (row8, r8)
        assert rep['pulse_dropped'] == ['invoice.vendor_name'] and rep['extract_invented'] == ['invoice.tax'], rep
        assert rep['nodes']['row1']['pulse_dropped'] == 0
        md = (td / 'report.md').read_text()
        assert '| Pulse-dropped |' in md and 'Extract-invented (1' in md and 'invoice.tax' in md
    lb = tq.make_requests({8}, docs, packets, page_text, truth, 'per-document',
                          truth_b=tq.load_truth(docs, set_b / 'truth'))
    inv = next(r for r in lb if r['subject'] == 'invoice')
    assert inv['label_a']['vendor_name'] is True and inv['label']['vendor_name'] is False
    assert all('label_a' not in r for r in reqs), 'label_a must be absent by default'

    ran = []                                                                                              # 11
    def no_run(cmd, **kw):
        ran.append(cmd); raise AssertionError('subprocess started before the --model check')
    subprocess.run, old_argv = no_run, sys.argv
    err = io.StringIO()
    try:
        sys.argv = ['typed_questions.py', '--mode', 'live']
        with contextlib.redirect_stderr(err):
            code = tq.main()
    finally:
        subprocess.run, sys.argv = real, old_argv
    assert code == 2 and not ran and '--model' in err.getvalue() and err.getvalue().count('\n') == 1, (code, err.getvalue())
    o = subprocess.run([sys.executable, runner, '--mode', 'live'], capture_output=True, text=True, env={k: v for k, v in os.environ.items() if 'KEY' not in k})
    assert o.returncode == 2 and '--model' in o.stderr and not o.stdout, o
    def cli(cmd, **kw):
        if cmd[:3] == ['claude', 'auth', 'status']:
            return FakeProc(json.dumps({'loggedIn': True}))
        assert cmd[cmd.index('--model') + 1] == 'claude-test-pin'
        return FakeProc(json.dumps({'result': '{"answer": true, "p_true": 0.9}', 'num_turns': 1,
                                    'usage': {'input_tokens': 5, 'output_tokens': 2},
                                    'modelUsage': {'claude-test-pin-20260930': {'inputTokens': 5}}}))
    td = tempfile.mkdtemp()
    subprocess.run = cli
    try:
        sys.argv = ['typed_questions.py', '--run', str(run_dir), '--mode', 'live', '--rows', '5', '--model', 'claude-test-pin', '--out', td]
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            code = tq.main()
    finally:
        subprocess.run, sys.argv = real, old_argv
    recs = [json.loads(l) for l in (pathlib.Path(td) / 'calls.jsonl').read_text().splitlines()]
    rep = json.loads((pathlib.Path(td) / 'report.json').read_text())
    assert code == 0 and len(recs) == 3 and all(r['model_requested'] == 'claude-test-pin' and r['served_model'] == 'claude-test-pin-20260930' for r in recs), recs
    assert rep['model_requested'] == 'claude-test-pin' and rep['served_models'] == ['claude-test-pin-20260930'], rep

    d = tq.score_choice({'answer': 'afe_cover', 'probabilities': {'afe': 0.9, 'afe_cover': 0.1}}, opts, 'afe', disagree_abstain=False)   # 12
    assert d['disagree'] and not d['abstain'] and d['final'] == 'afe' and d['correct'], d
    d = tq.score_choice({'answer': 'afe', 'probabilities': {'afe': 0.55, 'afe_cover': 0.45}}, opts, 'afe', disagree_abstain=False)
    assert d['abstain'] and not d['disagree'], d
    d = tq.score_noul({'answer': False, 'p_true': 0.9}, True, disagree_abstain=False)
    assert d['disagree'] and not d['abstain'] and d['correct'], d
    assert tq.score_noul({'answer': True, 'p_true': 0.5}, True, disagree_abstain=False)['abstain']
    s = tq.score(dict(shape='noul-batch', label={'a': True}), {'fields': {'a': {'answer': False, 'p_true': 0.9}}}, disagree_abstain=False)
    assert s['fields']['a']['correct'] and not s['fields']['a']['abstain']
    assert tq.score(dict(shape='noul-batch', label={'a': True}), {'fields': {'a': {'answer': False, 'p_true': 0.9}}})['fields']['a']['abstain']
    par, _ = fixture('--parity')
    assert par['parity'] is True and par['disagree_abstain'] is False and par['calls'] == 85 and par['row8_mode'] == 'per-field'

    assert tq.ESCALATE_BELOW == 0.80                                                                      # 14
    for shape, p, esc in (('choice', 0.79, True), ('choice', 0.80, False), ('noul', 0.79, True), ('noul', 0.80, False),
                          ('noul', 0.21, True), ('noul', 0.20, False), ('noul', 0.5, True), ('choice', 1.0, False)):
        top = tq.top_probability(shape, {'p': p})
        assert tq.escalates(top, 0.80) is esc, (shape, p, top)
    s = tq.score_choice({'answer': 'afe', 'probabilities': {'afe': 0.79, 'afe_cover': 0.21}}, opts, 'afe', disagree_abstain=False)
    assert tq.top_probability('choice', s) == 0.79 and tq.escalates(tq.top_probability('choice', s), 0.80)
    s = tq.score_noul({'answer': False, 'p_true': 0.2}, False, disagree_abstain=False)
    assert tq.top_probability('noul', s) == 0.8 and not tq.escalates(tq.top_probability('noul', s), 0.80)

    ran, err = [], io.StringIO()                                                                          # 15
    subprocess.run = no_run
    try:
        sys.argv = ['typed_questions.py', '--backend', 'cascade', '--mode', 'live', '--escalate-below', '0.80']
        with contextlib.redirect_stderr(err):
            code = tq.main()
    finally:
        subprocess.run, sys.argv = real, old_argv
    assert code == 2 and not ran and 'cascade backend needs --model' in err.getvalue() and err.getvalue().count('\n') == 1, err.getvalue()

    rep, td = fixture('--backend', 'cascade', '--escalate-below', '0.80')                                 # 16
    c = rep['cascade']
    assert c['escalated_by_node'] == {'row1': 2, 'row5': 1, 'row8': 1} and c['escalated_abstain'] == 2, c
    assert (c['jev_requests'], c['claude_calls'], rep['calls'], rep['units'], rep['errors']) == (26, 4, 30, 85, 0), rep
    assert c['units_answered_by_jev'] == 81 and c['wrong_not_abstained_by'] == {'jev': 1, 'claude': 1, 'software': 0}, c
    assert c['units_to_person'] == 2 and c['jev_billed_usd'] == 0 and rep['cost_usd'] == 0 and c['claude_alone_calls'] == 85
    assert c['h4'] == 'H4: Claude calls in cascade = 4, Claude-alone calls would be 85' and c['escalate_metric'].startswith('top probability')
    assert sorted(c['escalated_units']) == ['afe_cover', 'day01', 'invoice.vendor_name', 'ticket_b'], c['escalated_units']
    recs = [json.loads(l) for l in (td / 'calls.jsonl').read_text().splitlines()]
    us = {r['subject']: r for r in recs if r.get('kind') == 'unit'}
    assert len(us) == 85 and all(u['answered_by'] in ('jev', 'claude') for u in us.values())
    assert us['invoice.total']['answered_by'] == 'jev' and us['invoice.total']['jev']['p_top'] == 0.8
    esc = [u for u in us.values() if u['jev']['escalated']]
    assert len(esc) == 4 and all(u['parity_sha256']['jev'] == u['parity_sha256']['claude'] and u['claude']['asked'] for u in esc)
    assert us['ticket_b']['claude']['abstain'] and us['day01']['claude']['abstain'] and us['afe_cover']['claude']['final'] == 'afe'
    assert all('latency_ms' in u['claude'] and 'model_requested' in u['claude'] and 'served_model' in u['claude'] for u in esc)
    md = (td / 'report.md').read_text()
    assert '## Cascade' in md and 'H4: Claude calls in cascade = 4' in md and 'SYNTHETIC' in md

    ab = tq.score_choice({'answer': 'afe', 'probabilities': {'afe': 0.55, 'afe_cover': 0.45}}, opts, 'afe')             # 17
    assert ab['abstain'] and ab['top'] == 'afe' and ab['top_correct'] and not ab['correct'], ab
    nu = tq.score_noul({'answer': True, 'p_true': 0.5}, True)
    assert nu['abstain'] and nu['top'] is True and nu['top_correct'], nu
    assert tq.score_noul({'answer': False, 'p_true': 0.1}, False)['top_correct'] and not tq.ERROR_UNIT['top_correct']
    for extra, want in ((('--backend', 'claude'), {'row1': 6, 'row4': 9, 'row5': 1, 'row8': 66}),
                        (('--backend', 'jev'), {'row1': 6, 'row4': 9, 'row5': 1, 'row8': 66}),
                        (('--backend', 'cascade'), {'row1': 6, 'row4': 9, 'row5': 1, 'row8': 66})):
        rep, td = fixture(*extra)
        assert {k: v['top_correct'] for k, v in rep['nodes'].items()} == want, (extra, rep['nodes'])
        assert '| top = label |' in (td / 'report.md').read_text()
    c = rep['cascade']
    assert c['top_correct_by_half'] == {'jev': 82, 'jev_n': 85, 'claude': 2, 'claude_n': 4} and c['jev_errors'] == 0, c
    assert c['escalated_by_reason'] == {'below_line': 4}
    us = {r['subject']: r for r in map(json.loads, (td / 'calls.jsonl').read_text().splitlines()) if r.get('kind') == 'unit'}
    assert us['afe_cover']['jev']['top'] == 'afe' and us['afe_cover']['claude']['top_correct'] is False

    set_b = corpus({('invoice', 'vendor_name'): None})                                                    # 18
    rep, td = fixture('--backend', 'cascade', '--set', str(corpus()), '--truth-b', str(set_b / 'truth'))
    r8, c = rep['nodes']['row8'], rep['cascade']
    assert (r8['n'], r8['pulse_dropped'], r8['scored'], r8['correct'], r8['error'], r8['top_correct']) == (66, 1, 65, 65, 0, 65), r8
    assert rep['pulse_dropped'] == ['invoice.vendor_name'] and 'invoice.vendor_name' in c['escalated_units']
    assert c['units_to_person'] == 2 and c['escalated_abstain'] == 2 and c['top_correct_by_half']['claude_n'] == 3, c
    assert '| Pulse-dropped | scored |' in (td / 'report.md').read_text()
    dropped = tq._layers(dict(tq.ERROR_UNIT, reason='boom'), True, False)
    assert dropped['pulse_dropped'] and not dropped['error'] and dropped['dropped_error'] == 'boom' and not dropped['top_correct']

    subprocess.run = no_run                                                                               # 19
    ran.clear(); td = tempfile.mkdtemp()
    try:
        sys.argv = ['typed_questions.py', '--run', str(run_dir), '--backend', 'cascade', '--mode', 'fixture', '--out', td]
        with contextlib.redirect_stdout(io.StringIO()):
            code = tq.main()
    finally:
        subprocess.run, sys.argv = real, old_argv
    assert code == 0 and not ran and json.loads((pathlib.Path(td) / 'report.json').read_text())['cascade']['claude_calls'] == 4

    seen = []                                                                                             # 20
    def capture(cmd, **kw):
        seen.append(kw); return FakeProc(good_env)
    old_key = os.environ.get(tq.jev.KEY_ENV)
    os.environ[tq.jev.KEY_ENV] = 'k' * 40
    subprocess.run = capture
    try:
        ans, env, err = tq.ask_model('q', cwd='/tmp')
    finally:
        subprocess.run = real
        os.environ.pop(tq.jev.KEY_ENV, None) if old_key is None else os.environ.__setitem__(tq.jev.KEY_ENV, old_key)
    assert err is None and isinstance(seen[0].get('env'), dict) and tq.jev.KEY_ENV not in seen[0]['env'], sorted(seen[0])
    assert 'PATH' in seen[0]['env'], 'the child must keep the rest of the environment'

    mm = tq.model_mismatch                                                                                # 21
    assert not mm('claude-fable-5-1', 'claude-fable-5-1') and not mm('opus', 'claude-opus-4-1-20250805')
    assert not mm('claude-fable-5-1', 'Claude-Fable-5-1-20260901') and not mm('claude-fable-5-1-20260901', 'claude-fable-5-1')
    assert mm('claude-fable-5-1', 'claude-haiku-4-5-20251001') and not mm('claude-fable-5-1', None) and not mm(None, 'x')
    assert not mm('claude-fable-5-1', 'claude-haiku-4-5,claude-fable-5-1-20260901')
    def served_as(model):
        def f(cmd, **kw):
            if cmd[:3] == ['claude', 'auth', 'status']:
                return FakeProc(json.dumps({'loggedIn': True}))
            return FakeProc(json.dumps({'result': '{"answer": true, "p_true": 0.9}', 'num_turns': 1, 'modelUsage': {model: {}}}))
        return f
    for served, want in (('claude-test-pin-20260930', 0), ('claude-other-9', 3)):
        td = tempfile.mkdtemp(); subprocess.run = served_as(served)
        try:
            sys.argv = ['typed_questions.py', '--run', str(run_dir), '--mode', 'live', '--rows', '5', '--model', 'claude-test-pin', '--out', td]
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                code = tq.main()
        finally:
            subprocess.run, sys.argv = real, old_argv
        rep = json.loads((pathlib.Path(td) / 'report.json').read_text())
        recs = [json.loads(l) for l in (pathlib.Path(td) / 'calls.jsonl').read_text().splitlines()]
        assert code == 0 and rep['errors'] == 0 and rep['model_mismatches'] == want, rep
        assert sum(1 for r in recs if r.get('model_mismatch')) == want
    rep, _ = fixture('--backend', 'cascade')
    assert rep['model_mismatches'] == 0

    ren = {'day01': 'afe_cover', 'day12': 'ticket_a', 'day30': 'jib'}                                     # 22
    cset, crun = pathlib.Path(tempfile.mkdtemp()), pathlib.Path(tempfile.mkdtemp())
    m2 = json.loads(json.dumps(manifest))
    for pk in m2['packets']:
        pk['packet_id'] = ren[pk['packet_id']]
    for doc in m2['documents']:
        doc['packet'] = ren[doc['packet']]
    (cset / 'manifest.json').write_text(json.dumps(m2)); shutil.copytree(ROOT / 'truth' / 'synth', cset / 'truth')
    (crun / 'raw').mkdir()
    for old, new in ren.items():
        shutil.copy(run_dir / 'raw' / f'{old}__extract.json', crun / 'raw' / f'{new}__extract.json')
    assert {pk['packet_id'] for pk in m2['packets']} <= {d['doc_id'] for d in m2['documents']}, 'the copy must collide'
    o = subprocess.run([sys.executable, runner, '--set', str(cset), '--run', str(crun), '--mode', 'parity-check', '--parity'],
                       capture_output=True, text=True)
    assert o.returncode == 0 and o.stdout.splitlines()[0] == 'parity 85 of 85', o.stdout[:300]
    o = subprocess.run([sys.executable, runner, '--set', str(cset), '--run', str(crun), '--mode', 'dry-run', '--parity'], capture_output=True, text=True)
    assert json.loads(o.stdout)['requests'] == 85
    td = pathlib.Path(tempfile.mkdtemp())
    o = subprocess.run([sys.executable, runner, '--set', str(cset), '--run', str(crun), '--backend', 'cascade', '--mode', 'fixture', '--out', str(td)],
                       capture_output=True, text=True)
    assert o.returncode == 0, o.stderr
    rep = json.loads((td / 'report.json').read_text())
    assert rep['units'] == 85 and rep['errors'] == 0 and rep['cascade']['claude_alone_calls'] == 85, rep['cascade']
    us = {(r['node'], r['subject']): r for r in map(json.loads, (td / 'calls.jsonl').read_text().splitlines()) if r.get('kind') == 'unit'}
    u1, u5 = us[('row1', 'afe_cover')], us[('row5', 'afe_cover')]
    assert u1['jev']['escalated'] and 'probabilities' in u1['claude']['answer'] and u1['claude']['final'] == 'afe', u1['claude']
    assert u1['parity_sha256']['jev'] == u1['parity_sha256']['claude'] != u5['parity_sha256']['jev'], (u1['parity_sha256'], u5['parity_sha256'])

    def dry(*extra):    # dry-run summary JSON; no key in the child's env, out dir in a temp folder (jev writes bodies)
        o = subprocess.run([sys.executable, runner, '--run', str(run_dir), '--mode', 'dry-run', '--out', tempfile.mkdtemp(), *extra],
                           capture_output=True, text=True, env={k: v for k, v in os.environ.items() if k != tq.jev.KEY_ENV})
        assert o.returncode == 0, (extra, o.stderr)
        return json.loads(o.stdout)
    A = tq.ALIAS_AFE_NUMBER                                                                               # 23
    assert A == '. The approval reference may appear under a different label.', A
    n_afe = sum(1 for d in docs if 'afe_number' in tq.REQUIRED[d['class']])
    assert n_afe > 0
    for row8 in ('per-field', 'per-document'):
        base8 = tq.make_requests({8}, docs, packets, page_text, truth, row8, 'short')
        ali8 = tq.make_requests({8}, docs, packets, page_text, truth, row8, 'short', alias='afe_number')
        assert tq.make_requests({8}, docs, packets, page_text, truth, row8, 'short', alias='none') == base8
        assert len(base8) == len(ali8)
        changed = 0
        for b, x in zip(base8, ali8):
            if row8 == 'per-field':
                if b['subject'].endswith('.afe_number'):
                    assert x['question'] == b['question'] + A and x['question'].endswith(A), x['question']
                    assert dict(x, question=b['question']) == b; changed += 1
                else:
                    assert x == b, x['subject']
            else:
                bd, xd = b['descriptions'], x['descriptions']
                if 'afe_number' in bd:
                    assert xd['afe_number'] == bd['afe_number'] + A; changed += 1
                assert {k: v for k, v in xd.items() if k != 'afe_number'} == {k: v for k, v in bd.items() if k != 'afe_number'}
                jb, jx = tq.jev.build_request(b), tq.jev.build_request(x)      # the Jev body carries it too, afe_number only
                assert all(jx['questions'][f]['instructions'] == jb['questions'][f]['instructions'] + (A if f == 'afe_number' else '')
                           for f in b['fields'])
                assert (tq.parity_hashes(x, 'jev') != tq.parity_hashes(b, 'jev')) == ('afe_number' in bd)
        assert changed == n_afe, (row8, changed, n_afe)
    assert tq.make_requests({1, 4, 5, 8}, docs, packets, page_text, truth, 'per-document', alias='none') == reqs
    try:
        tq.make_requests({8}, docs, packets, page_text, truth, 'per-field', alias='afe_number'); raise AssertionError('alias with no descriptions')
    except SystemExit as e:
        assert '--alias afe_number needs --field-desc' in str(e), e
    o = subprocess.run([sys.executable, runner, '--run', str(run_dir), '--mode', 'parity-check', '--parity', '--alias', 'afe_number'],
                       capture_output=True, text=True)
    assert o.returncode == 0 and o.stdout.splitlines()[0] == 'parity 85 of 85' and json.loads(o.stdout.splitlines()[-1])['alias'] == 'afe_number', o.stdout[:300]
    rep, td = fixture('--parity', '--alias', 'afe_number')
    assert (rep['alias'], rep['claude_row8'], rep['calls'], rep['errors']) == ('afe_number', 'per-field', 85, 0), rep
    prompts = [json.loads(l)['prompt'] for l in (td / 'prompts.jsonl').read_text().splitlines()]
    assert sum(1 for p in prompts if A in p) == n_afe and 'Alias arm' in (td / 'report.md').read_text()
    assert base['alias'] == 'none' and par['alias'] == 'none' and par['claude_row8'] == 'per-field'
    rep, _ = fixture('--backend', 'cascade', '--alias', 'afe_number')
    assert rep['alias'] == 'afe_number' and rep['cascade']['claude_calls'] == 4, rep['cascade']
    assert dry('--parity')['tag'] == 'parity-desc-short-opt-verbatim' and dry('--backend', 'cascade')['tag'] == 'cascade-0.80'
    assert dry('--parity', '--alias', 'afe_number')['tag'] == 'parity-desc-short-opt-verbatim-alias-afe_number'
    assert dry('--backend', 'jev', '--parity', '--alias', 'afe_number')['tag'] == 'jev-parity-desc-short-opt-verbatim-alias-afe_number'
    assert dry('--backend', 'cascade', '--alias', 'afe_number')['tag'] == 'cascade-0.80-alias-afe_number'

    rep, td = fixture('--parity', '--claude-row8', 'per-document')                                       # 24
    assert (rep['calls'], rep['units'], rep['row8_mode'], rep['claude_row8'], rep['parity'], rep['disagree_abstain'], rep['errors']) == \
        (26, 85, 'per-document', 'per-document', True, False, 0), rep
    assert rep['nodes']['row8']['n'] == 66 and 'Batched arm' in (td / 'report.md').read_text()
    recs = [json.loads(l) for l in (td / 'calls.jsonl').read_text().splitlines()]
    assert sum(1 for r in recs if r['node'] == 'row8') == 7 and all(len(r['parity_sha256']) == len(r['label']) for r in recs if r['node'] == 'row8')
    sent8 = [json.loads(l)['prompt'] for l in (td / 'prompts.jsonl').read_text().splitlines()][-7:]
    assert sent8 == [tq.prompt_for(r) for r in tq.make_requests({8}, docs, packets, page_text, truth, 'per-document', 'short', 'verbatim')]
    o = subprocess.run([sys.executable, runner, '--run', str(run_dir), '--mode', 'dry-run', '--claude-row8', 'per-document'], capture_output=True, text=True)
    assert o.returncode == 2 and '--claude-row8 applies under --parity' in o.stderr and not o.stdout, o
    d = dry('--parity', '--claude-row8', 'per-document')
    assert (d['requests'], d['by_node']['row8'], d['row8'], d['tag']) == (26, 7, 'per-document', 'parity-desc-short-opt-verbatim-c8-per-document'), d
    assert dry('--parity', '--claude-row8', 'per-document', '--alias', 'afe_number')['tag'] == 'parity-desc-short-opt-verbatim-alias-afe_number-c8-per-document'
    rep, _ = fixture('--backend', 'cascade', '--claude-row8', 'per-document')
    c = rep['cascade']
    assert (c['claude_calls'], c['claude_alone_calls'], rep['claude_row8'], rep['row8_mode']) == (4, 85, 'per-field', 'jev per-document, claude per-field'), rep
    dc, dc0 = dry('--backend', 'cascade', '--claude-row8', 'per-document'), dry('--backend', 'cascade')
    assert dc['tag'] == 'cascade-0.80' and (dc['calls_upper_bound'], dc['parity']) == (dc0['calls_upper_bound'], dc0['parity']) == (111, '85 of 85'), dc
    dj = dry('--backend', 'jev', '--parity', '--claude-row8', 'per-document')
    assert dj['tag'] == 'jev-parity-desc-short-opt-verbatim' and dj['requests'] == dry('--backend', 'jev', '--parity')['requests'] == 26, dj

    g5 = ROOT.parent / 'artifacts' / 'typed-questions-2026-09-28' / 'live-results' / 'g5-row4-collapsed' / 'live-synth-03' / 'calls.jsonl'   # 13
    if g5.exists():
        o = subprocess.run([sys.executable, runner, '--run', str(run_dir), '--mode', 'dry-run', '--compare-hashes', str(g5)],
                           capture_output=True, text=True)
        d = json.loads(o.stdout)
        assert o.returncode == 0 and d['hash_match'] == '26 of 26' and d['network_calls'] == 0, (o.stdout, o.stderr)
        n = 24
    else:
        print('SKIP group 13: G5 artifact absent'); n = 23
    print(f'OK {n} assertion groups')
    return 0

if __name__ == '__main__':
    sys.exit(main())
