#!/usr/bin/env python3
"""Gate 2. Never substitutes source values for missing PDF-derived truth."""
from pathlib import Path
from collections import Counter
import json,hashlib,sys
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
C=json.loads((ROOT/'src/field_contract.json').read_text())
def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def resolve(p):
 q=(ROOT.parent/p).resolve();assert q.is_relative_to(ROOT),p
 return q

def main():
 if not (ROOT/'manifest.json').exists():raise SystemExit('BLOCKED: manifest.json is absent; Chrome has not produced the corpus.')
 m=load(ROOT/'manifest.json');docs=m['documents'];packets=m['packets']
 for kind in ('clean','scan'):
  assert len(list((ROOT/kind).glob('*.pdf')))==71
  assert len(list((ROOT/kind/'packets').glob('*.pdf')))==39
 assert len(list((ROOT/'truth').glob('*.json')))==71
 assert m['synthetic'] is True
 assert len(docs)==71 and len(packets)==39
 assert len({d['doc_id'] for d in docs})==71
 assert Counter(d['class'] for d in docs)=={'field_ticket':45,'hauling_log':9,'invoice':4,'afe_cover':4,'afe':4,'jib_statement':5}
 assert sum(d['page_count'] for d in docs)==80
 assert sum(p['pages'] for p in packets)==80
 printed=0;nulls=[];keys={};clean_pages=0
 for d in docs:
  for filekey,hashkey in [('file','sha256'),('scan_file','scan_sha256')]:
   p=resolve(d[filekey]);assert sha(p)==d[hashkey],p
   reader=PdfReader(p);assert len(reader.pages)==d['page_count'],p
   if filekey=='scan_file':
    assert all(not pg.extract_text().strip() for pg in reader.pages),p
   if filekey=='file':
    for pg in reader.pages:assert pg.extract_text().strip(),p;clean_pages+=1
  k=load(ROOT/'truth'/f'{d["doc_id"]}.json');keys[d['doc_id']]=k
  assert k['doc_id']==d['doc_id'] and k['source_file']==d['file']
  assert k['keyed_by']=='codex (author key, layer A)' and k['keyed_from']=='rendered PDF'
  assert isinstance(k['uncertain'],list)
  for f in C['REQUIRED'][d['class']]:
   assert f in k['values'] and f in k['page_of'],(d['doc_id'],f)
   if f!='customer_signature_present':
    if k['values'][f] is not None:printed+=1
    else:nulls.append(d['doc_id']+'.'+f)
  if d['class'] in C['LISTS']:
   name,fields,exact,minimum=C['LISTS'][d['class']]
   assert name in k['values'] and isinstance(k['values'][name],list)
   rows=k['values'][name];assert len(rows)>=minimum
   if exact is not None:assert len(rows)==exact
   for i,row in enumerate(rows):
    for f in fields:assert f in row and f'{name}[{i}].{f}' in k['page_of']
  for f,p in k['page_of'].items():assert p is None or 1<=p<=d['page_count'],(d['doc_id'],f,p)
 for p in packets:
  group=[d for d in docs if d['packet']==p['packet_id']]
  assigned=[n for d in group for n in d['pages']]
  assert sorted(assigned)==list(range(1,p['pages']+1))
  split=[n for ns in p['split_truth'].values() for n in ns]
  assert sorted(split)==list(range(1,p['pages']+1)),p['packet_id']
  for d in group:assert all(n in p['split_truth'][d['class']] for n in d['pages'])
  for filekey,hashkey in [('file','sha256'),('scan_file','scan_sha256')]:
   path=resolve(p[filekey]);assert sha(path)==p[hashkey]
   reader=PdfReader(path);assert len(reader.pages)==p['pages']
   # Compare content streams, including embedded scan JPEGs, in document order.
   for d in group:
    original=PdfReader(resolve(d[filekey]))
    for local,pkt_page in enumerate(d['pages']):
     a=original.pages[local];b=reader.pages[pkt_page-1]
     assert a.get_contents().get_data()==b.get_contents().get_data()
     if filekey=='scan_file':
      assert a['/Resources']['/XObject']['/Im0'].get_data()==b['/Resources']['/XObject']['/Im0'].get_data()
 ticket_counts=[sum(d['class']=='field_ticket' for d in docs if d['packet']==p['packet_id']) for p in packets]
 assert Counter(ticket_counts)=={2:15,1:15,0:9}
 assert sha(ROOT/'planted.json')==m['planted_sha256']
 plants=load(ROOT/'planted.json')['defects'];assert len(plants)==3
 assert keys['jib_01']['values']['lines'][1]['owner_decimal']==.24
 assert keys['ticket_03']['values']['line_items'][0]['rate']==205
 assert keys['jib_01']['values']['lines'][6]['afe_ref']=='DB-26-902'
 ts=load(ROOT/'traps.json')['traps'];assert {t['trap_id'] for t in ts}=={f'T{i}' for i in range(1,11)}
 t1={(t['doc_id'],p) for t in ts if t['trap_id']=='T1' for p in t['pages']};assert len(t1)==20
 assert sum(len([f for f in C['REQUIRED'][d['class']] if f!='customer_signature_present']) for d in docs)==465
 assert printed<=465 and 190+printed+142<=797
 print('PASS: 71 documents; 39 packets; 80 pages per set; 220 PDF hashes and page counts verified.')
 print('PASS: packet page coverage, packet content order, required fields, list row keys, 3 plants, T1-T10.')
 print(f'PASS: {clean_pages} clean document pages have non-empty extracted text.')
 for name in ['clean','scan']:
  print(f'{name}: row1=71; row4=80; row5=39; row8 printed={printed}; decoys=142; requested subtotal={190+printed+142}.')
  print(f'{name}: all presence questions include {len(nulls)} absent REQUIRED slots; row8=607; total=797.')
 print('Absent REQUIRED non-boolean fields: '+', '.join(nulls))
 print('Scan OCR and normal-zoom visual legibility require separate audit; this check does not certify either.')
if __name__=='__main__':main()
