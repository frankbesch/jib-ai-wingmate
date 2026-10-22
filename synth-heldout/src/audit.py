#!/usr/bin/env python3
"""Read-only corpus checks beyond the four requested gates."""
from pathlib import Path
import json,collections,hashlib
ROOT=Path(__file__).resolve().parents[1]
def load(p):return json.loads((ROOT/p).read_text())
b=load('src/book.json');c=load('src/field_contract.json');ts=load('traps.json')['traps'];ds=b['documents']
lookup={d['doc_id']:d for d in ds}
assert len(ds)==71
assert collections.Counter(d['class'] for d in ds)=={'field_ticket':45,'hauling_log':9,'invoice':4,'afe_cover':4,'afe':4,'jib_statement':5}
packets=collections.defaultdict(list)
for d in ds:
 packets[d['packet']].append(d)
 assert set(c['REQUIRED'][d['class']])<=set(d['values'])
assert len(packets)==39
assert sum((ROOT/'src'/f'{d["doc_id"]}.html').read_text().count('<section class="page">') for d in ds)==80
counts=collections.Counter(t['trap_id'] for t in ts)
assert all(counts[f'T{i}']>=3 for i in range(1,11))
trapped={t['packet'] for t in ts if t['trap_id'] in ('T4','T5') and t['packet']}
assert len(trapped)==12
assert collections.Counter(sum(d['class']=='field_ticket' for d in packets[p]) for p in trapped)=={2:6,1:6}
for p,group in packets.items():
 tickets=[d for d in group if d['class']=='field_ticket']
 if len(tickets)==2 and p in trapped:
  a,z=[dict(d['values']) for d in tickets]
  a.pop('ticket_number');z.pop('ticket_number')
  a['line_items']=[dict(r) for r in a['line_items']];z['line_items']=[dict(r) for r in z['line_items']]
  a['line_items'][1].pop('description');z['line_items'][1].pop('description')
  assert a==z,p
for t in ts:
 assert t['doc_id'] in lookup
 for p in t['pages']:assert p<= (2 if lookup[t['doc_id']]['class'] in ('afe','jib_statement') else 1)
 if 'distinct_tickets_in_packet' in t['correct']:
  packet=t['packet'] or lookup[t['doc_id']]['packet']
  count=len({d['values']['ticket_number'] for d in packets[packet] if d['class']=='field_ticket'})
  assert count==t['correct']['distinct_tickets_in_packet'],(t,count)
density={}
for variant in ['clean','scan']:
 units={1:set(),4:set(),5:set(),8:set()}
 for t in ts:
  if variant not in t['sets']:continue
  d=lookup[t['doc_id']]
  for r in t['rows']:
   if r==1:units[r].add(d['doc_id'])
   if r==4:units[r].update((d['doc_id'],p) for p in t['pages'])
   if r==5:units[r].add(t['packet'] or d['packet'])
   if r==8:units[r].update((d['doc_id'],f) for f in t['fields'] if f in c['REQUIRED'][d['class']] and f!='customer_signature_present')
 density[variant]={str(r):len(u) for r,u in units.items()}
 density[variant]['total']=sum(map(len,units.values()))
printed=sum(d['values'][f] is not None for d in ds for f in c['REQUIRED'][d['class']] if f!='customer_signature_present')
result={'documents':71,'packets':39,'pages_per_set':80,'source_printed':printed,'trap_instances':dict(counts),'mapped_trap_units':density,'denominators':{'1':71,'4':80,'5':39,'8':607,'total':797},'unmapped_cover_decoys':8,'ticket_packet_traps':12,'plain_ticket_packets':18}
(ROOT/'audit/design.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
