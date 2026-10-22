#!/usr/bin/env python3
"""Offline deterministic authoring. All writes stay below synth-pilot."""
from pathlib import Path
import json, hashlib, subprocess, html, random, io, sys, os
from string import Template
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, DictionaryObject, NumberObject, DecodedStreamObject
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
SEED=239021
R=random.Random(SEED)
CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
OP='Zelvori Basin Operations LLC'; OWNER='Mavren Fold Interests LLC'
VENDOR='Orvessa Field Services LLC'; HAULER='Telnori Fluid Transit LLC'
WELL='Nacrevale 7-QH'; WELL2='Fennovar 2-RH'; COUNTY='Velquorin'
CONTRACT=json.loads((ROOT/'src/field_contract.json').read_text())
BOOK=[]; TRAPS=[]
def dump(p,x):
 p=ROOT/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(args):
 cp=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=120)
 if cp.returncode:raise RuntimeError(f'{args[0]} failed ({cp.returncode}): {cp.stderr[-3000:]}')
 return cp.stdout
LABELS={
'letter_date':'Letter date','operator_name':'Operator','addressee':'To','afe_number':'AFE number','well_name':'Well',
'response_due_date':'Response due','wi_decimal_stated':'WI decimal stated','net_share_stated':'Net share stated',
'api_number':'API number','county':'County','state':'State','afe_date':'AFE date','afe_type':'Operation','total_estimate':'Total estimate',
'ticket_number':'Ticket number','vendor_name':'Vendor','service_date':'Service date','total':'Total',
'log_number':'Log number','hauler_name':'Hauler','log_date':'Log date','total_barrels':'Total barrels',
'invoice_number':'Invoice number','invoice_date':'Invoice date','subtotal':'Subtotal','tax':'Tax',
'statement_period':'Statement period','property_number':'Property number','owner_name':'Owner','owner_number':'Owner number',
'wi_decimal':'WI decimal','gross_total':'Gross total','net_total':'Net total','due_date':'Due date'}
HEADS={'line_no':'Line','account_code':'Account','description':'Description','category':'Category','amount':'Amount',
'quantity':'Qty','unit':'Unit','rate':'Rate','load_no':'Load','time':'Time','fluid_type':'Fluid','barrels':'Barrels',
'destination':'Destination','ticket_ref':'Ticket ref','afe_ref':'AFE ref','gross_amount':'Gross','owner_decimal':'Decimal','net_amount':'Net'}
def fmt(k,v):
 if v is None:return ''
 if isinstance(v,(int,float)):
  if 'decimal' in k:return f'{v:.6f}'
  if k in ['line_no','load_no','quantity']:return str(v)
  return f'{v:,.2f}'
 return str(v)
def fields(v,keys=None,aliases=None,struck=()):
 aliases=aliases or {};out='<div class="fields">'
 for k in keys or v:
  if k not in LABELS:continue
  val=html.escape(fmt(k,v.get(k)))
  if k in struck:val='<s>'+val+'</s>'
  out+=f'<div class="field"><span class="label">{html.escape(aliases.get(k,LABELS[k]))}:</span><span class="value">{val}</span></div>'
 return out+'</div>'
def table(rows,keys,compact=False):
 return '<table class="'+('compact' if compact else '')+'"><thead><tr>'+''.join('<th>'+HEADS[k]+'</th>' for k in keys)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(fmt(k,row.get(k)))+'</td>' for k in keys)+'</tr>' for row in rows)+'</tbody></table>'
def page(title,content,banner='OPERATIONS / OWNER RECORD',foot='SYNTHETIC STUDY DOCUMENT - NOT VALID FOR PAYMENT'):
 return f'<section class="page"><div class="eyebrow">{banner}</div><h1>{title}</h1>{content}<footer>{foot}</footer></section>'
