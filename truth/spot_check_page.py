#!/usr/bin/env python3
"""Build the thirty-field spot-check page for the synthetic month's truth.

  python3 truth/spot_check_page.py            → truth/synth/spot-check.html

One row per field a person should verify: the keyed value (from truth/synth/*.json, keyed by a non-Claude hand),
the printed row cropped from the clean PDF with the value outlined, and a Matches / Differs toggle. The page keeps
its state in the browser and prints a result block to paste back. Crops come from the PDF text layer
(pdftotext -bbox-layout) so the outline sits on the printed value; a value the text layer cannot place shows the
whole page instead. Everything on the page is synthetic.
"""
import base64, html, io, json, pathlib, re, subprocess

HERE = pathlib.Path(__file__).resolve().parent          # truth/
ROOT = HERE.parent                                        # demo/
SYNTH = ROOT / 'synth' / 'caprock'
TRUTH = HERE / 'synth'
OUT = TRUTH / 'spot-check.html'
DPI = 130

# (doc_id, file, label, field path or printed label, page, printed string to locate, occurrence index)
ROWS = [
    ('jib', '07_jib.pdf', 'JIB line 3 owner decimal (the planted 0.26)', 'lines[2].owner_decimal', 1, '0.260000', 0),
    ('ticket_b', '04_ticket_b.pdf', 'Ticket B line 2 quantity (handwritten)', 'line_items[1].quantity', 1, '240', 0),
    ('afe_cover', '01_afe_cover.pdf', 'Cover letter: net share stated', 'net_share_stated', 1, '121,700.00', 0),
    ('afe_cover', '01_afe_cover.pdf', 'Cover letter: total gross estimate (printed label)', '"TOTAL GROSS ESTIMATE"', 1, '486,800.00', 0),
    ('afe', '02_afe.pdf', 'AFE subtotal, intangible (printed label)', '"Subtotal, intangible"', 1, '405,850.00', 0),
    ('afe', '02_afe.pdf', 'AFE subtotal, tangible (printed label)', '"Subtotal, tangible"', 1, '80,950.00', 0),
    ('afe', '02_afe.pdf', 'AFE total estimate', 'total_estimate', 1, '486,800.00', 0),
    ('ticket_a', '03_ticket_a.pdf', 'Ticket A total', 'total', 1, '2,830.00', 0),
    ('ticket_b', '04_ticket_b.pdf', 'Ticket B total', 'total', 1, '3,285.00', 0),
    ('hauling_log', '05_hauling_log.pdf', 'Hauling log total barrels', 'total_barrels', 1, '590', 0),
    ('invoice', '06_invoice.pdf', 'Invoice subtotal', 'subtotal', 1, '6,115.00', 0),
    ('invoice', '06_invoice.pdf', 'Invoice total', 'total', 1, '6,619.49', 0),
    ('jib', '07_jib.pdf', 'JIB gross total', 'gross_total', 1, '329,570.00', 0),
    ('jib', '07_jib.pdf', 'JIB net total', 'net_total', 1, '83,356.90', 0),
    ('afe_cover', '01_afe_cover.pdf', 'Cover letter: AFE number', 'afe_number', 1, 'AFE-2026-0417', 0),
    ('afe', '02_afe.pdf', 'AFE: AFE number', 'afe_number', 1, 'AFE-2026-0417', 0),
    ('afe', '02_afe.pdf', 'AFE: API number', 'api_number', 1, '42-389-41207', 0),
    ('ticket_a', '03_ticket_a.pdf', 'Ticket A: AFE number', 'afe_number', 1, 'AFE-2026-0417', 0),
    ('ticket_b', '04_ticket_b.pdf', 'Ticket B: AFE number', 'afe_number', 1, 'AFE-2026-0417', 0),
    ('invoice', '06_invoice.pdf', 'Invoice: AFE number', 'afe_number', 1, 'AFE-2026-0417', 0),
    ('jib', '07_jib.pdf', 'JIB: property number', 'property_number', 1, 'TX-04412', 0),
    ('jib', '07_jib.pdf', 'JIB: owner number', 'owner_number', 1, 'OW-10287', 0),
] + [('jib', '07_jib.pdf', f'JIB line {i + 1} AFE reference', f'lines[{i}].afe_ref', 1, 'AFE-2026-0417', i) for i in range(8)]
assert len(ROWS) == 30


