#!/usr/bin/env python3
"""F2: measure the Claude API cost per typed-question call (D-228 revisit trigger).

Replays the exact recorded prompts of a Claude-arm run (`live-results/<set>/prompts.jsonl`) through the
Anthropic Messages API, with the same system prompt the `claude -p` arm used, and records the metered
`usage` of every response. Scoring reuses `typed_questions.score`, so accuracy stays comparable.

Why: the `claude -p` envelopes carried about 48k tokens of CLI harness per call (cache_creation
48,625 on a 2k-character prompt), so their `cost_usd` (mean $0.108 per call pooled over the two G5 sets, list price) prices the
harness, not the question. This replay sends the bare question. Its usage is what the API bills.

Modes:
  --mode dry-run    no network (socket guard); loads, checks prompt hashes, prints a byte-bound estimate
  --mode preflight  count_tokens per prompt (free endpoint); prints the worst-case spend; no messages
  --mode live       Frank runs this (D-218) through run-claude-api-cost.sh; stops at --max-usd

Choices, declared before the first live run:
  - No prompt caching: each prompt is one short user turn; a cache would change the per-call price.
  - No server-side fallbacks: a fallback answers on another model at another price, which would
    confound the measurement. A refusal is recorded as an error unit, never retried elsewhere.
  - No `thinking` parameter: Claude Fable 5.1 thinks by default; thinking tokens bill as output.
  - Default model claude-fable-5-1: the arithmetic match for the recorded envelopes (UNVERIFIED as
    the CLI default; the envelopes did not keep a model field).

Prices per million tokens, platform.claude.com/docs/en/about-claude/pricing, fetched 2026-09-29.
The key comes from ANTHROPIC_API_KEY (or an `ant auth login` profile). It is never printed or written.
"""
import argparse, datetime, hashlib, json, pathlib, re, socket, statistics, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from typed_questions import (CLASSES, TOPICS, NEEDS_REVIEW, SYSTEM_PROMPT, ERROR_UNIT,  # noqa: E402
                             Malformed, score, flatten)

ARTIFACTS = pathlib.Path(__file__).resolve().parents[2] / 'artifacts/typed-questions-2026-09-28/live-results'
DEFAULT_SETS = ['g5-row4-collapsed/live-synth-03', 'g5-row4-collapsed/live-synth-scan-01']
PRICES = {  # input, output, cache write 5m, cache write 1h, cache read
    'claude-fable-5-1': (10.00, 50.00, 12.50, 20.00, 0.25),
    'claude-opus-5-5': (4.00, 20.00, 5.00, 8.00, 0.20),
    'claude-sonnet-5-5': (2.00, 10.00, 2.50, 4.00, 0.20),
    'claude-haiku-4-5': (1.00, 5.00, 1.25, 2.00, 0.10),
}
MAX_CONSECUTIVE_ERRORS = 3
SYSTEM_PROMPT_SHA256 = '3a830a83410277ccb04de500043605bbc3582661dd6fc5ab0dd1fc1261d33763'  # as recorded in G5


def usd(model, u):
    p_in, p_out, p_w5, p_w1, p_rd = PRICES[model]
    cc = u.get('cache_creation') or {}
    w5 = cc.get('ephemeral_5m_input_tokens', 0) or 0
    w1 = cc.get('ephemeral_1h_input_tokens', 0) or 0
    if not cc:
        w5 = u.get('cache_creation_input_tokens', 0) or 0
    return ((u.get('input_tokens', 0) or 0) * p_in + (u.get('output_tokens', 0) or 0) * p_out
            + w5 * p_w5 + w1 * p_w1 + (u.get('cache_read_input_tokens', 0) or 0) * p_rd) / 1e6


def load_set(rel):
    d = ARTIFACTS / rel
    prompts = {p['i']: p['prompt'] for p in map(json.loads, open(d / 'prompts.jsonl'))}
    reqs = []
    for c in map(json.loads, open(d / 'calls.jsonl')):
        if c.get('software'):
            continue
        prompt = prompts[c['i']]
        if hashlib.sha256(prompt.encode()).hexdigest() != c['prompt_sha256']:
            sys.exit(f'HASH MISMATCH {rel} i={c["i"]}: prompts.jsonl does not match calls.jsonl')
        r = dict(i=c['i'], node=c['node'], shape=c['shape'], subject=c['subject'], label=c['label'], prompt=prompt,
                 recorded=dict(cost_usd=c.get('cost_usd'), usage=c.get('usage'), correct=_units_correct(c)))
        if r['shape'] == 'choice':
            r['options'] = (CLASSES if r['node'] == 'row1' else TOPICS) + [NEEDS_REVIEW]
            m = re.search(r'Options \(unordered\): (\[.*?\])\n', prompt)
            if not m or set(json.loads(m.group(1))) != set(r['options']):
                sys.exit(f'OPTION MISMATCH {rel} i={c["i"]}: prompt options differ from the runner set')
        if r['shape'] == 'noul-batch':
            r['fields'] = list(r['label'])
        reqs.append(r)
    return reqs