def add(doc_id,cls,packet,values,pages,notes=None):
 BOOK.append(dict(doc_id=doc_id,**{'class':cls},packet=packet,values=values,html_pages=pages,notes=notes or []))
def trap(doc,tid,pages,fields_,reason,correct,rows=(8,),sets=('clean','scan'),packet=None):
 TRAPS.append(dict(doc_id=doc,trap_id=tid,pages=pages,fields=fields_,rows=list(rows),sets=list(sets),reason=reason,correct=correct,packet=packet))
# Four two-ticket packets followed by four one-ticket packets. First three are controls.
for n in range(1,13):
 pkt= f'ticket_{(n+1)//2:02d}' if n<=8 else f'ticket_{n-4:02d}'
 day=3+(n+1)//2 if n<=8 else n-1
 qty=6 if n in (7,8) else R.choice([4,5,6,7])
 rate=205 if n==3 else 175
 lines=[dict(description='Pressure unit service',quantity=qty,unit='hour',rate=rate,amount=qty*rate),
        dict(description='Hose kit rental',quantity=1,unit='day',rate=90,amount=90)]
 v=dict(ticket_number=f'OV-{8300+n}',vendor_name=VENDOR,service_date=f'2026-08-{day:02d}',well_name=WELL,afe_number='ZB-26-701',line_items=lines,total=qty*rate+90,customer_signature_present=False)
 aliases={};extra='';struck=[]
 if n==8:
  lines[1]['description']='Gauge kit rental'
 if n in (9,10,11,12):
  aliases={'service_date':'Serviced','afe_number':'Ref'}
  extra+='<div class="stamp">REPRINT</div><p>Replacement office copy. No additional service authorized.</p>'
  trap(f'ticket_{n:02d}','T4',[1],[], 'Replacement copy retains its ticket number.', {'distinct_tickets_in_packet':1},rows=(5,),packet=pkt)
  trap(f'ticket_{n:02d}','T10',[1],['service_date'] if n in (9,11) else ['service_date','afe_number'],'Serviced and Ref denote the frozen fields.',{'printed':True,'rules':['R3']})
 if n in (9,11):
  v['afe_number']=None
  trap(f'ticket_{n:02d}','T6',[1],['afe_number'],'Ref is labelled but blank.',{'afe_number':None,'printed':False,'rules':['R2']})
 if n==10:
  lines[0]['unit']=None
  trap('ticket_10','T4',[1],['line_items[0].unit'],'Bare quantity has an empty unit cell.',{'value':None,'printed':False,'rules':['R2']},rows=())
 if n==11:
  v['well_name']='N/A';struck=['service_date']
  trap('ticket_11','T6',[1],['well_name'],'N/A is literal printed content.',{'value':'N/A','printed':True,'rules':['R4']})
  trap('ticket_11','T3',[1],['service_date'],'Struck service date remains visible; dispatch date differs.',{'value':v['service_date'],'printed':True,'rules':['R5']})
  extra+='<p>Dispatch date: 2026-08-04. The struck service date remains on this retained copy.</p>'
 if n==12:
  v['total']=None
  extra+=fields({'subtotal':qty*rate+90})
  trap('ticket_12','T8',[1],['total'],'Only Subtotal is printed; the Total field is blank.',{'value':None,'printed':False,'rules':['R2']})
 if n in (7,8):
  extra+='<p>Worksite note: Nacrevale 7Q-H. Use the well identification in the header for this ticket.</p>'
  trap(f'ticket_{n:02d}','T3',[1],['well_name'],'Body spelling conflicts with the well header.',{'value':WELL,'printed':True,'rules':['R3']})
 if n>=7:
  aliases={'ticket_number':'Dispatch docket','vendor_name':'Service firm','service_date':'Serviced','well_name':'Asset','afe_number':'Ref','total':'Amount due'}
  trap(f'ticket_{n:02d}','T10',[1],[k for k in aliases if v[k] is not None],'Alternate service and accounting labels carry the frozen fields.',{'printed':True})
 title='Field service ticket'
 body=extra+fields(v,['ticket_number','vendor_name','service_date','well_name','afe_number'],aliases,struck)+table(lines,CONTRACT['LISTS']['field_ticket'][1])+fields(v,['total'],aliases)+'<div class="signature">Customer signature: __________________________</div>'
 add(f'ticket_{n:02d}','field_ticket',pkt,v,[page(title,body)])
