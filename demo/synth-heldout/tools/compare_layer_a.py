#!/usr/bin/env python3
"""Compare the author layer-A key with the blind re-key. Flattens nested values (lists by index).
Writes disagreements.json in the pilot's shape: [{doc, field, author, blind, ruling: null}].
Separates value disagreements (both sides present, values differ) from key-name aliases (one side only)."""
import json, glob, os, sys, re
a_dir, b_dir, out = sys.argv[1], sys.argv[2], sys.argv[3]
def flat(v, p=''):
    if isinstance(v, dict):
        for k, x in v.items(): yield from flat(x, f'{p}.{k}' if p else k)
    elif isinstance(v, list):
        for i, x in enumerate(v): yield from flat(x, f'{p}[{i}]')
    else: yield p, v
def norm(x):
    if isinstance(x, str):
        s = x.strip()
        try: return float(s.replace(',', '').replace('$', ''))
        except ValueError: return s.lower()
    if isinstance(x, bool): return x
    if isinstance(x, (int, float)): return float(x)
    return x
rows, vals, alias, exact, docs, classes = [], 0, 0, 0, 0, 0
for fa in sorted(glob.glob(a_dir + '/*.json')):
    d = os.path.basename(fa)[:-5]; fb = f'{b_dir}/{d}.json'
    if not os.path.exists(fb): rows.append(dict(doc=d, field='<file>', author='present', blind='missing', ruling=None)); continue
    A, B = json.load(open(fa)), json.load(open(fb)); docs += 1
    fa_, fb_ = dict(flat(A['values'])), dict(flat(B['values']))
    for k in sorted(set(fa_) | set(fb_)):
        if k in fa_ and k in fb_:
            if norm(fa_[k]) == norm(fb_[k]): exact += 1
            else: vals += 1; rows.append(dict(doc=d, field=k, author=fa_[k], blind=fb_[k], ruling=None))
        else:
            alias += 1; rows.append(dict(doc=d, field=k, author=fa_.get(k), blind=fb_.get(k), ruling=None))
pages = json.load(open(b_dir + '/pages.json')) if os.path.exists(b_dir + '/pages.json') else {}
cls_mismatch = []
man = json.load(open(os.path.dirname(a_dir.rstrip('/')) + '/manifest.json'))
for doc in man['documents']:
    pj = pages.get(doc['doc_id'], {})
    if pj: classes += 1
    if pj and pj.get('class_by_eye') != doc['class']: cls_mismatch.append((doc['doc_id'], doc['class'], pj.get('class_by_eye')))
    if pj and pj.get('page_count') != doc['page_count']: cls_mismatch.append((doc['doc_id'], 'pages', doc['page_count'], pj.get('page_count')))
json.dump(rows, open(out, 'w'), indent=1)
print(f'documents compared {docs}; fields agreeing {exact}; VALUE DISAGREEMENTS {vals}; key-name aliases (one side only) {alias}')
print(f'classes by eye: {classes - len([c for c in cls_mismatch if c[1] != "pages"])} of {classes} match; mismatches: {cls_mismatch}')
for r in rows:
    if r['field'] != '<file>' and r['author'] is not None and r['blind'] is not None: print('  VALUE', r['doc'], r['field'], 'author=', r['author'], 'blind=', r['blind'])
