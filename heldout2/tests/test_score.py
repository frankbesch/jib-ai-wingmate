"""Tests for heldout2/score_heldout2.py on the synthetic fixture (tests/fixtures/build_fixture.py). No network."""
import json, pathlib, subprocess, sys, tempfile, unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE / 'fixtures'))
import score_heldout2 as sc  # noqa: E402
import build_fixture as bf  # noqa: E402

R1, R2 = 'redo-cascade-20261101T000000Z-r1', 'redo-cascade-20261101T000000Z-r2'
ALIAS1 = 'redo-cascade-20261101T000000Z-alias-afe_number-r1'


def T(p, i):
    return ('row8', f't{p}{i}.afe_number')


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_score(self, audit=None, audit2=None, sets=('clean', 'scan'), **kw):
        corpus, runs = bf.build(self.root, sets=sets, **kw)
        cases = sc.load_cases(corpus / 'cases.json')
        doi = json.loads((corpus / 'reference' / 'doi.json').read_text())
        return sc.score(corpus, runs, cases, doi, audit or {}, audit2 or {})

    def answers(self, edit):
        docs = bf.documents()
        a = bf.base_answers(docs)
        edit(a)
        return a


class Discovery(Base):
    def test_arm_tags(self):
        self.assertEqual(sc.arm_of('redo-cascade-20261101T000000Z-r1'), 'C')
        self.assertEqual(sc.arm_of('redo-cascade-x-alias-afe_number-r2'), 'C-alias')
        self.assertEqual(sc.arm_of('redo-claude-x-r1'), 'A')
        self.assertEqual(sc.arm_of('redo-claude-x-c8-per-document-r1'), 'A-batched')
        self.assertEqual(sc.arm_of('redo-jev-x-r3'), 'B')
        self.assertEqual(sc.arm_of('redo-jev-x-alias-afe_number-r1'), 'B-alias')
        self.assertIsNone(sc.arm_of('quarantine-redo-claude-x-r1'))
        self.assertEqual(sc.repeat_of('redo-cascade-x-alias-afe_number-r2'), 2)

    def test_batch_records_expand_per_field(self):
        res = self.run_score()
        self.assertEqual(res['sets']['clean']['arms']['A-batched'], ['redo-claude-20261101T000000Z-c8-per-document-r1'])
        a = res['layers']['A_pre_audit']['per_set']['clean']['arms']['redo-jev-20261101T000000Z-r1']
        self.assertEqual((a['wrong'], a['abstain']), (20, 1))

    def test_incomplete_run_listed_not_scored(self):
        corpus, runs = bf.build(self.root)
        (runs['clean'] / 'typed' / 'redo-cascade-20261102T000000Z-r3').mkdir()
        arms, inc = sc.discover(runs['clean'])
        self.assertEqual(inc, ['redo-cascade-20261102T000000Z-r3'])
        self.assertEqual(len(arms['C']), 2)

    def test_cases_shape_checked(self):
        with self.assertRaises(SystemExit):
            self.run_score(cases_patch=lambda cs: [dict(c, flag_would_be_false_alarm='yes') for c in cs])


