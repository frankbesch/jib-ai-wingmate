#!/usr/bin/env python3
"""Derive analysis.json for the held-out run (S3.5). Read-only over the artifacts copy.

Usage: python3 analyze_heldout.py <heldout-dir> <runner-logs-dir> <audit-discordant-dir> [--out analysis.json]
Prints the analysis JSON; with --out also writes it.
"""
import collections, json, os, re, statistics, sys

HD, RL, AU = sys.argv[1], sys.argv[2], sys.argv[3]
AUREL = 'synth-heldout/audit-discordant'
OUT = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else None
REL = 'private-artifacts/typed-questions-2026-09-28/live-results/heldout-2026-10-01'
RLREL = 'runs/typed-redo'


def load(p):
    return [json.loads(l) for l in open(p)]


def receipts():
    out = {}
    for stamp in sorted(os.listdir(RL)):
        p = os.path.join(RL, stamp, 'runner.log')
        if not os.path.isfile(p):
            continue
        for line in open(p):
            m = re.search(r'RECEIPT (\d+)-\S+-r(\d+): rc=(\d+) .* wall=(\d+)s out=\S+/(redo-\S+)', line)
            if m:
                out[m.group(5)] = dict(rc=int(m.group(3)), wall_s=int(m.group(4)),
                                       source=f'{RLREL}/{stamp}/runner.log')
    return out


REC = receipts()
res = dict(source_dir=REL, generated_by='scratchpad analyze_heldout.py (S3.5 hands); every value cites its file',
           runs={}, cascade_wrong_sources={}, excluded_runs={})