for n in (7,8):trap(f'ticket_{n:02d}','T5',[1],['ticket_number'],'Paired tickets differ in ticket number and one charge description.',{'distinct_tickets_in_packet':2},rows=(5,),packet='ticket_04')
# Three logs ride with ticket packets. A reference is not another field ticket.
for i,pkt in enumerate(['ticket_01','ticket_05','ticket_07'],1):
 loads=[dict(load_no=j,time=f'{7+j:02d}:15',fluid_type='Produced water',barrels=60,destination='Quenvori recovery bay') for j in range(1,5)]
 v=dict(log_number=f'TF-{910+i}',hauler_name=HAULER,log_date=f'2026-08-{[4,8,10][i-1]:02d}',well_name=WELL,loads=loads,total_barrels=240)
 aliases={};extra=''
 if i==2:
  v['well_name']=None
  extra='<p>See ticket OV-9987 in the prior dispatch batch. No ticket is enclosed for that reference.</p>'
  trap('haul_02','T7',[1],[], 'A reference to a missing ticket is not a field ticket.',{'class':'hauling_log','distinct_tickets_in_packet':1},rows=(1,4,5),packet=pkt)
  trap('haul_02','T6',[1],['well_name'],'Well is labelled but blank.',{'value':None,'printed':False,'rules':['R2']})
 if i==3:
  aliases={'hauler_name':'Transport by','log_date':'Moved on','well_name':'Origin'}
  trap('haul_03','T10',[1],list(aliases),'Alternate dispatch labels retain field meaning.',{'printed':True})
 if i>=2:
  aliases={'log_number':'Movement sheet','hauler_name':'Transport by','log_date':'Moved on','well_name':'Origin','total_barrels':'Volume moved (barrels)'}
  trap(f'haul_{i:02d}','T10',[1],[k for k in aliases if v[k] is not None],'Alternate movement labels carry the frozen fields.',{'printed':True})
 add(f'haul_{i:02d}','hauling_log',pkt,v,[page('Fluid movement log',fields(v,['log_number','hauler_name','log_date','well_name'],aliases)+extra+table(loads,CONTRACT['LISTS']['hauling_log'][1])+fields(v,['total_barrels'],aliases))])
