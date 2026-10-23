from pathlib import Path
from PIL import Image,ImageDraw
import json
root=Path(__file__).resolve().parents[1]
m=json.loads((root/'manifest.json').read_text())
pages=[(d['doc_id'],p) for d in m['documents'] for p in range(1,d['page_count']+1)]
out=root/'audit/review';out.mkdir(exist_ok=True)
for i in range(0,len(pages),2):
 canvas=Image.new('RGB',(1700,1130),'#dde3e7');draw=ImageDraw.Draw(canvas)
 for j,(doc,p) in enumerate(pages[i:i+2]):
  im=Image.open(root/'audit/rendered'/f'{doc}-{p}-scan.jpg').convert('RGB').resize((850,1100))
  canvas.paste(im,(850*j,30));draw.text((850*j+10,8),f'{doc} / page {p}',fill='black')
 canvas.save(out/f'{i//2+1:02d}.jpg',quality=92)
(root/'audit/review/index.json').write_text(json.dumps(pages,indent=2)+'\n')
