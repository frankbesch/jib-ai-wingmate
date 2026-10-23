#!/usr/bin/env python3
"""Pilot gates (plan §2, spec 05 §1) from the redo runs of one set. Read-only; prints JSON."""
import json, glob, os, sys, statistics
run = sys.argv[1]  # e.g. runs/live-pilot-scan-01
def load(p): return [json.loads(l) for l in open(p)]
def units(path):
    sys.path.insert(0, 'typed'); sys.path.insert(0, '.')
    import typed_questions as tq
    calls = load(path + '/calls.jsonl')
    if any(c.get('kind') == 'unit' for c in calls):          # cascade: unit records carry the score
        flat = [dict(node=c['node'], subject=c['subject'], **c['score']) for c in calls if c.get('kind') == 'unit']
    else:
        flat = tq.flatten(calls)
    return {(u['node'], u['subject']): ('error' if u.get('error') else 'abstain' if u.get('abstain') else 'correct' if u.get('correct') else 'wrong') for u in flat}
def rep(path): return json.load(open(path + '/report.json'))
A = sorted(glob.glob(run + '/typed/redo-claude-*-r?')); B = sorted(glob.glob(run + '/typed/redo-jev-*')); C = sorted(glob.glob(run + '/typed/redo-cascade-*'))
res = {'set': run, 'arms': {}}
for name, paths in (('A', A), ('B', B), ('C', C)):
    for p in paths:
        r = rep(p); n8 = r['nodes']['row8']
        res['arms'][os.path.basename(p)] = dict(arm=name, calls=r['calls'], errors=r['errors'],
            row8=dict(scored=n8['scored'], correct=n8['correct'], abstain=n8['abstain'], wrong=n8['wrong_not_abstained'],
                      pct_correct=round(100 * n8['correct'] / n8['scored'], 1), not_correct=n8['scored'] - n8['correct']),
            person=sum(v['abstain'] for v in r['nodes'].values()) + sum(v.get('error', 0) for v in r['nodes'].values()),
            wrong_total=sum(v['wrong_not_abstained'] for v in r['nodes'].values()),
            claude_calls=(r.get('cascade') or {}).get('claude_calls', r['calls'] if name == 'A' else 0))
# P1..P3 on arm A
a8 = [v['row8'] for v in res['arms'].values() if v['arm'] == 'A']
res['P1_below_ceiling_le90_both'] = all(x['pct_correct'] <= 90 for x in a8) if a8 else None
res['P2_stable_misses_ge8_both'] = all(x['not_correct'] >= 8 for x in a8) if a8 else None
res['P3_not_broken_ge60'] = all(x['pct_correct'] >= 60 for x in a8) if a8 else None
# discordant units A(r1) vs B
if A and B:
    ua, ub = units(A[0]), units(B[0])
    disc = [k for k in ua if k in ub and (ua[k] == 'correct') != (ub[k] == 'correct')]
    fields = {}
    for k in disc: fields[k[1].split('.')[-1] if k[0] == 'row8' else k[0]] = fields.get(k[1].split('.')[-1] if k[0] == 'row8' else k[0], 0) + 1
    res['discordant_A_vs_B'] = dict(count=len(disc), by_field=fields, gate_pilot_ge3=len(disc) >= 3)
# H2..H4 dry read (pilot only): C vs mean of A
if A and C:
    am_w = statistics.mean(v['wrong_total'] for v in res['arms'].values() if v['arm'] == 'A')
    am_p = statistics.mean(v['person'] for v in res['arms'].values() if v['arm'] == 'A')
    am_c = statistics.mean(v['claude_calls'] for v in res['arms'].values() if v['arm'] == 'A')
    for k, v in res['arms'].items():
        if v['arm'] == 'C':
            res['H_dry_read_' + k] = dict(H2_wrong=f"{v['wrong_total']} vs A mean {am_w} (+5 allowed)", H2=v['wrong_total'] <= am_w + 5,
                H3_person=f"{v['person']} vs A mean {am_p} (+10 allowed)", H3=v['person'] <= am_p + 10,
                H4_claude_calls=f"{v['claude_calls']} vs 50% of {am_c}", H4=v['claude_calls'] <= 0.5 * am_c)
print(json.dumps(res, indent=1))
