import json,pathlib
OUT=pathlib.Path('truth-blind')
PAGES={}
def put(prefix,typ,v,unc=None,page=None):
 f=next(pathlib.Path('pdfs').glob(prefix+'_*.pdf')); did=f.stem.split('_',1)[1]
 n=len(list(pathlib.Path('page-images').glob(f.stem+'-*.png')))
 po={}
 def walk(x,path):
  if isinstance(x,list):
   for i,y in enumerate(x): walk(y,f'{path}[{i}]')
  elif isinstance(x,dict):
   for k,y in x.items(): walk(y,f'{path}.{k}' if path else k)
  elif x is not None: po[path]=1
 walk(v,'')
 if page: po.update(page)
 obj=dict(doc_id=did,source_file=f.name,keyed_by='codex blind re-key (layer A, second session)',keyed_from='page images',values=v,page_of=po,uncertain=unc or [])
 (OUT/(did+'.json')).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
 PAGES[did]=dict(page_count=n,class_by_eye=typ,page_topics=[typ]+['continuation']*(n-1))
def ticket(prefix,num,vendor,date,well,afe,rows,total,sig=False,unc=None):
 put(prefix,'field_ticket',dict(ticket_number=num,vendor_name=vendor,service_date=date,well_name=well,afe_number=afe,line_items=[dict(zip(['description','quantity','unit','rate','amount'],r)) for r in rows],total=total,customer_signature_present=sig),unc)
def haul(prefix,num,vendor,date,well,rows,total,unc=None):
 put(prefix,'hauling_log',dict(log_number=num,hauler_name=vendor,log_date=date,well_name=well,loads=[dict(zip(['load_no','time','fluid_type','barrels','destination'],r)) for r in rows],total_barrels=total),unc)
B='Brelquor Field Services LLC'; T='Tressaline 9-VH'; D='DB-26-901'; S='Sovarek Fluid Transit LLC'
def pressure(q,r,a): return [['Pressure unit service',q,'hour',r,a],['Hose kit rental',1,'day',90,90]]
ticket('01','BQ-9601',B,'2026-09-01',T,D,pressure(5,175,875),965)
ticket('02','BQ-9602',B,'2026-09-02',T,D,pressure(8,175,1400),1490)
haul('03','SF-911',S,'2026-09-03',T,[[i,f'{7+i:02}:15','Produced water',60,'Pelmora recovery bay'] for i in range(1,5)],240)
ticket('04','BQ-9603',B,'2026-09-03',T,D,pressure(6,205,1230),1320)
ticket('05','BQ-9604',B,'2026-09-04',T,D,pressure(7,175,1225),1315)
haul('06','SF-912',S,'2026-09-04',T,[[i,f'{7+i:02}:15','Produced water',60,'Pelmora recovery bay'] for i in range(1,5)],240)
ticket('07','BQ-9605',B,'2026-09-05',T,D,pressure(4,175,700),790)
ticket('08','BQ-9606',B,'2026-09-06',T,D,pressure(8,175,1400),1490)
haul('09','SF-913',S,'2026-09-05',T,[[i,f'{7+i:02}:15','Produced water',60,'Pelmora recovery bay'] for i in range(1,5)],240)
ticket('10','BQ-9607',B,'2026-09-07',T,D,pressure(5,175,875),965)
def invoice(prefix,num,vendor,date,afe,well,rows,sub,tax,total,unc=None):
 put(prefix,'invoice',dict(invoice_number=num,vendor_name=vendor,invoice_date=date,afe_number=afe,well_name=well,line_items=[dict(zip(['ticket_ref','description','quantity','unit','rate','amount'],r)) for r in rows],subtotal=sub,tax=tax,total=total),unc)