# Invoice packet eight deliberately refers to tickets outside its own packet.
for i,pkt,ns in [(1,'ticket_02',[3,4]),(2,'ticket_08',[11,12])]:
 rows=[]
 for n in ns:
  t=next(d for d in BOOK if d['doc_id']==f'ticket_{n:02d}')['values']
  amount=sum(l['amount'] for l in t['line_items'])
  rows.append(dict(ticket_ref=t['ticket_number'],description='Field service bundle',quantity=1,unit='each',rate=amount,amount=amount))
 sub=sum(r['amount'] for r in rows)
 v=dict(invoice_number=f'OVI-{640+i}',vendor_name=VENDOR,invoice_date=f'2026-08-{14+i:02d}',afe_number='ZB-26-701',well_name=WELL,line_items=rows,subtotal=sub,tax=0,total=sub)
 extra='<p>Bill To: '+OP+'</p>';aliases={}
 if i==2:
  v['total']=None;v['afe_number']=None;aliases={'vendor_name':'Remit to','invoice_date':'Issued','well_name':'Service location'}
  extra+='<p>See ticket OV-8311 in the prior packet. Ticket OV-8312 is enclosed.</p>'
  trap('invoice_02','T7',[1],['line_items[0].ticket_ref'],'Printed reference points to another packet.',{'value':'OV-8311','printed':True,'distinct_tickets_in_packet':1},rows=(1,4,5),packet=pkt)
  trap('invoice_02','T8',[1],['total'],'Subtotal is present; Total is labelled blank.',{'value':None,'printed':False,'rules':['R2']})
  trap('invoice_02','T6',[1],['afe_number'],'AFE number is labelled blank.',{'value':None,'printed':False,'rules':['R2']})
  trap('invoice_02','T10',[1],list(aliases),'Remit to, Issued, and Service location carry field values.',{'printed':True})
 if i==2:
  aliases={'invoice_number':'Account request','vendor_name':'Remit to','invoice_date':'Issued','afe_number':'Ref','well_name':'Service location','subtotal':'Pre-tax amount','tax':'Sales levy','total':'Remittance due'}
  trap('invoice_02','T10',[1],[k for k in aliases if v[k] is not None],'Alternate billing labels carry the frozen fields.',{'printed':True})
 add(f'invoice_{i:02d}','invoice',pkt,v,[page('Vendor invoice',extra+fields(v,['invoice_number','vendor_name','invoice_date','afe_number','well_name'],aliases)+table(rows,CONTRACT['LISTS']['invoice'][1])+fields(v,['subtotal','tax','total'],aliases))])
# AFE letters and two-page estimates. AFE 702 is explicitly declined.
costs=[('710','Site preparation','intangible',4000),('720','Pressure service','intangible',6000),('730','Fluid handling','intangible',3000),('810','Valve assembly','tangible',5000),('820','Gauge package','tangible',2000),('830','Spare seals','tangible',0)]
for i in (1,2):
 af=f'ZB-26-70{i}';well=WELL if i==1 else WELL2
 rows=[dict(line_no=j,account_code=a,description=d,category=c,amount=m) for j,(a,d,c,m) in enumerate(costs,1)]
 v=dict(letter_date=f'2026-08-0{i}',operator_name=OP,addressee=OWNER,afe_number=af,well_name=well,response_due_date='2026-08-12',wi_decimal_stated=.2,net_share_stated=4000)
 aliases={};body=''
 if i==2:
  v['response_due_date']='TBD';aliases={'operator_name':'From','afe_number':'Ref','well_name':'Subject well'}
  body='<h2>Estimate copied for owner review</h2>'+table(rows,CONTRACT['LISTS']['afe'][1])
  trap('cover_02','T2',[1],[], 'Letter contains the attached AFE cost table.',{'class':'afe_cover','topic':'afe_cover','rules':['R7']},rows=(1,4))
  trap('cover_02','T10',[1],list(aliases),'Letter uses From, Ref, and Subject well.',{'printed':True})
  trap('cover_02','T6',[1],['response_due_date'],'TBD is printed, not a blank.',{'value':'TBD','printed':True,'rules':['R4']})
 if i==2:
  aliases={'letter_date':'Sent','operator_name':'From','addressee':'Interest owner','afe_number':'Ref','well_name':'Subject well','response_due_date':'Reply by','wi_decimal_stated':'Stated participation decimal','net_share_stated':'Stated owner share'}
  trap('cover_02','T10',[1],list(aliases),'Alternate owner correspondence labels retain field meaning.',{'printed':True})
 for field in ['wi_decimal','net_total']:
  trap(f'cover_{i:02d}','T8',[1],[field],'Stated letter share is not a JIB header decimal or billed net total.',{'printed':False,'value':None})
 content=fields(v,aliases=aliases)+'<p class="letter">Dear interest owner,</p><p class="letter">Please review the enclosed authorization and return your election. This letter transmits the estimate; it does not authorize billing.</p>'+body+'<p class="letter">Sincerely,<br>Owner relations desk</p>'
 add(f'cover_{i:02d}','afe_cover',f'afe_{i:02d}',v,[page('Owner election letter',content)])
 av=dict(afe_number=af,operator_name=OP,well_name=well,api_number=f'00-000-0070{i}',county=COUNTY,state='TX',afe_date=f'2026-08-0{i}',afe_type='Workover',total_estimate=20000,cost_lines=rows)
 aa={}
 if i==2:
  av['api_number']=None;aa={'operator_name':'Bill To','afe_number':'Ref','afe_date':'Prepared','afe_type':'Scope'}
  trap('afe_02','T6',[1],['api_number'],'API number is labelled blank.',{'printed':False,'value':None,'rules':['R2']})
  trap('afe_02','T10',[1],list(aa),'Alternate labels identify the same frozen fields.',{'printed':True})
 if i==2:
  aa={'operator_name':'Bill To','afe_number':'Ref','afe_date':'Prepared','afe_type':'Scope','well_name':'Asset','api_number':'API reference','county':'Parish / county','state':'Jurisdiction','total_estimate':'Authorized estimate'}
  trap('afe_02','T10',[1],[k for k in aa if av[k] is not None and k!='total_estimate'],'Alternate AFE identification labels retain field meaning.',{'printed':True})
  trap('afe_02','T10',[2],['total_estimate'],'Authorized estimate is the printed total.',{'printed':True})
 first=fields(av,['afe_number','operator_name','well_name','api_number','county','state','afe_date','afe_type'],aa)+table(rows[:3],CONTRACT['LISTS']['afe'][1])+'<p>Estimate continues on the attached cost schedule.</p>'
 second=table(rows[3:],CONTRACT['LISTS']['afe'][1])+fields(av,['total_estimate'],aa)+'<p>Election applies to the complete estimate. Zero-dollar rows remain in the schedule.</p>'
 if i==2:second+='<div class="note">Owner election: DECLINED. No participation in ZB-26-702, including account 810.</div>'
 add(f'afe_{i:02d}','afe',f'afe_{i:02d}',av,[page('Authorization for Expenditure',first),page('Cost schedule',second)])
 trap(f'afe_{i:02d}','T6',[2],['well_name','operator_name','afe_number'],'Header fields do not repeat on the cost schedule.',{'page_printed':False,'document_printed':True,'rules':['R3']},rows=())
 trap(f'afe_{i:02d}','T9',[2],[], 'Cost schedule continues the AFE without a page banner.',{'topic':'afe','rules':['R6']},rows=(4,))
