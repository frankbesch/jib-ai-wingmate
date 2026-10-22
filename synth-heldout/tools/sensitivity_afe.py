#!/usr/bin/env python3
"""Two DERIVED reads of H2 around the T10 trap (AFE number printed under "Ref"). Neither is a gate.
Run from the repo root:  python3 synth-heldout/tools/sensitivity_afe.py > /tmp/sens.json
  removal: every afe_number unit (57 per set) dropped from every run.
  rekey:   the 29 trap units per set (traps.json, T10 with afe_number) scored as "not printed":
           a correct unit becomes wrong, a wrong unit becomes correct, an abstain stays an abstain."""
import json, glob, sys, statistics
sys.path.insert(0, 'typed'); sys.path.insert(0, '.')
import typed_questions as tq
def st(path):
    calls = [json.loads(l) for l in open(path + '/calls.jsonl')]
    if any(c.get('kind') == 'unit' for c in calls):
        flat = [dict(node=c['node'], subject=c['subject'], **c['score']) for c in calls if c.get('kind') == 'unit']
    else: flat = tq.flatten(calls)
    return {(u['node'], u['subject']): ('error' if u.get('error') else 'abstain' if u.get('abstain') else 'correct' if u.get('correct') else 'wrong') for u in flat}
traps = json.load(open('synth-heldout/traps.json'))['traps']
trap = {x['doc_id'] + '.afe_number' for x in traps if x.get('trap_id') == 'T10' and 'afe_number' in (x.get('fields') or [])}
flip = {'correct': 'wrong', 'wrong': 'correct'}
out = {'trap_units_per_set': len(trap), 'trap_units': sorted(trap)}
for s in ('clean', 'scan'):
    runs = sorted(glob.glob(f'runs/live-heldout-{s}-01/typed/redo-*')); d = {r.split('/')[-1]: st(r) for r in runs}
    isafe = lambda u: u[0] == 'row8' and u[1].endswith('.afe_number'); intrap = lambda u: u[0] == 'row8' and u[1] in trap
    per = {}
    for k, v in d.items():
        per[k] = dict(wrong_as_scored=sum(1 for x in v.values() if x == 'wrong'),
                      wrong_without_afe_number=sum(1 for u, x in v.items() if x == 'wrong' and not isafe(u)),
                      wrong_rekeyed=sum(1 for u, x in v.items() if (flip.get(x, x) if intrap(u) else x) == 'wrong'),
                      trap_not_correct=sum(1 for u, x in v.items() if intrap(u) and x != 'correct'),
                      trap_abstain=sum(1 for u, x in v.items() if intrap(u) and x == 'abstain'),
                      trap_wrong=sum(1 for u, x in v.items() if intrap(u) and x == 'wrong'))
    res = {'per_run': per}
    for key in ('wrong_without_afe_number', 'wrong_rekeyed'):
        A = [v[key] for k, v in per.items() if 'claude' in k]; C = [v[key] for k, v in per.items() if 'cascade' in k]
        mark = statistics.mean(A) + 5
        res[key] = dict(A=A, C=C, mark=mark, H2_holds=all(c <= mark for c in C))
    out[s] = res
print(json.dumps(out, indent=1))
