#!/usr/bin/env python3
"""Synthetic fixture for the heldout2 tests: a fake corpus (manifest, cases.json, reference/doi.json) and one fake
Pulse run folder per set (month.json, run.json, raw/<packet>__extract.json, typed/redo-*/ arm runs).
Nothing here is real data. `python3 build_fixture.py` rewrites ./base; tests call build(<dir>, **changes).

Base scenario (every mark holds; A abstains on 16 ticket numbers, so its mean to-a-person is 16):
  afe_01: cover_01 (afe_cover) and afe_01 (afe), both extract DB-26-901. afe_02: afe_02 (afe), DB-26-902.
  tk_1..tk_5: four field tickets each, t<p><i>; the approval number printed under label variant VARIANTS[i]
    (tk_5 prints DB-26-902, the others DB-26-901). Truth afe_number True. Base C answers False: 20 targets per repeat.
  tk_6: po_01 (text 'PO 4471', afe_number absent; class unrelated-ref, a flag would be a false alarm) and near_01
    (text 'Ref DB-26-9011', absent; class near-miss, a flag would be a false alarm). Base C answers False, correctly.
Each document has row-8 units ticket_number/afe_number (tickets) or afe_number/well_name (AFE documents) and a
row-1 unit. Arms: A x2 (per field), B x1 (per-document batch records), base C x2, C-alias x2, A-batched x1.
"""
import copy, json, pathlib

VARIANTS = ['AFE No', 'Ref', 'Approval', 'Auth']


def documents():
    docs = [dict(doc_id='cover_01', packet='afe_01', cls='afe_cover', text='Election letter\nAFE: **DB-26-901**\nWell: Tressaline 9-VH',
                 values=dict(afe_number='DB-26-901', well_name='Tressaline 9-VH'), truth=dict(afe_number=True, well_name=True)),
            dict(doc_id='afe_01', packet='afe_01', cls='afe', text='AUTHORITY FOR EXPENDITURE\nAFE Number: **DB-26-901**\nWell: Tressaline 9-VH',
                 values=dict(afe_number='DB-26-901', well_name='Tressaline 9-VH'), truth=dict(afe_number=True, well_name=True)),
            dict(doc_id='afe_02', packet='afe_02', cls='afe', text='AUTHORITY FOR EXPENDITURE\nAFE Number: **DB-26-902**\nWell: Orlin 2-H',
                 values=dict(afe_number='DB-26-902', well_name='Orlin 2-H'), truth=dict(afe_number=True, well_name=True))]
    for p in range(1, 6):
        for i in range(4):
            num = 'DB-26-902' if p == 5 else 'DB-26-901'
            docs.append(dict(doc_id=f't{p}{i}', packet=f'tk_{p}', cls='field_ticket', variant=VARIANTS[i],
                             text=f'Dispatch docket: **TK-{p}{i}**\n{VARIANTS[i]}: **{num}**\nAsset: Tressaline 9-VH',
                             values=dict(ticket_number=f'TK-{p}{i}'), truth=dict(ticket_number=True, afe_number=True),
                             case='label-trap', fa=False))
    docs.append(dict(doc_id='po_01', packet='tk_6', cls='field_ticket', text='Dispatch docket: **TK-61**\nPO 4471',
                     values=dict(ticket_number='TK-61'), truth=dict(ticket_number=True, afe_number=False), case='unrelated-ref', fa=True))
    docs.append(dict(doc_id='near_01', packet='tk_6', cls='field_ticket', text='Dispatch docket: **TK-62**\nRef DB-26-9011',
                     values=dict(ticket_number='TK-62'), truth=dict(ticket_number=True, afe_number=False), case='near-miss', fa=True))
    return docs


def base_answers(docs):
    """{arm dir: {(node, subject): (final, abstain)}} for the base scenario."""
    right = {}
    for d in docs:
        right[('row1', d['doc_id'])] = (d['cls'], False)
        for f, v in d['truth'].items():
            right[('row8', f"{d['doc_id']}.{f}")] = (v, False)
    targets = {('row8', f"t{p}{i}.afe_number") for p in range(1, 6) for i in range(4)}
    a1 = dict(right); a1.update({('row8', f't{p}{i}.ticket_number'): (None, True) for p in range(1, 5) for i in range(4)})
    a2 = dict(a1)
    a1[('row8', 't50.ticket_number')] = (False, False); a2[('row8', 't51.ticket_number')] = (False, False)
    c = dict(right); c.update({k: (False, False) for k in targets})
    alias = dict(right); alias[('row8', 'po_01.afe_number')] = (True, False)
    batched = dict(right); batched[('row8', 't20.ticket_number')] = (None, True)
    b = dict(c); b[('row8', 't30.ticket_number')] = (None, True)
    return {'redo-claude-20261101T000000Z-r1': a1, 'redo-claude-20261101T000000Z-r2': a2,
            'redo-jev-20261101T000000Z-r1': b,
            'redo-cascade-20261101T000000Z-r1': dict(c), 'redo-cascade-20261101T000000Z-r2': dict(c),
            'redo-cascade-20261101T000000Z-alias-afe_number-r1': alias,
            'redo-cascade-20261101T000000Z-alias-afe_number-r2': dict(alias),
            'redo-claude-20261101T000000Z-c8-per-document-r1': batched}


def _score(final, abstain, label):
    return dict(final=final, abstain=abstain, error=False, correct=(not abstain and final == label),
                wrong_not_abstained=(not abstain and final != label))