ticket('11','BQ-9608',B,'2026-09-08',T,D,pressure(7,175,1225),1315)
invoice('12','BQI-641',B,'2026-09-15',D,T,[['BQ-9607','Field service bundle',1,'each',965,965],['BQ-9608','Field service bundle',1,'each',1315,1315]],2280,0,2280)
ticket('13','BQ-9609',B,'2026-09-09',T,D,pressure(6,175,1050),1140)
ticket('14','BQ-9610',B,'2026-09-10',T,D,pressure(8,175,1400),1490)
invoice('15','BQI-643',B,'2026-09-17',D,T,[['BQ-9609','Field service bundle',1,'each',1140,1140],['BQ-9610','Field service bundle',1,'each',1490,1490]],2630,0,2630)
ticket('16','BQ-9611',B,'2026-09-11',T,D,pressure(4,175,700),790)
ticket('17','BQ-9612',B,'2026-09-12',T,D,pressure(7,175,1225),1315)
invoice('18','BQI-644',B,'2026-09-18',D,T,[['BQ-9611','Field service bundle',1,'each',790,790],['BQ-9612','Field service bundle',1,'each',1315,1315]],2105,0,2105)
ticket('19','BQ-9613',B,'2026-09-13',T,D,pressure(5,175,875),965)
ticket('20','BQ-9614',B,'2026-09-14',T,D,pressure(8,175,1400),1490)
ticket('21','BQ-9615',B,'2026-09-15',T,D,pressure(6,175,1050),1140)
ticket('22','BQ-9616',B,'2026-09-16',T,D,pressure(7,175,1225),1315)
ticket('23','BQ-9617',B,'2026-09-17',T,D,pressure(4,175,700),790)
ticket('24','BQ-9618',B,'2026-09-18',T,D,pressure(8,175,1400),1490)
variant=['well_name: Asset prints Tressaline 9-VH; worksite note prints Tressaline 9V-H.']
ticket('25','BQ-9619',B,'2026-09-11',T,D,pressure(6,175,1050),1140,unc=variant)
ticket('26','BQ-9620',B,'2026-09-11',T,D,[['Pressure unit service',6,'hour',175,1050],['Gauge kit rental',1,'day',90,90]],1140,unc=variant)
haul('27','SF-914',S,'2026-09-06',None,[[i,f'{7+i:02}:15','Produced water',60,'Pelmora recovery bay'] for i in range(1,5)],240)
ticket('28','BQ-9621',B,'2026-09-12',T,D,pressure(6,175,1050),1140,unc=variant)
def gauge(): return [['Pressure unit service',6,'hour',175,1050],['Gauge kit rental',1,'day',90,90]]
ticket('29','BQ-9622',B,'2026-09-12',T,D,gauge(),1140,unc=variant)
haul('30','SF-915',S,'2026-09-07',T,[[i,f'{7+i:02}:15','Produced water',60,'Pelmora recovery bay'] for i in range(1,5)],240)
ticket('31','BQ-9623',B,'2026-09-13',T,D,pressure(6,175,1050),1140,unc=variant)
ticket('32','BQ-9624',B,'2026-09-13',T,D,gauge(),1140,unc=variant)
haul('33','SF-916',S,'2026-09-08',T,[[i,f'{7+i:02}:15','Produced water',60,'Pelmora recovery bay'] for i in range(1,5)],240)
ticket('34','BQ-9625',B,'2026-09-14',T,D,pressure(6,175,1050),1140,unc=variant)
ticket('35','BQ-9626',B,'2026-09-14',T,D,gauge(),1140,unc=variant)
ticket('36','BQ-9627',B,'2026-09-15',T,D,pressure(6,175,1050),1140,unc=variant)
ticket('37','BQ-9628',B,'2026-09-15',T,D,gauge(),1140,unc=variant)
ticket('38','BQ-9629',B,'2026-09-16',T,D,pressure(6,175,1050),1140,unc=variant)
ticket('39','BQ-9630',B,'2026-09-16',T,D,gauge(),1140,unc=variant)
ticket('40','BQ-9631',B,'2026-09-16',T,D,pressure(7,175,1225),1315)
ticket('41','BQ-9632',B,'2026-09-17',T,D,pressure(6,175,1050),1140)
ticket('42','BQ-9633',B,'2026-09-18',T,D,pressure(5,175,875),965)
ticket('43','BQ-9634',B,'2026-09-19',T,D,pressure(5,175,875),965)
ticket('44','BQ-9635',B,'2026-09-20',T,D,pressure(4,175,700),790)
ticket('45','BQ-9636',B,'2026-09-21',T,D,pressure(5,175,875),965)
ticket('46','BQ-9637',B,'2026-09-22',T,D,pressure(4,175,700),790)
ticket('47','BQ-9638',B,'2026-09-23',T,D,pressure(5,175,875),965)
ticket('48','BQ-9639',B,'2026-09-24',T,D,pressure(5,175,875),965)
ticket('49','BQ-9640',B,'2026-09-25',T,None,pressure(5,175,875),965)
haul('50','SF-917',S,'2026-09-09',None,[[i,f'{7+i:02}:15','Produced water',60,'Pelmora recovery bay'] for i in range(1,5)],240)
ticket('51','BQ-9641',B,'2026-09-26',T,D,[['Pressure unit service',6,None,175,1050],['Hose kit rental',1,'day',90,90]],None)
ticket('52','BQ-9642',B,'2026-09-27',T,None,pressure(7,175,1225),1315)
haul('53','SF-918',S,'2026-09-10',T,[[i,f'{7+i:02}:15','Produced water',60,'Pelmora recovery bay'] for i in range(1,5)],240)
ticket('54','BQ-9643',B,'2026-09-28',T,D,[['Pressure unit service',6,None,175,1050],['Hose kit rental',1,'day',90,90]],None)
ticket('55','BQ-9644',B,'2026-09-29','N/A',None,pressure(5,175,875),965,unc=['service_date: 2026-09-29 is struck out; the separate dispatch date is 2026-09-04.'])
haul('56','SF-919',S,'2026-09-11',None,[[i,f'{7+i:02}:15','Produced water',60,'Pelmora recovery bay'] for i in range(1,5)],240)
ticket('57','BQ-9645',B,'2026-09-30',T,D,[['Pressure unit service',6,None,175,1050],['Hose kit rental',1,'day',90,90]],None)
invoice('58','BQI-642',B,'2026-09-16',None,T,[['BQ-9644','Field service bundle',1,'each',965,965],['BQ-9645','Field service bundle',1,'each',1140,1140]],2105,0,None)
O='Darsenne Basin Operations LLC'; U='Ultraven Fold Interests LLC'
def cover(prefix,date,afe,well,due,wi,net):
 put(prefix,'afe_cover',dict(letter_date=date,operator_name=O,addressee=U,afe_number=afe,well_name=well,response_due_date=due,wi_decimal_stated=wi,net_share_stated=net))
