"""Tests for heldout2/run_heldout2.py (BUILD-SPEC H3). No network, no live call, no spend.

Every end-to-end test runs the orchestrator in --stub mode against a throwaway demo tree under the system temp
dir (real briefs and inputs copied in, placeholders for the code files), so nothing is written into the real
repo tree. Run: python3 -m pytest heldout2/tests/test_orchestrator.py -q   (or python3 -m unittest)
"""
import importlib.util, json, os, pathlib, shutil, signal, subprocess, sys, tempfile, time, unittest

HERE = pathlib.Path(__file__).resolve().parent
DEMO = HERE.parent.parent
SCRIPT = DEMO / 'heldout2' / 'run_heldout2.py'
spec = importlib.util.spec_from_file_location('run_heldout2', SCRIPT)
rh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rh)

MARKERS = ('KEY', 'TOKEN', 'SECRET')
PLACEHOLDER_HEADERS = {   # used only when a real brief is missing
    'critic': ('heldout2/inputs/composition.md, schemas/field_ticket.json', 'coverage.json', 'synth-heldout2/design/'),
    'designer': ('@critic/coverage.json, heldout2/inputs/composition.md', 'case_spec.json', 'synth-heldout2/design/'),
    'generator': ('@designer/case_spec.json, heldout2/inputs/composition.md, synth-heldout/src/', 'src/build.py, cases.json',
                  'synth-heldout2/'),
    'key_a': ('@render/, heldout2/inputs/composition.md', 'truth/, manifest.json, REPORT.md', 'synth-heldout2/'),
    'rekey': ('@render/clean/, @render/page-images/clean/, heldout2/inputs/rekey_fields.md', 'truth-blind/', 'synth-heldout2/blind/'),
    'adjudicate': ('@compare/disagreements.json, @render/page-images/', 'rulings.json', 'synth-heldout2/adjudication/'),
    'layerb': ('@make_layerb/pages/, heldout2/inputs/layerb_fields.md', 'truth-b/', 'synth-heldout2/layerB/'),
    'audit': ('@make_audit2/', 'answers/answers.json', 'synth-heldout2/audit/'),
}


def make_tree(tmp):
    """A throwaway demo tree: the real heldout2 code, briefs, inputs, typed/ runner, reconcile.py, schemas/, run 1
    tools, H2's fixture builder, and two run 1 PDFs (one page, two pages) the stub render reuses. Placeholders only
    for the run 1 generator inputs. Nothing is written into the real demo tree."""
    d = pathlib.Path(tmp) / 'demo'
    w = lambda rel, text: (d / rel).parent.mkdir(parents=True, exist_ok=True) or (d / rel).write_text(text)

    def cp(rel, dst=None):
        (d / (dst or rel)).parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if (DEMO / rel).is_dir() else shutil.copy2)(DEMO / rel, d / (dst or rel))
    for b in rh.BRIEFS:
        real = DEMO / 'heldout2' / 'briefs' / f'{b}.md'
        if real.is_file():
            cp(f'heldout2/briefs/{b}.md')
        else:
            i, o, c = PLACEHOLDER_HEADERS[b]
            w(f'heldout2/briefs/{b}.md', f'INPUTS: {i}\nOUTPUTS: {o}\nCOPY_OUT: {c}\n\nPlaceholder brief {b}.\n')
    for name in ('composition.md', 'layerb_fields.md', 'rekey_fields.md', 'run1_labels.txt'):
        real = DEMO / 'heldout2' / 'inputs' / name
        w(f'heldout2/inputs/{name}', real.read_text() if real.is_file() else f'placeholder {name}\n')
    for rel in ('heldout2/controls.py', 'heldout2/score_heldout2.py', 'heldout2/make_audit2.py',
                'heldout2/tests/fixtures/build_fixture.py', 'reconcile.py', 'schemas', 'typed/__init__.py',
                'typed/typed_questions.py', 'typed/jev_backend.py', 'synth-heldout/tools/freeze_hashes.py',
                'synth-heldout/tools/make_layerb.py', 'synth-pilot/layerB/clean/BRIEF.md'):
        cp(rel)
    for s in ('clean', 'scan'):
        for f in ('01_ticket_01.pdf', '60_afe_01.pdf', 'packets/ticket_16.pdf', 'packets/jib_01.pdf', 'packets/afe_01.pdf'):
            cp(f'synth-heldout/{s}/{f}')
    w('synth-heldout/src/build.py', '# placeholder run 1 generator\n')
    for rel in ('synth-heldout/manifest.json', 'synth-heldout/reference'):   # the earlier corpus: gate 5b reads its names
        cp(rel)
    w('synth-heldout/traps.json', '[]\n')
    return d


def test_env(extra=None):
    """Parent env without any real secret, plus dummy secrets the children must not see."""
    env = {k: v for k, v in os.environ.items() if not any(m in k.upper() for m in MARKERS)}
    env.update({'PULSE_API_KEY': 'p' * 24, 'TYPESAFE_API_KEY': 't' * 24, 'FAKE_SERVICE_KEY': 'dummy',
                'SOME_AUTH_TOKEN': 'dummy', 'MY_SECRET_THING': 'dummy', 'lower_case_key_name': 'dummy'})
    env.update(extra or {})
    return env


def orch(demo, *args, timeout=240):
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, str(SCRIPT), '--demo', str(demo), *args], capture_output=True, text=True,
                       env=test_env(), timeout=timeout)
    p.wall = time.monotonic() - t0
    return p


def run_root(demo):
    roots = sorted((demo / 'runs' / 'heldout2').iterdir())
    assert len(roots) == 1, roots
    return roots[0]


def faults(tmp, obj):
    p = pathlib.Path(tmp) / 'faults.json'
    p.write_text(json.dumps(obj))
    return str(p)


def calls(root):
    out = {}
    f = root / 'stub-calls.jsonl'
    for line in (f.read_text().splitlines() if f.is_file() else []):
        r = json.loads(line)
        out[r['stage']] = out.get(r['stage'], 0) + 1
    return out


def state(root):
    return json.loads((root / 'state.json').read_text())


def ledger(root):
    return rh.Ledger(root / 'ledger.json')


# ------------------------------------------------------------------------------------------------ end to end
class TestStubEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.demo = make_tree(cls.tmp.name)
        cls.p = orch(cls.demo, '--stub')
        cls.root = run_root(cls.demo)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_reaches_score_with_every_stage_done(self):
        self.assertEqual(self.p.returncode, 0, self.p.stderr[-2000:])
        st = state(self.root)
        self.assertEqual([s for s in st['stage_order'] if st['stages'][s]['status'] != 'DONE'], [])
        self.assertTrue((self.root / 'score.json').is_file())
        log = (self.root / 'status.log').read_text()
        self.assertIn('score', log)
        self.assertRegex(log, r'score\s+DONE')
        self.assertIn('COMPLETE', log)
        self.assertFalse((self.root / 'quarantine').exists())

    def test_arms_order_count_and_tags(self):
        arms = json.loads((self.root / 'arms.json').read_text())
        want = {a: n for a, _, n, _, _ in rh.ARMS}
        for s in rh.SETS:
            self.assertEqual({a: len(v) for a, v in arms[s].items()}, want)
            for a, runs in arms[s].items():
                for r in runs:
                    name = pathlib.Path(r['out']).name
                    self.assertEqual('-alias-afe_number' in name, 'alias' in a, name)
                    self.assertEqual('-c8-per-document' in name, a == 'A-batched', name)
        order = [s for s in state(self.root)['stage_order'] if s.startswith('arm.clean.')]
        self.assertEqual(order[:4], ['arm.clean.A.r1', 'arm.clean.A.r2', 'arm.clean.B.r1', 'arm.clean.B.r2'])

    def test_ledger_settles_actuals(self):
        lg = ledger(self.root)
        self.assertAlmostEqual(lg.spent('pulse_credits'), 720.0, places=6)
        self.assertAlmostEqual(lg.spent('jev_usd'), 16 * 0.0106, places=9)
        self.assertTrue(all(e['state'] == 'settled' for e in lg.d['entries']))

    def test_children_never_see_secrets(self):
        dumps = sorted((self.root / 'logs').glob('env-*.json'))
        self.assertGreater(len(dumps), 40)
        for f in dumps:
            names = {n for n in json.loads(f.read_text()) if any(m in n.upper() for m in MARKERS)}
            stage = f.name[4:].rsplit('-a', 1)[0]
            if stage.startswith('pulse.'):
                allowed = {'PULSE_API_KEY'}
            elif stage.startswith('arm.') and any(f'.{a}.' in stage for a in ('B', 'C', 'B-alias', 'C-alias')):
                allowed = {'TYPESAFE_API_KEY'}
            else:
                allowed = set()
            self.assertEqual(names, allowed, f.name)
        for f in [self.root / 'state.json', self.root / 'status.log', self.root / 'ledger.json'] + list((self.root / 'records').glob('*.json')):
            self.assertNotIn('p' * 24, f.read_text())
            self.assertNotIn('t' * 24, f.read_text())

    def test_codex_records(self):
        rec = json.loads((self.root / 'records' / 'critic-a1.json').read_text())
        self.assertEqual(len(rec['prompt_sha256']), 64)
        self.assertEqual(rec['scan']['hits'], [])
        self.assertIn('rollout', rec['scan']['sources'])
        self.assertGreaterEqual(rec['env_names_removed'], 6)
        self.assertTrue(rec['argv'][-1].startswith('<prompt sha256'))
        folder = self.root / 'stub-sessions' / 'critic'
        self.assertTrue((folder / 'composition.md').is_file())          # heldout2/inputs/ arrives by file name
        self.assertTrue((folder / 'schemas' / 'field_ticket.json').is_file())
        key_a = self.root / 'stub-sessions' / 'key_a'
        self.assertTrue((key_a / 'case_spec.json').is_file())           # @render/ arrives at the folder root
        self.assertTrue((self.root / 'stub-sessions' / 'rekey' / 'page-images' / 'clean').is_dir())
        self.assertRegex((self.root / 'status.log').read_text(), r'critic\s+INHERITS')