def page_words(pdf: pathlib.Path):
    xml = subprocess.run(['pdftotext', '-bbox-layout', str(pdf), '-'], capture_output=True, text=True).stdout
    pages = {}
    for pn, block in enumerate(re.findall(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', xml, re.S), start=1):
        W, H, body = float(block[0]), float(block[1]), block[2]
        words = [(html.unescape(m.group(5)), float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
                 for m in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', body)]
        pages[pn] = (W, H, words)
    return pages


def locate(pages, page, text, occurrence):
    W, H, words = pages[page]
    hits = []
    for cand in (text, '$' + text):  # money on the cover letter prints with a dollar sign
        hits = _hits(words, W, H, cand)
        if len(hits) > occurrence:
            break
    return hits[occurrence] if occurrence < len(hits) else None


def _hits(words, W, H, text):
    toks = text.split()
    hits = []
    for i in range(len(words) - len(toks) + 1):
        if all(words[i + j][0] == toks[j] for j in range(len(toks))):
            span = words[i:i + len(toks)]
            hits.append([min(w[1] for w in span) / W, min(w[2] for w in span) / H, max(w[3] for w in span) / W, max(w[4] for w in span) / H])
    return hits


def render_page(pdf: pathlib.Path, page: int, cache: dict):
    key = (str(pdf), page)
    if key not in cache:
        from PIL import Image
        stem = pathlib.Path('/tmp') / f'spot-{pdf.stem}-p{page}'
        subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-r', str(DPI), '-png', '-singlefile', str(pdf), str(stem)], check=True)
        cache[key] = Image.open(stem.with_suffix('.png')).convert('RGB')
    return cache[key]


def crop_uri(im, box):
    from PIL import ImageDraw
    w, h = im.size
    if box:
        x0, y0, x1, y1 = box
        top, bot = max(0, int((y0 - 0.02) * h)), min(h, int((y1 + 0.02) * h))
        crop = im.crop((int(0.04 * w), top, int(0.96 * w), bot))
        d = ImageDraw.Draw(crop)
        d.rectangle([int(x0 * w) - int(0.04 * w) - 4, int(y0 * h) - top - 4, int(x1 * w) - int(0.04 * w) + 4, int(y1 * h) - top + 4], outline=(181, 93, 67), width=3)
    else:
        crop = im
    buf = io.BytesIO(); crop.save(buf, 'PNG', optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode(), bool(box)


def dig(values, path):
    cur = values
    for part in re.findall(r'[^.\[\]]+|\[\d+\]', path):
        if part.startswith('['):
            cur = cur[int(part[1:-1])]
        else:
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


def main():
    truth = {p.stem: json.loads(p.read_text()) for p in TRUTH.glob('*.json')}
    keyed_by = {d['doc_id']: d.get('keyed_by') for d in truth.values()}
    words_cache, img_cache, rows_html = {}, {}, ''
    placed = 0
    for n, (doc_id, fname, label, path, page, printed, occ) in enumerate(ROWS, start=1):
        pdf = SYNTH / fname
        if str(pdf) not in words_cache:
            words_cache[str(pdf)] = page_words(pdf)
        box = locate(words_cache[str(pdf)], page, printed, occ)
        uri, ok = crop_uri(render_page(pdf, page, img_cache), box)
        placed += ok
        keyed = dig(truth[doc_id]['values'], path) if not path.startswith('"') else None
        keyed_txt = 'not a schema field; check the printed figure' if keyed is None else (f'{keyed:,.2f}' if isinstance(keyed, float) and not float(keyed).is_integer() and abs(keyed) >= 100 else (f'{keyed:.6f}' if 'decimal' in path else str(keyed)))
        rows_html += f'''<section class="row" data-n="{n}">
  <div class="meta"><span class="n">{n}</span><div><b>{html.escape(label)}</b><div class="small">{html.escape(doc_id)} · p{page} · <code>{html.escape(path)}</code></div>
  <div class="keyed">keyed: <b>{html.escape(keyed_txt)}</b> · expect on paper: <b>{html.escape(printed)}</b></div></div>
  <div class="btns"><button class="ok" data-v="match">Matches</button><button class="bad" data-v="differs">Differs</button><span class="state"></span></div></div>
  <img src="{uri}" alt="row {n}" loading="lazy">{'' if ok else '<div class="small warn">value not placed by the text layer; the whole page is shown</div>'}
</section>'''
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Thirty-field spot check — Caprock month (synthetic)</title>
<style>
:root{{--paper:#F7F5F2;--card:#fff;--ink:#2F3437;--slate:#67727A;--rule:#D7D2CB;--moss:#5F7A61;--terra:#B55D43;--ochre:#C8923B;--navy:#50687A}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,"Avenir Next","Helvetica Neue",Arial,sans-serif;font-size:14.5px;line-height:1.45}}
header{{position:sticky;top:0;background:var(--paper);border-bottom:1px solid var(--rule);padding:10px 18px;display:flex;gap:14px;align-items:center;flex-wrap:wrap;z-index:2}}
h1{{font-size:16px;margin:0}} .kicker{{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--ochre);font-weight:600}}
.banner{{background:var(--ochre);color:#2F3437;padding:3px 10px;border-radius:4px;font-weight:600;font-size:12.5px}}
main{{max-width:1080px;margin:0 auto;padding:14px 18px 60px}}
.row{{background:var(--card);border:1px solid var(--rule);border-radius:8px;padding:12px 14px;margin:10px 0}}
.row.match{{border-color:var(--moss);box-shadow:inset 4px 0 0 var(--moss)}} .row.differs{{border-color:var(--terra);box-shadow:inset 4px 0 0 var(--terra)}}
.meta{{display:flex;gap:12px;align-items:flex-start;flex-wrap:wrap}} .n{{display:inline-block;min-width:26px;height:26px;border-radius:50%;background:var(--navy);color:#fff;text-align:center;line-height:26px;font-weight:600}}
.meta>div:nth-child(2){{flex:1;min-width:260px}} .small{{font-size:12.5px;color:var(--slate)}} .keyed{{margin-top:4px}}
.btns{{display:flex;gap:6px;align-items:center}} button{{font:inherit;padding:6px 12px;border:1px solid var(--rule);background:#fff;border-radius:6px;cursor:pointer}}
button.ok:hover{{border-color:var(--moss)}} button.bad:hover{{border-color:var(--terra)}} .state{{font-size:12.5px;color:var(--slate);min-width:60px}}
img{{display:block;max-width:100%;border:1px solid var(--rule);border-radius:4px;margin-top:10px}}
.warn{{color:var(--terra)}} code{{font-size:12px}}
#out{{width:100%;min-height:120px;font:12.5px Menlo,monospace;margin-top:8px}}
footer{{font-size:12px;color:var(--slate);padding:10px 18px;border-top:1px solid var(--rule)}}
</style></head><body>
<header><div><div class="kicker">Pulse × operator's month · truth spot check</div><h1>Thirty fields, one screen</h1></div>
<span class="banner">SYNTHETIC DOCUMENTS</span><span class="spacer" style="flex:1"></span>
<span id="progress" class="small"></span><button id="copy">Copy results</button><button id="reset" class="small">Reset</button></header>
<main>
<p class="small">Each row shows the value keyed by a non-Claude hand ({html.escape(keyed_by.get('jib') or '')}) beside the printed row from the clean PDF with the value outlined. Press <b>Matches</b> when the paper shows the keyed value, <b>Differs</b> when it does not. State is kept in this browser. When all thirty are marked, press <b>Copy results</b> and paste the block into the chat.</p>
{rows_html}
<h2 style="font-size:15px">Results</h2><textarea id="out" readonly placeholder="Press Copy results when the thirty rows are marked."></textarea>
</main>
<footer>Built from truth/synth/*.json and synth/caprock/*.pdf · {placed} of 30 values placed by the text layer · Synthetic demonstration documents — not actual records</footer>
<script>
const KEY='caprock-spot-check-v1'; let state={{}}; try{{state=JSON.parse(localStorage.getItem(KEY)||'{{}}')}}catch(e){{state={{}}}}
const rows=[...document.querySelectorAll('.row')];
function paint(){{ let m=0,d=0; rows.forEach(r=>{{const v=state[r.dataset.n]; r.classList.toggle('match',v==='match'); r.classList.toggle('differs',v==='differs'); r.querySelector('.state').textContent=v||''; if(v==='match')m++; if(v==='differs')d++;}});
  document.getElementById('progress').textContent=`${{m+d}}/30 marked · ${{m}} match · ${{d}} differ`; }}
rows.forEach(r=>r.querySelectorAll('button[data-v]').forEach(b=>b.onclick=()=>{{state[r.dataset.n]=b.dataset.v; try{{localStorage.setItem(KEY,JSON.stringify(state))}}catch(e){{}} paint();}}));
document.getElementById('reset').onclick=()=>{{ if(!confirm('Clear all thirty marks?'))return; state={{}}; try{{localStorage.removeItem(KEY)}}catch(e){{}} paint(); document.getElementById('out').value=''; }};
document.getElementById('copy').onclick=async()=>{{ const lines=rows.map(r=>{{const lab=r.querySelector('b').textContent; const v=state[r.dataset.n]||'unmarked'; return `${{r.dataset.n}}. ${{v.toUpperCase()}} — ${{lab}}`;}});
  const m=Object.values(state).filter(v=>v==='match').length, d=Object.values(state).filter(v=>v==='differs').length;
  const txt=`SPOT CHECK — Caprock month truth (synthetic) — ${{new Date().toISOString().slice(0,16)}}Z\\nchecked by: (type your name here)\\n${{m}} match · ${{d}} differ · ${{30-m-d}} unmarked\\n`+lines.join('\\n');
  document.getElementById('out').value=txt; try{{await navigator.clipboard.writeText(txt); document.getElementById('progress').textContent+=' · copied';}}catch(e){{}} }};
paint();
</script></body></html>'''
    OUT.write_text(page)
    print(f'spot-check page written: {OUT} ({len(page) / 1e6:.1f} MB, {placed}/30 values placed)')


if __name__ == '__main__':
    main()