# Eight JIB rows, with a wrong decimal and one charge against the declined AFE.
gross=[1200,1800,2400,900,700,500,650,850]
jrows=[]
for j,g in enumerate(gross,1):
 dec=.24 if j==2 else .2
 jrows.append(dict(line_no=j,afe_ref='ZB-26-702' if j==7 else 'ZB-26-701',account_code='810' if j==7 else ['710','720','730','810','820','720','810','730'][j-1],description=['Site preparation','Pressure service','Fluid handling','Valve assembly','Gauge package','Pressure service','Valve assembly','Fluid handling'][j-1],gross_amount=g,owner_decimal=dec,net_amount=round(g*dec,2)))
jv=dict(statement_period='August 2026',operator_name=OP,property_number='ZV-6071',well_name=WELL,owner_name=OWNER,owner_number='MF-204',wi_decimal=.2,gross_total=sum(gross),net_total=sum(r['net_amount'] for r in jrows),due_date='2026-09-25',lines=jrows)
add('jib_01','jib_statement','jib_01',jv,[page('Joint Interest Billing',fields(jv,['statement_period','operator_name','property_number','well_name','owner_name','owner_number','wi_decimal'],{'statement_period':'Accounting month','operator_name':'Operating company','owner_name':'Interest holder'})+table(jrows[:4],CONTRACT['LISTS']['jib_statement'][1],True)),page('Billing detail',table(jrows[4:],CONTRACT['LISTS']['jib_statement'][1],True)+fields(jv,['gross_total','net_total','due_date'])+'<p>Remit using the owner number on the statement face.</p>')])
trap('jib_01','T10',[1],['statement_period','operator_name','owner_name'],'Alternate statement identity labels retain field meaning.',{'printed':True})
trap('jib_01','T9',[2],[], 'Billing rows and totals continue without a page N of M banner.',{'topic':'jib_statement','rules':['R6']},rows=(4,))
trap('jib_01','T6',[2],['well_name','operator_name','wi_decimal'],'Header fields do not repeat; row decimals cannot supply the header.',{'page_printed':False,'document_printed':True,'rules':['R3']},rows=())
trap('jib_01','T3',[1],['wi_decimal'],'A line decimal differs from the statement header.',{'value':.2,'printed':True})
# Fixed deterministic ordering: packets, then ticket/log/invoice or letter/AFE.
order=[f'ticket_{i:02d}' for i in range(1,9)]+['afe_01','afe_02','jib_01']
rank={'field_ticket':0,'hauling_log':1,'invoice':2,'afe_cover':0,'afe':1,'jib_statement':0}
BOOK.sort(key=lambda d:(order.index(d['packet']),rank[d['class']],d['doc_id']))
# Exactly six of twenty-five pages receive T1. Stamp crosses the first identity value.
HARD={('ticket_07',1):2.4,('ticket_09',1):-2.8,('haul_02',1):3.1,('cover_02',1):-2.3,('afe_02',1):2.6,('jib_01',2):-3.0}
for (doc,p),angle in HARD.items():
 d=next(x for x in BOOK if x['doc_id']==doc)
 ff=list(CONTRACT['REQUIRED'][d['class']]) if len(d['html_pages'])==1 or p==1 else ['gross_total','net_total','due_date']
 ff=[f for f in ff if f!='customer_signature_present']
 trap(doc,'T1',[p],ff,'150 dpi gray; seeded noise, skew, translucent stamp across first value, clipped paper margin.',{'rule':'Read the visible value; unreadable units require adjudication/drop.','angle_degrees':angle},rows=(1,4,8),sets=('scan',))