class TestResume(unittest.TestCase):
    def test_forced_stop_then_resume_skips_finished_and_keeps_counters(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stub-faults', faults(tmp, {'layerb.clean': {'kill_parent': [1]}}))
            self.assertEqual(p.returncode, 1, p.stderr[-1500:])
            self.assertIn('interrupted', p.stderr)
            root = run_root(demo)
            st = state(root)
            self.assertEqual(st['stages']['layerb.clean']['status'], 'FAILED')
            self.assertEqual(st['stages']['layerb.clean']['attempts'], 1)
            before = calls(root)
            p2 = orch(demo, '--resume', root.name)
            self.assertEqual(p2.returncode, 0, p2.stderr[-1500:])
            after = calls(root)
            for sid in st['stage_order'][:st['stage_order'].index('layerb.clean')]:
                self.assertEqual(after.get(sid, 0), before.get(sid, 0), f'{sid} re-ran on resume')
            st2 = state(root)
            self.assertEqual(st2['stages']['layerb.clean']['attempts'], 2)
            self.assertEqual(st2['pools']['layerb.clean'], 1)
            self.assertEqual(after['layerb.clean'], 2)
            self.assertTrue((root / 'quarantine' / 'layerb.clean-a1').is_dir())
            self.assertIn('RESUME', (root / 'status.log').read_text())

    def test_retry_budget_persists_across_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stub-faults', faults(tmp, {'designer': {'fail': [1, 2]}}))
            self.assertEqual(p.returncode, 1)
            self.assertIn('retry budget for design used (1/1)', p.stderr)
            root = run_root(demo)
            p2 = orch(demo, '--resume', root.name)                      # no faults now; counters must still bind
            self.assertEqual(p2.returncode, 1)
            self.assertIn('retry budget for design used (1/1)', p2.stderr)
            self.assertEqual(calls(root)['designer'], 2)
            self.assertEqual(state(root)['pools']['design'], 1)

    def test_r7_build_group_reruns_all_three(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stop-after', 'key_a', '--stub-faults', faults(tmp, {'key_a': {'fail': [1]}}))
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            root = run_root(demo)
            c = calls(root)
            self.assertEqual((c['generator_source'], c['render'], c['key_a']), (2, 2, 2))
            self.assertEqual(state(root)['pools']['build'], 1)
            self.assertIn('R7 group build', (root / 'status.log').read_text())

    def test_r7_amended_build_group_gets_two_rebuilds_then_stops(self):   # Frank's ruling, 2026-10-02
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stop-after', 'key_a', '--stub-faults', faults(tmp, {'key_a': {'fail': [1, 2]}}))
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            root = run_root(demo)
            c = calls(root)
            self.assertEqual((c['generator_source'], c['render'], c['key_a']), (3, 3, 3))
            self.assertEqual(state(root)['pools']['build'], 2)
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stop-after', 'key_a', '--stub-faults', faults(tmp, {'key_a': {'fail': [1, 2, 3]}}))
            self.assertEqual(p.returncode, 1)
            self.assertIn('retry budget for build used (2/2)', p.stderr)


class TestLedger(unittest.TestCase):
    def test_caps_and_unknown_outcome_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            lg = rh.Ledger(pathlib.Path(tmp) / 'ledger.json')
            lg.reserve('pulse.clean', 1, 'pulse_credits', 400)
            lg.settle('pulse.clean', 1, 'pulse_credits', 500)
            self.assertTrue(lg.would_pass('pulse_credits', 400))          # 500 + 400 > 800
            self.assertFalse(lg.would_pass('pulse_credits', 300))         # 800 is the cap, not past it
            lg.reserve('arm.clean.B.r1', 1, 'jev_usd', 0.03)
            lg.settle('arm.clean.B.r1', 1, 'jev_usd', 0.48)
            self.assertTrue(lg.would_pass('jev_usd', 0.03))               # 0.48 + 0.03 > 0.50
            lg.reserve('arm.clean.C.r1', 1, 'jev_usd', 0.01)              # outcome never learned
            lg2 = rh.Ledger(pathlib.Path(tmp) / 'ledger.json')            # a restart reloads the file
            self.assertAlmostEqual(lg2.spent('jev_usd'), 0.49)
            lg2.mark_unknown('arm.clean.C.r1', 1, 'jev_usd')
            lg2.settle('arm.clean.C.r1', 1, 'jev_usd', 0.0)               # unknown stays at its bound
            self.assertAlmostEqual(rh.Ledger(pathlib.Path(tmp) / 'ledger.json').spent('jev_usd'), 0.49)

    def test_pulse_cap_refusal_e2e(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stub-faults', faults(tmp, {'pulse.clean': {'credits': 500}}))
            self.assertEqual(p.returncode, 1)
            root = run_root(demo)
            self.assertEqual(state(root)['stages']['pulse.scan']['status'], 'REFUSED')
            self.assertIn('CAP: pulse_credits spent 500 + bound 400 would pass cap 800', p.stderr)
            self.assertIn('Pulse retry is whole-set only', p.stderr)
            self.assertNotIn('pulse.scan', calls(root))

    def test_jev_cap_refusal_e2e(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stub-faults', faults(tmp, {'arm.clean.B.r1': {'jev_cost': 0.49}}))
            self.assertEqual(p.returncode, 1)
            root = run_root(demo)
            self.assertEqual(state(root)['stages']['arm.clean.B.r2']['status'], 'REFUSED')
            self.assertIn('CAP: jev_usd spent 0.49 + bound 0.045 would pass cap 0.5', p.stderr)

    def test_unknown_outcome_counted_as_spent_e2e(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stub-faults', faults(tmp, {'pulse.clean': {'kill_parent': [1]}}))
            self.assertEqual(p.returncode, 1)
            lg = ledger(run_root(demo))
            self.assertEqual([e['state'] for e in lg.d['entries']], ['unknown'])
            self.assertEqual(lg.spent('pulse_credits'), 400.0)


# ------------------------------------------------------------------------------------------------ R4 scan
class TestScan(unittest.TestCase):
    F = '/work/run/sessions/critic'
    H = '/Users/someone'

    def hits(self, cmds):   # made-up paths: every mentioned path counts as existing
        return [h for h in rh.scan_commands(cmds, self.F, home=self.H, exists=lambda p: True) if h[0] == 'hit']

    def test_inside_and_system_paths_pass(self):
        cmds = [('ls -la', self.F), (f'/bin/zsh -lc "cat {self.F}/coverage.json >/dev/null 2>&1"', self.F),
                ('cd truth && cat ../composition.md', self.F), ('python3 -c "print(1/2)"', None),
                ('curl https://example.com/x', self.F), (f'cat {self.H}/.codex/plugins/cache/pdf/SKILL.md', self.F)]
        self.assertEqual(self.hits(cmds), [])

    def test_outside_reads_are_hits(self):
        cases = ['cat /Users/someone/Documents/private/plan.md', 'cat ../../frozen-code.json', 'cat ~/notes.txt',
                 'head $HOME/x', 'cd truth && cat ../../../x', 'sed -n 1p /tmp/leak.txt']
        for c in cases:
            self.assertTrue(self.hits([(c, self.F)]), c)
        self.assertTrue(self.hits([('ls', '/Users/someone')]))           # workdir outside the folder

    def test_html_closing_tags_in_written_templates_are_not_paths(self):
        tpl = ('cat > src/templates.py <<\'PY\'\nT = "<div class=\\"h\\"><span>{v}</span><p>x</p></div>\\n"'
               '<table><tbody><tr><td>1</td></tr></tbody></table></ h1>\nPY')
        self.assertEqual(self.hits([(tpl, self.F)]), [])
        py = "h=(ROOT/'src'/f'{ident}.html').read_text(); css = ''' /* note */ '''"
        self.assertEqual(self.hits([(py, self.F)]), [])                 # "/f" and "/*" are not top-level names
        for c in ('cat </Users/someone/passwd', 'echo "</span>" && cat /Users/someone/x.md', 'cat <~/secret>',
                  'ls /tmp/x', 'cat /private/var/log/x'):
            self.assertTrue(self.hits([(c, self.F)]), c)

    def test_mention_of_a_path_that_does_not_exist_is_not_a_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / 'sessions' / 'key_a'
            (f / 'scan').mkdir(parents=True)
            real = pathlib.Path(tmp) / 'sessions' / 'outside.md'
            real.write_text('x')
            hits = lambda c: [h for h in rh.scan_commands(c, f, home='/Users/someone') if h[0] == 'hit']
            prose = ("python3 - <<'PY'\ns=scan.read_text().replace('old', 'See ../REPORT.md for file checks and "
                     "../README.md for visual checks.')\nPY")
            self.assertEqual(hits([(prose, f)]), [])                               # ../REPORT.md does not exist
            self.assertEqual([h[1] for h in hits([(f'cat ../outside.md', f)])], [str(real)])   # it does
            self.assertTrue(hits([('cat /Users/someone/*.md', f)]))                # a glob may match real files

    def test_own_temp_file_is_allowed_but_a_foreign_one_is_not(self):
        own = [("/bin/zsh -lc \"cat > /tmp/build_case_spec.py <<'PY'\nimport json\nPY\"", self.F),
               ('python3 /tmp/build_case_spec.py', self.F), ('rm /tmp/build_case_spec.py', self.F),
               ('cat /tmp/build_case_spec.py > /tmp/copy.py', self.F)]
        self.assertEqual(self.hits(own), [])
        foreign = [('python3 /tmp/left_by_someone.py', self.F), ('echo x > /tmp/left_by_someone.py', self.F)]
        self.assertEqual([h[2] for h in self.hits(foreign)], ['python3 /tmp/left_by_someone.py'])   # the read came first
        self.assertEqual([h[1] for h in self.hits([('cat /tmp/leak.txt > /tmp/mine.txt', self.F)])], ['/tmp/leak.txt'])
        self.assertTrue(self.hits([('echo x > /Users/someone/not_temp.txt', self.F)]))         # redirect outside temp

    def test_rollout_and_stdout_parsers(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = pathlib.Path(tmp) / 'rollout.jsonl'
            r.write_text('\n'.join(json.dumps(x) for x in [
                {'type': 'session_meta', 'payload': {'cwd': self.F}},
                {'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'exec_command',
                                                      'arguments': json.dumps({'cmd': 'cat /etc/hosts', 'workdir': self.F})}},
                {'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'name': 'exec',
                                                      'input': 'tools.exec_command({cmd:"ls\\n/Users/someone/secret.md"})'}},
                {'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'name': 'apply_patch',
                                                      'input': '*** Add File: /Applications/Google Chrome.app'}},
            ]) + '\n')
            cwd, cmds = rh.commands_from_rollout(r)
            self.assertEqual(cwd, self.F)
            self.assertEqual(len(cmds), 2)
            self.assertEqual([h[1] for h in self.hits(cmds)], ['/Users/someone/secret.md'])
            s = pathlib.Path(tmp) / 'stdout.log'
            s.write_text(f"workdir: {self.F}\nexec\n/bin/zsh -lc 'cat ../x' in {self.F}\n succeeded in 3ms:\n"
                         f"[2026-10-02T10:00:00] exec bash -lc 'ls' in {self.F}\n")
            cmds = rh.commands_from_stdout(s)
            self.assertEqual(len(cmds), 2)
            self.assertEqual([h[1] for h in self.hits(cmds)], ['/work/run/sessions/x'])

    def test_out_of_folder_read_marks_stage_invalid_e2e(self):
        for stage, kind in (('critic', 'read_outside'), ('rekey', 'read_dotdot')):
            with tempfile.TemporaryDirectory() as tmp:
                demo = make_tree(tmp)
                p = orch(demo, '--stub', '--stub-faults', faults(tmp, {stage: {kind: [1]}}))
                self.assertEqual(p.returncode, 3, p.stderr[-1500:])
                root = run_root(demo)
                st = state(root)
                self.assertEqual(st['stages'][stage]['status'], 'INVALID')
                self.assertIn('R4 out-of-folder read', st['stages'][stage]['detail'])
                self.assertEqual(calls(root).get(stage), 1)               # INVALID never retries
                after = st['stage_order'][st['stage_order'].index(stage) + 1]
                self.assertEqual(st['stages'].get(after, {'status': 'PENDING'})['status'], 'PENDING')
                rec = json.loads((root / 'records' / f'{stage}-a1.json').read_text())
                self.assertTrue(rec['scan']['hits'])
                p2 = orch(demo, '--resume', root.name)                    # an INVALID stage cannot be resumed past
                self.assertEqual(p2.returncode, 3)


# ------------------------------------------------------------------------------------------------ deadlines
class TestDeadline(unittest.TestCase):
    def test_sleeping_stage_is_killed_at_its_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            # critic deadline 30 min x 0.002 = 3.6 s; the fake sleeps 60 s on attempt 1 only
            p = orch(demo, '--stub', '--deadline-scale', '0.002', '--stop-after', 'critic',
                     '--stub-faults', faults(tmp, {'critic': {'sleep': {'1': 60}}}))
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            self.assertLess(p.wall, 40)
            root = run_root(demo)
            log = (root / 'status.log').read_text()
            self.assertRegex(log, r'critic\s+FAILED\s+a=1 .*DEADLINE')
            self.assertRegex(log, r'critic\s+DONE\s+a=2')
            pid = int((root / 'logs' / 'sleeper-critic-a1.pid').read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_usage_limit_stops_without_waiting(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stub-faults', faults(tmp, {'arm.clean.A.r1': {'usage_limit': [1]}}))
            self.assertEqual(p.returncode, 1)
            self.assertIn('R11 usage-limit', p.stderr)
            self.assertLess(p.wall, 50)
            self.assertEqual(state(run_root(demo))['stages']['arm.clean.A.r1']['status'], 'USAGE-LIMIT')


# ------------------------------------------------------------------------------------------------ environment
class TestEnv(unittest.TestCase):
    def test_strip_env_unit(self):
        base = {'PATH': '/bin', 'HOME': '/h', 'PULSE_API_KEY': 'x', 'TYPESAFE_API_KEY': 'y', 'GH_TOKEN': 'z',
                'AWS_SECRET_ACCESS_KEY': 'w', 'my_key_var': 'v', 'KEYCHAIN_PATH': 'k'}
        env = rh.strip_env(base=base)
        self.assertEqual({k for k in env if any(m in k.upper() for m in MARKERS)}, set())
        self.assertEqual(env['PATH'], '/bin')
        env = rh.strip_env(allow=('PULSE_API_KEY',), base=base)
        self.assertEqual({k for k in env if any(m in k.upper() for m in MARKERS)}, {'PULSE_API_KEY'})

    def test_real_child_dumps_env_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            o = rh.Orchestrator(DEMO, pathlib.Path(tmp) / 'r', 'stub', pathlib.Path(tmp) / 'w')
            o.state = {}
            o.save = lambda: None
            os.environ['ORCH_TEST_SECRET_X'] = 'dummy'
            os.environ['ORCH_TEST_API_KEY'] = 'dummy'
            try:
                out = pathlib.Path(tmp) / 'env.json'
                child = [sys.executable, '-c', f'import json, os; json.dump(sorted(os.environ), open({str(out)!r}, "w"))']
                outcome, rc = o.run_proc(child, tmp, rh.strip_env(), pathlib.Path(tmp) / 'child.log', 30)
            finally:
                del os.environ['ORCH_TEST_SECRET_X'], os.environ['ORCH_TEST_API_KEY']
            self.assertEqual((outcome, rc), ('exit', 0))
            names = json.loads(out.read_text())
            self.assertEqual([n for n in names if any(m in n.upper() for m in MARKERS)], [])


# ------------------------------------------------------------------------------------------------ freeze
class TestFreeze(unittest.TestCase):
    def test_controls_change_after_freeze_stops_before_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stub-faults', faults(tmp, {'audit.scan': {'touch_code': 'heldout2/controls.py'}}))
            self.assertEqual(p.returncode, 1)
            self.assertIn('FREEZE-MISMATCH: heldout2/controls.py changed after the freeze', p.stderr)
            root = run_root(demo)
            st = state(root)
            self.assertEqual(st['stages']['verify_freeze']['status'], 'FAILED')
            self.assertNotIn('score', calls(root))
            self.assertEqual(st['stages'].get('score', {'status': 'PENDING'})['status'], 'PENDING')
            p2 = orch(demo, '--resume', root.name)
            self.assertEqual(p2.returncode, 1)
            self.assertIn('FREEZE-MISMATCH', p2.stderr)


# ------------------------------------------------------------------------------------------------ compare, R6
class TestAdjudication(unittest.TestCase):
    def test_blinded_list_rulings_applied_and_resume_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            fl = faults(tmp, {'rekey': {'disagree': 3}, 'adjudicate': {'undecidable': 1}})
            p = orch(demo, '--stub', '--stop-after', 'apply_rulings', '--stub-faults', fl)
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            root = run_root(demo)
            dis = json.loads((root / 'stages' / 'compare' / 'disagreements.json').read_text())
            self.assertEqual(len(dis), 3)
            self.assertTrue(all(set(x) == {'doc_id', 'field', 'page', 'images'} for x in dis))   # never a keyer's value
            self.assertIn('blind', json.loads((root / 'private' / 'compare-full.json').read_text())[0])
            sess = root / 'stub-sessions' / 'adjudicate'
            self.assertEqual(json.loads((sess / 'disagreements.json').read_text()), dis)
            work = root / 'work' / 'synth-heldout2'
            self.assertEqual(len(json.loads((work / 'adjudication' / 'changes.json').read_text())), 2)
            self.assertEqual(len(json.loads((work / 'adjudication' / 'excluded.json').read_text())), 1)
            orig = json.loads((work / 'truth-original' / 'ticket_02.json').read_text())['values']['afe_number']
            new = json.loads((work / 'truth' / 'ticket_02.json').read_text())['values']['afe_number']
            self.assertEqual((orig, new), ('TICKET_02-AFE_NUMBER', None))
            p2 = orch(demo, '--resume', root.name)                         # key_a hashes verify through truth-original
            self.assertEqual(p2.returncode, 0, p2.stderr[-1500:])

    def test_r6_more_than_ten_excluded_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            fl = faults(tmp, {'rekey': {'disagree': 12}, 'adjudicate': {'undecidable': 11}})
            p = orch(demo, '--stub', '--stub-faults', fl)
            self.assertEqual(p.returncode, 3)
            self.assertIn('R6: 11 excluded units', p.stderr)
            self.assertEqual(state(run_root(demo))['stages']['apply_rulings']['status'], 'INVALID')


# ------------------------------------------------------------------------------------------------ real checks
class TestRealPieces(unittest.TestCase):
    def test_real_briefs_parse_and_refs_resolve(self):
        o = rh.Orchestrator(DEMO, pathlib.Path(tempfile.gettempdir()) / 'unused', 'live', DEMO)
        for s in o.plan:
            if s['kind'] != 'codex':
                continue
            b = o.brief(s)
            self.assertTrue(b['outputs'] and b['copy_out'], s['id'])
            for e in b['inputs']:
                src, dest, is_dir, ref = o.resolve_input(s, e)
                if e.startswith('@'):
                    self.assertLess(o.ids.index(ref.split('#')[0]), o.ids.index(s['id']), f'{s["id"]} {e}')
        self.assertEqual(o.ref_stage(o.by_id['adjudicate_audit.scan'], 'compare'), 'audit_compare.scan')
        self.assertEqual(o.ref_stage(o.by_id['layerb.clean'], 'make_layerb'), 'make_layerb.clean')
        self.assertEqual(o.ref_stage(o.by_id['audit2.scan'], 'make_audit2'), 'make_audit2.scan#secondary')
        self.assertTrue(str(o.stage_folder('critic')).startswith(os.path.expanduser('~/heldout2-sessions/')))
        self.assertEqual(o.stage_folder('render'), o.stage_folder('generator_source'))

    @unittest.skipUnless(shutil.which('sandbox-exec') and shutil.which('getconf'), 'sandbox-exec or getconf not available')
    def test_render_profile_confines_a_child(self):
        """Finding 11: write inside R allowed; write to home denied; read under ~/Documents denied; TCP connect denied."""
        import socket
        with tempfile.TemporaryDirectory(dir='/private/tmp' if os.path.isdir('/private/tmp') else None) as tmp:
            sess = pathlib.Path(tmp) / 'session'
            sess.mkdir()
            T, D = rh.darwin_temp_dir(), os.path.realpath(os.path.expanduser('~/Documents'))
            self.assertTrue(T and not T.endswith('/'))
            prof = pathlib.Path(tmp) / 'p.sb'
            prof.write_text(rh.RENDER_PROFILE.replace('{R}', os.path.realpath(sess)).replace('{T}', T).replace('{D}', D))
            home_probe = os.path.join(os.path.expanduser('~'), f'.heldout2-sandbox-probe-{os.getpid()}')
            cache = subprocess.run(['getconf', 'DARWIN_USER_CACHE_DIR'], capture_output=True, text=True).stdout.strip()
            cache_probe = os.path.join(os.path.realpath(cache), f'heldout2-sandbox-probe-{os.getpid()}')   # /var/folders, not T
            srv = socket.socket()
            srv.bind(('127.0.0.1', 0))
            srv.listen(1)
            port = srv.getsockname()[1]
            probe = (
                'import os, socket, sys\n'
                'def t(f):\n'
                '    try: f(); return "ok"\n'
                '    except OSError: return "denied"\n'
                'def home(): os.close(os.open(sys.argv[1], os.O_CREAT | os.O_EXCL | os.O_WRONLY))\n'
                'def tcp(): socket.create_connection(("127.0.0.1", int(sys.argv[3])), timeout=3).close()\n'
                'def cache(): os.close(os.open(sys.argv[4], os.O_CREAT | os.O_EXCL | os.O_WRONLY))\n'
                'print(t(lambda: open("inside.txt", "w").write("x")), t(home), t(lambda: open(sys.argv[2]).read()), t(tcp),'
                ' t(lambda: open("/dev/null", "w").write("x")), t(cache))\n')
            try:
                r = subprocess.run(['sandbox-exec', '-f', str(prof), sys.executable, '-c', probe, home_probe, str(SCRIPT), str(port),
                                    cache_probe],
                                   cwd=sess, capture_output=True, text=True, env=rh.strip_env(extra=rh.RENDER_ENV), timeout=60)
            finally:
                srv.close()
                for f in (home_probe, cache_probe):    # only if the sandbox failed; the probe files are ours
                    if os.path.exists(f):
                        os.unlink(f)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(str(SCRIPT).startswith(D))
            # write inside R, write to home, read under Documents, TCP connect, write /dev/null, write in the user cache dir
            self.assertEqual(r.stdout.split(), ['ok', 'denied', 'denied', 'denied', 'ok', 'denied'])

    def test_real_redo_runner_accepts_every_arm_command(self):
        """typed/run-typed-redo.sh (copied, read-only use) parses each arm's flags in --stub --dry-run-only mode."""
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            shutil.copy2(DEMO / 'typed' / 'run-typed-redo.sh', demo / 'typed' / 'run-typed-redo.sh')
            o = rh.Orchestrator(demo, demo / 'runs' / 'heldout2' / 'x', 'live', demo)
            for s in rh.SETS:
                (demo / 'runs' / o.run_id(s)).mkdir(parents=True)
            for st in o.plan:
                if st['kind'] != 'arm' or st['rep'] != 1:
                    continue
                if st['backend'] != 'jev' and not shutil.which('claude'):
                    continue
                argv, cwd, allow, extra = o.argv(st)
                cut = argv.index('--') if '--' in argv else len(argv)
                argv = argv[:cut] + ['--stub', '--dry-run-only'] + argv[cut:]
                r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=60,
                                   env=rh.strip_env(allow, extra, base=test_env()))
                self.assertEqual(r.returncode, 0, f"{st['id']}: {r.stderr[-800:]}")
                self.assertIn('dry-run-only: stopping before confirm', r.stdout, st['id'])


# ------------------------------------------------------------------------------------------------ audits, P5, integration
class TestAudits(unittest.TestCase):
    def test_empty_secondary_set_skips_its_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stub-faults', faults(tmp, {'make_audit2.clean': {'secondary_empty': True},
                                                                    'audit.scan': {'audit_flip': 2}}))
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            root = run_root(demo)
            st = state(root)['stages']
            for sid in ('audit2.clean', 'audit2_compare.clean', 'adjudicate_audit2.clean', 'apply_audit2.clean'):
                self.assertEqual(st[sid]['status'], 'SKIPPED', sid)
            for sid in ('audit2.scan', 'apply_audit2.scan'):
                self.assertEqual(st[sid]['status'], 'DONE', sid)
            self.assertIn('secondary audit set for clean is empty', (root / 'status.log').read_text())
            score_log = (root / 'logs' / 'score-a1.log').read_text()
            self.assertIn('--audit clean=', score_log)
            self.assertIn('--audit2 scan=', score_log)
            self.assertNotIn('--audit2 clean=', score_log)
            self.assertIn('--arms', score_log)
            # the scan primary audit disagreed on 2 items; the stub adjudicator rules them, giving scorer-shaped JSON
            a = json.loads((root / 'work' / 'synth-heldout2' / 'adjudication' / 'scan' / 'audit.json').read_text())
            self.assertEqual(set(a), {'corrections', 'excluded'})
            self.assertTrue(all(':' in k for k in list(a['corrections']) + a['excluded']))
            dis = json.loads((root / 'stages' / 'audit_compare.scan' / 'disagreements.json').read_text())
            self.assertEqual(len(dis), 2)
            self.assertEqual({x['field'] for x in dis}, {'afe_number'})


class TestScorerArmsPairing(unittest.TestCase):
    """score_heldout2 --arms: every orchestrator out dir ends -r1, so P5 must pair by arms.json repeat numbers."""

    def test_p5_pairs_by_orchestrator_repeat(self):
        sys.path.insert(0, str(DEMO / 'heldout2' / 'tests' / 'fixtures'))
        sys.path.insert(0, str(DEMO / 'heldout2'))
        import build_fixture as bf
        import score_heldout2 as sc
        with tempfile.TemporaryDirectory() as tmp:
            docs = bf.documents()
            base = bf.base_answers(docs)
            ren = {'redo-claude-20261101T000000Z-r1': ('redo-claude-20261101T000001Z-r1', 'A', 1),
                   'redo-claude-20261101T000000Z-r2': ('redo-claude-20261101T000002Z-r1', 'A', 2),
                   'redo-jev-20261101T000000Z-r1': ('redo-jev-20261101T000003Z-r1', 'B', 1),
                   'redo-cascade-20261101T000000Z-r1': ('redo-cascade-20261101T000004Z-r1', 'C', 1),
                   'redo-cascade-20261101T000000Z-r2': ('redo-cascade-20261101T000005Z-r1', 'C', 2),
                   'redo-cascade-20261101T000000Z-alias-afe_number-r1': ('redo-cascade-alias-afe_number-20261101T000006Z-r1', 'C-alias', 1),
                   'redo-cascade-20261101T000000Z-alias-afe_number-r2': ('redo-cascade-alias-afe_number-20261101T000007Z-r1', 'C-alias', 2),
                   'redo-claude-20261101T000000Z-c8-per-document-r1': ('redo-claude-c8-per-document-20261101T000008Z-r1', 'A-batched', 1)}
            answers = {ren[k][0]: v for k, v in base.items()}
            corpus, runs = bf.build(tmp, answers=answers)
            arms = {s: {} for s in runs}
            for s, rd in runs.items():
                for old, (name, arm, rep) in ren.items():
                    arms[s].setdefault(arm, []).append({'repeat': rep, 'stage': f'arm.{s}.{arm}.r{rep}', 'out': str(rd / 'typed' / name)})
            ap = pathlib.Path(tmp) / 'arms.json'
            ap.write_text(json.dumps(arms))
            cases = sc.load_cases(corpus / 'cases.json')
            doi = json.loads((corpus / 'reference' / 'doi.json').read_text())
            pair = lambda res: {n: v['paired_with'] for n, v in res['layers']['A_pre_audit']['per_set']['clean']['P5']['per_pair'].items()}
            without = pair(sc.score(corpus, runs, cases, doi, {}, {}))
            with_arms = pair(sc.score(corpus, runs, cases, doi, {}, {}, sc.load_arms(ap)))
            self.assertEqual(len(set(without.values())), 1)            # the bug: both alias runs pair with one base run
            self.assertEqual(with_arms, {'redo-cascade-alias-afe_number-20261101T000006Z-r1': 'redo-cascade-20261101T000004Z-r1',
                                         'redo-cascade-alias-afe_number-20261101T000007Z-r1': 'redo-cascade-20261101T000005Z-r1'})
            out = pathlib.Path(tmp) / 'score.json'
            r = subprocess.run([sys.executable, str(DEMO / 'heldout2' / 'score_heldout2.py'), '--corpus', str(corpus),
                                '--run-clean', str(runs['clean']), '--run-scan', str(runs['scan']), '--arms', str(ap),
                                '--out', str(out)], capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 3, r.stderr[-1500:])     # this fixture's inventory is incomplete: INVALID exits 3
            res = json.loads(out.read_text())
            self.assertEqual(pair(res), with_arms)


class TestIntegration(unittest.TestCase):
    """A --stub run in which the REAL make_layerb.py, make_audit2.py (with pdftoppm and pdfimages), and
    score_heldout2.py run inside the chain. Still faked: every Codex session, render (copies run 1 PDFs), Pulse,
    and the arm runner (calls.jsonl written by H2's build_fixture.write_run)."""

    @unittest.skipUnless(shutil.which('pdftoppm') and shutil.which('pdfimages'), 'poppler tools not available')
    def test_real_audit_builder_and_scorer_in_the_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stub-in-place', '--stub-real', 'make_layerb,make_audit2,score', timeout=600)
            self.assertEqual(p.returncode, 0, p.stdout[-2500:] + p.stderr[-2500:])
            root = run_root(demo)
            log = (root / 'status.log').read_text()
            for tool in ('make_layerb.clean', 'make_audit2.clean', 'make_audit2.scan', 'score'):
                self.assertRegex(log, tool.replace('.', r'\.') + r'\s+DONE .*REAL tool inside a stub run')
            c = calls(root)
            self.assertNotIn('score', c)
            self.assertNotIn('make_audit2.clean', c)
            res = json.loads((root / 'score.json').read_text())
            self.assertEqual(set(res['meta']['audit']), {'clean', 'scan'})
            self.assertEqual(set(res['meta']['audit2']), {'clean', 'scan'})
            self.assertIn('A_post_audit', res['layers'])
            p5 = res['layers']['A_post_audit']['per_set']['clean']['P5']['per_pair']
            self.assertEqual(sorted(v['paired_with'] for v in p5.values()),
                             sorted(x['out'].rsplit('/', 1)[1] for x in json.loads((root / 'arms.json').read_text())['clean']['C']))
            rec = json.loads((root / 'private' / 'audit-record-clean.json').read_text())
            self.assertGreater(rec['primary']['items'], 20)
            self.assertTrue(any(f.suffix == '.png' for f in (demo / 'synth-heldout2' / 'audit' / 'clean' / 'pages').iterdir()))
            self.assertTrue(any(f.suffix == '.jpg' for f in (demo / 'synth-heldout2' / 'audit' / 'scan' / 'pages').iterdir()))
            md = (root / 'score.md').read_text().splitlines()
            print('\n--- integration: verdict ' + json.dumps(res['verdict']))
            print('--- integration: first lines of score.md\n' + '\n'.join(md[:14]))
            print('--- integration: audit items primary/secondary clean %d/%d, scan %d/%d' % (
                rec['primary']['items'], rec['secondary']['items'],
                *[json.loads((root / 'private' / 'audit-record-scan.json').read_text())[t]['items'] for t in ('primary', 'secondary')]))


# ------------------------------------------------------------------------------------------------ review 1 fixes
class TestReviewFixes(unittest.TestCase):
    def test_f1_secrets_redacted_in_logs_status_and_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stop-after', 'pulse.clean', '--stub-faults', faults(tmp, {'pulse.clean': {'echo_key': True}}))
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            root = run_root(demo)
            self.assertIn('Bearer [REDACTED]', (root / 'logs' / 'pulse.clean-a1.log').read_text())
            for f in root.rglob('*'):
                if f.is_file() and 'work' not in f.relative_to(root).parts:
                    self.assertNotIn(b'p' * 24, f.read_bytes(), str(f))
            self.assertNotIn('p' * 24, p.stdout + p.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            rh.load_secrets({'X_API_KEY': 'S3cretValue12345', 'PATH_TOKEN_DIR': '/Users/x', 'SHORT_KEY': 'abc'})
            try:
                o = rh.Orchestrator(DEMO, pathlib.Path(tmp), 'stub', pathlib.Path(tmp))
                o.status('x', 'FAILED', 1, 'server echoed S3cretValue12345')
                rh.write_json(pathlib.Path(tmp) / 'state.json', {'detail': 'S3cretValue12345 abc /Users/x'})
                text = (pathlib.Path(tmp) / 'status.log').read_text() + (pathlib.Path(tmp) / 'state.json').read_text()
                self.assertNotIn('S3cretValue12345', text)
                self.assertEqual(text.count('[REDACTED]'), 2)
                self.assertIn('/Users/x', text)               # path-like values are not treated as secrets
            finally:
                rh.load_secrets({})

    def test_f2_unknown_or_failed_charges_keep_the_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            fl = faults(tmp, {'pulse.clean': {'credits': 0}, 'arm.clean.B.r1': {'errors': [1]},
                              'arm.clean.C.r1': {'jev_cost_missing': True}})
            p = orch(demo, '--stub', '--stop-after', 'arm.clean.C.r1', '--stub-faults', fl)
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            e = {(x['stage'], x['attempt']): x for x in ledger(run_root(demo)).d['entries']}
            self.assertEqual((e[('pulse.clean', 1)]['state'], e[('pulse.clean', 1)]['bound']), ('unknown', 400.0))
            self.assertEqual((e[('arm.clean.B.r1', 1)]['state'], e[('arm.clean.B.r1', 1)]['bound']), ('unknown', 0.045))
            self.assertEqual(e[('arm.clean.B.r1', 2)]['state'], 'settled')
            self.assertEqual((e[('arm.clean.C.r1', 1)]['state'], e[('arm.clean.C.r1', 1)]['bound']), ('unknown', 0.045))

    def test_f3_pulse_killed_when_observed_credits_pass_the_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stub-faults', faults(tmp, {'pulse.scan': {'credits': 900, 'progressive': 0.15}}))
            self.assertEqual(p.returncode, 1, p.stderr[-1500:])
            self.assertIn('CAP-KILLED pulse.scan', p.stderr)
            root = run_root(demo)
            e = [x for x in ledger(root).d['entries'] if x['stage'] == 'pulse.scan'][0]
            self.assertEqual(e['state'], 'unknown')
            self.assertGreater(e['bound'], 440.0)                       # the observed spend, above the 400 bound
            self.assertLess(len(list((demo / 'runs').glob('heldout2/*/work/runs/live-heldout2-scan-01/raw/*'))), 39)

    def test_f4_lock_and_malformed_files_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            bg = subprocess.Popen([sys.executable, str(SCRIPT), '--demo', str(demo), '--stub', '--stub-faults',
                                   faults(tmp, {'critic': {'sleep': {'1': 60}}})], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, env=test_env())
            try:
                t = time.monotonic() + 60
                while time.monotonic() < t:
                    roots = list((demo / 'runs' / 'heldout2').glob('*')) if (demo / 'runs' / 'heldout2').is_dir() else []
                    if roots and (roots[0] / 'logs' / 'sleeper-critic-a1.pid').exists():
                        break
                    time.sleep(0.2)
                root = run_root(demo)
                p = orch(demo, '--resume', root.name)
                self.assertEqual(p.returncode, 1)
                self.assertIn('holds', p.stderr)
            finally:
                bg.send_signal(signal.SIGTERM)
                bg.wait(timeout=60)
            (root / 'ledger.json').write_text('{"caps": ')
            p = orch(demo, '--resume', root.name)
            self.assertEqual(p.returncode, 1)
            self.assertIn('ledger.json is missing, unreadable, or malformed', p.stderr)
            (root / 'state.json').write_text('[]')
            p = orch(demo, '--resume', root.name)
            self.assertEqual(p.returncode, 1)
            self.assertIn('state.json is missing, unreadable, or malformed', p.stderr)

    def test_f5_term_ignoring_descendant_is_killed_after_a_clean_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stop-after', 'make_layerb.clean',
                     '--stub-faults', faults(tmp, {'make_layerb.clean': {'orphan': True}}))
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            pid = int((run_root(demo) / 'logs' / 'orphan-make_layerb.clean.pid').read_text())
            time.sleep(0.5)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
            self.assertRegex((run_root(demo) / 'status.log').read_text(), r'make_layerb\.clean\s+DONE')

    def test_f6_build_gates_fail_the_build_group_before_pulse(self):
        for fault, needle in (({'key_a': {'gate_fail': True}}, 'gates.json reports failed gate(s): sha256'),
                              ({'key_a': {'bad_sha': True}, 'generator_source': {'flag_flip': True}},
                               'sha256 differs from the manifest')):
            with tempfile.TemporaryDirectory() as tmp:
                demo = make_tree(tmp)
                p = orch(demo, '--stub', '--stub-faults', faults(tmp, fault))
                self.assertEqual(p.returncode, 1, p.stderr[-1500:])
                root = run_root(demo)
                st = state(root)
                self.assertIn(needle, st['stages']['key_a']['detail'])
                if 'generator_source' in fault:
                    self.assertIn('flag_would_be_false_alarm disagrees with layer A', st['stages']['key_a']['detail'])
                self.assertEqual(calls(root)['generator_source'], 3)             # R7 as amended: the group was rebuilt twice
                self.assertNotIn('pulse.clean', calls(root))
                self.assertEqual(ledger(root).d['entries'], [])

    def test_f7_arm_registry_change_stops_before_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stop-after', 'arm.scan.A-batched.r2')
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            root = run_root(demo)
            reg = json.loads((root / 'arms.json').read_text())
            c = reg['clean']['C']
            c[0]['repeat'], c[1]['repeat'] = c[1]['repeat'], c[0]['repeat']     # swap repeat numbers after the stop
            (root / 'arms.json').write_text(json.dumps(reg))
            p = orch(demo, '--resume', root.name)
            self.assertEqual(p.returncode, 1)
            self.assertIn('ARM-REGISTRY mismatch', p.stderr)
            self.assertNotIn('make_audit2.clean', calls(root))

    def test_f9_r6_on_union_of_layer_a_and_primary_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            fl = faults(tmp, {'rekey': {'disagree': 6}, 'adjudicate': {'undecidable': 6},
                              'audit.clean': {'audit_flip': 6}, 'adjudicate_audit.clean': {'undecidable': 6}})
            p = orch(demo, '--stub', '--stub-faults', fl)
            self.assertEqual(p.returncode, 3, p.stderr[-1500:])
            self.assertIn('R6: 12 unique excluded units on set clean (layer A 6 + primary audit 6', p.stderr)

    def test_f10_required_is_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stub-faults', faults(tmp, {'audit.scan': {'touch_code': 'reconcile.py'}}))
            self.assertEqual(p.returncode, 1)
            self.assertIn('FREEZE-MISMATCH: reconcile.py changed after the freeze', p.stderr)
            o = rh.Orchestrator(demo, run_root(demo), 'stub', run_root(demo) / 'work')
            rec = demo / 'reconcile.py'
            rec.write_text(rec.read_text().replace("'tax', 'total'", "'tax'"))
            with self.assertRaisesRegex(rh.Stop, r'reconcile.py:REQUIRED \(parsed value\)'):
                o.verify_code('test')


class TestScorerInventory(unittest.TestCase):
    """Finding 8: with --arms the exact inventory, clean reports, and identical unit sets are required."""

    def build(self, tmp, extra=True):
        sys.path.insert(0, str(DEMO / 'heldout2' / 'tests' / 'fixtures'))
        sys.path.insert(0, str(DEMO / 'heldout2'))
        import build_fixture as bf
        docs = bf.documents()
        base = bf.base_answers(docs)
        b, a1 = base['redo-jev-20261101T000000Z-r1'], base['redo-claude-20261101T000000Z-c8-per-document-r1']
        plan = [('redo-claude-20261101T000000Z-r1', 'A', 1), ('redo-claude-20261101T000000Z-r2', 'A', 2),
                ('redo-jev-20261101T000000Z-r1', 'B', 1), ('redo-cascade-20261101T000000Z-r1', 'C', 1),
                ('redo-cascade-20261101T000000Z-r2', 'C', 2), ('redo-cascade-20261101T000000Z-alias-afe_number-r1', 'C-alias', 1),
                ('redo-cascade-20261101T000000Z-alias-afe_number-r2', 'C-alias', 2),
                ('redo-claude-20261101T000000Z-c8-per-document-r1', 'A-batched', 1)]
        answers = dict(base)
        if extra:
            for name, arm, rep, ans in (('redo-jev-20261101T000001Z-r1', 'B', 2, b), ('redo-jev-20261101T000002Z-r1', 'B', 3, b),
                                        ('redo-jev-alias-afe_number-20261101T000003Z-r1', 'B-alias', 1, b),
                                        ('redo-claude-c8-per-document-20261101T000004Z-r1', 'A-batched', 2, a1)):
                answers[name] = ans
                plan.append((name, arm, rep))
        corpus, runs = bf.build(tmp, answers=answers)
        arms = {s: {} for s in runs}
        for s, rd in runs.items():
            for name, arm, rep in plan:
                arms[s].setdefault(arm, []).append({'repeat': rep, 'stage': f'arm.{s}.{arm}.r{rep}', 'out': str(rd / 'typed' / name)})
        import score_heldout2 as sc
        arms['_expected_units'] = {s: sorted(sc.kstr(k) for k in sc.load_units(rd / 'typed' / plan[0][0])) for s, rd in runs.items()}
        ap = pathlib.Path(tmp) / 'arms.json'
        ap.write_text(json.dumps(arms))
        return corpus, runs, ap

    def cli(self, corpus, runs, ap=None, rc=0):
        out = pathlib.Path(tempfile.mkdtemp(dir=corpus.parent)) / 'score.json'
        args = [sys.executable, str(DEMO / 'heldout2' / 'score_heldout2.py'), '--corpus', str(corpus), '--run-clean',
                str(runs['clean']), '--run-scan', str(runs['scan']), '--out', str(out)] + (['--arms', str(ap)] if ap else [])
        r = subprocess.run(args, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, rc, r.stderr[-1500:])
        return json.loads(out.read_text()), r.stdout, out.with_suffix('.md').read_text()

    def test_incomplete_inventory_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus, runs, ap = self.build(tmp, extra=False)
            res, _, md = self.cli(corpus, runs, ap, rc=3)        # INVALID exits 3 (review 3, item 1)
            self.assertEqual(res['verdict']['Overall'], 'INVALID')
            self.assertIn('clean: arm B has repeats [1], expected 1..3', res['verdict']['invalid_reasons'])
            self.assertIn('**VERDICT INVALID**', md)

    def test_full_inventory_scores_and_a_failed_report_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus, runs, ap = self.build(tmp)
            res, _, _ = self.cli(corpus, runs, ap)
            self.assertNotEqual(res['verdict']['Overall'], 'INVALID', res.get('inventory'))
            self.assertTrue(res['inventory']['ok'])
            rp = runs['scan'] / 'typed' / 'redo-cascade-20261101T000000Z-r2' / 'report.json'
            r = json.loads(rp.read_text()); r['errors'] = 3
            rp.write_text(json.dumps(r))
            res, _, _ = self.cli(corpus, runs, ap, rc=3)
            self.assertEqual(res['verdict']['Overall'], 'INVALID')
            self.assertTrue(any('errors=3' in x for x in res['verdict']['invalid_reasons']))

    def test_without_arms_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus, runs, _ = self.build(tmp)
            res, out, md = self.cli(corpus, runs)
            self.assertIn('WARNING: no --arms given', out)
            self.assertFalse(res['inventory']['checked'])
            self.assertIn('WARNING:', md)


# ------------------------------------------------------------------------------------------------ review 2 fixes
class TestReview2Fixes(unittest.TestCase):
    def test_a_cascade_with_jev_side_errors_keeps_the_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stop-after', 'arm.clean.C.r2', '--stub-faults', faults(tmp, {'arm.clean.C.r1': {'jev_errors': 2}}))
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            e = {(x['stage'], x['attempt']): x for x in ledger(run_root(demo)).d['entries']}
            self.assertEqual((e[('arm.clean.C.r1', 1)]['state'], e[('arm.clean.C.r1', 1)]['bound']), ('unknown', 0.045))
            self.assertEqual(e[('arm.clean.C.r2', 1)]['state'], 'settled')

    def test_b_missing_mandatory_gate_fails_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stub-faults', faults(tmp, {'key_a': {'gate_missing': 'unit_arithmetic'}}))
            self.assertEqual(p.returncode, 1)
            self.assertIn('gates.json lacks mandatory gate(s): unit_arithmetic', state(run_root(demo))['stages']['key_a']['detail'])
            self.assertTrue(all(g in (DEMO / 'heldout2/briefs/key_a.md').read_text() for g in rh.GATE_IDS))

    def test_c_expected_units_recorded_and_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stop-after', 'arm.clean.A.r1')
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            reg = json.loads((run_root(demo) / 'arms.json').read_text())
            self.assertEqual(len(reg['_expected_units']['clean']), 71 + 45 * 2 + 4 + 8 * 2 + 9 + 5)   # row 1 + row 8 = 195
        sys.path.insert(0, str(DEMO / 'heldout2'))
        import score_heldout2 as sc
        with tempfile.TemporaryDirectory() as tmp:
            corpus, runs, ap = TestScorerInventory().build(tmp)
            a = json.loads(ap.read_text())
            a['_expected_units']['scan'].append('row5:tk_1')              # a unit no run answered
            ap.write_text(json.dumps(a))
            res = sc.score(corpus, runs, sc.load_cases(corpus / 'cases.json'), None, {}, {}, sc.load_arms(ap))
            self.assertEqual(res['verdict']['Overall'], 'INVALID')
            self.assertTrue(any('not the expected' in x for x in res['verdict']['invalid_reasons']))

    @unittest.skipUnless((DEMO / 'runs/live-heldout-clean-01/typed').is_dir(), 'run 1 folders not present')
    def test_c_real_expected_units_equal_run1_arms(self):
        sys.path.insert(0, str(DEMO / 'heldout2'))
        import score_heldout2 as sc
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / 'exp.json'
            r = subprocess.run([sys.executable, '-c', rh.EXPECT_UNITS_PY, str(DEMO), 'runs/live-heldout-clean-01', 'synth-heldout',
                                'synth-heldout/layerB/clean/truth-b', str(out)], capture_output=True, text=True, timeout=120,
                               env=rh.strip_env())
            self.assertEqual(r.returncode, 0, r.stderr[-800:])
            exp = set(json.loads(out.read_text()))
            runs = sorted((DEMO / 'runs/live-heldout-clean-01/typed').glob('redo-*'))
            self.assertGreaterEqual(len(runs), 7)
            for d in runs:
                self.assertEqual({sc.kstr(k) for k in sc.load_units(d)}, exp, d.name)

    def test_d_validation_inside_the_stage_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            # key_a deadline 60 min x 0.00111 = 4.0 s; the session uses 3.8 s, so validation must stop on the deadline
            p = orch(demo, '--stub', '--deadline-scale', '0.00111', '--stop-after', 'key_a',
                     '--stub-faults', faults(tmp, {'key_a': {'sleep': {'1': 3.8, '2': 3.8, '3': 3.8}}}))   # R7: 2 rebuilds
            self.assertEqual(p.returncode, 1, p.stdout[-1500:] + p.stderr[-1500:])
            self.assertIn('DEADLINE', state(run_root(demo))['stages']['key_a']['detail'])
            self.assertLess(p.wall, 60)

    def test_e_finished_audit_is_skipped_on_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stop-after', 'audit.clean')
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            root = run_root(demo)
            p2 = orch(demo, '--resume', root.name, '--stop-after', 'audit.scan')
            self.assertEqual(p2.returncode, 0, p2.stderr[-1500:])
            self.assertEqual(calls(root)['audit.clean'], 1)
            self.assertEqual(state(root)['stages']['audit.scan']['status'], 'DONE')

    def test_g_adjudication_sees_one_rendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stop-after', 'adjudicate_audit.scan',
                     '--stub-faults', faults(tmp, {'rekey': {'disagree': 2}, 'audit.scan': {'audit_flip': 2}}))
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            sess = run_root(demo) / 'stub-sessions'
            self.assertEqual(sorted(x.name for x in (sess / 'adjudicate' / 'page-images').iterdir()), ['clean'])
            self.assertEqual(sorted(x.name for x in (sess / 'adjudicate_audit.scan' / 'page-images').iterdir()), ['scan'])
            self.assertEqual(sorted(x.name for x in (sess / 'adjudicate_audit.clean' / 'page-images').iterdir()), ['clean'])
            dis = json.loads((sess / 'adjudicate_audit.scan' / 'disagreements.json').read_text())
            self.assertTrue(dis and all(i.startswith('page-images/scan/') for x in dis for i in x['images']))
            for x in dis:
                self.assertTrue(all((sess / 'adjudicate_audit.scan' / i).is_file() for i in x['images']), x)
            dis = json.loads((sess / 'adjudicate' / 'disagreements.json').read_text())
            self.assertTrue(dis and all(i.startswith('page-images/clean/') for x in dis for i in x['images']))


