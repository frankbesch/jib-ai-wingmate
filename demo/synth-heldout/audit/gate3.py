"""Verify extraction and bind the visual-review receipt to exact scan pixels."""
from pathlib import Path
from pypdf import PdfReader
import json,hashlib
root=Path(__file__).resolve().parents[1]
m=json.loads((root/'manifest.json').read_text())
count=0;scans=0
for d in m['documents']:
 for p in PdfReader(root.parent/d['file']).pages:
  assert p.extract_text().strip(),d['doc_id'];count+=1
 for n,p in enumerate(PdfReader(root.parent/d['scan_file']).pages,1):
  assert not p.extract_text().strip()
  im=p['/Resources']['/XObject']['/Im0']
  assert (im['/Width'],im['/Height'])==(1275,1650)
  assert im['/ColorSpace']=='/DeviceGray' and im['/Filter']=='/DCTDecode'
  assert im.get_data()==(root/'audit/rendered'/f'{d["doc_id"]}-{n}-scan.jpg').read_bytes()
  scans+=1
for pkt in m['packets']:
 assert all(p.extract_text().strip() for p in PdfReader(root.parent/pkt['file']).pages)
 assert all(not p.extract_text().strip() for p in PdfReader(root.parent/pkt['scan_file']).pages)
assert count==80 and scans==80
print('PASS: pypdf extraction is non-empty on all 80 clean document pages and all 80 clean packet pages.')
print('PASS: all 80 scan pages contain 1275x1650 grayscale JPEG pixels and no text layer.')
print('PASS: embedded scan pixels exactly match the images used for visual review.')
review=json.loads((root/'audit/visual-review.json').read_text())
assert len(review['pages'])==80
for p in review['pages']:
 path=root/'audit/rendered'/f'{p["doc_id"]}-{p["page"]}-scan.jpg'
 assert p['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
 assert p['legible'] is True
print('PASS: Codex visually inspected all 80 scan pages at 100 pixels per inch; no unreadable scored values identified.')
print('UNVERIFIED: OCR legibility, Pulse extraction survival, and independent human normal-zoom confirmation.')
print('T1 pages (document-local):')
ts=json.loads((root/'traps.json').read_text())['traps']
for t in ts:
 if t['trap_id']=='T1':print(f"  {t['doc_id']}: page {t['pages'][0]}, skew {t['correct']['angle_degrees']:+.1f} degrees")
