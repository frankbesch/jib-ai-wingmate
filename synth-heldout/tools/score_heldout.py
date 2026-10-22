#!/usr/bin/env python3
"""Held-out gates (plan reviews/2026-09-30-pulse-typed-redo-plan.md section 2) from the redo runs of one or two
sets. Generalises synth-pilot/score_pilot.py. Read-only; prints JSON; exits 0 whatever the verdicts.

Arm runs under runs/<id>/typed/: A = redo-claude-*-r?, B = redo-jev-*, C = redo-cascade-* (sorted by name).
  arms       per-arm-run rows, same fields and arithmetic as score_pilot.py.
  discordant A r1 against each B repeat: a unit whose correct / not-correct status differs; count and by_field
             per repeat, min / max / mean of the counts, and the union over repeats with its by_field.
  H1         every B repeat has >= 10 discordant units and more than one field name.
  H2..H4     per C repeat against the mean of the A repeats: wrong-not-abstained <= mean(A) + 5;
             person-reviews <= mean(A) + 10; Claude calls <= 50% of mean(A) Claude calls.
             A set is SUPPORTED on Hn only if every C repeat present holds (planned: 2; the rule reads over
             the repeats present and the output says how many there were).
  pulse_dropped / extract_invented from report.json (A r1; `consistent` says whether every arm run agrees).
  --audit <answers.json> --changed <n>: per --run, in order; reports items answered / printed and the count
             of changed-truth units.
Two --run: both sets plus `overall`: goal SUPPORTED only if H2, H3, H4 hold in every C repeat on both sets.

Usage: score_heldout.py --run runs/<id> [--run runs/<id>] [--audit answers.json --changed N ...]
"""
import argparse, glob, json, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(DEMO, 'typed')); sys.path.insert(0, DEMO)
import typed_questions as tq  # noqa: E402

PLANNED = dict(A=2, B=3, C=2)
V = {True: 'SUPPORTED', False: 'NOT SUPPORTED'}


def load(p):
    return [json.loads(l) for l in open(p)]


def unit_records(path):
    """Flat scored units of one arm run; cascade unit records carry the score (layered like flatten)."""
    calls = load(path + '/calls.jsonl')
    if any(c.get('kind') == 'unit' for c in calls):
        return [tq._layers(dict(node=c['node'], subject=c['subject'], **c['score']), c.get('label_a'), c.get('label'))
                for c in calls if c.get('kind') == 'unit']
    return tq.flatten(calls)


def status(u):
    return 'error' if u.get('error') else 'abstain' if u.get('abstain') else 'correct' if u.get('correct') else 'wrong'


def units(path):
    return {(u['node'], u['subject']): status(u) for u in unit_records(path)}


def field_of(k):
    return k[1].split('.')[-1] if k[0] == 'row8' else k[0]


def arm_runs(run):
    return (sorted(glob.glob(run + '/typed/redo-claude-*-r?')), sorted(glob.glob(run + '/typed/redo-jev-*')),
            sorted(glob.glob(run + '/typed/redo-cascade-*')))


def rep(path):
    return json.load(open(path + '/report.json'))


def discordant(ua, ub):
    disc = [k for k in ua if k in ub and (ua[k] == 'correct') != (ub[k] == 'correct')]
    by = {}
    for k in disc:
        by[field_of(k)] = by.get(field_of(k), 0) + 1
    return disc, by