def write_run(rd, docs, answers, variant, labels_b=None, claude_calls=None):
    rd.mkdir(parents=True)
    (rd / 'raw').mkdir()
    (rd / 'run.json').write_text(json.dumps(dict(run_id=rd.name, variant=variant)))
    packets = {}
    for d in docs:
        packets.setdefault(d['packet'], []).append(d)
    for pid, ds in packets.items():
        md = ''.join(d['text'] + (f'\n<!-- PageBreak [{n}] -->\n' if n < len(ds) else '') for n, d in enumerate(ds, 1))
        (rd / 'raw' / f'{pid}__extract.json').write_text(json.dumps(dict(markdown=md)))
    month = dict(classify=[dict(doc_id=d['doc_id'], predicted=d.get('pulse_cls', d['cls'])) for d in docs],
                 documents={d['doc_id']: dict(**{'class': d['cls']}, packet=d['packet'], values=d['values']) for d in docs})
    (rd / 'month.json').write_text(json.dumps(month, indent=1))
    truth_a = {('row1', d['doc_id']): d['cls'] for d in docs}
    truth_a.update({('row8', f"{d['doc_id']}.{f}"): v for d in docs for f, v in d['truth'].items()})
    truth_b = dict(truth_a); truth_b.update(labels_b or {})
    for name, ans in answers.items():
        td = rd / 'typed' / name
        td.mkdir(parents=True)
        recs = []
        if name.startswith('redo-jev-') or '-c8-per-document' in name:
            for k in sorted(k for k in ans if k[0] == 'row1'):
                recs.append(dict(node='row1', shape='choice', subject=k[1], label=truth_b[k], label_a=truth_a[k],
                                 score=_score(*ans[k], truth_b[k])))
            for d in docs:
                fs = list(d['truth'])
                recs.append(dict(node='row8', shape='noul-batch', subject=d['doc_id'],
                                 label={f: truth_b[('row8', f"{d['doc_id']}.{f}")] for f in fs},
                                 label_a={f: truth_a[('row8', f"{d['doc_id']}.{f}")] for f in fs},
                                 score=dict(fields={f: _score(*ans[('row8', f"{d['doc_id']}.{f}")], truth_b[('row8', f"{d['doc_id']}.{f}")])
                                                    for f in fs})))
        else:
            for k in sorted(ans):
                rec = dict(node=k[0], subject=k[1], label=truth_b[k], label_a=truth_a[k], score=_score(*ans[k], truth_b[k]))
                if name.startswith('redo-cascade-'):
                    recs.append(dict(kind='jev_request', node=k[0], subject=k[1]))
                    rec = dict(kind='unit', answered_by='jev', **rec)
                recs.append(rec)
        (td / 'calls.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in recs))
        rep = dict(calls=len(recs), errors=0, field_desc='short')
        if name.startswith('redo-cascade-'):
            rep['cascade'] = dict(claude_calls=(claude_calls or {}).get(name, 20))
        (td / 'report.json').write_text(json.dumps(rep))


def build(root, docs=None, answers=None, cases_patch=None, labels_b=None, claude_calls=None, doi=None, sets=('clean', 'scan')):
    """Write corpus/ and run-<set>/ under root. Returns (corpus dir, {set: run dir})."""
    root = pathlib.Path(root)
    docs = docs or documents()
    answers = answers or base_answers(docs)
    corpus = root / 'corpus'
    (corpus / 'reference').mkdir(parents=True)
    packets, mdocs = {}, []
    for d in docs:
        packets.setdefault(d['packet'], []).append(d)
        mdocs.append(dict(doc_id=d['doc_id'], packet=d['packet'], **{'class': d['cls']}, pages=[len(packets[d['packet']])],
                          page_count=1, file=f"corpus/clean/{d['doc_id']}.pdf", scan_file=f"corpus/scan/{d['doc_id']}.pdf"))
    man = dict(packets=[dict(packet_id=p, pages=len(ds), file=f'corpus/clean/packet_{p}.pdf', scan_file=f'corpus/scan/packet_{p}.pdf')
                        for p, ds in packets.items()], documents=mdocs)
    (corpus / 'manifest.json').write_text(json.dumps(man, indent=1))
    cases = [dict(doc_id=d['doc_id'], packet=d['packet'], class_id=d.get('case', 'baseline'),
                  label_variant=d.get('variant'), flag_would_be_false_alarm=d.get('fa', False), overlaps=[]) for d in docs]
    if cases_patch:
        cases = cases_patch(copy.deepcopy(cases))
    (corpus / 'cases.json').write_text(json.dumps(cases, indent=1))
    doi = doi if doi is not None else dict(property_number='DS-8093', well_name='Tressaline 9-VH',
                                           owners=[dict(owner_name='Ultraven Fold Interests LLC', owner_number='UF-306')])
    (corpus / 'reference' / 'doi.json').write_text(json.dumps(doi, indent=1))
    runs = {}
    for s in sets:
        runs[s] = root / f'run-{s}'
        write_run(runs[s], docs, answers, s, labels_b, claude_calls)
    return corpus, runs


if __name__ == '__main__':
    here = pathlib.Path(__file__).resolve().parent / 'base'
    if here.exists():
        raise SystemExit(f'{here} exists; move it aside first (this script never deletes)')
    build(here)
    print(f'wrote {here}')
