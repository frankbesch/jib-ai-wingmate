"""Tests for heldout2/make_audit2.py on the synthetic fixture. Page rendering is replaced by a stub (no PDFs)."""
import json, pathlib, random, sys, tempfile, unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE / 'fixtures'))
import make_audit2 as ma  # noqa: E402
import score_heldout2 as sc  # noqa: E402
import build_fixture as bf  # noqa: E402


def fake_render(pdf, page, stem, variant):
    stem.with_suffix('.png').write_text(f'{pdf} p{page}')
    return stem.name + '.png'


class Audit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.corpus, self.runs = bf.build(self.root, sets=('clean',))

    def tearDown(self):
        self.tmp.cleanup()

    def main(self, tag='a'):
        out, out2, rec = self.root / f'{tag}-primary', self.root / f'{tag}-secondary', self.root / f'{tag}-record.json'
        argv = ['make_audit2.py', '--run', str(self.runs['clean']), '--corpus', str(self.corpus), '--out', str(out),
                '--out-secondary', str(out2), '--record', str(rec)]
        with mock.patch.object(ma, 'render', fake_render), mock.patch.object(sys, 'argv', argv), \
                mock.patch('builtins.print'):
            ma.main()
        return out, out2, json.loads(rec.read_text())

    def test_selection(self):
        arms, _ = sc.discover(self.runs['clean'])
        pm, right, sec, used = ma.select(arms)
        # A: 16 abstained ticket numbers + 1 wrong each (t50, t51); C: 20 afe_number targets; B: t30 abstain (in A's)
        self.assertEqual(len(pm), 38)
        self.assertIn(('row8', 't10.afe_number'), pm)
        self.assertIn(('row8', 't51.ticket_number'), pm)
        self.assertEqual(sec, {('row8', 'po_01.afe_number')})             # only the alias runs missed it
        self.assertNotIn(('row8', 't20.ticket_number'), sec)               # batched missed it, but so did A
        self.assertEqual(len(right), 75 - 38)
        self.assertFalse(pm & right)
        self.assertEqual(sorted(used), sorted(['redo-claude-20261101T000000Z-r1', 'redo-claude-20261101T000000Z-r2',
                                               'redo-jev-20261101T000000Z-r1', 'redo-cascade-20261101T000000Z-r1',
                                               'redo-cascade-20261101T000000Z-r2']))

    def test_sets_record_and_seed(self):
        out, out2, rec = self.main()
        self.assertEqual(rec['seed'], 20261002)
        self.assertEqual(len(rec['primary']['misses']), 38)
        self.assertEqual(len(rec['primary']['random_right']), 37)         # pool of 37 < 40: all of them
        self.assertEqual(rec['primary']['items'], 75)
        self.assertEqual(rec['secondary']['items'], 1)
        self.assertEqual(rec['secondary']['misses'], ['row8:po_01.afe_number'])
        items = json.loads((out / 'items.json').read_text())
        self.assertEqual(len(items), 75)
        _, _, rec2 = self.main('b')
        self.assertEqual(rec['primary']['id_to_unit'], rec2['primary']['id_to_unit'])   # deterministic

    def test_lucky_sample_is_seeded_40(self):
        pool = sorted(('row8', f'd{i}.f') for i in range(100))
        got = random.Random(ma.AUDIT_SEED).sample(pool, ma.AUDIT_LUCKY)
        self.assertEqual(len(got), 40)
        self.assertEqual(got, random.Random(20261002).sample(pool, 40))

    def test_blind_order_and_names(self):
        out, out2, rec = self.main()
        items = json.loads((out / 'items.json').read_text())
        units = [rec['primary']['id_to_unit'][it['id']] for it in items]
        self.assertNotEqual(units, sorted(units))                          # shuffled, not sorted
        misses = set(rec['primary']['misses'])
        flags = [u in misses for u in units]
        self.assertNotEqual(flags, sorted(flags, reverse=True))            # misses are not all first
        names = sorted(p.name for p in (out / 'pages').iterdir())
        self.assertTrue(all(n.startswith('page-') for n in names))
        self.assertEqual(len(names), rec['primary']['pages'])
        for it in items:
            self.assertTrue(all(p.startswith('pages/page-') for p in it['pages']))
            self.assertNotIn('label', it)
            self.assertNotIn('answer', it)
            self.assertNotIn('printed', it)
        for p in out.rglob('*'):                                            # nothing in the folder names the lists
            if p.is_file() and p.suffix in ('.json', '.md'):
                self.assertNotIn('misses', p.read_text())
                self.assertNotIn('random_right', p.read_text())

    def test_brief(self):
        out, out2, _ = self.main()
        b = (out / 'BRIEF.md').read_text()
        for line in ma.SEMANTICS.splitlines():
            self.assertIn(line, b)
        self.assertIn('`afe_number`: AFE number', b)                      # definitions the arms received (short)
        for bad in ('for example', 'e.g.', '"Ref"', 'Bill To'):
            self.assertNotIn(bad, b)
        self.assertIn('pick the one option', b)                           # row-1 items are present
        b2 = (out2 / 'BRIEF.md').read_text()
        self.assertIn('AFE number written on the ticket', b2)
        item = json.loads((out2 / 'items.json').read_text())[0]
        self.assertEqual((item['document'], item['field'], item['definition']),
                         ('po_01', 'afe_number', 'AFE number written on the ticket'))

    def test_refuses_record_inside_folder_and_overwrite(self):
        argv = ['x', '--run', str(self.runs['clean']), '--corpus', str(self.corpus), '--out', str(self.root / 'p'),
                '--out-secondary', str(self.root / 's'), '--record', str(self.root / 'p' / 'rec.json')]
        with mock.patch.object(sys, 'argv', argv), self.assertRaises(SystemExit):
            ma.main()
        self.main()
        with self.assertRaises(SystemExit):
            self.main()


if __name__ == '__main__':
    unittest.main()
