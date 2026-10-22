#!/usr/bin/env python3
"""Reviewer stub: page image + citation overlays + named-approver decisions → append-only audit trail.

Pulse ships no human-review product (docs, 2026-09-01). In a PoC the SE builds this stub from the raw material
Pulse does return (citations, word boxes, failed pages, table confidence) and hands it to the FDE.

  python3 reviewer/serve.py --run runs/fixture-clean-01 [--port 8765]
  open http://127.0.0.1:8765/

Decisions land in audit/decisions.jsonl with UTC time, approver (typed by the human, never defaulted), run id,
permit, field, disposition (approved-as-is | approved-after-edit | routed), value shown, value entered, and a
synthetic flag copied from the run. The approver field is an attestation: the server refuses empty names and
never fills one in.

Two run shapes are served from the same process:

  run.json   RRC permit packets  -> /        field-by-field reviewer (index.html), unchanged.
  month.json JV month record     -> /queue   exception queue (queue.html), three columns by approver role.

The queue reads runs/<id>/exceptions.json, written by reconcile.py. A queue decision also carries
exception_id and approver_role, and the disposition set adds "disputed". The server refuses a decision whose
role does not own the exception ("this exception belongs to supply_chain") and, as before, refuses a blank
approver. No name is ever defaulted, suggested, or remembered.
"""
import argparse, json, pathlib, subprocess, sys, urllib.parse
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
AUDIT = ROOT / 'audit' / 'decisions.jsonl'


def page_png(packet_pdf: pathlib.Path, page: int, cache: pathlib.Path) -> pathlib.Path:
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f'{packet_pdf.stem}-p{page}.png'
    if not out.exists():
        subprocess.run(['pdftoppm', '-r', '90', '-f', str(page), '-l', str(page), '-png', '-singlefile', str(packet_pdf), str(out.with_suffix(''))], check=True)
    return out


ROLES = ('jv_accountant', 'supply_chain', 'field')
DISPOSITIONS = ('approved-as-is', 'approved-after-edit', 'routed', 'disputed')


class H(BaseHTTPRequestHandler):
    run_dir: pathlib.Path = None

    # ---- run-shape helpers -------------------------------------------------
    def month_path(self):
        return self.run_dir / 'month.json'

    def load_month(self):
        return json.loads(self.month_path().read_text())

    def load_exceptions(self):
        p = self.run_dir / 'exceptions.json'
        return json.loads(p.read_text()) if p.exists() else {'exceptions': [], 'clean_lines': [], 'summary': {}}

    def _send(self, code, body, ctype='application/json'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path == '/':
            page = 'index.html' if (self.run_dir / 'run.json').exists() else 'queue.html'
            return self._send(200, (HERE / page).read_text(), 'text/html; charset=utf-8')
        if u.path == '/queue':
            return self._send(200, (HERE / 'queue.html').read_text(), 'text/html; charset=utf-8')
        if u.path == '/api/month':
            if not self.month_path().exists():
                return self._send(404, {'error': 'this run has no month.json'})
            return self._send(200, self.load_month())
        if u.path == '/api/exceptions':
            if not self.month_path().exists():
                return self._send(404, {'error': 'this run has no month.json'})
            return self._send(200, self.load_exceptions())
        if u.path == '/api/run':
            run = json.loads((self.run_dir / 'run.json').read_text())
            recs = [json.loads((self.run_dir / f'{p}.json').read_text()) for p in run['permits']]
            sc = self.run_dir / 'scorecard.json'
            return self._send(200, {'run': run, 'records': recs, 'scorecard': json.loads(sc.read_text()) if sc.exists() else None})
        if u.path == '/api/page':
            page = int(q.get('page', ['1'])[0])
            if 'packet' in q:
                if not self.month_path().exists():
                    return self._send(404, {'error': 'this run has no month.json'})
                pk = (self.load_month().get('packets') or {}).get(q['packet'][0])
                if not pk:
                    return self._send(404, {'error': f'no packet {q["packet"][0]} in this month'})
                pdf = pathlib.Path(pk['file'])
                pdf = pdf if pdf.is_absolute() else ROOT / pdf
                if not pdf.exists():
                    return self._send(404, {'error': f'packet pdf not found: {pdf}'})
                png = page_png(pdf, page, self.run_dir / 'pages')
                return self._send(200, png.read_bytes(), 'image/png')
            permit = q['permit'][0]
            rec = json.loads((self.run_dir / f'{permit}.json').read_text())
            png = page_png(ROOT / rec['packet'], page, self.run_dir / 'pages')
            return self._send(200, png.read_bytes(), 'image/png')
        if u.path == '/api/decisions':
            rows = [json.loads(l) for l in AUDIT.read_text().splitlines()] if AUDIT.exists() else []
            return self._send(200, [r for r in rows if r.get('run_id') == self.run_dir.name])
        return self._send(404, {'error': 'not found'})

    def do_POST(self):
        if self.path != '/api/decision':
            return self._send(404, {'error': 'not found'})
        n = int(self.headers.get('Content-Length', '0')); d = json.loads(self.rfile.read(n) or b'{}')
        approver = (d.get('approver') or '').strip()
        if not approver:
            return self._send(400, {'error': 'approver name required — the human types it; the server never fills it in'})
        if d.get('disposition') not in DISPOSITIONS:
            return self._send(400, {'error': 'disposition must be one of ' + ', '.join(DISPOSITIONS)})

        exception_id = d.get('exception_id')
        role = (d.get('approver_role') or '').strip() or None
        if exception_id:
            hits = [e for e in self.load_exceptions()['exceptions'] if e['id'] == exception_id]
            if not hits:
                return self._send(400, {'error': f'no exception {exception_id} in this run'})
            owner = hits[0]['approver_role']
            if not role:
                return self._send(400, {'error': f'approver_role required — this exception belongs to {owner}'})
            if role != owner:
                return self._send(400, {'error': f'this exception belongs to {owner}'})
        if role and role not in ROLES:
            return self._send(400, {'error': 'approver_role must be one of ' + ', '.join(ROLES)})

        row = {'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'run_id': self.run_dir.name, 'approver': approver,
               'approver_role': role, 'exception_id': exception_id,
               'permit': d.get('permit'), 'field': d.get('field'), 'disposition': d['disposition'],
               'value_shown': d.get('value_shown'), 'value_entered': d.get('value_entered'), 'reason': d.get('reason'),
               'synthetic': bool(d.get('synthetic'))}
        AUDIT.parent.mkdir(exist_ok=True)
        with open(AUDIT, 'a') as f:
            f.write(json.dumps(row) + '\n')
        return self._send(200, row)

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--run', required=True); ap.add_argument('--port', type=int, default=8765)
    a = ap.parse_args()
    rd = pathlib.Path(a.run); rd = rd if rd.is_absolute() else ROOT / rd
    has_run, has_month = (rd / 'run.json').exists(), (rd / 'month.json').exists()
    if not (has_run or has_month):
        sys.exit(f'no run.json or month.json at {rd}')
    H.run_dir = rd
    landing = '/' if has_run else '/queue'
    shape = 'permit packets' if has_run else 'JV month record'
    if has_month and not (rd / 'exceptions.json').exists():
        print(f'note: no exceptions.json yet — run  python3 reconcile.py --run {rd}')
    print(f'reviewer on http://127.0.0.1:{a.port}{landing}  run={rd.name}  shape={shape}  audit={AUDIT}')
    HTTPServer(('127.0.0.1', a.port), H).serve_forever()


if __name__ == '__main__':
    main()