def _units_correct(c):
    s = c.get('score') or {}
    if 'fields' in s:
        return sum(bool(u.get('correct')) for u in s['fields'].values())
    return int(bool(s.get('correct')))


def error_score(r, reason):
    if r['shape'] == 'noul-batch':
        return dict(fields={f: dict(ERROR_UNIT, reason=reason) for f in r['fields']})
    return dict(ERROR_UNIT, reason=reason)


def install_socket_guard():
    def _blocked(*a, **k):
        raise RuntimeError('SOCKET GUARD: dry-run makes zero network calls')
    socket.socket = socket.create_connection = socket.getaddrinfo = _blocked


def ask(client, model, r, max_tokens, effort):
    kw = dict(model=model, max_tokens=max_tokens, system=SYSTEM_PROMPT,
              messages=[{'role': 'user', 'content': r['prompt']}])
    if effort:
        kw['output_config'] = {'effort': effort}
    t0 = time.time()
    resp = client.messages.create(**kw)
    ms = int((time.time() - t0) * 1000)
    u = resp.usage.model_dump(exclude_none=True)
    meta = dict(latency_ms=ms, usage=u, model=resp.model, stop_reason=resp.stop_reason, cost_usd=usd(model, u))
    for k in ('speed', 'service_tier'):
        if u.get(k) not in (None, 'standard'):
            meta['nonstandard_' + k] = u[k]   # usd() prices standard only; flag, never guess
    if resp.stop_reason == 'refusal':
        sd = getattr(resp, 'stop_details', None)
        cat = getattr(sd, 'category', None) if sd else None
        return None, meta, f'refusal ({cat})'
    if resp.stop_reason == 'max_tokens':
        return None, meta, f'max_tokens {max_tokens} reached'
    text = ''.join(b.text for b in resp.content if b.type == 'text').strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    try:
        return json.loads(text), meta, None
    except Exception:
        return None, meta, 'model returned no JSON: ' + text[:200]