for s in ('clean', 'scan'):
    runs = sorted(d for d in os.listdir(os.path.join(HD, s)) if d.startswith('redo-'))
    claude_alone = {}
    for r in runs:
        rp = os.path.join(HD, s, r, 'report.json')
        rep = json.load(open(rp))
        n = rep['nodes']
        row = dict(source=f'{REL}/{s}/{r}/report.json', set=s,
                   arm={'claude': 'A', 'jev': 'B', 'cascade': 'C'}[r.split('-')[1]],
                   backend=rep['backend'], calls=rep['calls'], errors=rep['errors'], parity=rep['parity'],
                   served_models=rep['served_models'], model_mismatches=rep['model_mismatches'],
                   jev_model=rep.get('jev_model') or (rep['model_requested'] if 'jev' in rep['backend'] else None),
                   nodes={k: {f: v[f] for f in ('n', 'correct', 'abstain', 'wrong_not_abstained', 'error', 'top_correct')}
                          for k, v in n.items()},
                   wrong_not_abstained_total=sum(v['wrong_not_abstained'] for v in n.values()),
                   top_correct_total=sum(v['top_correct'] for v in n.values()),
                   latency_ms_p50_report=rep['latency_ms_p50'], cost_usd=rep['cost_usd'],
                   wall_s=REC.get(r, {}).get('wall_s'), wall_source=REC.get(r, {}).get('source'))
        recs = load(os.path.join(HD, s, r, 'calls.jsonl'))
        if 'cascade' in r:
            c = rep['cascade']
            row.update(claude_calls=c['claude_calls'], jev_requests=c['jev_requests'], units_to_person=c['units_to_person'],
                       wrong_not_abstained_by=c['wrong_not_abstained_by'], top_correct_by_half=c['top_correct_by_half'],
                       claude_cost_estimate_usd=c['claude_cost_estimate_usd'], jev_billed_usd=c['jev_billed_usd'])
            jl = [x['latency_ms'] for x in recs if x['kind'] == 'jev_request' and x.get('latency_ms') is not None]
            cl = [x['claude']['latency_ms'] for x in recs if x['kind'] == 'unit' and x.get('claude', {}).get('asked')
                  and x['claude'].get('latency_ms') is not None]
            row['served_model_calls'] = dict(collections.Counter(x['claude']['served_model'] for x in recs
                                                                 if x['kind'] == 'unit' and x.get('claude', {}).get('asked')))
            row['latency_ms_p50_derived'] = dict(jev=statistics.median(jl), claude=statistics.median(cl),
                                                 source='calls.jsonl jev_request.latency_ms and unit.claude.latency_ms')
        else:
            if 'claude' in r:
                row['cost_usd_is'] = 'envelope total_cost_usd sum: list-price ESTIMATE, not billed (subscription)'
                claude_alone[r] = {(x['node'], x['subject']): x['score'] for x in recs}
                row['served_model_calls'] = dict(collections.Counter(x['served_model'] for x in recs))
                row['wrong_by_field'] = dict(collections.Counter(x['subject'].split('.')[-1] if x['node'] == 'row8' else x['node']
                                                                 for x in recs if x['score']['wrong_not_abstained']).most_common())
                af = [x for x in recs if x['subject'].endswith('.afe_number')]
                row['afe_number'] = dict(n=len(af), not_correct=sum(not x['score']['correct'] for x in af),
                                         wrong_not_abstained=sum(x['score']['wrong_not_abstained'] for x in af))
        res['runs'][f'{s}/{r}'] = row
    # section (e): where the cascade's wrong answers come from
    audited = {x['id'] for x in json.load(open(os.path.join(AU, s, 'answers', 'answers.json')))}
    a_names = sorted(claude_alone)
    a1 = claude_alone[a_names[0]]
    for r in runs:
        if 'cascade' not in r:
            continue
        units = [x for x in load(os.path.join(HD, s, r, 'calls.jsonl')) if x['kind'] == 'unit']
        rep = res['runs'][f'{s}/{r}']
        kept = [u for u in units if u['answered_by'] == 'jev' and u['score']['wrong_not_abstained']]
        esc_w = [u for u in units if u['answered_by'] == 'claude' and u['score']['wrong_not_abstained']]
        err = [u for u in units if u['score']['error']]
        assert all(u['jev']['p_top'] >= 0.80 and not u['jev']['escalated'] for u in kept)
        key = lambda u: (u['node'], u['subject'])
        ps = [u['jev']['p_top'] for u in kept]
        a1_wrong = sum(1 for u in kept if a1[key(u)]['wrong_not_abstained'])
        both_wrong = sum(1 for u in kept if all(claude_alone[a][key(u)]['wrong_not_abstained'] for a in a_names))
        a1_notcorrect = sum(1 for u in kept if not a1[key(u)]['correct'])
        both_notcorrect = sum(1 for u in kept if all(not claude_alone[a][key(u)]['correct'] for a in a_names))
        a1_correct = sum(1 for u in kept if a1[key(u)]['correct'])
        both_correct = sum(1 for u in kept if all(claude_alone[a][key(u)]['correct'] for a in a_names))
        fld = collections.Counter(u['subject'].split('.')[-1] if u['node'] == 'row8' else u['node'] for u in kept + esc_w)
        # Jev-wrong units that escalated: Jev's thresholded answer would have been wrong-not-abstained
        esc = [u for u in units if u['jev']['escalated']]
        jw_esc = [u for u in esc if u['jev']['decision'] == 'answer' and u['jev']['final'] != u['label']]
        jtop_esc = [u for u in esc if not u['jev']['top_correct']]
        outc = lambda us: dict(correct=sum(u['score']['correct'] for u in us), abstain=sum(u['score']['abstain'] for u in us),
                               wrong=sum(u['score']['wrong_not_abstained'] for u in us), error=sum(u['score']['error'] for u in us))
        # self-check of the Jev-wrong definition on units Jev kept
        nonesc = [u for u in units if not u['jev']['escalated']]
        assert all((u['jev']['decision'] == 'answer' and u['jev']['final'] != u['label']) == u['score']['wrong_not_abstained']
                   for u in nonesc), 'Jev-wrong definition disagrees with score on kept units'
        res['cascade_wrong_sources'][f'{s}/{r}'] = dict(
            source=f'{REL}/{s}/{r}/calls.jsonl (unit records); Claude alone: {", ".join(f"{REL}/{s}/{a}/calls.jsonl" for a in a_names)}',
            wrong_not_abstained_report=rep['wrong_not_abstained_total'],
            kept_wrong_jev=len(kept), escalated_wrong_claude=len(esc_w), error_units=len(err),
            sum_check=len(kept) + len(esc_w) + len(err) == rep['wrong_not_abstained_total'],
            kept_wrong_jev_p_top_min=round(min(ps), 4) if ps else None, kept_wrong_jev_p_top_max=round(max(ps), 4) if ps else None,
            kept_wrong_jev_p_top_ge_0_95=sum(p >= 0.95 for p in ps),
            kept_wrong_by_node=dict(collections.Counter(u['node'] for u in kept)),
            kept_wrong_claude_alone=dict(a_runs=a_names, r1_wrong_not_abstained=a1_wrong, both_wrong_not_abstained=both_wrong,
                                         r1_not_correct=a1_notcorrect, both_not_correct=both_notcorrect,
                                         r1_correct=a1_correct, both_correct=both_correct),
            kept_wrong_in_blind_audit=dict(count=sum(u['subject'] in audited for u in kept),
                                           afe_number_kept_wrong=sum(u['subject'].endswith('.afe_number') for u in kept),
                                           afe_number_in_audit=sum(u['subject'].endswith('.afe_number') and u['subject'] in audited for u in kept),
                                           afe_number_labels=sorted({str(u['label']) for u in kept if u['subject'].endswith('.afe_number')}),
                                           source=f'{AUREL}/{s}/answers/answers.json (item ids)'),
            wrong_by_field=dict(fld.most_common()),
            escalated_wrong_units=[u['subject'] for u in esc_w],
            escalated_units=len(esc),
            jev_wrong_escalated=dict(definition='escalated unit whose Jev thresholded decision was answer and final != label',
                                     count=len(jw_esc), claude_outcome=outc(jw_esc)),
            jev_top_wrong_escalated=dict(definition='escalated unit whose Jev top answer != label (threshold-free)',
                                         count=len(jtop_esc), claude_outcome=outc(jtop_esc)),
        )

# the excluded scan Claude repeat (stopped run): receipt only, its outputs are not in the artifacts copy
for r, v in REC.items():
    if v['rc'] != 0:
        res['excluded_runs'][r] = dict(v, note='stopped run, excluded whole from scoring; rerun whole')

s = json.dumps(res, indent=1, sort_keys=False)
print(s)
if OUT:
    open(OUT, 'w').write(s + '\n')