dump(Path('src/book.json'),{'seed':SEED,'synthetic':True,'documents':[{k:v for k,v in d.items() if k!='html_pages'} for d in BOOK]})
dump(Path('reference/doi.json'),dict(property_number='ZV-6071',well_name=WELL,owners=[dict(owner_name=OWNER,owner_number='MF-204',interest_type='WI',decimal=.2)],synthetic=True))
dump(Path('reference/contract_rates.json'),dict(vendor_name=VENDOR,effective_date='2026-01-01',rates=[dict(description='Pressure unit service',unit='hour',contract_rate=175),dict(description='Hose kit rental',unit='day',contract_rate=90),dict(description='Gauge kit rental',unit='day',contract_rate=90)],synthetic=True))
dump(Path('reference/afe_election.json'),dict(afe_number='ZB-26-702',owner_name=OWNER,election='decline',wi_decimal=.2,election_date='2026-08-11',synthetic=True))
dump(Path('planted.json'),{'synthetic':True,'defects':[
 {'plant_id':'P1','doc_id':'jib_01','field':'lines[1].owner_decimal','printed':.24,'correct':.2,'gross_amount':1800,'printed_net':432,'correct_net':360,'overcharge':72,'reference':'reference/doi.json'},
 {'plant_id':'P2','doc_id':'ticket_03','field':'line_items[0].rate','printed':205,'correct':175,'quantity':next(d for d in BOOK if d['doc_id']=='ticket_03')['values']['line_items'][0]['quantity'],'reference':'reference/contract_rates.json'},
 {'plant_id':'P3','doc_id':'jib_01','field':'lines[6].afe_ref','printed':'ZB-26-702','account_code':'810','correct':'Do not bill this owner; AFE 702 declined, including line 4/account 810.','printed_net':130,'correct_net':0,'reference':'reference/afe_election.json'}]})