# ------------------------------------------------------------------------------------------------ review 3 fixes
class TestReview3Fixes(unittest.TestCase):
    def test_1_invalid_verdict_stops_the_run(self):
        for fault in ({'invalid': True}, {'invalid': True, 'invalid_exit0': True}):
            with tempfile.TemporaryDirectory() as tmp:
                demo = make_tree(tmp)
                p = orch(demo, '--stub', '--stub-faults', faults(tmp, {'score': fault}))
                self.assertEqual(p.returncode, 3, p.stderr[-1500:])
                root = run_root(demo)
                self.assertEqual(state(root)['stages']['score']['status'], 'INVALID')
                self.assertNotIn('COMPLETE', (root / 'status.log').read_text())

    def test_1_legitimate_verdict_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub')
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            self.assertRegex((run_root(demo) / 'status.log').read_text(), r'COMPLETE .*verdict Overall INCONCLUSIVE')

    def launcher(self, tmp, claude_body, timeout_s='2'):
        b = pathlib.Path(tmp) / 'bin'
        b.mkdir()
        (b / 'claude').write_text('#!/bin/sh\n' + claude_body)
        (b / 'python3').write_text('#!/bin/sh\necho WOULD-EXEC-ORCHESTRATOR "$@"\n')   # never start a live run in a test
        for f in b.iterdir():
            f.chmod(0o755)
        env = test_env({'PATH': f"{b}:{os.environ['PATH']}", 'HELDOUT2_AUTH_TIMEOUT': timeout_s})
        t0 = time.monotonic()
        r = subprocess.run(['bash', str(DEMO / 'heldout2' / 'run-heldout2.sh')], capture_output=True, text=True, env=env, timeout=25)
        return r, time.monotonic() - t0

    def test_2_stalled_sign_in_check_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidf = pathlib.Path(tmp) / 'claude.pid'
            r, wall = self.launcher(tmp, f'echo $$ > {pidf}\nexec sleep 120\n')
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn('did not answer within 2s', r.stderr)
            self.assertNotIn('WOULD-EXEC', r.stdout)
            self.assertLess(wall, 15)
            time.sleep(0.5)
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pidf.read_text()), 0)
        with tempfile.TemporaryDirectory() as tmp:
            r, _ = self.launcher(tmp, 'echo \'{"loggedIn": true}\'\n')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('WOULD-EXEC-ORCHESTRATOR', r.stdout)

    def test_3_packet_images_in_packet_order(self):
        o = rh.Orchestrator(DEMO, pathlib.Path(tempfile.gettempdir()) / 'unused', 'stub', DEMO)
        man = {'documents': [{'doc_id': 'tb', 'packet': 'p1', 'pages': [3], 'page_count': 1},
                             {'doc_id': 'ta', 'packet': 'p1', 'pages': [1, 2], 'page_count': 2},
                             {'doc_id': 'x', 'packet': 'p2', 'pages': [1], 'page_count': 1}]}
        b = o.blind_item('row5', 'p1', {'question': 'q', 'options': [True, False]}, None, man)
        self.assertEqual(o.item_images(b, 'scan', man),
                         ['page-images/scan/ta-1.png', 'page-images/scan/ta-2.png', 'page-images/scan/tb-1.png'])
        self.assertEqual(o.images('ta', None, 'clean', man), ['page-images/clean/ta-1.png', 'page-images/clean/ta-2.png'])

    def test_3_missing_evidence_image_fails_the_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            p = orch(demo, '--stub', '--stub-faults', faults(tmp, {'rekey': {'disagree': 1}, 'render': {'drop_image': 'ticket_01'}}))
            self.assertEqual(p.returncode, 1, p.stderr[-1500:])
            st = state(run_root(demo))['stages']['adjudicate']
            self.assertIn('adjudication evidence: 1 image path(s) missing', st['detail'])
            self.assertNotIn('adjudicate', calls(run_root(demo)))            # Codex never launched without evidence

    def test_4_p3_restriction_follows_each_layer(self):
        sys.path.insert(0, str(DEMO / 'heldout2' / 'tests' / 'fixtures'))
        sys.path.insert(0, str(DEMO / 'heldout2'))
        import build_fixture as bf
        import score_heldout2 as sc
        with tempfile.TemporaryDirectory() as tmp:
            corpus, runs = bf.build(tmp)
            cases = sc.load_cases(corpus / 'cases.json')
            # the audit says t10's approval number is NOT printed; K2 flagged t10 in every base C repeat
            audit = {s: dict(path='x', corrections={('row8', 't10.afe_number'): False}, excluded={('row8', 'po_01.afe_number')})
                     for s in ('clean', 'scan')}
            res = sc.score(corpus, runs, cases, None, audit, {})
            pre, post = (res['layers'][k]['final']['P3_zero_flag'] for k in ('A_pre_audit', 'A_post_audit'))
            self.assertTrue(pre['holds'])
            self.assertFalse(post['holds'])
            self.assertEqual(post['failing'], ['t10'])
            self.assertIn('t10', post['label_vs_cases']['clean'])
            self.assertIn('po_01', post['unrestricted_excluded']['clean'])
            self.assertEqual(res['verdict']['Overall'], 'FAIL')

    def test_5_gates_checked_by_the_orchestrator(self):
        for fault, needle in (({'generator_source': {'leak_noun': True}}, 'earlier-corpus proper noun(s) in the new corpus'),
                              ({'render': {'blank_clean': 'ticket_06'}}, 'clean pages without extractable text: 1, first ticket_06 p1')):
            with tempfile.TemporaryDirectory() as tmp:
                demo = make_tree(tmp)
                p = orch(demo, '--stub', '--stop-after', 'key_a', '--stub-faults', faults(tmp, fault))
                self.assertEqual(p.returncode, 1, p.stderr[-1500:])
                self.assertIn(needle, state(run_root(demo))['stages']['key_a']['detail'])
        terms = rh.earlier_nouns(DEMO)
        for t in ('Lumereth County', 'Tressaline', 'Brelquor', 'Ultraven Fold Interests LLC', 'Sovarek', 'Darsenne'):
            self.assertIn(t, terms)
        self.assertNotIn('September', terms)