COST=[[1,710,'Site preparation','intangible',4000],[2,720,'Pressure service','intangible',6000],[3,730,'Fluid handling','intangible',3000],[4,810,'Valve assembly','tangible',5000],[5,820,'Gauge package','tangible',2000],[6,830,'Spare seals','tangible',0]]
def afe(prefix,num,well,api,date,total,rows,unc=None):
 fields=['line_no','account_code','description','category','amount']
 po={'total_estimate':2}
 po.update({f'cost_lines[{i}].{k}':2 for i in range(3,len(rows)) for k in fields if rows[i][fields.index(k)] is not None})
 put(prefix,'afe',dict(afe_number=num,operator_name=O,well_name=well,api_number=api,county='Lumereth',state='TX',afe_date=date,afe_type='Workover',total_estimate=total,cost_lines=[dict(zip(fields,r)) for r in rows]),unc,po)
cover('59','2026-09-01',D,T,'2026-09-12',.2,4000)
afe('60',D,T,'00-000-00701','2026-09-01',20000,COST)
cover('61','2026-09-02','DB-26-902','Ostrand 4-KH','TBD',.2,4000)
afe('62','DB-26-902','Ostrand 4-KH',None,'2026-09-02',20000,COST)
cover('63','2026-09-03','DB-26-903','Ostrand 4-KH','2026-09-12',.2,4000)
afe('64','DB-26-903','Ostrand 4-KH','00-000-00703','2026-09-03',20000,COST)
cover('65','2026-09-04','DB-26-904','Ostrand 4-KH','TBD',.2,4000)
afe('66','DB-26-904','Ostrand 4-KH',None,'2026-09-04',20000,COST)
def jib(prefix,prop,well,owner_num,wi,rows,gross,net,due,unc=None):
 fields=['line_no','afe_ref','account_code','description','gross','owner_decimal','net']
 po={k:2 for k,x in [('gross_total',gross),('net_total',net),('due_date',due)] if x is not None}
 po.update({f'lines[{i}].{k}':2 for i in range(4,len(rows)) for k in fields if rows[i][fields.index(k)] is not None})
 put(prefix,'jib_statement',dict(statement_period='September 2026',operator_name=O,property_number=prop,well_name=well,owner_name=U,owner_number=owner_num,wi_decimal=wi,gross_total=gross,net_total=net,due_date=due,lines=[dict(zip(fields,r)) for r in rows]),unc,po)
J=[[1,D,710,'Site preparation',1200,.2,240],[2,D,720,'Pressure service',1800,.2,360],[3,D,730,'Fluid handling',2400,.2,480],[4,D,810,'Valve assembly',900,.2,180],[5,D,820,'Gauge package',700,.2,140],[6,D,720,'Pressure service',500,.2,100],[7,D,810,'Valve assembly',650,.2,130],[8,D,730,'Fluid handling',850,.2,170]]
j1=[r.copy() for r in J]; j1[1][5:]=[.24,432]; j1[5][1]=None; j1[6][1]='DB-26-902'
jib('67','DS-8093',T,'UF-306',.2,j1,9000,1872,'2026-10-25')
jib('68','DS-8094',T,'UF-306',.2,J,9000,1800,'2026-10-25')
jib('69','DS-8095',T,'UF-306',.2,J,9000,1800,'2026-10-25')
jib('70','DS-8096',T,'UF-306',.2,J,9000,1800,'2026-10-25')
jib('71','DS-8097',T,'UF-306',.2,J,9000,1800,'2026-10-25')
(OUT/'pages.json').write_text(json.dumps(PAGES,indent=2)+'\n')
