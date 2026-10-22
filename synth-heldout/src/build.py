#!/usr/bin/env python3
"""Offline deterministic authoring. All writes stay below synth-heldout."""
from pathlib import Path
import json, hashlib, subprocess, html, random, io, sys, os, time, math
from string import Template
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, DictionaryObject, NumberObject, DecodedStreamObject
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
for folder in ['clean/packets','scan/packets','truth','reference','audit/rendered','tmp']:(ROOT/folder).mkdir(parents=True,exist_ok=True)
SEED=931047
R=random.Random(SEED)
CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
OP='Darsenne Basin Operations LLC'; OWNER='Ultraven Fold Interests LLC'
VENDOR='Brelquor Field Services LLC'; HAULER='Sovarek Fluid Transit LLC'
WELL='Tressaline 9-VH'; WELL2='Ostrand 4-KH'; COUNTY='Lumereth'
CONTRACT=json.loads((ROOT/'src/field_contract.json').read_text())
BOOK=[]; TRAPS=[]
def dump(p,x):
 p=ROOT/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(args):
 if str(args[0])==CHROME:
  output=Path(next(str(a).split('=',1)[1] for a in args if str(a).startswith('--print-to-pdf=')))
  if output.exists():output.unlink()
  log=ROOT/'audit/chrome.log'
  with log.open('a') as stream:
   proc=subprocess.Popen([str(x) for x in args],stdout=stream,stderr=stream)
   deadline=time.monotonic()+90
   while time.monotonic()<deadline:
    if output.exists() and output.read_bytes().rstrip().endswith(b'%%EOF'):
     proc.terminate()
     try:proc.wait(timeout=5)
     except subprocess.TimeoutExpired:proc.kill();proc.wait()
     return ''
    if proc.poll() is not None:raise RuntimeError(f'Chrome failed ({proc.returncode}); see audit/chrome.log')
    time.sleep(.2)
   proc.terminate();raise RuntimeError('Chrome PDF timeout')
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
# Fifteen pairs and fifteen singles; nine of each are plain controls.
for n in range(1,46):
 pkt= f'ticket_{(n+1)//2:02d}' if n<=30 else f'ticket_{n-15:02d}'
 day=1+(n+1)//2 if n<=30 else n-15
 qty=6 if 19<=n<=30 else R.choice([4,5,6,7])
 if n<=18:
  day=n
  qty=4+((n+1)//2)%3 if n%2 else 7+((n+1)//2)%2
 rate=205 if n==3 else 175
 lines=[dict(description='Pressure unit service',quantity=qty,unit='hour',rate=rate,amount=qty*rate),
        dict(description='Hose kit rental',quantity=1,unit='day',rate=90,amount=90)]
 v=dict(ticket_number=f'BQ-{9600+n}',vendor_name=VENDOR,service_date=f'2026-09-{day:02d}',well_name=WELL,afe_number='DB-26-901',line_items=lines,total=qty*rate+90,customer_signature_present=False)
 aliases={};extra='';struck=[]
 if 19<=n<=30 and n%2==0:
  lines[1]['description']='Gauge kit rental'
 if n>=40:
  aliases={'service_date':'Serviced','afe_number':'Ref'}
  extra+='<div class="stamp">REPRINT</div><p>Replacement office copy. No additional service authorized.</p>'
  trap(f'ticket_{n:02d}','T4',[1],[], 'Replacement copy retains its ticket number.', {'distinct_tickets_in_packet':1},rows=(5,),packet=pkt)
  trap(f'ticket_{n:02d}','T10',[1],['service_date'] if n in (40,42,44) else ['service_date','afe_number'],'Serviced and Ref denote the frozen fields.',{'printed':True,'rules':['R3']})
 if n in (40,42,44):
  v['afe_number']=None
  trap(f'ticket_{n:02d}','T6',[1],['afe_number'],'Ref is labelled but blank.',{'afe_number':None,'printed':False,'rules':['R2']})
 if n in (41,43,45):
  lines[0]['unit']=None
  trap(f'ticket_{n:02d}','T4',[1],['line_items[0].unit'],'Bare quantity has an empty unit cell.',{'value':None,'printed':False,'rules':['R2']},rows=())
 if n==44:
  v['well_name']='N/A';struck=['service_date']
  trap(f'ticket_{n:02d}','T6',[1],['well_name'],'N/A is literal printed content.',{'value':'N/A','printed':True,'rules':['R4']})
  trap(f'ticket_{n:02d}','T3',[1],['service_date'],'Struck service date remains visible; dispatch date differs.',{'value':v['service_date'],'printed':True,'rules':['R5']})
  extra+='<p>Dispatch date: 2026-09-04. The struck service date remains on this retained copy.</p>'
 if n in (41,43,45):
  v['total']=None
  extra+=fields({'subtotal':qty*rate+90})
  trap(f'ticket_{n:02d}','T8',[1],['total'],'Only Subtotal is printed; the Total field is blank.',{'value':None,'printed':False,'rules':['R2']})
 if 19<=n<=30:
  extra+='<p>Worksite note: Tressaline 9V-H. Use the well identification in the header for this ticket.</p>'
  trap(f'ticket_{n:02d}','T3',[1],['well_name'],'Body spelling conflicts with the well header.',{'value':WELL,'printed':True,'rules':['R3']})
 if 19<=n<=30 or n>=40 or n in (1,2,5,6,9,10,13,14,17,18):
  aliases={'ticket_number':'Dispatch docket','vendor_name':'Service firm','service_date':'Serviced','well_name':'Asset','afe_number':'Ref','total':'Amount due'}
  trap(f'ticket_{n:02d}','T10',[1],[k for k in aliases if v[k] is not None],'Alternate service and accounting labels carry the frozen fields.',{'printed':True})
 title='Field service ticket'
 body=extra+fields(v,['ticket_number','vendor_name','service_date','well_name','afe_number'],aliases,struck)+table(lines,CONTRACT['LISTS']['field_ticket'][1])+fields(v,['total'],aliases)+'<div class="signature">Customer signature: __________________________</div>'
 add(f'ticket_{n:02d}','field_ticket',pkt,v,[page(title,body)])
for n in range(19,31):trap(f'ticket_{n:02d}','T5',[1],['ticket_number'],'Paired tickets differ in ticket number and one charge description.',{'distinct_tickets_in_packet':2},rows=(5,),packet=f'ticket_{(n+1)//2:02d}')
# Nine logs ride with ticket packets. A reference is not another field ticket.
for i,pkt in enumerate(['ticket_01','ticket_02','ticket_03','ticket_10','ticket_11','ticket_12','ticket_25','ticket_27','ticket_29'],1):
 loads=[dict(load_no=j,time=f'{7+j:02d}:15',fluid_type='Produced water',barrels=60,destination='Pelmora recovery bay') for j in range(1,5)]
 v=dict(log_number=f'SF-{910+i}',hauler_name=HAULER,log_date=f'2026-09-{i+2:02d}',well_name=WELL,loads=loads,total_barrels=240)
 aliases={};extra=''
 if i in (4,7,9):
  v['well_name']=None
  extra='<p>See ticket BQ-9987 in the prior dispatch batch. No ticket is enclosed for that reference.</p>'
  trap(f'haul_{i:02d}','T7',[1],[], 'A reference to a missing ticket is not a field ticket.',{'class':'hauling_log','distinct_tickets_in_packet':2 if i==4 else 1},rows=(1,4,5),packet=pkt)
  trap(f'haul_{i:02d}','T6',[1],['well_name'],'Well is labelled but blank.',{'value':None,'printed':False,'rules':['R2']})
 if i==9:
  aliases={'hauler_name':'Transport by','log_date':'Moved on','well_name':'Origin'}
  trap(f'haul_{i:02d}','T10',[1],list(aliases),'Alternate dispatch labels retain field meaning.',{'printed':True})
 if i in (3,4,6,7,9):
  aliases={'log_number':'Movement sheet','hauler_name':'Transport by','log_date':'Moved on','well_name':'Origin','total_barrels':'Volume moved (barrels)'}
  trap(f'haul_{i:02d}','T10',[1],[k for k in aliases if v[k] is not None],'Alternate movement labels carry the frozen fields.',{'printed':True})
 add(f'haul_{i:02d}','hauling_log',pkt,v,[page('Fluid movement log',fields(v,['log_number','hauler_name','log_date','well_name'],aliases)+extra+table(loads,CONTRACT['LISTS']['hauling_log'][1])+fields(v,['total_barrels'],aliases))])
# One invoice deliberately refers to a ticket outside its packet.
for i,pkt,ns in [(1,'ticket_04',[7,8]),(2,'ticket_30',[44,45]),(3,'ticket_05',[9,10]),(4,'ticket_06',[11,12])]:
 rows=[]
 for n in ns:
  t=next(d for d in BOOK if d['doc_id']==f'ticket_{n:02d}')['values']
  amount=sum(l['amount'] for l in t['line_items'])
  rows.append(dict(ticket_ref=t['ticket_number'],description='Field service bundle',quantity=1,unit='each',rate=amount,amount=amount))
 sub=sum(r['amount'] for r in rows)
 v=dict(invoice_number=f'BQI-{640+i}',vendor_name=VENDOR,invoice_date=f'2026-09-{14+i:02d}',afe_number='DB-26-901',well_name=WELL,line_items=rows,subtotal=sub,tax=0,total=sub)
 extra='<p>Bill To: '+OP+'</p>';aliases={}
 if i==2:
  v['total']=None;v['afe_number']=None;aliases={'vendor_name':'Remit to','invoice_date':'Issued','well_name':'Service location'}
  extra+='<p>See ticket BQ-9644 in the prior packet. Ticket BQ-9645 is enclosed.</p>'
  trap('invoice_02','T7',[1],['line_items[0].ticket_ref'],'Printed reference points to another packet.',{'value':'BQ-9644','printed':True,'distinct_tickets_in_packet':1},rows=(1,4,5),packet=pkt)
  trap('invoice_02','T8',[1],['total'],'Subtotal is present; Total is labelled blank.',{'value':None,'printed':False,'rules':['R2']})
  trap('invoice_02','T6',[1],['afe_number'],'AFE number is labelled blank.',{'value':None,'printed':False,'rules':['R2']})
  trap('invoice_02','T10',[1],list(aliases),'Remit to, Issued, and Service location carry field values.',{'printed':True})
 if i==2:
  aliases={'invoice_number':'Account request','vendor_name':'Remit to','invoice_date':'Issued','afe_number':'Ref','well_name':'Service location','subtotal':'Pre-tax amount','tax':'Sales levy','total':'Remittance due'}
  trap('invoice_02','T10',[1],[k for k in aliases if v[k] is not None],'Alternate billing labels carry the frozen fields.',{'printed':True})
 add(f'invoice_{i:02d}','invoice',pkt,v,[page('Vendor invoice',extra+fields(v,['invoice_number','vendor_name','invoice_date','afe_number','well_name'],aliases)+table(rows,CONTRACT['LISTS']['invoice'][1])+fields(v,['subtotal','tax','total'],aliases))])
# AFE letters and two-page estimates. AFE 902 is explicitly declined.
costs=[('710','Site preparation','intangible',4000),('720','Pressure service','intangible',6000),('730','Fluid handling','intangible',3000),('810','Valve assembly','tangible',5000),('820','Gauge package','tangible',2000),('830','Spare seals','tangible',0)]
for i in (1,2,3,4):
 af=f'DB-26-90{i}';well=WELL if i==1 else WELL2
 rows=[dict(line_no=j,account_code=a,description=d,category=c,amount=m) for j,(a,d,c,m) in enumerate(costs,1)]
 v=dict(letter_date=f'2026-09-0{i}',operator_name=OP,addressee=OWNER,afe_number=af,well_name=well,response_due_date='2026-09-12',wi_decimal_stated=.2,net_share_stated=4000)
 aliases={};body=''
 if i in (2,4):
  v['response_due_date']='TBD';aliases={'operator_name':'From','afe_number':'Ref','well_name':'Subject well'}
  body='<h2>Estimate copied for owner review</h2>'+table(rows,CONTRACT['LISTS']['afe'][1])
  trap(f'cover_{i:02d}','T2',[1],[], 'Letter contains the attached AFE cost table.',{'class':'afe_cover','topic':'afe_cover','rules':['R7']},rows=(1,4))
  trap(f'cover_{i:02d}','T10',[1],list(aliases),'Letter uses From, Ref, and Subject well.',{'printed':True})
  trap(f'cover_{i:02d}','T6',[1],['response_due_date'],'TBD is printed, not a blank.',{'value':'TBD','printed':True,'rules':['R4']})
 if i in (2,4):
  aliases={'letter_date':'Sent','operator_name':'From','addressee':'Interest owner','afe_number':'Ref','well_name':'Subject well','response_due_date':'Reply by','wi_decimal_stated':'Stated participation decimal','net_share_stated':'Stated owner share'}
  trap(f'cover_{i:02d}','T10',[1],list(aliases),'Alternate owner correspondence labels retain field meaning.',{'printed':True})
 for field in ['wi_decimal','net_total']:
  trap(f'cover_{i:02d}','T8',[1],[field],'Stated letter share is not a JIB header decimal or billed net total.',{'printed':False,'value':None})
 content=fields(v,aliases=aliases)+'<p class="letter">Dear interest owner,</p><p class="letter">Please review the enclosed authorization and return your election. This letter transmits the estimate; it does not authorize billing.</p>'+body+'<p class="letter">Sincerely,<br>Owner relations desk</p>'
 add(f'cover_{i:02d}','afe_cover',f'afe_{i:02d}',v,[page('Owner election letter',content)])
 av=dict(afe_number=af,operator_name=OP,well_name=well,api_number=f'00-000-0070{i}',county=COUNTY,state='TX',afe_date=f'2026-09-0{i}',afe_type='Workover',total_estimate=20000,cost_lines=rows)
 aa={}
 if i in (2,4):
  av['api_number']=None;aa={'operator_name':'Bill To','afe_number':'Ref','afe_date':'Prepared','afe_type':'Scope'}
  trap(f'afe_{i:02d}','T6',[1],['api_number'],'API number is labelled blank.',{'printed':False,'value':None,'rules':['R2']})
  trap(f'afe_{i:02d}','T10',[1],list(aa),'Alternate labels identify the same frozen fields.',{'printed':True})
 if i in (2,4):
  aa={'operator_name':'Bill To','afe_number':'Ref','afe_date':'Prepared','afe_type':'Scope','well_name':'Asset','api_number':'API reference','county':'Parish / county','state':'Jurisdiction','total_estimate':'Authorized estimate'}
  trap(f'afe_{i:02d}','T10',[1],[k for k in aa if av[k] is not None and k!='total_estimate'],'Alternate AFE identification labels retain field meaning.',{'printed':True})
  trap(f'afe_{i:02d}','T10',[2],['total_estimate'],'Authorized estimate is the printed total.',{'printed':True})
 if i in (2,4):
  trap(f'afe_{i:02d}','T2',[1],[], 'AFE form opens with a transmittal paragraph.',{'class':'afe','topic':'afe'},rows=(1,4))
 first=fields(av,['afe_number','operator_name','well_name','api_number','county','state','afe_date','afe_type'],aa)+table(rows[:3],CONTRACT['LISTS']['afe'][1])+'<p>Estimate continues on the attached cost schedule.</p>'
 second=table(rows[3:],CONTRACT['LISTS']['afe'][1])+fields(av,['total_estimate'],aa)+'<p>Election applies to the complete estimate. Zero-dollar rows remain in the schedule.</p>'
 if i==2:second+='<div class="note">Owner election: DECLINED. No participation in DB-26-902, including account 810.</div>'
 if i in (2,4):first='<p>Dear interest owner, please review this authorization and return your election.</p>'+first
 add(f'afe_{i:02d}','afe',f'afe_{i:02d}',av,[page('Authorization for Expenditure',first),page('Cost schedule',second)])
 trap(f'afe_{i:02d}','T6',[2],['well_name','operator_name'] if i==2 else ['well_name','operator_name','afe_number'],'Header fields do not repeat on the cost schedule.',{'page_printed':False,'document_printed':True,'rules':['R3']},rows=())
 trap(f'afe_{i:02d}','T9',[2],[], 'Cost schedule continues the AFE without a page banner.',{'topic':'afe','rules':['R6']},rows=(4,))
# Eight JIB rows, with a wrong decimal and one charge against the declined AFE.
for ji in range(1,6):
 gross=[1200,1800,2400,900,700,500,650,850]
 jrows=[]
 for j,g in enumerate(gross,1):
  dec=.24 if ji==1 and j==2 else .2
  jrows.append(dict(line_no=j,afe_ref='DB-26-902' if ji==1 and j==7 else 'DB-26-901',account_code='810' if j==7 else ['710','720','730','810','820','720','810','730'][j-1],description=['Site preparation','Pressure service','Fluid handling','Valve assembly','Gauge package','Pressure service','Valve assembly','Fluid handling'][j-1],gross_amount=g,owner_decimal=dec,net_amount=round(g*dec,2)))
 jv=dict(statement_period='September 2026',operator_name=OP,property_number=f'DS-{8092+ji}',well_name=WELL,owner_name=OWNER,owner_number='UF-306',wi_decimal=.2,gross_total=sum(gross),net_total=sum(r['net_amount'] for r in jrows),due_date='2026-10-25',lines=jrows)
 add(f'jib_{ji:02d}','jib_statement',f'jib_{ji:02d}',jv,[page('Joint Interest Billing',fields(jv,['statement_period','operator_name','property_number','well_name','owner_name','owner_number','wi_decimal'],{'statement_period':'Accounting month','operator_name':'Operating company','owner_name':'Interest holder'})+table(jrows[:4],CONTRACT['LISTS']['jib_statement'][1],True)),page('Billing detail',table(jrows[4:],CONTRACT['LISTS']['jib_statement'][1],True)+fields(jv,['gross_total','net_total','due_date'])+'<p>Remit using the owner number on the statement face.</p>')])
 trap(f'jib_{ji:02d}','T10',[1],['statement_period','operator_name','owner_name'],'Alternate statement identity labels retain field meaning.',{'printed':True})
 trap(f'jib_{ji:02d}','T9',[2],[], 'Billing rows and totals continue without a page N of M banner.',{'topic':'jib_statement','rules':['R6']},rows=(4,))
 trap(f'jib_{ji:02d}','T6',[2],['well_name','operator_name','wi_decimal'],'Header fields do not repeat; row decimals cannot supply the header.',{'page_printed':False,'document_printed':True,'rules':['R3']},rows=())
 if ji==1:trap(f'jib_{ji:02d}','T3',[1],['wi_decimal'],'A line decimal differs from the statement header.',{'value':.2,'printed':True})
# Fixed deterministic ordering: packets, then ticket/log/invoice or letter/AFE.
order=[f'ticket_{i:02d}' for i in range(1,31)]+[f'afe_{i:02d}' for i in range(1,5)]+[f'jib_{i:02d}' for i in range(1,6)]
rank={'field_ticket':0,'hauling_log':1,'invoice':2,'afe_cover':0,'afe':1,'jib_statement':0}
BOOK.sort(key=lambda d:(order.index(d['packet']),rank[d['class']],d['doc_id']))
# Exactly twenty of eighty pages receive T1. Stamp crosses the first identity value.
HARD={}
for ix,doc in enumerate([*[f'ticket_{i:02d}' for i in (19,20,21,22,23,24,25,26,40,41,42,43)],'haul_04','haul_07','invoice_02','cover_02','cover_04','afe_02','afe_04','jib_01']):
 HARD[(doc,2 if doc=='jib_01' else 1)]=[2.4,-2.8,3.1,-2.3,2.6,-3.0][ix%6]
for (doc,p),angle in HARD.items():
 d=next(x for x in BOOK if x['doc_id']==doc)
 ff=list(CONTRACT['REQUIRED'][d['class']]) if len(d['html_pages'])==1 or p==1 else ['gross_total','net_total','due_date']
 ff=[f for f in ff if f!='customer_signature_present']
 trap(doc,'T1',[p],ff,'150 dpi gray; seeded noise, skew, translucent stamp across first value, clipped paper margin.',{'rule':'Read the visible value; unreadable units require adjudication/drop.','angle_degrees':angle},rows=(1,4,8),sets=('scan',))
dump(Path('src/book.json'),{'seed':SEED,'synthetic':True,'documents':[{k:v for k,v in d.items() if k!='html_pages'} for d in BOOK]})
dump(Path('reference/doi.json'),dict(property_number='DS-8093',well_name=WELL,owners=[dict(owner_name=OWNER,owner_number='UF-306',interest_type='WI',decimal=.2)],synthetic=True))
dump(Path('reference/contract_rates.json'),dict(vendor_name=VENDOR,effective_date='2026-01-01',rates=[dict(description='Pressure unit service',unit='hour',contract_rate=175),dict(description='Hose kit rental',unit='day',contract_rate=90),dict(description='Gauge kit rental',unit='day',contract_rate=90)],synthetic=True))
dump(Path('reference/afe_election.json'),dict(afe_number='DB-26-902',owner_name=OWNER,election='decline',wi_decimal=.2,election_date='2026-09-11',synthetic=True))
dump(Path('planted.json'),{'synthetic':True,'defects':[
 {'plant_id':'P1','doc_id':'jib_01','field':'lines[1].owner_decimal','printed':.24,'correct':.2,'gross_amount':1800,'printed_net':432,'correct_net':360,'overcharge':72,'reference':'reference/doi.json'},
 {'plant_id':'P2','doc_id':'ticket_03','field':'line_items[0].rate','printed':205,'correct':175,'quantity':next(d for d in BOOK if d['doc_id']=='ticket_03')['values']['line_items'][0]['quantity'],'reference':'reference/contract_rates.json'},
 {'plant_id':'P3','doc_id':'jib_01','field':'lines[6].afe_ref','printed':'DB-26-902','account_code':'810','correct':'Do not bill this owner; AFE 902 declined, including line 4/account 810.','printed_net':130,'correct_net':0,'reference':'reference/afe_election.json'}]})
dump(Path('traps.json'),{'synthetic':True,'traps':TRAPS,'documents':[{'doc_id':d['doc_id'],'trap_ids':sorted({t['trap_id'] for t in TRAPS if t['doc_id']==d['doc_id']})} for d in BOOK],'unit_policy':'Only explicitly mapped row/field/page units carry traps; list-cell and page-presence extras do not enlarge row 8.'})
def normalize(src,dest):
 w=PdfWriter();r=PdfReader(src)
 for p in r.pages:w.add_page(p)
 w.add_metadata({'/Producer':'Synthetic heldout / fixed build 931047','/CreationDate':'D:20260930000000Z','/ModDate':'D:20260930000000Z'})
 with open(dest,'wb') as f:w.write(f)
def stamp_location(pdf,page_number,angle):
 # Anchor the unchanged stamp to a rendered bold field value, after skew.
 last_label=[None];found=[]
 def visit(text,cm,tm,font,size):
  if text.strip().endswith(':') and tm[5]>0:last_label[0]=tm[5]
  if text.strip() and font and 'Bold' in str(font.get('/BaseFont','')) and size==12 and last_label[0] and not found:
   found.append(last_label[0])
 PdfReader(pdf).pages[page_number-1].extract_text(visitor_text=visit)
 if not found:raise ValueError(f'No rendered stamp anchor: {pdf} page {page_number}')
 x=232.8*150/96;y=(found[0]-(page_number-1)*1056-30)*150/96
 rad=math.radians(angle);dx=x-637.5;dy=y-825
 return f'+{round(637.5+dx*math.cos(rad)-dy*math.sin(rad))}+{round(825+dx*math.sin(rad)+dy*math.cos(rad))}'
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
 w.add_metadata({'/Producer':'Synthetic heldout scan / fixed build 931047','/CreationDate':'D:20260930000000Z','/ModDate':'D:20260930000000Z'})
 with open(dest,'wb') as f:w.write(f)
def merge(files,dest):
 w=PdfWriter()
 for f in files:
  for p in PdfReader(f).pages:w.add_page(p)
 w.add_metadata({'/Producer':'Synthetic heldout packet / fixed build 931047'})
 with open(dest,'wb') as f:w.write(f)
manifest=dict(built='2026-09-30',synthetic=True,story=f'{OP} sends September records to {OWNER}. Vendors are {VENDOR} and {HAULER}. Fictional wells {WELL} and {WELL2} sit in fictional {COUNTY} County. Three billing defects are planted.',documents=[],packets=[],references={k:'synth-heldout/'+v for k,v in {'book':'src/book.json','planted':'planted.json','doi':'reference/doi.json','contract_rates':'reference/contract_rates.json','afe_election':'reference/afe_election.json'}.items()},planted_sha256=sha('planted.json'))
template=Template(Path('src/templates/page.html').read_text())
for d in BOOK:
 (ROOT/'src'/f"{d['doc_id']}.html").write_text(template.substitute(pages=''.join(d['html_pages'])))
Path('scan/README.md').write_text('# Scan pass\n\nSee REPORT.md for rendering and visual checks.\n\nConfigured for all pages: 150 dpi grayscale, seeded Gaussian noise, skew, JPEG embedding without a text layer.\n\nT1 pages (document-local numbering):\n\n'+''.join(f'- {d}, page {p}: {a:+.1f} degree skew; stronger noise; translucent RECEIVED stamp; clipped paper margins.\n' for (d,p),a in HARD.items())+'\nT1 covers 20/80 pages (25%). Margins clip paper but preserve glyphs. Visual and OCR checks are recorded in REPORT.md.\n')
if '--source-only' in sys.argv:
 print('SOURCE ONLY: 71 HTML documents; PDFs, manifest, and layer A are NOT produced.')
 sys.exit(0)
for idx,d in enumerate(BOOK,1):
 ident=d['doc_id'];name=f'{idx:02d}_{ident}.pdf'
 hp=ROOT/'src'/f'{ident}.html';hp.write_text(template.substitute(pages=''.join(d['html_pages'])))
 raw=ROOT/'tmp'/f'{ident}.pdf';cp=ROOT/'clean'/name;sp=ROOT/'scan'/name
 run([CHROME,'--headless=new','--user-data-dir='+str(ROOT/'tmp/chrome-profile'),'--no-sandbox','--disable-gpu','--disable-background-networking','--disable-component-update','--disable-sync','--disable-extensions','--no-first-run','--no-default-browser-check','--disable-crash-reporter','--disable-breakpad','--metrics-recording-only','--host-resolver-rules=MAP * ~NOTFOUND','--no-pdf-header-footer','--print-to-pdf='+str(raw),hp.as_uri()])
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
   args+=['-fill','rgba(60,60,60,0.32)','-stroke','none','-font','Helvetica','-pointsize','27','-gravity','NorthWest','-annotate',stamp_location(cp,p,angle),'RECEIVED','-fill','white','-draw','rectangle 0,0 20,1650','-draw','rectangle 1257,0 1275,1650','-blur','0x0.22']
  args+=['-sampling-factor','1x1','-quality','59' if hard else '78',jpg]
  run(args);jpegs.append(jpg)
 image_pdf(jpegs,sp)
 prior=sum(x['page_count'] for x in manifest['documents'] if x['packet']==d['packet'])
 manifest['documents'].append(dict(doc_id=ident,file='synth-heldout/clean/'+name,scan_file='synth-heldout/scan/'+name,**{'class':d['class']},packet=d['packet'],pages=list(range(prior+1,prior+len(d['html_pages'])+1)),page_count=len(d['html_pages']),sha256=sha(cp),scan_sha256=sha(sp)))
 print('SHA256 clean document',ident,sha(cp),flush=True);print('SHA256 scan document',ident,sha(sp),flush=True)
for pkt in order:
 docs=[x for x in manifest['documents'] if x['packet']==pkt];split={}
 for d in docs:split.setdefault(d['class'],[]).extend(d['pages'])
 item=dict(packet_id=pkt,file=f'synth-heldout/clean/packets/{pkt}.pdf',scan_file=f'synth-heldout/scan/packets/{pkt}.pdf',pages=sum(d['page_count'] for d in docs),split_truth=split)
 for kind,field,hashfield in [('clean','file','sha256'),('scan','scan_file','scan_sha256')]:
  dest=ROOT/kind/'packets'/f'{pkt}.pdf';merge([ROOT.parent/d[field] for d in docs],dest);item[hashfield]=sha(dest)
  print('SHA256',kind,'packet',pkt,item[hashfield],flush=True)
 manifest['packets'].append(item)
dump(Path('manifest.json'),manifest)

print('PDF BUILD OK: 71 documents, 39 packets, 80 pages per set',flush=True)
subprocess.run([sys.executable, str(ROOT/'src/key.py')],check=True)
subprocess.run([sys.executable, str(ROOT/'src/check.py')],check=True)