class TestRun2StartFixes(unittest.TestCase):
    def test_new_run_refused_when_earlier_outputs_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = make_tree(tmp)
            (demo / 'synth-heldout2' / 'design').mkdir(parents=True)
            p = orch(demo, '--stub', '--stub-in-place')
            self.assertEqual(p.returncode, 1)
            self.assertIn('new run refused, outputs of an earlier run exist', p.stderr)
            self.assertFalse((demo / 'runs' / 'heldout2').exists())   # nothing started, no retry burned

    def test_copy_in_skips_chrome_singleton_socket_and_dangling_links(self):
        import socket
        with tempfile.TemporaryDirectory() as tmp:
            src = pathlib.Path(tmp) / 'render'
            (src / 'tmp' / 'chrome-profile').mkdir(parents=True)
            (src / 'clean').mkdir()
            (src / 'clean' / 'a.pdf').write_bytes(b'%PDF')
            (src / 'tmp' / 'chrome-profile' / 'SingletonLock').symlink_to('host-99999')     # dangling
            s = socket.socket(socket.AF_UNIX); s.bind(str(src / 'tmp' / 'chrome-profile' / 'SingletonSocket'))
            try:
                o = rh.Orchestrator(DEMO, pathlib.Path(tmp) / 'run', 'stub', pathlib.Path(tmp) / 'work')
                folder = pathlib.Path(tmp) / 'session'
                folder.mkdir()
                o.copy_in(src, folder, None, 'key_a')
            finally:
                s.close()
            self.assertEqual((folder / 'clean' / 'a.pdf').read_bytes(), b'%PDF')
            self.assertFalse((folder / 'tmp' / 'chrome-profile' / 'SingletonLock').exists())
            self.assertFalse((folder / 'tmp' / 'chrome-profile' / 'SingletonSocket').exists())
        self.assertIn('treat any error from stopping Chrome', (DEMO / 'heldout2' / 'briefs' / 'generator.md').read_text())

    def test_briefs_put_plain_controls_outside_every_class(self):
        self.assertIn('do not define a class for them', (DEMO / 'heldout2' / 'briefs' / 'critic.md').read_text())
        self.assertIn('A plain control belongs to no class', (DEMO / 'heldout2' / 'briefs' / 'designer.md').read_text())


if __name__ == '__main__':
    unittest.main()
