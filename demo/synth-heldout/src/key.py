#!/usr/bin/env python3
"""Key only rendered PDF text; load source values only AFTER candidate keys are written.
Reject missing PDFs. Visual audit remains separate from text extraction.
"""
from pathlib import Path
import json,re,hashlib,sys
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
C=json.loads((ROOT/'src/field_contract.json').read_text())
LABELS={
'letter_date':['Letter date'],'operator_name':['Operator','From','Bill To'],'addressee':['To'],'afe_number':['AFE number','Ref'],
'well_name':['Well','Subject well','Origin','Service location'],'response_due_date':['Response due'],
'wi_decimal_stated':['WI decimal stated'],'net_share_stated':['Net share stated'],
'api_number':['API number'],'county':['County'],'state':['State'],'afe_date':['AFE date','Prepared'],'afe_type':['Operation','Scope'],
 'total_estimate':['Total estimate'],'ticket_number':['Ticket number'],'vendor_name':['Vendor','Remit to'],
'service_date':['Service date','Serviced'],'total':['Total'],'log_number':['Log number'],
'hauler_name':['Hauler','Transport by'],'log_date':['Log date','Moved on'],'total_barrels':['Total barrels'],
'invoice_number':['Invoice number'],'invoice_date':['Invoice date','Issued'],'subtotal':['Subtotal'],'tax':['Tax'],
'statement_period':['Statement period'],'property_number':['Property number'],'owner_name':['Owner'],'owner_number':['Owner number'],
'wi_decimal':['WI decimal'],'gross_total':['Gross total'],'net_total':['Net total'],'due_date':['Due date']}
for key,aliases in {
 'ticket_number':['Dispatch docket'],'vendor_name':['Service firm'],'well_name':['Asset'],
 'total':['Amount due','Remittance due'],'log_number':['Movement sheet'],'total_barrels':['Volume moved (barrels)'],
 'invoice_number':['Account request'],'subtotal':['Pre-tax amount'],'tax':['Sales levy'],
 'letter_date':['Sent'],'addressee':['Interest owner'],'response_due_date':['Reply by'],
 'wi_decimal_stated':['Stated participation decimal'],'net_share_stated':['Stated owner share'],
 'api_number':['API reference'],'county':['Parish / county'],'state':['Jurisdiction'],'total_estimate':['Authorized estimate'],
 'statement_period':['Accounting month'],'operator_name':['Operating company'],'owner_name':['Interest holder']
}.items():LABELS[key].extend(aliases)

HEADS={'line_no':'Line','account_code':'Account','description':'Description','category':'Category','amount':'Amount',
'quantity':'Qty','unit':'Unit','rate':'Rate','load_no':'Load','time':'Time','fluid_type':'Fluid','barrels':'Barrels',
'destination':'Destination','ticket_ref':'Ticket ref','afe_ref':'AFE ref','gross_amount':'Gross','owner_decimal':'Decimal','net_amount':'Net'}
def dump(path,x):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(x,indent=2)+'\n')
def convert(s,schema):
 s=s.strip()
 if not s:return None
 typ=schema.get('type')
 if typ in ('number','integer'):
  s=s.replace(',','').removeprefix('$')
  if not re.fullmatch(r'-?\d+(?:\.\d+)?',s):raise ValueError(f'Unresolved numeric extraction: {s!r}')
  return int(float(s)) if typ=='integer' or float(s).is_integer() else float(s)
 return s

def read_table(text,keys,schema):
 lines=text.splitlines();rows=[]
 for i,line in enumerate(lines):
  starts=[];cursor=0
  for k in keys:
   at=line.find(HEADS[k],cursor)
   if at<0:break
   starts.append(at);cursor=at+len(HEADS[k])
  if len(starts)!=len(keys):continue
  for line in lines[i+1:]:
   if not line.strip():continue
   if ':' in line and keys[0]!='load_no':break
   if any(x in line for x in ['SYNTHETIC STUDY','Estimate continues','Election applies','Owner election','Remit using']):break
   parts=[line[max(0,s-1):max(0,starts[j+1]-1) if j+1<len(starts) else None].strip() for j,s in enumerate(starts)]
   try:
    row={k:convert(v,schema[k]) for k,v in zip(keys,parts)}
   except ValueError:
    if rows:break
    raise
   if row[keys[0]] is None:break
   # A printed charge row must contain at least one numeric cell.
   if not any(isinstance(v,(int,float)) for v in row.values()):break
   rows.append(row)
 return rows