def summarize(model, set_name, calls):
    units = flatten(calls)
    live = [c for c in calls if c.get('usage')]
    rec = [c['recorded'] for c in calls]
    mean = lambda xs: (statistics.mean(xs) if xs else None)  # noqa: E731
    return dict(
        set=set_name, model=model, calls=len(calls), units=len(units),
        correct=sum(u['correct'] for u in units), abstain=sum(u['abstain'] for u in units),
        wrong_not_abstained=sum(u['wrong_not_abstained'] for u in units),
        errors=sum(bool(u.get('error')) for u in units),
        mean_input_tokens=mean([c['usage'].get('input_tokens', 0) for c in live]),
        mean_output_tokens=mean([c['usage'].get('output_tokens', 0) for c in live]),
        api_usd_total=sum(c.get('cost_usd') or 0 for c in calls),
        api_usd_per_call=mean([c['cost_usd'] for c in live]),
        latency_ms_p50=(statistics.median([c['latency_ms'] for c in live]) if live else None),
        recorded_cli_usd_per_call=mean([x['cost_usd'] for x in rec if x['cost_usd'] is not None]),
        recorded_units_correct=sum(x['correct'] for x in rec),
        models_seen=sorted({c.get('model') for c in live if c.get('model')}),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--mode', choices=['dry-run', 'preflight', 'live'], default='dry-run')
    ap.add_argument('--sets', nargs='+', default=DEFAULT_SETS, help='dirs under live-results/')
    ap.add_argument('--model', default='claude-fable-5-1', choices=sorted(PRICES))
    ap.add_argument('--max-tokens', type=int, default=4096)
    ap.add_argument('--effort', choices=['low', 'medium', 'high', 'xhigh', 'max'], default=None)
    ap.add_argument('--max-usd', type=float, default=15.0, help='hard stop; also the preflight worst-case gate')
    ap.add_argument('--limit', type=int, default=None, help='first N calls per set (smoke test)')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    if hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest() != SYSTEM_PROMPT_SHA256:
        sys.exit('SYSTEM PROMPT CHANGED since G5: the replay would not be comparable')
    sets = {s: load_set(s)[:a.limit] if a.limit else load_set(s) for s in a.sets}
    n = sum(len(v) for v in sets.values())
    p_in, p_out = PRICES[a.model][:2]
    print(f'PHASE load: {n} calls across {len(sets)} set(s); prompt hashes and option sets verified')

    if a.mode == 'dry-run':
        install_socket_guard()
        in_bound = sum(len((SYSTEM_PROMPT + r['prompt']).encode()) for v in sets.values() for r in v)
        worst = (in_bound * p_in + n * a.max_tokens * p_out) / 1e6
        print(f'DRY-RUN {a.model}: input bound {in_bound} tokens (UTF-8 bytes), output bound {n}x{a.max_tokens}; '
              f'worst case ${worst:.2f}; cap ${a.max_usd:.2f}; zero network calls')
        return 0

    import anthropic
    client = anthropic.Anthropic(max_retries=0, timeout=300.0)   # no silent re-sends: every attempt is counted
    counted = {}
    for s, reqs in sets.items():
        for r in reqs:
            counted[(s, r['i'])] = client.messages.count_tokens(
                model=a.model, system=SYSTEM_PROMPT, messages=[{'role': 'user', 'content': r['prompt']}]).input_tokens
    tin = sum(counted.values())
    worst = (tin * p_in + n * a.max_tokens * p_out) / 1e6
    expect = (tin * p_in + n * 300 * p_out) / 1e6
    print(f'PREFLIGHT {a.model}: {tin} input tokens counted (mean {tin / n:.0f}/call); '
          f'expected ~${expect:.2f} at 300 output tokens/call; worst case ${worst:.2f}; cap ${a.max_usd:.2f}')
    if worst > a.max_usd:
        print(f'STOP: worst case ${worst:.2f} exceeds --max-usd {a.max_usd:.2f}. Raise the cap or lower --max-tokens.')
        return 2
    if a.mode == 'preflight':
        return 0

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = pathlib.Path(a.out) if a.out else ARTIFACTS / 'claude-api-replay' / f'{a.model}-{stamp}'
    out.mkdir(parents=True, exist_ok=True)
    spent, summaries, capped = 0.0, [], False
    for s, reqs in sets.items():
        calls, consecutive = [], 0
        sd = out / s.replace('/', '__')
        sd.mkdir(exist_ok=True)
        with open(sd / 'calls.jsonl', 'w') as fh:
            for r in reqs:
                next_worst = (counted[(s, r['i'])] * p_in + a.max_tokens * p_out) / 1e6
                if spent + next_worst > a.max_usd:
                    print(f'STOP: spent ${spent:.4f}; the next call could pass the ${a.max_usd:.2f} cap')
                    capped = True
                    break
                rec = {k: r[k] for k in ('i', 'node', 'shape', 'subject', 'label', 'recorded')}
                rec['prompt_sha256'] = hashlib.sha256(r['prompt'].encode()).hexdigest()
                rec['counted_input_tokens'] = counted[(s, r['i'])]
                try:
                    ans, meta, err = ask(client, a.model, r, a.max_tokens, a.effort)
                except anthropic.APIStatusError as e:
                    ans, meta, err = None, {}, f'API {e.status_code}: {type(e).__name__}'
                except anthropic.APIConnectionError as e:
                    # a timed-out request may still be billed: count its worst case, never $0
                    ans, meta, err = None, {'cost_usd_bound': next_worst}, f'connection: {type(e).__name__}'
                    spent += next_worst
                except anthropic.APIError as e:
                    ans, meta, err = None, {}, f'API error: {type(e).__name__}'
                rec.update(meta)
                spent += rec.get('cost_usd') or 0
                if err:
                    rec['error'], rec['score'] = err, error_score(r, err)
                    consecutive += 1
                else:
                    try:
                        rec['error'], rec['score'] = None, score(r, ans)
                        consecutive = 0
                    except Malformed as e:
                        rec['error'], rec['score'] = f'malformed: {e}', error_score(r, f'malformed: {e}')
                        consecutive += 1
                rec['answer'] = ans
                fh.write(json.dumps(rec) + '\n'); fh.flush()
                calls.append(rec)
                print(f'  {s} i={r["i"]:>2} {r["node"]} {rec.get("latency_ms", "-")}ms '
                      f'${rec.get("cost_usd") or 0:.5f} {"ERR " + rec["error"] if rec["error"] else "ok"}')
                if consecutive >= MAX_CONSECUTIVE_ERRORS:
                    print(f'STOP: {consecutive} consecutive errors')
                    break
        summaries.append(summarize(a.model, s, calls))
        print(f'PHASE set {s}: done')
        if capped or consecutive >= MAX_CONSECUTIVE_ERRORS or spent >= a.max_usd:
            break
    rep = dict(model=a.model, stamp=stamp, max_tokens=a.max_tokens, effort=a.effort, spent_usd=spent,
               basis='metered usage x list price (pricing page fetched 2026-09-29)', sets=summaries)
    (out / 'report.json').write_text(json.dumps(rep, indent=2))
    lines = [f'# Claude API replay — {a.model} — {stamp}', '',
             'Metered `usage` from the Messages API x list price. Bare question: no CLI harness, no cache.', '',
             '| set | calls | units | correct/abstain/wrong | errors | mean in | mean out | API $/call | recorded CLI $/call | p50 ms |',
             '|---|---|---|---|---|---|---|---|---|---|']
    for x in summaries:
        f = lambda v, d=0: '-' if v is None else f'{v:,.{d}f}'  # noqa: E731
        lines.append(f"| {x['set']} | {x['calls']} | {x['units']} | {x['correct']}/{x['abstain']}/{x['wrong_not_abstained']} | "
                     f"{x['errors']} | {f(x['mean_input_tokens'])} | {f(x['mean_output_tokens'])} | "
                     f"{f(x['api_usd_per_call'], 5)} | {f(x['recorded_cli_usd_per_call'], 5)} | {f(x['latency_ms_p50'])} |")
    lines += ['', f'Spent ${spent:.4f}. Models reported: {", ".join(sorted({m for x in summaries for m in x["models_seen"]}))}.']
    (out / 'report.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print(f'RESULTS {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
