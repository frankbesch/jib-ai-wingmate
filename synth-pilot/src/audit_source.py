#!/usr/bin/env python3
"""Source-only checks. These cannot establish rendered-PDF truth or pass corpus gates."""
from pathlib import Path
import json,hashlib,collections,ast
ROOT=Path(__file__).resolve().parents[1]
load=lambda p:json.loads((ROOT/p).read_text())
b=load('src/book.json');c=load('src/field_contract.json');ts=load('traps.json')['traps'];ds=b['documents']
assert len(ds)==22
counts=collections.Counter(d['class'] for d in ds)
assert counts=={'field_ticket':12,'hauling_log':3,'invoice':2,'afe_cover':2,'afe':2,'jib_statement':1}
packets=collections.defaultdict(list)
for d in ds:
 packets[d['packet']].append(d)
 assert set(c['REQUIRED'][d['class']])<=set(d['values'])
 if d['class'] in c['LISTS']:
  name,keys,exact,minimum=c['LISTS'][d['class']]
  rows=d['values'][name]
  assert len(rows)>=minimum and (exact is None or len(rows)==exact)
  for row in rows:assert set(keys)<=set(row)
 assert (ROOT/'src'/f'{d["doc_id"]}.html').exists()
assert len(packets)==11
assert sum((ROOT/'src'/f'{d["doc_id"]}.html').read_text().count('<section class="page">') for d in ds)==25
assert collections.Counter(sum(d['class']=='field_ticket' for d in group) for group in packets.values())=={2:4,1:4,0:3}
assert {t['trap_id'] for t in ts}=={f'T{i}' for i in range(1,11)}
assert len(load('planted.json')['defects'])==3
for p in (ROOT/'src').glob('*.py'):ast.parse(p.read_text())
lookup={d['doc_id']:d for d in ds};density={}
# Required-field mapping is exact. Decoy mapping cannot be certified without runner integration.
for variant in ['clean','scan']:
 units={1:set(),4:set(),5:set(),8:set()}
 for t in ts:
  if variant not in t['sets']:continue
  d=lookup[t['doc_id']]
  for r in t['rows']:
   if r==1:units[r].add(d['doc_id'])
   if r==4:units[r].update(f'{d["doc_id"]}:p{p}' for p in t['pages'])
   if r==5:units[r].add(t['packet'] or d['packet'])
   if r==8:units[r].update(f'{d["doc_id"]}.{f}' for f in t['fields'] if f in c['REQUIRED'][d['class']] and f!='customer_signature_present')
 density[variant]={str(r):len(u) for r,u in units.items()}
 density[variant]['total_excluding_unmapped_decoy_traps']=sum(map(len,units.values()))
printed=sum(d['values'].get(f) is not None for d in ds for f in c['REQUIRED'][d['class']] if f!='customer_signature_present')
result={'status':'SOURCE ONLY; not PDF gates','documents':len(ds),'packets':len(packets),'planned_pages':25,'classes':dict(counts),'source_nonnull_required_nonboolean':printed,'source_null_required_nonboolean':147-printed,'planned_units_all_required':249,'requested_printed_subtotal':58+printed+44,'mapped_trap_units':density,'planted_sha256':hashlib.sha256((ROOT/'planted.json').read_bytes()).hexdigest()}
(ROOT/'audit/source-check.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
