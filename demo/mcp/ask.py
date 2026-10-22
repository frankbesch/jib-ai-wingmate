#!/usr/bin/env python3
"""Deterministic analyst fallback: answer questions from stored schema output with citations. No model, no key.

  python3 mcp/ask.py --run runs/fixture-clean-01 --permit 918133 "api number"
  python3 mcp/ask.py --run runs/fixture-clean-01 --permit 918133 "mud weight"     → not in this document
"""
import argparse, json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
GLOSS = {
    'api': ['api_number'], 'operator': ['operator_name', 'operator_number'], 'lease': ['lease_name', 'lease_perpendiculars'],
    'well number': ['well_number'], 'county': ['county'], 'district': ['district'], 'depth': ['total_depth', 'fields'],
    'field': ['fields'], 'completion': ['fields'], 'lease line': ['lease_perpendiculars'], 'survey line': ['survey_perpendiculars'],
    'town': ['nearest_town', 'miles_from_town', 'direction_from_town'], 'purpose': ['purpose_of_filing'], 'profile': ['wellbore_profile'],
    'horizontal': ['wellbore_profile'], 'acres': ['contiguous_acres'], 'abstract': ['abstract_number'], 'filer': ['filer_name', 'date_submitted'],
    'h2s': ['rule_36_h2s'], 'status': ['permit_status'], 'permit': ['permit_number'],
}
OUT_OF_SCOPE = {'mud': 'mud weight is a drilling-report field; a W-1 permit does not carry it', 'logging': 'logging company is a well-log header field; not on a W-1',
                'casing': 'casing detail lives on the W-2/G-1 completion report, not the permit', 'curve': 'curve digitization is out of scope; the log vendor owns it',
                'las': 'LAS output is out of scope for this pipeline', 'p&id': 'P&ID connectivity is out of scope'}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--run', required=True); ap.add_argument('--permit', required=True); ap.add_argument('question')
    a = ap.parse_args()
    rd = pathlib.Path(a.run); rd = rd if rd.is_absolute() else ROOT / rd
    rec = json.loads((rd / f'{a.permit}.json').read_text())
    if rec.get('synthetic'):
        print('[SYNTHETIC FIXTURE — values are not Pulse output]')
    q = a.question.lower()
    for k, msg in OUT_OF_SCOPE.items():
        if k in q:
            print(f'Not in this document: {msg}. Route to the reviewer queue if a person should look.'); return
    keys = []
    for g, ks in GLOSS.items():
        if g in q:
            keys += [k for k in ks if k not in keys]
    if not keys:
        print('I can answer only from extracted, cited fields. Ask about: ' + ', '.join(sorted(GLOSS))); return
    vals = rec['schema_w1']['values']; cites = rec['schema_w1'].get('citations', {})
    for k in keys:
        v = vals.get(k)
        if v in (None, '', []):
            print(f'{k}: not in this document (null) → reviewer queue'); continue
        if k == 'fields':
            for i, row in enumerate(v):
                print(f"fields[{i}]: {row.get('field_name')} ({row.get('field_number')}) {row.get('well_type')} completion depth {row.get('completion_depth')} ft  [cite: field table, page {cites.get('fields', {}).get('page', 1)}]")
            continue
        if isinstance(v, dict):
            for kk, vv in v.items():
                c = cites.get(f'{k}.{kk}')
                print(f"{k}.{kk}: {vv}  [cite: page {c['page']}, box {c['bbox']}]" if c else f"{k}.{kk}: {vv}  [no citation returned]")
            continue
        c = cites.get(k)
        print(f"{k}: {v}  [cite: page {c['page']}, box {c['bbox']}]" if c else f"{k}: {v}  [no citation returned → reviewer queue]")


if __name__ == '__main__':
    main()
