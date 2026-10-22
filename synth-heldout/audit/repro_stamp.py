"""Repeat the final continuation-page scan operation without replacing deliverables."""
from pathlib import Path
import ast,math,json,subprocess,hashlib
from pypdf import PdfReader,PdfWriter
from pypdf.generic import NameObject,DictionaryObject,NumberObject,DecodedStreamObject
from PIL import Image
root=Path(__file__).resolve().parents[1]
s=ast.parse((root/'src/build.py').read_text())
ns={'PdfReader':PdfReader,'PdfWriter':PdfWriter,'Path':Path,'Image':Image,'math':math,'NameObject':NameObject,'DictionaryObject':DictionaryObject,'NumberObject':NumberObject,'DecodedStreamObject':DecodedStreamObject}
for name in ['stamp_location','image_pdf','merge']:
 n=next(n for n in s.body if isinstance(n,ast.FunctionDef) and n.name==name)
 exec(compile(ast.Module(body=[n],type_ignores=[]),name,'exec'),ns)
m=json.loads((root/'manifest.json').read_text());d=next(d for d in m['documents'] if d['doc_id']=='jib_01');idx=m['documents'].index(d)+1
jpg=root/'audit/repro-jib-page2.jpg';cp=root.parent/d['file'];angle=-2.8
args=['magick',root/'audit/rendered/jib_01-2.png','-colorspace','Gray','-seed',str(931047+idx*10+2),'-attenuate','0.13','+noise','Gaussian','-background','white','-rotate',str(angle),'-gravity','center','-extent','1275x1650','-fill','rgba(60,60,60,0.32)','-stroke','none','-font','Helvetica','-pointsize','27','-gravity','NorthWest','-annotate',ns['stamp_location'](cp,2,angle),'RECEIVED','-fill','white','-draw','rectangle 0,0 20,1650','-draw','rectangle 1257,0 1275,1650','-blur','0x0.22','-sampling-factor','1x1','-quality','59',jpg]
subprocess.run([str(a) for a in args],check=True)
assert jpg.read_bytes()==(root/'audit/rendered/jib_01-2-scan.jpg').read_bytes()
out=root/'audit/repro-jib.pdf';ns['image_pdf']([root/'audit/rendered/jib_01-1-scan.jpg',jpg],out)
assert out.read_bytes()==(root.parent/d['scan_file']).read_bytes()
pkt=next(p for p in m['packets'] if p['packet_id']=='jib_01')
outpkt=root/'audit/repro-jib-packet.pdf';ns['merge']([out],outpkt)
assert outpkt.read_bytes()==(root.parent/pkt['scan_file']).read_bytes()
print('PASS: final jib_01 scan document and packet reproduce byte-for-byte after the continuation stamp fix.')
before=json.loads((root/'audit/rebuild-baseline.json').read_text())
unchanged=0;changed=[]
for collection in ['documents','packets']:
 for a,b in zip(before[collection],m[collection]):
  for f in ['sha256','scan_sha256']:
   if a[f]==b[f]:unchanged+=1
   else:changed.append((b.get('doc_id',b.get('packet_id')),f))
assert unchanged==218 and changed==[('jib_01','scan_sha256'),('jib_01','scan_sha256')],(unchanged,changed)
print('PASS: 218/220 PDF hashes match the preceding full build; only the two corrected jib_01 scan files changed.')
print('PASS: all 110 clean PDFs reproduced byte-for-byte across complete builds.')
print('UNVERIFIED: byte reproducibility across different Chrome, Poppler, ImageMagick, Python, or font versions.')