class P1(Base):
    def test_base_passes(self):
        res = self.run_score()
        self.assertEqual(res['verdict'], dict(P1='PASS', P2='PASS', P5='PASS', Overall='PASS', P3_zero_flag_holds=True))
        p1 = res['layers']['A_pre_audit']['per_set']['clean']['P1']
        self.assertEqual((p1['unique_targets'], len(p1['packets']), len(p1['label_variants'])), (20, 5, 4))
        self.assertEqual(p1['per_repeat'][R1]['recall'], 1.0)
        self.assertEqual(p1['unique']['t20.afe_number']['label_variant'], 'AFE No')
        self.assertEqual(p1['unique']['t20.afe_number']['target_in'], [R1, R2])

    def test_repeat_with_zero_targets_inconclusive(self):
        def edit(a):
            for p in range(1, 6):
                for i in range(4):
                    a[R2][T(p, i)] = (True, False)
        res = self.run_score(answers=self.answers(edit))
        p1 = res['layers']['A_pre_audit']['per_set']['clean']['P1']
        self.assertEqual(p1['per_repeat'][R1]['holds'], True)
        self.assertEqual(p1['verdict'], 'INCONCLUSIVE')
        self.assertIn(f'{R2}: zero target errors', p1['inconclusive_because'])
        self.assertEqual(res['verdict']['P1'], 'INCONCLUSIVE')
        self.assertEqual(res['verdict']['Overall'], 'INCONCLUSIVE')

    def test_flag_in_other_repeat_is_not_a_catch(self):
        corpus, runs = bf.build(self.root, answers=self.answers(lambda a: a[R1].__setitem__(T(1, 0), (True, False))))
        cases = sc.load_cases(corpus / 'cases.json')
        S = sc.prepare('clean', runs['clean'], corpus, cases, None)
        # t10 is a target only in r2; move its K2 flag to r1, where t10 was answered correctly
        S['flags'][R2]['K2'].discard('t10.afe_number')
        S['flags'][R1]['K2'].add('t10.afe_number')
        e = sc.evaluate_set(S, S['label_a'], set())['P1']
        self.assertEqual(e['per_repeat'][R2]['targets'], 20)
        self.assertEqual(e['per_repeat'][R2]['caught'], 19)
        self.assertIn('t10.afe_number', e['per_repeat'][R2]['missed'])
        self.assertEqual(e['per_repeat'][R1]['false_alarm_units'], ['t10.afe_number'])
        self.assertEqual(e['unique']['t10.afe_number']['caught_in'], [])
        self.assertEqual(e['unique_caught'], 19)

    def test_fewer_than_15_unique_targets(self):
        def edit(a):
            for r in (R1, R2):
                for p, i in ((1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (5, 1)):
                    a[r][T(p, i)] = (True, False)
        res = self.run_score(answers=self.answers(edit))
        p1 = res['layers']['A_pre_audit']['per_set']['clean']['P1']
        self.assertEqual(p1['unique_targets'], 14)
        self.assertEqual(p1['verdict'], 'INCONCLUSIVE')
        self.assertIn('14 unique targets < 15', p1['inconclusive_because'])

    def test_fewer_than_5_packets(self):
        docs = bf.documents()
        docs += [dict(d, doc_id=d['doc_id'] + 'x') for d in docs if d['packet'] == 'tk_1']   # 8 tickets in tk_1
        a = bf.base_answers(docs)
        for r in (R1, R2):
            for i in range(4):
                a[r][T(5, i)] = (True, False)
                a[r][('row8', f't1{i}x.afe_number')] = (False, False)
        res = self.run_score(docs=docs, answers=a)
        p1 = res['layers']['A_pre_audit']['per_set']['clean']['P1']
        self.assertEqual((p1['unique_targets'], len(p1['packets'])), (20, 4))
        self.assertEqual(p1['verdict'], 'INCONCLUSIVE')
        self.assertIn('targets from 4 packets < 5', p1['inconclusive_because'])

    def test_fewer_than_3_label_variants(self):
        res = self.run_score(cases_patch=lambda cs: [dict(c, label_variant=c['label_variant'] and
                                                         ('Ref' if c['label_variant'] in ('Ref', 'Auth') else 'AFE No')) for c in cs])
        p1 = res['layers']['A_pre_audit']['per_set']['clean']['P1']
        self.assertEqual(p1['label_variants'], ['AFE No', 'Ref'])
        self.assertEqual(p1['verdict'], 'INCONCLUSIVE')

    def test_missing_source_is_a_miss_and_reported(self):
        docs = bf.documents()
        for d in docs:
            if d['doc_id'] == 'afe_02':
                d['pulse_cls'] = 'invoice'
        res = self.run_score(docs=docs)
        s = res['sets']['clean']
        self.assertEqual([m['doc_id'] for m in s['missing_sources']], ['afe_02'])
        self.assertIn("Pulse classified it as 'invoice'", s['missing_sources'][0]['reason'])
        p1 = res['layers']['A_pre_audit']['per_set']['clean']['P1']['per_repeat'][R1]
        self.assertEqual((p1['targets'], p1['caught'], p1['recall']), (20, 16, 0.8))   # tk_5 prints DB-26-902

    def test_too_many_false_alarms_fail(self):
        docs = bf.documents()
        for d in docs:
            if d['packet'] == 'tk_6':
                d['text'] = d['text'] + '\nPO DB-26-901'
        docs.append(dict(docs[-1], doc_id='near_02'))
        res = self.run_score(docs=docs, cases_patch=lambda cs: [dict(c, flag_would_be_false_alarm=False) for c in cs])
        p1 = res['layers']['A_pre_audit']['per_set']['clean']['P1']['per_repeat'][R1]
        self.assertEqual(p1['false_alarms'], 3)
        self.assertFalse(p1['holds'])
        self.assertEqual(res['verdict']['P1'], 'FAIL')


class P2P3(Base):
    def test_to_person_counts_each_unit_once(self):
        res = self.run_score()
        p2 = res['layers']['A_pre_audit']['per_set']['clean']['P2']
        # K1 flags 22 (20 targets + po_01 + near_01), K2 flags 20, all inside K1: union 22, not 42
        self.assertEqual(p2['K1+K2']['per_repeat'][R1]['to_person'], 22)
        self.assertEqual(p2['K1+K2']['per_repeat'][R1]['flags'], 22)
        self.assertEqual(p2['K2']['per_repeat'][R1]['to_person'], 20)
        self.assertEqual(p2['none']['per_repeat'][R1]['wrong_unflagged'], 20)
        self.assertEqual(p2['limits'], dict(wrong_unflagged=6, to_person=26, claude_calls=37.5))

    def test_abstained_unit_and_flag_counted_once(self):
        corpus, runs = bf.build(self.root, answers=self.answers(lambda a: a[R1].__setitem__(('row8', 't10.ticket_number'), (None, True))))
        S = sc.prepare('clean', runs['clean'], corpus, sc.load_cases(corpus / 'cases.json'), None)
        S['flags'][R1]['K1'].add('t10.ticket_number')        # a flag on an abstained unit must not count twice
        c = sc.counts(S['arms']['C'][0], S['label_a'], set(), S['flags'][R1]['K1'] | S['flags'][R1]['K2'])
        self.assertEqual(c['to_person'], 23)

    def test_p2_decided_on_k1_plus_k2(self):
        res = self.run_score(claude_calls={R1: 40, R2: 20})
        p2 = res['layers']['A_pre_audit']['per_set']['clean']['P2']
        self.assertFalse(p2['K1+K2']['per_repeat'][R1]['checks']['claude_calls'])
        self.assertEqual(res['verdict']['P2'], 'FAIL')
        self.assertEqual(res['verdict']['Overall'], 'FAIL')

    def test_p3_zero_flag_blocks_overall(self):
        docs = bf.documents()
        for d in docs:
            if d['doc_id'] == 'po_01':
                d['text'] = 'Dispatch docket: **TK-61**\nPO DB-26-901'
        res = self.run_score(docs=docs)
        z = res['layers']['A_pre_audit']['final']['P3_zero_flag']
        self.assertEqual(z['failing'], ['po_01'])                  # decided per document (review 2, finding F)
        self.assertEqual(z['k2_flags']['po_01'], dict(clean=2, scan=2))
        self.assertEqual(z['by_class']['unrelated-ref'], dict(clean=2, scan=2))
        self.assertEqual(res['verdict']['P1'], 'PASS')            # 1 false alarm per repeat is within P1
        self.assertEqual(res['verdict']['P2'], 'PASS')
        self.assertFalse(res['verdict']['P3_zero_flag_holds'])
        self.assertEqual(res['verdict']['Overall'], 'FAIL')
        p3 = res['layers']['A_pre_audit']['per_set']['clean']['P3']['unrelated-ref']
        self.assertEqual((p3['k2_flags'], p3['false_alarms']), (2, 2))

    def test_p3_mixed_class_catch_is_not_a_false_alarm(self):
        # one class holds a plain printed ticket (a K2 catch there is legitimate) and a not-printed ticket (flag true)
        res = self.run_score(cases_patch=lambda cs: [dict(c, class_id='baseline') if c['doc_id'] in ('t10', 'po_01') else c
                                                     for c in cs])
        z = res['layers']['A_pre_audit']['final']['P3_zero_flag']
        self.assertTrue(z['holds'])
        self.assertGreater(z['by_class']['baseline']['clean'], 0)  # a per-class rule would have failed here
        self.assertEqual(res['verdict']['Overall'], 'PASS')

    def test_contradictory_flags_for_one_document_are_invalid(self):
        def patch(cs):
            extra = [dict(c, class_id='second', flag_would_be_false_alarm=not c['flag_would_be_false_alarm'])
                     for c in cs if c['doc_id'] == 'po_01']
            return cs + extra
        res = self.run_score(cases_patch=patch)
        self.assertEqual(res['verdict']['Overall'], 'INVALID')
        self.assertIn('cases.json: entries for po_01 disagree on flag_would_be_false_alarm', res['verdict']['invalid_reasons'])

    def test_near_miss_class_raises_no_flag(self):
        res = self.run_score()
        self.assertEqual(res['layers']['A_pre_audit']['per_set']['clean']['P3']['near-miss']['k2_flags'], 0)


class SourceLossLayersAudit(Base):
    def test_source_loss_table(self):
        res = self.run_score()
        rows = {(r['source_doc'], r['repeat']): r for r in res['sets']['clean']['source_loss']}
        self.assertEqual(sorted({d for d, _ in rows}), ['afe_01', 'afe_02', 'cover_01'])
        self.assertEqual(rows[('afe_02', R1)]['catches_lost'], 4)
        self.assertEqual(rows[('afe_02', R1)]['lost_units'], [f't5{i}.afe_number' for i in range(4)])
        self.assertEqual(rows[('afe_01', R1)]['catches_lost'], 0)       # cover_01 still carries DB-26-901
        self.assertEqual(rows[('cover_01', R2)]['catches_lost'], 0)

    def test_layer_b_side_by_side(self):
        res = self.run_score(labels_b={T(1, 0): False})
        a = res['layers']['A_pre_audit']['per_set']['clean']['P1']['per_repeat'][R1]
        b = res['layers']['B']['per_set']['clean']['P1']['per_repeat'][R1]
        self.assertEqual((a['targets'], a['false_alarms']), (20, 0))
        self.assertEqual((b['targets'], b['false_alarms']), (19, 1))
        self.assertEqual(res['sets']['clean']['pulse_dropped'], ['row8:t10.afe_number'])

    def test_audit_recomputes_and_prints_both(self):
        p = self.root / 'audit-clean.json'
        p.write_text(json.dumps(dict(corrections={'row8:t10.afe_number': False, 'row8:t11.afe_number': False,
                                                  'row8:t12.afe_number': False}, excluded=[])))
        res = self.run_score(audit=sc.load_audit([f'clean={p}']))
        self.assertEqual(res['meta']['primary_layer'], 'A_post_audit')
        pre = res['layers']['A_pre_audit']['per_set']['clean']['P1']['per_repeat'][R1]
        post = res['layers']['A_post_audit']['per_set']['clean']['P1']['per_repeat'][R1]
        self.assertEqual((pre['false_alarms'], post['false_alarms']), (0, 3))
        self.assertEqual(res['layers']['A_pre_audit']['final']['P1'], 'PASS')
        self.assertEqual(res['verdict']['P1'], 'FAIL')

    def test_exclusion_that_could_reverse_p1_reads_inconclusive(self):
        docs = bf.documents()
        for n in ('po_02', 'po_03'):
            docs.append(dict(doc_id=n, packet='tk_6', cls='field_ticket', text='Docket\nPO DB-26-901', values={},
                             truth=dict(ticket_number=True, afe_number=False), case='po-ref', fa=False))
        next(d for d in docs if d['doc_id'] == 'po_01')['text'] = 'Docket\nPO DB-26-901'   # 2 false alarms
        p = self.root / 'audit.json'
        p.write_text(json.dumps(dict(corrections={}, excluded=['row8:po_03.afe_number'])))
        res = self.run_score(docs=docs, audit=sc.load_audit([f'clean={p}', f'scan={p}']))
        lay = res['layers']['A_post_audit']
        self.assertEqual(lay['marks']['P1'], 'PASS')                 # excluded unit left out: 2 false alarms
        self.assertEqual(lay['exclusion_bounds']['reachable']['P1'], ['FAIL', 'PASS'])
        self.assertEqual(lay['exclusion_bounds']['scored_for']['P1'], 'PASS')
        self.assertEqual(lay['exclusion_bounds']['scored_against']['P1'], 'FAIL')
        self.assertEqual(res['verdict']['P1'], 'INCONCLUSIVE')
        self.assertEqual(res['layers']['A_pre_audit']['final']['P1'], 'FAIL')   # pre-audit: po_03 is a false alarm

    def test_exclusion_that_cannot_reverse_keeps_verdict(self):
        p = self.root / 'audit-clean.json'
        p.write_text(json.dumps(dict(corrections={}, excluded=['row8:t10.afe_number'])))
        res = self.run_score(audit=sc.load_audit([f'clean={p}']))
        self.assertEqual(res['layers']['A_post_audit']['exclusion_bounds']['reachable']['P1'], ['PASS'])
        self.assertEqual(res['verdict']['P1'], 'PASS')

    def test_alias_audit_is_a_sensitivity_line(self):
        p = self.root / 'audit2-clean.json'
        p.write_text(json.dumps(dict(corrections={'row8:po_01.afe_number': True}, excluded=[])))
        res = self.run_score(audit2=sc.load_audit([f'clean={p}']))
        self.assertIn('A_sensitivity_alias_audit', res['layers'])
        self.assertEqual(res['meta']['primary_layer'], 'A_pre_audit')


class P4P5P6(Base):
    def test_p5_pairs_by_repeat(self):
        res = self.run_score()
        p5 = res['layers']['A_pre_audit']['per_set']['clean']['P5']['per_pair'][ALIAS1]
        self.assertEqual(p5['paired_with'], R1)
        self.assertEqual((p5['right_to_wrong_or_abstain'], p5['wrong_or_abstain_to_right']), (1, 20))
        self.assertTrue(p5['holds'])

    def test_p5_fails_on_six_regressions(self):
        def edit(a):
            for d in ('t10', 't11', 't12', 't13', 't20'):
                a[ALIAS1][('row8', f'{d}.ticket_number')] = (None, True)
        res = self.run_score(answers=self.answers(edit))
        p5 = res['layers']['A_pre_audit']['per_set']['clean']['P5']['per_pair'][ALIAS1]
        self.assertEqual(p5['right_to_wrong_or_abstain'], 6)
        self.assertEqual(res['verdict']['P5'], 'FAIL')
        self.assertEqual(res['verdict']['Overall'], 'PASS')          # P5 is Q2; it does not enter Overall

    def test_p4_and_p6_reported(self):
        res = self.run_score()
        e = res['layers']['A_pre_audit']['per_set']['clean']
        self.assertEqual(set(e['P4']), {'well_name', 'owner_name', 'owner_number', 'property_number'})
        self.assertEqual(e['P4']['well_name'][R1], dict(flags=0, catches=0, false_alarms=0, not_printed_errors=0))
        self.assertEqual(e['P6']['batched']['mean_abstain'], 1)
        self.assertEqual(e['P6']['per_field']['mean_wrong'], 1)


class CLI(Base):
    def test_end_to_end(self):
        corpus, runs = bf.build(self.root)
        out = self.root / 'score.json'
        r = subprocess.run([sys.executable, str(HERE.parent / 'score_heldout2.py'), '--corpus', str(corpus),
                            '--run-clean', str(runs['clean']), '--run-scan', str(runs['scan']), '--out', str(out)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(out.read_text())['verdict']['Overall'], 'PASS')
        self.assertIn('| P1 | PASS |', out.with_suffix('.md').read_text())

    def test_one_set_missing_is_inconclusive(self):
        res = self.run_score(sets=('clean',))
        self.assertEqual(res['verdict']['P1'], 'INCONCLUSIVE')
        self.assertEqual(res['verdict']['Overall'], 'INCONCLUSIVE')

    def test_static_fixture_matches_builder(self):
        corpus, runs = bf.build(self.root)
        base = HERE / 'fixtures' / 'base'
        for p in sorted(self.root.rglob('*')):
            if p.is_file():
                self.assertEqual(p.read_bytes(), (base / p.relative_to(self.root)).read_bytes(), str(p))


if __name__ == '__main__':
    unittest.main()