dump(Path('traps.json'),{'synthetic':True,'traps':TRAPS,'documents':[{'doc_id':d['doc_id'],'trap_ids':sorted({t['trap_id'] for t in TRAPS if t['doc_id']==d['doc_id']})} for d in BOOK],'unit_policy':'Only explicitly mapped row/field/page units carry traps; list-cell and page-presence extras do not enlarge row 8.'})
def normalize(src,dest):
 w=PdfWriter();r=PdfReader(src)
 for p in r.pages:w.add_page(p)
 w.add_metadata({'/Producer':'Synthetic pilot / fixed build 239021','/CreationDate':'D:20260831000000Z','/ModDate':'D:20260831000000Z'})
 with open(dest,'wb') as f:w.write(f)
def image_pdf(jpegs,dest):
 w=PdfWriter()
 for jp in jpegs:
  im=Image.open(jp);wid,hei=im.size
  p=w.add_blank_page(612,792)
  stream=DecodedStreamObject();stream.set_data(Path(jp).read_bytes())
  stream.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),NameObject('/Width'):NumberObject(wid),NameObject('/Height'):NumberObject(hei),NameObject('/ColorSpace'):NameObject('/DeviceGray'),NameObject('/BitsPerComponent'):NumberObject(8),NameObject('/Filter'):NameObject('/DCTDecode')})
  ref=w._add_object(stream)
  p[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Im0'):ref})})
  content=DecodedStreamObject();content.set_data(b'q 612 0 0 792 0 0 cm /Im0 Do Q')
  p[NameObject('/Contents')]=w._add_object(content)
 w.add_metadata({'/Producer':'Synthetic pilot scan / fixed build 239021','/CreationDate':'D:20260831000000Z','/ModDate':'D:20260831000000Z'})
 with open(dest,'wb') as f:w.write(f)
def merge(files,dest):
 w=PdfWriter()
 for f in files:
  for p in PdfReader(f).pages:w.add_page(p)
 w.add_metadata({'/Producer':'Synthetic pilot packet / fixed build 239021'})
 with open(dest,'wb') as f:w.write(f)
manifest=dict(built='2026-09-30',synthetic=True,story=f'{OP} sends August records to {OWNER}. Fictional wells {WELL} and {WELL2} sit in fictional {COUNTY} County. Three billing defects are planted.',documents=[],packets=[],references={k:'synth-pilot/'+v for k,v in {'book':'src/book.json','planted':'planted.json','doi':'reference/doi.json','contract_rates':'reference/contract_rates.json','afe_election':'reference/afe_election.json'}.items()},planted_sha256=sha('planted.json'))
template=Template(Path('src/templates/page.html').read_text())
for d in BOOK:
 (ROOT/'src'/f"{d['doc_id']}.html").write_text(template.substitute(pages=''.join(d['html_pages'])))
Path('scan/README.md').write_text('# Scan pass\n\nCONFIGURATION ONLY until the PDF build succeeds. Rendering and legibility remain UNVERIFIED.\n\nConfigured for all pages: 150 dpi grayscale, seeded Gaussian noise, skew, JPEG embedding without a text layer.\n\nT1 pages (document-local numbering):\n\n'+''.join(f'- {d}, page {p}: {a:+.1f} degree skew; stronger noise; translucent RECEIVED stamp; clipped paper margins.\n' for (d,p),a in HARD.items())+'\nT1 covers 6/25 pages (24%). Margins clip paper but preserve glyphs. Visual and OCR checks are recorded in REPORT.md.\n')
if '--source-only' in sys.argv:
 print('SOURCE ONLY: 22 HTML documents; PDFs, manifest, and layer A are NOT produced.')
 sys.exit(0)
for idx,d in enumerate(BOOK,1):
 ident=d['doc_id'];name=f'{idx:02d}_{ident}.pdf'
 hp=ROOT/'src'/f'{ident}.html';hp.write_text(template.substitute(pages=''.join(d['html_pages'])))
 raw=ROOT/'tmp'/f'{ident}.pdf';cp=ROOT/'clean'/name;sp=ROOT/'scan'/name
 run([CHROME,'--headless=new','--no-sandbox','--disable-gpu','--disable-background-networking','--disable-component-update','--disable-sync','--disable-extensions','--no-first-run','--no-default-browser-check','--disable-crash-reporter','--disable-breakpad','--metrics-recording-only','--host-resolver-rules=MAP * ~NOTFOUND','--no-pdf-header-footer','--print-to-pdf='+str(raw),hp.as_uri()])
 normalize(raw,cp)
 assert len(PdfReader(cp).pages)==len(d['html_pages']),(ident,len(PdfReader(cp).pages))
 run(['pdftoppm','-r','150','-png',cp,ROOT/'audit/rendered'/ident])
 jpegs=[]
 for p in range(1,len(d['html_pages'])+1):
  png=ROOT/'audit/rendered'/f'{ident}-{p}.png';jpg=ROOT/'audit/rendered'/f'{ident}-{p}-scan.jpg'
  hard=(ident,p) in HARD;angle=HARD.get((ident,p),.35 if idx%2 else -.4)
  args=['magick',png,'-colorspace','Gray','-seed',str(SEED+idx*10+p),'-attenuate','0.13' if hard else '0.025','+noise','Gaussian','-background','white','-rotate',str(angle),'-gravity','center','-extent','1275x1650']
  if hard:
   # A translucent received stamp intersects first field's value. Clip paper, not whole glyphs.
   args+=['-fill','rgba(60,60,60,0.32)','-stroke','none','-font','Helvetica','-pointsize','27','-gravity','NorthWest','-annotate','+440+242','RECEIVED','-fill','white','-draw','rectangle 0,0 20,1650','-draw','rectangle 1257,0 1275,1650','-blur','0x0.22']
  args+=['-sampling-factor','1x1','-quality','59' if hard else '78',jpg]
  run(args);jpegs.append(jpg)
 image_pdf(jpegs,sp)
 prior=sum(x['page_count'] for x in manifest['documents'] if x['packet']==d['packet'])
 manifest['documents'].append(dict(doc_id=ident,file='synth-pilot/clean/'+name,scan_file='synth-pilot/scan/'+name,**{'class':d['class']},packet=d['packet'],pages=list(range(prior+1,prior+len(d['html_pages'])+1)),page_count=len(d['html_pages']),sha256=sha(cp),scan_sha256=sha(sp)))
 print('SHA256 clean document',ident,sha(cp),flush=True);print('SHA256 scan document',ident,sha(sp),flush=True)
for pkt in order:
 docs=[x for x in manifest['documents'] if x['packet']==pkt];split={}
 for d in docs:split.setdefault(d['class'],[]).extend(d['pages'])
 item=dict(packet_id=pkt,file=f'synth-pilot/clean/packets/{pkt}.pdf',scan_file=f'synth-pilot/scan/packets/{pkt}.pdf',pages=sum(d['page_count'] for d in docs),split_truth=split)
 for kind,field,hashfield in [('clean','file','sha256'),('scan','scan_file','scan_sha256')]:
  dest=ROOT/kind/'packets'/f'{pkt}.pdf';merge([ROOT.parent/d[field] for d in docs],dest);item[hashfield]=sha(dest)
  print('SHA256',kind,'packet',pkt,item[hashfield],flush=True)
 manifest['packets'].append(item)
dump(Path('manifest.json'),manifest)

print('PDF BUILD OK: 22 documents, 11 packets, 25 pages per set',flush=True)
subprocess.run([sys.executable, str(ROOT/'src/key.py')],check=True)
subprocess.run([sys.executable, str(ROOT/'src/check.py')],check=True)
