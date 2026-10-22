"""Unit tests for heldout2/controls.py. No network, no model call. Run: python3 -m unittest discover heldout2/tests"""
import pathlib, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import controls as K  # noqa: E402

REQ = {'field_ticket': ['ticket_number', 'afe_number'], 'hauling_log': ['log_number'], 'afe': ['afe_number']}


def unit(subject, final, abstain=False, raw=True):
    s = dict(final=final, abstain=abstain)
    return dict(kind='unit', node='row8', subject=subject, score=s) if raw else dict(node='row8', subject=subject, **s)


def month(classes, values=None, documents_class=None):
    """classes = Pulse predicted class per doc; documents_class = the (manifest-derived) documents[].class."""
    values = values or {}
    return dict(classify=[dict(doc_id=d, predicted=c) for d, c in classes.items()],
                documents={d: {'class': (documents_class or classes)[d], 'values': values.get(d, {})} for d in classes})


class Norm(unittest.TestCase):
    def test_case_and_spacing_fold(self):
        self.assertEqual(K.norm('  DB-26-901 \n\t Ref  '), 'db-26-901 ref')
        self.assertEqual(K.norm('Straße'), 'strasse')        # casefold, not lower

    def test_nothing_else(self):
        self.assertEqual(K.norm('DB–26/901.'), 'db–26/901.')  # punctuation and dashes untouched


class Bounded(unittest.TestCase):
    def test_longer_number_is_not_a_match(self):
        self.assertFalse(K.bounded_in('DB-26-901', 'Ref: DB-26-9011'))
        self.assertFalse(K.bounded_in('DB-26-901', 'xDB-26-901'))
        self.assertFalse(K.bounded_in('DB-26-901', 'DB-26-901a'))

    def test_bounded_matches(self):
        self.assertTrue(K.bounded_in('DB-26-901', 'DB-26-901'))                 # text edges
        self.assertTrue(K.bounded_in('DB-26-901', 'Ref: **DB-26-901**'))
        self.assertTrue(K.bounded_in('DB-26-901', '(DB-26-901)'))
        self.assertTrue(K.bounded_in('DB-26-901', 'DB-26-9011 and DB-26-901'))  # a later occurrence counts

    def test_case_and_spacing_on_both_sides(self):
        self.assertTrue(K.bounded_in('db-26-901', 'AFE   DB-26-901\n'))
        self.assertTrue(K.bounded_in('DB 26  901', 'ref db 26\n901 end'))
        self.assertFalse(K.bounded_in('DB 26 901', 'DB-26-901'))               # no punctuation folding

    def test_empty_needle(self):
        self.assertFalse(K.bounded_in('   ', 'anything'))


class Required(unittest.TestCase):
    def test_parsed_not_imported(self):
        before = 'reconcile' in sys.modules
        req = K.required()
        self.assertEqual('reconcile' in sys.modules, before)
        self.assertIn('afe_number', req['field_ticket'])
        self.assertEqual(sorted(req), ['afe', 'afe_cover', 'field_ticket', 'hauling_log', 'invoice', 'jib_statement'])

    def test_source_has_no_manifest_or_truth_read(self):
        code = [l for l in (HERE.parent / 'controls.py').read_text().splitlines() if not l.lstrip().startswith('#')]
        body = '\n'.join(code).split('"""')[2:]          # skip the module docstring
        self.assertNotIn('manifest.json', '\n'.join(body))
        self.assertNotIn("'truth", '\n'.join(body))
        self.assertNotIn('import reconcile', '\n'.join(body))


class DocClass(unittest.TestCase):
    def test_uses_predicted_not_documents_class(self):
        m = month({'a': 'hauling_log'}, documents_class={'a': 'field_ticket'})
        self.assertEqual(K.doc_class(m), {'a': 'hauling_log'})

    def test_record_without_doc_id_skipped(self):
        m = dict(classify=[dict(file='x.pdf', predicted='afe')], documents={})
        self.assertEqual(K.doc_class(m), {})


class K1(unittest.TestCase):
    def test_pulse_class_decides(self):
        # documents[].class (manifest) says field_ticket; Pulse said hauling_log -> afe_number not required -> no flag
        m = month({'a': 'hauling_log', 'b': 'field_ticket'}, documents_class={'a': 'field_ticket', 'b': 'hauling_log'})
        us = [unit('a.afe_number', False), unit('b.afe_number', False)]
        self.assertEqual(K.k1_flags(us, m, REQ), ['b.afe_number'])

    def test_only_kept_not_printed(self):
        m = month({'a': 'field_ticket'})
        us = [unit('a.afe_number', False, abstain=True), unit('a.ticket_number', True), unit('a.afe_number', None)]
        self.assertEqual(K.k1_flags(us, m, REQ), [])
        self.assertEqual(K.k1_flags([unit('a.ticket_number', False, raw=False)], m, REQ), ['a.ticket_number'])

    def test_non_unit_and_other_rows_ignored(self):
        m = month({'a': 'field_ticket'})
        us = [dict(kind='jev_request', node='row8', subject='a.afe_number'),
              dict(kind='unit', node='row1', subject='a.afe_number', score=dict(final=False, abstain=False))]
        self.assertEqual(K.k1_flags(us, m, REQ), [])

    def test_unknown_class_no_flag(self):
        self.assertEqual(K.k1_flags([unit('z.afe_number', False)], month({'a': 'field_ticket'}), REQ), [])

    def test_default_reads_reconcile(self):
        self.assertEqual(K.k1_flags([unit('a.afe_number', False)], month({'a': 'field_ticket'})), ['a.afe_number'])