def main():
 mp=ROOT/'manifest.json'
 if not mp.exists():raise SystemExit('BLOCKED: manifest.json is absent; build rendered PDFs before keying layer A.')
 manifest=json.loads(mp.read_text());candidates=[];page_presence={}
 for d in manifest['documents']:
  path=ROOT.parent/d['file']
  if not path.exists():raise SystemExit(f'BLOCKED: rendered PDF absent: {path}')
  pages=[p.extract_text(extraction_mode='layout') for p in PdfReader(path).pages]
  if not all(t.strip() for t in pages):raise SystemExit(f'Empty rendered page: {d["doc_id"]}')
  cls=d['class'];schema=C['SCHEMAS'][cls]['properties'];values={};page_of={};uncertain=[];present=[]
  for pi,text in enumerate(pages,1):
   (ROOT/'audit/text').mkdir(parents=True,exist_ok=True)
   (ROOT/'audit/text'/f'{d["doc_id"]}-p{pi}.txt').write_text(text)
   pm={}
   for k in C['REQUIRED'][cls]:
    if k=='customer_signature_present':continue
    matches=[]
    for line in text.splitlines():
     for label in LABELS.get(k,[]):
      m=re.match(r'^\s*'+re.escape(label)+r':\s*(.*?)\s*$',line)
      if m:matches.append(m.group(1))
    nonblank=[x for x in matches if x]
    pm[k]=bool(nonblank)
    if matches:
     value=convert(nonblank[0] if nonblank else '',schema[k])
     if k not in values or values[k] is None:values[k]=value;page_of[k]=pi
     if len(set(nonblank))>1:uncertain.append({'field':k,'page':pi,'reason':'Multiple labelled values require author review.','occurrences':nonblank})
   # R3: the declined-election note repeats the AFE number on its continuation.
   if cls=='afe' and values.get('afe_number'):
    if 'No participation in '+values['afe_number'] in text:
     pm['afe_number']=True
   present.append(pm)
  for k in C['REQUIRED'][cls]:values.setdefault(k,None);page_of.setdefault(k,None)
  if cls=='field_ticket':
   signature=[(pi,line) for pi,t in enumerate(pages,1) for line in t.splitlines() if 'Customer signature:' in line]
   if len(signature)!=1:raise ValueError(f'Signature block requires visual adjudication: {d["doc_id"]}')
   # All authored signature blocks are empty. Reject extracted non-placeholder text.
   tail=signature[0][1].split('Customer signature:',1)[1].strip()
   if tail.strip('_ '):raise ValueError('Signature text requires visual review, not automatic inference.')
   values['customer_signature_present']=False;page_of['customer_signature_present']=signature[0][0]
  if cls in C['LISTS']:
   name,keys,_,minimum=C['LISTS'][cls];rows=[]
   for pi,text in enumerate(pages,1):
    for row in read_table(text,keys,schema[name]['items']['properties']):
     idx=len(rows);rows.append(row)
     for k in keys:page_of[f'{name}[{idx}].{k}']=pi
   if len(rows)<minimum:raise ValueError(f'Incomplete table extraction {d["doc_id"]}: {len(rows)} < {minimum}')
   values[name]=rows
  key=dict(doc_id=d['doc_id'],source_file=d['file'],keyed_by='codex (author key, layer A)',keyed_from='rendered PDF',values=values,page_of=page_of,uncertain=uncertain)
  candidates.append(key);page_presence[d['doc_id']]=present
  dump(ROOT/'audit/candidate-keys'/f'{d["doc_id"]}.json',key)
 # Candidate keys now exist. Only now open source values for discrepancy reporting.
 source=json.loads((ROOT/'src/book.json').read_text())
 expected={d['doc_id']:d['values'] for d in source['documents']}
 differences=[]
 def compare(a,b,path=''):
  if isinstance(a,dict) and isinstance(b,dict):
   for k in sorted(set(a)|set(b)):yield from compare(a.get(k),b.get(k),path+'.'+k if path else k)
  elif isinstance(a,list) and isinstance(b,list):
   for i in range(max(len(a),len(b))):yield from compare(a[i] if i<len(a) else None,b[i] if i<len(b) else None,f'{path}[{i}]')
  elif a!=b:yield {'field':path,'rendered_key':a,'source_value':b,'reason':'Rendered-PDF candidate differs from author source; retain candidate pending visual adjudication.'}
 for key in candidates:
  diffs=list(compare(key['values'],expected[key['doc_id']]))
  key['uncertain'].extend(diffs);differences.extend(dict(doc_id=key['doc_id'],**d) for d in diffs)
  dump(ROOT/'truth'/f'{key["doc_id"]}.json',key)
 dump(ROOT/'audit/page_presence.json',page_presence)
 dump(ROOT/'audit/source_comparison.json',{'method':'All candidates written from rendered PDF text before source values were opened.','differences':differences})
 print(f'LAYER A: {len(candidates)} PDF-derived keys; {len(differences)} source differences retained in uncertain.')
if __name__=='__main__':main()
