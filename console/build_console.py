#!/usr/bin/env python3
"""Pack a pipeline run into a single-file demo console.

  python3 console/build_console.py --run runs/fixture-clean-01 [--dpi 80] [--out console/index.html]
  python3 console/build_console.py --run runs/fixture-synth-01 [--dpi 80] [--out console/month.html]

Two consoles, one script. A run directory holding month.json is the synthetic non-operator month: it renders the
ten-step month console from month_template.html into console/month.html. Any other run is the RRC well-file console:
it reads run.json, <permit>.json, scorecard.json (run score.py first) and the corpus manifest, and renders
template.html into console/index.html. Both embed every packet page as a JPEG data URI (pdftoppm + PIL), open from a
file in any browser, need no server, and show the synthetic banner whenever the documents or responses are synthetic.
"""
import argparse, base64, io, json, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent


def page_images(pdf: pathlib.Path, dpi: int, tmp: pathlib.Path):
    from PIL import Image
    tmp.mkdir(parents=True, exist_ok=True)
    stem = tmp / pdf.stem
    for old in tmp.glob(f'{pdf.stem}-*.png'):
        old.unlink()
    subprocess.run(['pdftoppm', '-r', str(dpi), '-png', str(pdf), str(stem)], check=True)
    out = []
    for png in sorted(tmp.glob(f'{pdf.stem}-*.png'), key=lambda p: int(p.stem.rsplit('-', 1)[1])):
        im = Image.open(png).convert('RGB')
        buf = io.BytesIO(); im.save(buf, 'JPEG', quality=68, optimize=True)
        out.append({'w': im.size[0], 'h': im.size[1], 'src': 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()})
    return out


def load(path: pathlib.Path):
    return json.loads(path.read_text()) if path.exists() else None


def render(tpl_name: str, data: dict, out: str):
    tpl = (HERE / tpl_name).read_text()
    blob = json.dumps(data).replace('</script', '<\\/script')
    html = tpl.replace('/*__DATA__*/null', blob)
    pathlib.Path(out).write_text(html)
    return html


def build_month(run_dir: pathlib.Path, dpi: int, out: str):
    """The synthetic non-operator month: three packets, ten steps, month_template.html."""
    month = json.loads((run_dir / 'month.json').read_text())
    manifest = json.loads((ROOT / 'synth/manifest.json').read_text())
    scorecard = load(run_dir / 'scorecard.json') or {}
    exceptions = load(run_dir / 'exceptions.json')
    planted = load(ROOT / 'synth/planted.json') or {}
    handwritten = [{'doc_id': v['doc_id'], 'field_path': v['field_path']}
                   for v in planted.values() if isinstance(v, dict) and v.get('kind') == 'handwriting']
    ref = {k: load(ROOT / p) for k, p in (manifest.get('references') or {}).items()
           if k in ('doi', 'contract_rates', 'afe_election')}
    packets = {}
    for pk, rec in month['packets'].items():
        pdf = ROOT / rec['file']
        print(f'{pk}: rendering {rec["pages"]} pages ...', flush=True)
        entry = next((p for p in manifest['packets'] if p['packet_id'] == pk), {})
        packets[pk] = {'file': rec['file'], 'sha256': entry.get('sha256'), 'pages': page_images(pdf, dpi, HERE / '.pages')}
    data = {'month': month, 'exceptions': exceptions, 'scorecard': scorecard, 'manifest': manifest,
            'reference': ref, 'handwritten': handwritten, 'packets': packets,
            'audit_pack': load(run_dir / 'audit-pack.json'), 'built': manifest.get('built')}
    html = render('month_template.html', data, out)
    if exceptions is None:
        print('note: exceptions.json absent; the reconcile and queue steps will render empty')
    if data['audit_pack'] is None:
        print('note: audit-pack.json absent; step 8 renders from exceptions.json and says so')
    print(f'month console written: {out}  ({len(html)/1e6:.1f} MB, {sum(len(p["pages"]) for p in packets.values())} page images, '
          f'synthetic_documents={month.get("synthetic_documents")}, synthetic_responses={month.get("synthetic_responses")})')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True); ap.add_argument('--dpi', type=int, default=80); ap.add_argument('--out', default=None)
    a = ap.parse_args()
    run_dir = pathlib.Path(a.run); run_dir = run_dir if run_dir.is_absolute() else ROOT / run_dir
    if (run_dir / 'month.json').exists():
        return build_month(run_dir, a.dpi, a.out or str(HERE / 'month.html'))
    a.out = a.out or str(HERE / 'index.html')
    run = json.loads((run_dir / 'run.json').read_text())
    sc_path = run_dir / 'scorecard.json'
    if not sc_path.exists():
        sys.exit('run score.py --run first; the console needs scorecard.json')
    scorecard = json.loads(sc_path.read_text())
    manifest = json.loads((ROOT / 'corpus/manifest.json').read_text())
    packets = []
    for permit in run['permits']:
        rec = json.loads((run_dir / f'{permit}.json').read_text())
        pk = next(p for p in manifest['packets'] if p['permit'] == permit)
        docs = [d for d in manifest['documents'] if d['permit'] == permit]
        truth_split = json.loads((ROOT / pk['split_truth']).read_text())
        pdf = ROOT / rec['packet']
        print(f'{permit}: rendering {pk["pages"]} pages ...', flush=True)
        packets.append({'permit': permit, 'record': rec, 'manifest': pk, 'documents': docs, 'split_truth': truth_split['splits'],
                        'pages': page_images(pdf, a.dpi, HERE / '.pages')})
    data = {'run': run, 'scorecard': scorecard, 'packets': packets, 'built': manifest['built'],
            'sources': manifest['sources'], 'join': manifest.get('join')}
    html = render('template.html', data, a.out)
    print(f'console written: {a.out}  ({len(html)/1e6:.1f} MB, {sum(len(p["pages"]) for p in packets)} page images, synthetic={run.get("synthetic")})')


if __name__ == '__main__':
    main()