class K2(unittest.TestCase):
    def setUp(self):
        self.m = month({'cov': 'afe_cover', 'afe': 'afe', 't': 'field_ticket'},
                       {'cov': {'afe_number': 'DB-26-901'}, 'afe': {'afe_number': 'DB-26-901'}})
        self.texts = {'t': 'Docket\nRef: **DB-26-901**'}

    def test_fires(self):
        self.assertEqual(K.k2_flags([unit('t.afe_number', False)], self.m, self.texts), ['t.afe_number'])

    def test_only_afe_number_kept_false(self):
        us = [unit('t.ticket_number', False), unit('t.afe_number', True), unit('t.afe_number', False, abstain=True)]
        self.assertEqual(K.k2_flags(us, self.m, self.texts), [])

    def test_bounded_negative(self):
        self.assertEqual(K.k2_flags([unit('t.afe_number', False)], self.m, {'t': 'Ref DB-26-9011'}), [])

    def test_missing_or_short_source(self):
        for v in (None, '', '  ', 'DB', ' a1 ', 7):
            m = month({'afe': 'afe', 't': 'field_ticket'}, {'afe': {'afe_number': v}})
            self.assertEqual(K.k2_sources(m), {}, v)
            self.assertEqual(K.k2_flags([unit('t.afe_number', False)], m, {'t': f'Ref {v}'}), [], v)
        m = month({'afe': 'afe', 't': 'field_ticket'}, {'afe': {}})
        self.assertEqual(K.k2_sources(m), {})
        self.assertEqual(K.k2_sources(month({'afe': 'afe'}, {'afe': {'afe_number': 'A-1'}})), {'afe': 'A-1'})

    def test_source_from_pulse_class_only(self):
        # documents[].class says afe but Pulse said invoice -> no source; the reverse -> a source
        m = month({'x': 'invoice', 'y': 'afe', 't': 'field_ticket'},
                  {'x': {'afe_number': 'DB-26-901'}, 'y': {'afe_number': 'DB-26-777'}},
                  documents_class={'x': 'afe', 'y': 'field_ticket', 't': 'field_ticket'})
        self.assertEqual(K.k2_sources(m), {'y': 'DB-26-777'})
        self.assertEqual(K.k2_flags([unit('t.afe_number', False)], m, {'t': 'DB-26-901'}), [])
        self.assertEqual(K.k2_flags([unit('t.afe_number', False)], m, {'t': 'db-26-777'}), ['t.afe_number'])

    def test_drop_source(self):
        us = [unit('t.afe_number', False)]
        self.assertEqual(K.k2_flags(us, self.m, self.texts, drop_source='cov'), ['t.afe_number'])   # afe still holds it
        m = month({'afe': 'afe', 't': 'field_ticket'}, {'afe': {'afe_number': 'DB-26-901'}})
        self.assertEqual(K.k2_flags(us, m, self.texts, drop_source='afe'), [])

    def test_missing_text(self):
        self.assertEqual(K.k2_flags([unit('q.afe_number', False)], self.m, self.texts), [])


class K3(unittest.TestCase):
    DOI = dict(property_number='DS-8093', well_name='Tressaline 9-VH',
               owners=[dict(owner_name='Ultraven Fold Interests LLC', owner_number='UF-306'), dict(owner_number='QQ-1')])

    def test_mapping_and_owners_list(self):
        us = [unit('j.owner_number', False), unit('j.owner_name', False), unit('j.well_name', False),
              unit('j.property_number', False)]
        text = {'j': 'Owner ULTRAVEN  FOLD interests llc (UF-306)\nWell TRESSALINE 9-VH\nProperty DS-80931'}
        flags, skipped = K.k3_flags(us, self.DOI, text)
        self.assertEqual(flags, ['j.owner_name', 'j.owner_number', 'j.well_name'])
        self.assertEqual(skipped, [])

    def test_missing_key_skipped_and_reported(self):
        flags, skipped = K.k3_flags([unit('j.property_number', False)], dict(well_name='W-1 long', owners=[]),
                                    {'j': 'DS-8093'})
        self.assertEqual(flags, [])
        self.assertEqual(skipped, ['owner_name', 'owner_number', 'property_number'])

    def test_frozen_mapping(self):
        self.assertEqual(K.K3_KEYS, {'well_name': ('well_name',), 'owner_name': ('owners', '*', 'owner_name'),
                                     'owner_number': ('owners', '*', 'owner_number'),
                                     'property_number': ('property_number',)})


if __name__ == '__main__':
    unittest.main()