def score_set(run, audit=None, changed=None):
    A, B, C = arm_runs(run)
    res = {'set': run, 'repeats_present': dict(A=len(A), B=len(B), C=len(C)), 'repeats_planned': PLANNED, 'arms': {}}
    for name, paths in (('A', A), ('B', B), ('C', C)):
        for p in paths:
            r = rep(p); n8 = r['nodes']['row8']
            res['arms'][os.path.basename(p)] = dict(arm=name, calls=r['calls'], errors=r['errors'],
                row8=dict(scored=n8['scored'], correct=n8['correct'], abstain=n8['abstain'], wrong=n8['wrong_not_abstained'],
                          pct_correct=round(100 * n8['correct'] / n8['scored'], 1), not_correct=n8['scored'] - n8['correct']),
                person=sum(v['abstain'] for v in r['nodes'].values()) + sum(v.get('error', 0) for v in r['nodes'].values()),
                wrong_total=sum(v['wrong_not_abstained'] for v in r['nodes'].values()),
                claude_calls=(r.get('cascade') or {}).get('claude_calls', r['calls'] if name == 'A' else 0))
    rows = res['arms'].values()
    # discordant: A r1 against each B repeat
    if A and B:
        ua = units(A[0])
        per, union = {}, set()
        for b in B:
            disc, by = discordant(ua, units(b))
            per[os.path.basename(b)] = dict(count=len(disc), by_field=by)
            union |= set(disc)
        counts = [v['count'] for v in per.values()]
        uby = {}
        for k in sorted(union):
            uby[field_of(k)] = uby.get(field_of(k), 0) + 1
        res['discordant_A_vs_B'] = dict(a_run=os.path.basename(A[0]), per_B=per, min=min(counts), max=max(counts),
                                        mean=round(statistics.mean(counts), 2), union=dict(count=len(union), by_field=uby))
        h1 = all(v['count'] >= 10 and len(v['by_field']) > 1 for v in per.values())
        res['H1'] = dict(rule='every B repeat: >= 10 discordant A(r1)-vs-B units, more than one field name',
                         per_B={k: f"{v['count']} units on {len(v['by_field'])} field names" for k, v in per.items()},
                         verdict=V[h1])
    # H2..H4: each C repeat against the mean of the A repeats
    if A and C:
        am_w = statistics.mean(v['wrong_total'] for v in rows if v['arm'] == 'A')
        am_p = statistics.mean(v['person'] for v in rows if v['arm'] == 'A')
        am_c = statistics.mean(v['claude_calls'] for v in rows if v['arm'] == 'A')
        per_c, ok = {}, dict(H2=True, H3=True, H4=True)
        for k, v in res['arms'].items():
            if v['arm'] != 'C':
                continue
            h = dict(H2=v['wrong_total'] <= am_w + 5, H3=v['person'] <= am_p + 10, H4=v['claude_calls'] <= 0.5 * am_c)
            per_c[k] = dict(
                H2=dict(read=f"wrong-not-abstained {v['wrong_total']} vs A mean {am_w} + 5 = {am_w + 5}", verdict=V[h['H2']]),
                H3=dict(read=f"person-reviews {v['person']} vs A mean {am_p} + 10 = {am_p + 10}", verdict=V[h['H3']]),
                H4=dict(read=f"Claude calls {v['claude_calls']} vs 50% of A mean {am_c} = {0.5 * am_c}", verdict=V[h['H4']]))
            for n in ok:
                ok[n] = ok[n] and h[n]
        res['H_per_C'] = per_c
        note = f"rule reads over the {len(C)} C repeat(s) present (planned {PLANNED['C']})"
        for n in ('H2', 'H3', 'H4'):
            res[n] = dict(verdict=V[ok[n]], note=note)
    # Pulse-dropped / extract-invented (depend on truth only; every arm run should agree)
    lists = [(tuple(rep(p).get('pulse_dropped') or []), tuple(rep(p).get('extract_invented') or [])) for p in A + B + C]
    if lists:
        pd, ei = lists[0]
        res['pulse_dropped'] = dict(count=len(pd), units=list(pd), consistent=all(x == lists[0] for x in lists))
        res['extract_invented'] = dict(count=len(ei), units=list(ei), consistent=all(x == lists[0] for x in lists))
    if audit:
        ans = json.load(open(audit))
        res['audit'] = dict(file=audit, answered=len(ans), printed=sum(1 for x in ans if x.get('printed') is True),
                            not_printed=sum(1 for x in ans if x.get('printed') is False),
                            changed_truth_units=changed)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--run', action='append', required=True)
    ap.add_argument('--audit', action='append', default=[], help='answers.json, one per --run, in order')
    ap.add_argument('--changed', action='append', type=int, default=[], help='changed-truth units, one per --audit')
    a = ap.parse_args()
    if a.audit and (len(a.audit) != len(a.run) or len(a.changed) != len(a.audit)):
        raise SystemExit('give one --audit and one --changed per --run, in the same order')
    sets = [score_set(r, a.audit[i] if a.audit else None, a.changed[i] if a.changed else None) for i, r in enumerate(a.run)]
    if len(sets) == 1:
        print(json.dumps(sets[0], indent=1))
        return
    held = all(s.get(n, {}).get('verdict') == 'SUPPORTED' for s in sets for n in ('H2', 'H3', 'H4'))
    overall = dict(rule='goal SUPPORTED only if H2, H3, H4 hold in every C repeat on every set',
                   c_repeats={s['set']: s['repeats_present']['C'] for s in sets},
                   per_set={s['set']: {n: s.get(n, {}).get('verdict') for n in ('H1', 'H2', 'H3', 'H4')} for s in sets},
                   verdict=V[held])
    print(json.dumps(dict(sets=sets, overall=overall), indent=1))


if __name__ == '__main__':
    main()
