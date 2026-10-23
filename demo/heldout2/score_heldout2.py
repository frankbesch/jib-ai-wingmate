#!/usr/bin/env python3
"""Held-out run 2 scorer: marks P1 to P6 and Overall of plan 06-control-test-plan.md section 6 (v4, ruling R1).
Read-only toward runs and corpus. No model call, no network. Writes only --out (JSON) and --md (markdown).

Usage:
  score_heldout2.py --corpus synth-heldout2 --run-clean runs/<id> --run-scan runs/<id> --out <json>
                    [--md <md>] [--cases <json>] [--doi <json>]
                    [--audit clean=<json> --audit scan=<json>] [--audit2 clean=<json> --audit2 scan=<json>]
                    [--arms <arms.json>]
  score_heldout2.py --corpus synth-heldout --smoke runs/<id> [--smoke runs/<id>]   (K1/K2 counts only)

cases.json (default <corpus>/cases.json), written by the case designer. A JSON list; one entry per
(document, case class); a document in two classes has two entries:
  {"doc_id": "ticket_07",              # document id as in the corpus manifest
   "packet": "ticket_05",              # packet id that holds the document
   "class_id": "body-text-number",     # the coverage critic's case class id
   "label_variant": "Approval ref",    # the label printed beside the approval number (string), or null
   "flag_would_be_false_alarm": false, # true when, for this class, any K2 flag would be a false alarm
   "overlaps": ["wrong-number"]}       # other class_ids this document also belongs to ([] if none)
Every corpus document should appear at least once; a document without a case uses class_id "baseline".
A document missing from cases.json gets packet from month.json and label_variant null (not counted).

Audit files (--audit <set>=<path>: primary audit, adjudicated; --audit2: the separate alias/batched audit):
  {"corrections": {"<node>:<subject>": <label>, ...}, "excluded": ["<node>:<subject>", ...]}
  e.g. key "row8:ticket_07.afe_number" with label true. Corrections replace the layer-A label. Excluded units
  (split under R6, or unresolved) leave every truth-dependent count and enter the exclusion bounds.

Arm discovery under <run>/typed/ by out-dir name: base C = redo-cascade-* without '-alias-'; C-alias = redo-cascade-*
with '-alias-afe_number'; A = redo-claude-* without '-c8-per-document' and without '-alias-'; A-batched =
redo-claude-* with '-c8-per-document'; B = redo-jev-* without '-alias-'; B-alias = redo-jev-* with '-alias-afe_number'.
Repeat number = trailing '-rN', or, with --arms <arms.json> (written by heldout2/run_heldout2.py, which starts one
runner call per repeat so every out dir ends -r1), the orchestrator's repeat number:
  {"<set>": {"<arm>": [{"repeat": N, "stage": "...", "out": "<path to the out dir>"}, ...]}, ...}; matched by
  out-dir name. P5 pairs C-alias rN with base C rN by this number. With --arms only registered out dirs are scored,
  and the inventory must be exact per set (EXPECTED_INVENTORY), each report with errors 0 and not stopped, each
  registered arm identity equal to its out-dir arm, and every run covering the same unit set; anything else makes
  the verdict INVALID with the reasons. Without --arms the old discovery stands and a warning is printed.
  A folder without report.json is listed as incomplete and not scored.

Definitions (plan section 6, frozen): status of a unit against a label = error | abstain | correct | wrong.
Confident wrong = wrong (not abstained, not error), whichever model answered. Target error (P1) = row-8 afe_number
unit, wrong, final answer False, in one base C repeat. Catch = K2 flag on that unit in the same repeat. False alarm
= a flag on a correct answer. To a person = abstained or error units plus flagged units, each unit once.
Marks use layer A (unit `label_a`; `label` when the run was not layered); layer B (`label` of a layered run) is
reported beside them. Labels are taken from the arm records, which carry the frozen keys.
"""
import argparse, hashlib, itertools, json, pathlib, re, statistics, sys

HERE = pathlib.Path(__file__).resolve().parent
DEMO = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(DEMO / 'typed')); sys.path.insert(0, str(DEMO))
import controls as K  # noqa: E402

ALIAS_TAG, BATCH_TAG = '-alias-afe_number', '-c8-per-document'
SETS = ('clean', 'scan')
MAX_ENUM = 4096                 # per set; above this the exclusion bounds are not enumerated (mark INCONCLUSIVE)
P1_RECALL, P1_MAX_FA, P1_MIN_UNIQUE, P1_MIN_PACKETS, P1_MIN_VARIANTS = 0.80, 2, 15, 5, 3
P2_WRONG_PLUS, P2_PERSON_PLUS, P2_CALLS_FRAC = 5, 10, 0.5
P5_MAX_REGRESS, P5_WRONG_PLUS = 5, 5
PASS, FAIL, INC = 'PASS', 'FAIL', 'INCONCLUSIVE'
INVALID = 'INVALID'
EXPECTED_INVENTORY = {'A': 2, 'B': 3, 'C': 2, 'B-alias': 1, 'C-alias': 2, 'A-batched': 2}   # runs per set (plan section 5)


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def jsonl(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text().splitlines() if l.strip()]


def kstr(key):
    return f'{key[0]}:{key[1]}'


def kparse(s):
    n, _, sub = s.partition(':')
    return (n, sub)


def doc_field(subject):
    d, _, f = subject.partition('.')
    return d, f


# ------------------------------------------------------------------ loading

def arm_of(name):
    if not name.startswith('redo-'):
        return None
    alias = ALIAS_TAG in name
    if name.startswith('redo-cascade-'):
        return 'C-alias' if alias else 'C'
    if name.startswith('redo-jev-'):
        return 'B-alias' if alias else 'B'
    if name.startswith('redo-claude-'):
        if alias:
            return 'A-alias'
        return 'A-batched' if BATCH_TAG in name else 'A'
    return None


def repeat_of(name):
    m = re.search(r'-r(\d+)$', name)
    return int(m.group(1)) if m else None


def load_units(path):
    """{(node, subject): dict(final, abstain, error, la, lb)}; row-8 batches expand per field."""
    out = {}

    def add(node, subject, s, lab, lab_a, layered):
        out[(node, subject)] = dict(final=s.get('final'), abstain=bool(s.get('abstain')), error=bool(s.get('error')),
                                    la=lab_a if layered else lab, lb=lab if layered else None)
    for c in jsonl(pathlib.Path(path) / 'calls.jsonl'):
        if 'score' not in c or c.get('kind', 'unit') != 'unit':
            continue
        s, layered = c['score'], 'label_a' in c
        if isinstance(s, dict) and 'fields' in s:
            la, lb = c.get('label_a') or {}, c.get('label') or {}
            for f, u in s['fields'].items():
                add(c['node'], f"{c['subject']}.{f}", u, lb.get(f), la.get(f), layered)
        else:
            add(c['node'], c['subject'], s, c.get('label'), c.get('label_a'), layered)
    return out


def discover(run, repeats=None):
    """repeats: optional {out-dir name: {'arm', 'repeat'}} (from --arms). Given, only those dirs are scored and
    the registry's repeat number replaces the trailing -rN."""
    arms, incomplete = {}, []
    typed = pathlib.Path(run) / 'typed'
    for p in sorted(typed.iterdir()) if typed.is_dir() else []:
        arm = arm_of(p.name) if p.is_dir() else None
        if arm is None or (repeats is not None and p.name not in repeats):
            continue
        if not (p / 'report.json').exists() or not (p / 'calls.jsonl').exists():
            incomplete.append(p.name)
            continue
        rep = json.loads((p / 'report.json').read_text())
        claude = (rep.get('cascade') or {}).get('claude_calls') if arm.startswith('C') else (
            rep.get('calls') if arm.startswith('A') else 0)
        reg = (repeats or {}).get(p.name)
        arms.setdefault(arm, []).append(dict(name=p.name, repeat=reg['repeat'] if reg else repeat_of(p.name), units=load_units(p),
                                             claude_calls=claude, errors=rep.get('errors'), stopped=rep.get('stopped'),
                                             registered_arm=reg['arm'] if reg else None))
    return arms, incomplete


def doc_texts(run, corpus):
    """{doc_id: text} exactly as the arms build it: typed_questions.pages_from_extract over the run's
    raw/<packet>__extract.json, then typed_questions.doc_text (manifest pages, MAX_PAGE_CHARS cut)."""
    import typed_questions as tq
    man = json.loads((pathlib.Path(corpus) / 'manifest.json').read_text())
    pages = {pk['packet_id']: tq.pages_from_extract(json.loads((pathlib.Path(run) / 'raw' / f"{pk['packet_id']}__extract.json").read_text()))
             for pk in man['packets']}
    return {d['doc_id']: tq.doc_text(d, pages) for d in man['documents']}, man


def load_cases(path):
    cases = json.loads(pathlib.Path(path).read_text())
    need = ('doc_id', 'packet', 'class_id', 'label_variant', 'flag_would_be_false_alarm', 'overlaps')
    for i, c in enumerate(cases):
        miss = [k for k in need if k not in c]
        if miss:
            raise SystemExit(f'cases.json entry {i}: missing {miss}')
        if not isinstance(c['flag_would_be_false_alarm'], bool):
            raise SystemExit(f'cases.json entry {i}: flag_would_be_false_alarm must be true or false')
    return cases


def load_audit(spec):
    out = {}
    for s in spec or []:
        name, _, path = s.partition('=')
        if name not in SETS or not path:
            raise SystemExit(f'audit spec {s!r}: expected clean=<path> or scan=<path>')
        a = json.loads(pathlib.Path(path).read_text())
        out[name] = dict(path=path, corrections={kparse(k): v for k, v in (a.get('corrections') or {}).items()},
                         excluded={kparse(k) for k in a.get('excluded') or []})
    return out


# ------------------------------------------------------------------ per-set preparation (label-free)

def prepare(name, run, corpus, cases, doi, repeats=None):
    month = json.loads((pathlib.Path(run) / 'month.json').read_text())
    texts, man = doc_texts(run, corpus)
    arms, incomplete = discover(run, repeats)
    req = K.required()
    S = dict(name=name, run=str(run), month=month, texts=texts, arms=arms, incomplete=incomplete)
    # layer labels, from the arm records; conflicts between runs are listed
    la, lb, conflicts = {}, {}, []
    for arm in sorted(arms):
        for r in arms[arm]:
            for k, u in r['units'].items():
                for store, v in ((la, u['la']), (lb, u['lb'])):
                    if v is None:
                        continue
                    if k in store and store[k] != v:
                        conflicts.append([r['name'], kstr(k)])
                    store.setdefault(k, v)
    S.update(label_a=la, label_b=lb or None, label_conflicts=conflicts,
             pulse_dropped=sorted(kstr(k) for k in la if lb and la[k] is True and lb.get(k) is False),
             extract_invented=sorted(kstr(k) for k in la if lb and la[k] is False and lb.get(k) is True))
    # documents: packet and label variant from cases.json, else month.json packet and no variant
    docs = {}
    for c in cases:
        d = docs.setdefault(c['doc_id'], dict(packet=c['packet'], label_variant=None, classes=[]))
        d['classes'].append(c['class_id'])
        if d['label_variant'] is None:
            d['label_variant'] = c['label_variant']
    for d, v in month.get('documents', {}).items():
        docs.setdefault(d, dict(packet=v.get('packet'), label_variant=None, classes=[]))
    S['docs'] = docs
    S['case_flag'] = {}
    for c in cases:                      # pre-audit default of the P3 restriction (any entry true)
        S['case_flag'][c['doc_id']] = S['case_flag'].get(c['doc_id'], False) or bool(c['flag_would_be_false_alarm'])
    S['docs_not_in_cases'] = sorted(set(month.get('documents', {})) - {c['doc_id'] for c in cases})
    # flags per base C repeat (label-free)
    S['flags'] = {}
    for r in arms.get('C', []):
        ul = [dict(node=k[0], subject=k[1], final=u['final'], abstain=u['abstain']) for k, u in r['units'].items()]
        k1, k2 = K.k1_flags(ul, month, req), K.k2_flags(ul, month, texts)
        drop = {d: K.k2_flags(ul, month, texts, drop_source=d) for d in K.k2_sources(month)}
        k3, skipped = K.k3_flags(ul, doi, texts) if doi is not None else ([], sorted(K.K3_KEYS))
        S['flags'][r['name']] = dict(K1=set(k1), K2=set(k2), K3=set(k3), K3_skipped=skipped,
                                     drop={d: set(v) for d, v in drop.items()})
    # sources and missing sources (the manifest is read here, in the scorer, only to name AFE documents)
    sources = K.k2_sources(month)
    pulse_cls = K.doc_class(month)
    missing = []
    for d in man['documents']:
        if d['class'] in K.AFE_CLASSES and d['doc_id'] not in sources:
            v = ((month.get('documents', {}).get(d['doc_id']) or {}).get('values') or {}).get('afe_number')
            why = (f"Pulse classified it as {pulse_cls.get(d['doc_id'])!r}" if pulse_cls.get(d['doc_id']) not in K.AFE_CLASSES
                   else f'extracted afe_number {v!r} is not a valid source')
            missing.append(dict(doc_id=d['doc_id'], manifest_class=d['class'], reason=why))
    S.update(sources=sources, missing_sources=missing)
    return S


# ------------------------------------------------------------------ label-dependent evaluation

def status(u, key, labels, excluded):
    if u['error']:
        return 'error'
    if u['abstain']:
        return 'abstain'
    if key in excluded or key not in labels or labels[key] is None:
        return 'excluded'
    return 'correct' if u['final'] == labels[key] else 'wrong'


def counts(run, labels, excluded, flags=frozenset()):
    """wrong total, wrong left unflagged, to a person (abstain/error plus flags, each unit once)."""
    wrong = unflagged = person = abst = 0
    for k, u in run['units'].items():
        s = status(u, k, labels, excluded)
        flagged = k[0] == 'row8' and k[1] in flags
        wrong += s == 'wrong'
        unflagged += s == 'wrong' and not flagged
        abst += s == 'abstain'
        person += s in ('abstain', 'error') or flagged
    return dict(wrong=wrong, wrong_unflagged=unflagged, to_person=person, abstain=abst)


def targets(run, labels, excluded):
    return {k[1] for k, u in run['units'].items() if k[0] == 'row8' and doc_field(k[1])[1] == 'afe_number'
            and u['final'] is False and status(u, k, labels, excluded) == 'wrong'}


def flag_split(run, flags, labels, excluded):
    """(flags on wrong answers, flags on correct answers) as subject sets."""
    hit, fa = set(), set()
    for s in flags:
        k = ('row8', s)
        st = status(run['units'][k], k, labels, excluded) if k in run['units'] else 'excluded'
        (hit if st == 'wrong' else fa if st == 'correct' else set()).add(s)
    return hit, fa


def combine(vs):
    vs = list(vs)
    if not vs or INC in vs:
        return INC
    return PASS if all(v == PASS for v in vs) else FAIL


def evaluate_set(S, labels, excluded):
    arms, docs = S['arms'], S['docs']
    A, C = arms.get('A', []), arms.get('C', [])
    out = dict(arms={})
    for arm, runs in sorted(arms.items()):
        for r in runs:
            out['arms'][r['name']] = dict(arm=arm, repeat=r['repeat'], claude_calls=r['claude_calls'], errors=r['errors'],
                                          **counts(r, labels, excluded))
    # ---- P1
    reps, uniq = {}, {}
    for r in C:
        t = targets(r, labels, excluded)
        hit, fa = flag_split(r, S['flags'][r['name']]['K2'], labels, excluded)
        caught = t & hit
        ok = bool(t) and len(caught) / len(t) >= P1_RECALL and len(fa) <= P1_MAX_FA
        reps[r['name']] = dict(targets=len(t), caught=len(caught), recall=round(len(caught) / len(t), 3) if t else None,
                               false_alarms=len(fa), false_alarm_units=sorted(fa), missed=sorted(t - caught),
                               k2_flags=len(S['flags'][r['name']]['K2']), holds=ok)
        for s in t:
            e = uniq.setdefault(s, dict(doc_id=doc_field(s)[0], target_in=[], caught_in=[]))
            e['target_in'].append(r['name'])
            if s in caught:
                e['caught_in'].append(r['name'])
    for s, e in uniq.items():
        d = docs.get(e['doc_id'], {})
        e.update(packet=d.get('packet'), label_variant=d.get('label_variant'))
    packets = {e['packet'] for e in uniq.values()}
    variants = {e['label_variant'] for e in uniq.values() if e['label_variant'] is not None}
    why = []
    if not C:
        why.append('no base C repeat')
    why += [f'{n}: zero target errors' for n, v in reps.items() if v['targets'] == 0]
    if len(uniq) < P1_MIN_UNIQUE:
        why.append(f'{len(uniq)} unique targets < {P1_MIN_UNIQUE}')
    if len(packets) < P1_MIN_PACKETS:
        why.append(f'targets from {len(packets)} packets < {P1_MIN_PACKETS}')
    if len(variants) < P1_MIN_VARIANTS:
        why.append(f'targets from {len(variants)} label variants < {P1_MIN_VARIANTS}')
    p1 = INC if why else (PASS if all(v['holds'] for v in reps.values()) else FAIL)
    out['P1'] = dict(verdict=p1, inconclusive_because=why, per_repeat=reps, unique_targets=len(uniq),
                     unique_caught=sum(1 for e in uniq.values() if e['caught_in']), packets=sorted(packets, key=str),
                     label_variants=sorted(variants, key=str), unique=dict(sorted(uniq.items())))
    # ---- P2 (K1+K2 decides; K1, K2, none printed)
    p2 = dict(A_runs=[r['name'] for r in A])
    if A and C:
        aw = statistics.mean(out['arms'][r['name']]['wrong'] for r in A)
        ap = statistics.mean(out['arms'][r['name']]['to_person'] for r in A)
        ac = statistics.mean(r['claude_calls'] or 0 for r in A)
        p2.update(A_mean_wrong=aw, A_mean_to_person=ap, A_mean_claude_calls=ac,
                  limits=dict(wrong_unflagged=aw + P2_WRONG_PLUS, to_person=ap + P2_PERSON_PLUS, claude_calls=P2_CALLS_FRAC * ac))
        for var in ('K1+K2', 'K1', 'K2', 'none'):
            per = {}
            for r in C:
                f = S['flags'][r['name']]
                fl = {'K1+K2': f['K1'] | f['K2'], 'K1': f['K1'], 'K2': f['K2'], 'none': set()}[var]
                c = counts(r, labels, excluded, fl)
                chk = dict(wrong_unflagged=c['wrong_unflagged'] <= aw + P2_WRONG_PLUS,
                           to_person=c['to_person'] <= ap + P2_PERSON_PLUS,
                           claude_calls=r['claude_calls'] is not None and r['claude_calls'] <= P2_CALLS_FRAC * ac)
                per[r['name']] = dict(wrong_unflagged=c['wrong_unflagged'], to_person=c['to_person'], flags=len(fl),
                                      claude_calls=r['claude_calls'], checks=chk, holds=all(chk.values()))
            p2[var] = dict(per_repeat=per, verdict=PASS if all(v['holds'] for v in per.values()) else FAIL)
        p2['verdict'] = p2['K1+K2']['verdict']
    else:
        p2['verdict'] = INC
        p2['inconclusive_because'] = 'no A run' if not A else 'no base C repeat'
    out['P2'] = p2
    # ---- P3 per critic class (counts; the zero-flag condition is decided across sets in finish())
    p3 = {}
    for cls in sorted({c for d in docs.values() for c in d['classes']}):
        cd = {d for d, v in docs.items() if cls in v['classes']}
        e = dict(targets=0, caught=0, k2_flags=0, false_alarms=0)
        for r in C:
            t = {s for s in targets(r, labels, excluded) if doc_field(s)[0] in cd}
            fl = {s for s in S['flags'][r['name']]['K2'] if doc_field(s)[0] in cd}
            hit, fa = flag_split(r, fl, labels, excluded)
            e['targets'] += len(t); e['caught'] += len(t & hit); e['k2_flags'] += len(fl); e['false_alarms'] += len(fa)
        p3[cls] = e
    out['P3'] = p3
    by_doc = {}
    for r in C:
        for subj in S['flags'][r['name']]['K2']:
            by_doc[doc_field(subj)[0]] = by_doc.get(doc_field(subj)[0], 0) + 1
    out['k2_flags_by_doc'] = by_doc
    # P3 restriction for THIS truth layer: a document is restricted (a K2 flag on it is a false alarm) when the layer's
    # own afe_number presence label says not printed. An excluded or unlabelled-None unit carries no restriction and is
    # reported; a document without an afe_number unit keeps its cases.json flag (the pre-audit default).
    restricted, unrestricted, disagree = set(), [], []
    docs_afe = {doc_field(k[1])[0] for k in labels if k[0] == 'row8' and doc_field(k[1])[1] == 'afe_number'}
    for d in sorted(docs_afe | set(S['case_flag'])):
        key = ('row8', f'{d}.afe_number')
        if key in excluded or (key in labels and labels[key] is None):
            unrestricted.append(d)
            continue
        r = (labels[key] is False) if key in labels else S['case_flag'].get(d, False)
        if r:
            restricted.add(d)
        if d in S['case_flag'] and key in labels and S['case_flag'][d] != r:
            disagree.append(d)
    out['zero_flag_restriction'] = dict(restricted=sorted(restricted), unrestricted_excluded=unrestricted,
                                        label_vs_cases=disagree)
    # ---- P4: K3 per field
    p4 = {}
    for r in C:
        f = S['flags'][r['name']]
        for field in K.K3_KEYS:
            if field in f['K3_skipped']:
                p4.setdefault(field, dict(skipped=True))
                continue
            fl = {s for s in f['K3'] if doc_field(s)[1] == field}
            hit, fa = flag_split(r, fl, labels, excluded)
            t = {k[1] for k, u in r['units'].items() if k[0] == 'row8' and doc_field(k[1])[1] == field
                 and u['final'] is False and status(u, k, labels, excluded) == 'wrong'}
            p4.setdefault(field, {})[r['name']] = dict(flags=len(fl), catches=len(hit & t), false_alarms=len(fa),
                                                       not_printed_errors=len(t))
    out['P4'] = p4
    # ---- P5: C-alias rN paired with base C rN
    base = {r['repeat']: r for r in C}
    per5 = {}
    for r in arms.get('C-alias', []):
        b = base.get(r['repeat'])
        if b is None:
            per5[r['name']] = dict(paired_with=None, holds=False, note='no base C run with this repeat number')
            continue
        reg, imp = [], []
        for k, u in r['units'].items():
            if k not in b['units']:
                continue
            sb, sa = status(b['units'][k], k, labels, excluded), status(u, k, labels, excluded)
            if sb == 'correct' and sa in ('wrong', 'abstain', 'error'):
                reg.append(kstr(k))
            elif sb in ('wrong', 'abstain', 'error') and sa == 'correct':
                imp.append(kstr(k))
        w = out['arms'][r['name']]['wrong']
        lim = (statistics.mean(out['arms'][a['name']]['wrong'] for a in A) + P5_WRONG_PLUS) if A else None
        h2 = lim is not None and w <= lim
        per5[r['name']] = dict(paired_with=b['name'], right_to_wrong_or_abstain=len(reg), wrong_or_abstain_to_right=len(imp),
                               regressions=sorted(reg), alias_wrong=w, h2_limit=lim, h2_holds=h2,
                               holds=h2 and len(reg) <= P5_MAX_REGRESS)
    out['P5'] = dict(per_pair=per5, verdict=INC if not per5 or not A else (PASS if all(v['holds'] for v in per5.values()) else FAIL))
    # ---- P6: batched against per-field, reported only
    def means(rs):
        if not rs:
            return None
        row8 = [counts(dict(units={k: u for k, u in r['units'].items() if k[0] == 'row8'}), labels, excluded) for r in rs]
        return dict(runs=[r['name'] for r in rs], mean_wrong=statistics.mean(out['arms'][r['name']]['wrong'] for r in rs),
                    mean_abstain=statistics.mean(out['arms'][r['name']]['abstain'] for r in rs),
                    row8_mean_wrong=statistics.mean(c['wrong'] for c in row8),
                    row8_mean_abstain=statistics.mean(c['abstain'] for c in row8))
    out['P6'] = dict(per_field=means(A), batched=means(arms.get('A-batched', [])))
    # ---- per packet
    pk = {}
    for s, e in uniq.items():
        p = pk.setdefault(e['packet'], dict(unique_targets=0, unique_caught=0, k2_flags=0, k2_false_alarms=0))
        p['unique_targets'] += 1; p['unique_caught'] += bool(e['caught_in'])
    for r in C:
        hit, fa = flag_split(r, S['flags'][r['name']]['K2'], labels, excluded)
        for s in S['flags'][r['name']]['K2']:
            p = pk.setdefault(docs.get(doc_field(s)[0], {}).get('packet'),
                              dict(unique_targets=0, unique_caught=0, k2_flags=0, k2_false_alarms=0))
            p['k2_flags'] += 1; p['k2_false_alarms'] += s in fa
    out['per_packet'] = {str(k): v for k, v in sorted(pk.items(), key=lambda x: str(x[0]))}
    return out


def zero_flag(cases, sets):
    """P3 condition, per DOCUMENT and per truth layer: K2 raises 0 flags on every document the layer restricts
    (its afe_number presence label says not printed; see evaluate_set), in every base C repeat of every set.
    Never per class, so a mixed class (e.g. baseline) cannot fail on a legitimate catch. Excluded units carry no
    restriction and are listed; documents whose label disagrees with the cases.json flag are listed. The per-class
    counts stay in by_class for reporting only."""
    zr = {s: S_out.get('zero_flag_restriction') or {} for s, S_out in sets.items()}
    docs = sorted({d for z in zr.values() for d in z.get('restricted', [])})
    per = {d: {s: (S_out.get('k2_flags_by_doc', {}).get(d, 0) if d in zr[s].get('restricted', []) else 0)
               for s, S_out in sets.items()} for d in docs}
    bad = [d for d, v in per.items() if sum(v.values())]
    req = sorted({c['class_id'] for c in cases if c['flag_would_be_false_alarm']})
    by_class = {cls: {s: S_out['P3'].get(cls, {}).get('k2_flags', 0) for s, S_out in sets.items()} for cls in req}
    return dict(documents=docs, k2_flags={d: v for d, v in per.items() if sum(v.values())}, failing=bad, holds=not bad,
                by_class=by_class, unrestricted_excluded={s: z.get('unrestricted_excluded', []) for s, z in zr.items()},
                label_vs_cases={s: z.get('label_vs_cases', []) for s, z in zr.items()})


def flag_contradictions(cases):
    """Documents whose cases.json entries disagree on flag_would_be_false_alarm (INVALID)."""
    seen = {}
    for c in cases:
        seen.setdefault(c['doc_id'], set()).add(c['flag_would_be_false_alarm'])
    return sorted(d for d, v in seen.items() if len(v) > 1)


def finish(evals, cases):
    """Cross-set marks from per-set evaluations {set: evaluate_set output}."""
    p1 = combine([evals[s]['P1']['verdict'] if s in evals else INC for s in SETS])
    p2 = combine([evals[s]['P2']['verdict'] if s in evals else INC for s in SETS])
    p5 = combine([evals[s]['P5']['verdict'] if s in evals else INC for s in SETS])
    z = zero_flag(cases, evals)
    overall = PASS if (p1 == PASS and p2 == PASS and z['holds']) else (
        FAIL if (p1 == FAIL or p2 == FAIL or not z['holds']) else INC)
    return dict(P1=p1, P2=p2, P3_zero_flag=z, P5=p5, Overall=overall)


# ------------------------------------------------------------------ exclusion bounds

def candidates(S, key):
    finals = {r['units'][key]['final'] for runs in S['arms'].values() for r in runs
              if key in r['units'] and not r['units'][key]['abstain'] and not r['units'][key]['error']}
    if key[0] == 'row8' or finals <= {True, False}:
        return [True, False]
    return sorted(finals, key=str) + ['__none_of_the_answers__']


def bounds(prep, labels, excluded, cases, point):
    """Every excluded unit scored each way. Returns reachable verdicts per mark and the final verdicts:
    a mark whose reachable verdicts differ from its point verdict reads INCONCLUSIVE."""
    per_set = {}
    for s, S in prep.items():
        ex = sorted(excluded.get(s, set()))
        opts = [candidates(S, k) for k in ex]
        n = 1
        for o in opts:
            n *= len(o)
        if n > MAX_ENUM:
            return dict(enumerated=False, note=f'{s}: {n} combinations > {MAX_ENUM}', reachable=None,
                        final=dict(point, P1=INC, P2=INC, P5=INC,
                                   Overall=INC if point['P3_zero_flag']['holds'] else FAIL))
        seen = set()
        for combo in itertools.product(*opts):
            lab = dict(labels[s]); lab.update(zip(ex, combo))
            e = evaluate_set(S, lab, set())
            seen.add((e['P1']['verdict'], e['P2']['verdict'], e['P5']['verdict']))
        per_set[s] = seen
    reach = dict(P1=set(), P2=set(), P5=set())
    for combo in itertools.product(*[sorted(per_set[s]) for s in SETS if s in per_set]):
        got = dict(zip(SETS, combo))
        for i, m in enumerate(('P1', 'P2', 'P5')):
            reach[m].add(combine([got[s][i] if s in got else INC for s in SETS]))
    final = dict(point)
    for m in ('P1', 'P2', 'P5'):
        if reach[m] != {point[m]}:
            final[m] = INC
    z = point['P3_zero_flag']['holds']
    final['Overall'] = PASS if (final['P1'] == PASS and final['P2'] == PASS and z) else (
        FAIL if (final['P1'] == FAIL or final['P2'] == FAIL or not z) else INC)
    order = [PASS, INC, FAIL]
    return dict(enumerated=True, excluded={s: sorted(kstr(k) for k in v) for s, v in excluded.items()},
                reachable={m: sorted(v) for m, v in reach.items()},
                scored_for={m: min(v, key=order.index) for m, v in reach.items() if v},
                scored_against={m: max(v, key=order.index) for m, v in reach.items() if v}, final=final)


# ------------------------------------------------------------------ driver

def strip(e):
    """JSON-safe copy (sets -> sorted lists)."""
    if isinstance(e, dict):
        return {str(k): strip(v) for k, v in e.items()}
    if isinstance(e, (set, frozenset)):
        return sorted(e, key=str)
    if isinstance(e, list):
        return [strip(v) for v in e]
    return e


def source_loss(S, labels, excluded):
    rows = []
    for r in S['arms'].get('C', []):
        f = S['flags'][r['name']]
        t = targets(r, labels, excluded)
        full = t & f['K2']
        for d, fl in sorted(f['drop'].items()):
            lost = sorted(full - fl)
            rows.append(dict(source_doc=d, source_value=S['sources'][d], repeat=r['name'], catches_lost=len(lost),
                             lost_units=lost, flags_removed=len(f['K2'] - fl)))
    return rows


def load_arms(path):
    """{set: {out-dir name: {'arm', 'repeat', 'out'}}} from the orchestrator's arms.json; None without --arms."""
    if not path:
        return None
    a = json.loads(pathlib.Path(path).read_text())
    reg = {s: {pathlib.Path(r['out']).name: dict(arm=arm, repeat=int(r['repeat']), out=r['out'])
               for arm, runs in arms.items() for r in runs} for s, arms in a.items() if not s.startswith('_')}
    reg['_expected_units'] = {s: {kparse(k) for k in v} for s, v in (a.get('_expected_units') or {}).items()}
    return reg


def inventory(prep, registry):
    """Reasons the arm inventory is not exactly the planned one (empty when it is)."""
    why = []
    expected = (registry or {}).get('_expected_units') or {}
    for s in SETS:
        reg = (registry or {}).get(s)
        if s not in prep:
            continue
        if not reg:
            why.append(f'{s}: no arms registered')
            continue
        S = prep[s]
        found = {r['name'] for runs in S['arms'].values() for r in runs}
        for name in sorted(set(reg) - found):
            why.append(f'{s}: registered run {name} missing or incomplete')
        for arm, n in EXPECTED_INVENTORY.items():
            runs = S['arms'].get(arm, [])
            reps = sorted(r['repeat'] for r in runs)
            if reps != list(range(1, n + 1)):
                why.append(f'{s}: arm {arm} has repeats {reps}, expected 1..{n}')
        for arm in sorted(set(S['arms']) - set(EXPECTED_INVENTORY)):
            why.append(f'{s}: unexpected arm {arm}')
        units = expected.get(s)
        if not units:
            why.append(f'{s}: arms.json has no expected unit set (_expected_units)')
        for arm, runs in sorted(S['arms'].items()):
            for r in runs:
                if r['registered_arm'] not in (None, arm):
                    why.append(f"{s}: {r['name']} registered as {r['registered_arm']} but its out dir names {arm}")
                if r['errors'] != 0 or r['stopped']:
                    why.append(f"{s}: {r['name']} errors={r['errors']} stopped={r['stopped']!r}")
                keys = set(r['units'])
                if units and keys != units:
                    why.append(f"{s}: {r['name']} covers {len(keys)} units, not the expected {len(units)} "
                               f"({len(units - keys)} missing, {len(keys - units)} unexpected)")
    return why


def score(corpus, runs, cases, doi, audit, audit2, repeats=None):
    prep = {s: prepare(s, r, corpus, cases, doi, (repeats or {}).get(s)) for s, r in runs.items() if s in SETS}
    la = {s: dict(S['label_a']) for s, S in prep.items()}
    post = {s: dict(la[s]) for s in prep}
    excl = {s: set() for s in prep}
    for s, a in audit.items():
        if s in post:
            post[s].update(a['corrections']); excl[s] |= a['excluded']
    layers = dict(A_pre_audit=(la, {s: set() for s in prep}))
    if audit:
        layers['A_post_audit'] = (post, excl)
    if audit2:
        p2 = {s: dict(post[s]) for s in prep}
        e2 = {s: set(excl[s]) for s in prep}
        for s, a in audit2.items():
            if s in p2:
                p2[s].update(a['corrections']); e2[s] |= a['excluded']
        layers['A_sensitivity_alias_audit'] = (p2, e2)
    if all(S['label_b'] for S in prep.values()):
        layers['B'] = ({s: S['label_b'] for s, S in prep.items()}, {s: set() for s in prep})
    primary = 'A_post_audit' if audit else 'A_pre_audit'
    res = dict(meta=dict(corpus=str(corpus), runs={s: str(r) for s, r in runs.items()}, primary_layer=primary,
                         controls_sha256=sha(HERE / 'controls.py'), scorer_sha256=sha(__file__),
                         reconcile_sha256=sha(K.RECONCILE), pulse_class_key="month.json classify[].predicted",
                         audit={s: a['path'] for s, a in audit.items()}, audit2={s: a['path'] for s, a in audit2.items()}),
               sets={}, layers={})
    for s, S in prep.items():
        res['sets'][s] = dict(run=S['run'], arms={a: [r['name'] for r in v] for a, v in sorted(S['arms'].items())},
                              incomplete_runs=S['incomplete'], label_conflicts=S['label_conflicts'],
                              pulse_dropped=S['pulse_dropped'], extract_invented=S['extract_invented'],
                              docs_not_in_cases=S['docs_not_in_cases'], k2_sources=S['sources'],
                              missing_sources=S['missing_sources'],
                              k3_skipped_fields=sorted({f for v in S['flags'].values() for f in v['K3_skipped']}),
                              source_loss=source_loss(S, *[layers[primary][i][s] for i in (0, 1)]))
    for name, (labs, ex) in layers.items():
        ev = {s: evaluate_set(S, labs[s], ex[s]) for s, S in prep.items()}
        marks = finish(ev, cases)
        entry = dict(marks=marks, per_set=ev)
        if any(ex.values()):
            entry['exclusion_bounds'] = bounds(prep, labs, ex, cases, marks)
            entry['final'] = entry['exclusion_bounds']['final']
        else:
            entry['final'] = marks
        res['layers'][name] = entry
    res['verdict'] = {k: v for k, v in res['layers'][primary]['final'].items() if k != 'P3_zero_flag'}
    res['verdict']['P3_zero_flag_holds'] = res['layers'][primary]['final']['P3_zero_flag']['holds']
    why = [f'cases.json: entries for {d} disagree on flag_would_be_false_alarm' for d in flag_contradictions(cases)]
    if repeats is None:
        res['inventory'] = dict(checked=False, warning='no --arms: arm inventory, report errors, and unit coverage not checked')
    else:
        inv = inventory(prep, repeats)
        res['inventory'] = dict(checked=True, ok=not inv, reasons=inv)
        why += inv
    if why:
        res['verdict'] = dict(P1=INVALID, P2=INVALID, P5=INVALID, Overall=INVALID, invalid_reasons=why)
    return strip(res)


def markdown(res):
    inv = res.get('inventory') or {}
    L = [f"# Held-out run 2 score ({res['meta']['primary_layer']} primary)", '']
    if res['verdict'].get('Overall') == INVALID:
        L += [f"**VERDICT INVALID**: {'; '.join(res['verdict']['invalid_reasons'][:10])}", '']
    elif not inv.get('checked'):
        L += [f"WARNING: {inv.get('warning')}", '']
    L += [
         '| Mark | ' + ' | '.join(res['layers']) + ' |', '|---|' + '---|' * len(res['layers'])]
    for m in ('P1', 'P2', 'P5', 'Overall'):
        L.append(f'| {m} | ' + ' | '.join(str(v['final'][m]) for v in res['layers'].values()) + ' |')
    L.append('| P3 zero-flag | ' + ' | '.join(str(v['final']['P3_zero_flag']['holds']) for v in res['layers'].values()) + ' |')
    prim = res['layers'][res['meta']['primary_layer']]
    for s, e in prim['per_set'].items():
        L += ['', f'## {s}: P1 per base C repeat', '', '| repeat | targets | caught | recall | false alarms | holds |', '|---|---|---|---|---|---|']
        L += [f"| {n} | {v['targets']} | {v['caught']} | {v['recall']} | {v['false_alarms']} | {v['holds']} |"
              for n, v in e['P1']['per_repeat'].items()]
        L.append(f"\nUnique targets {e['P1']['unique_targets']} (caught {e['P1']['unique_caught']}), packets "
                 f"{len(e['P1']['packets'])}, label variants {len(e['P1']['label_variants'])}. Verdict {e['P1']['verdict']} "
                 f"{'; '.join(e['P1']['inconclusive_because'])}")
        if 'K1+K2' in e['P2']:
            L += ['', f'## {s}: P2 per base C repeat (K1+K2 decides)', '',
                  '| control | repeat | wrong unflagged | to a person | Claude calls | holds |', '|---|---|---|---|---|---|']
            for var in ('K1+K2', 'K1', 'K2', 'none'):
                L += [f"| {var} | {n} | {v['wrong_unflagged']} | {v['to_person']} | {v['claude_calls']} | {v['holds']} |"
                      for n, v in e['P2'][var]['per_repeat'].items()]
            L.append(f"\nLimits: {e['P2']['limits']}")
        L += ['', f'## {s}: P3 per case class (K2)', '', '| class | targets | caught | K2 flags | false alarms |', '|---|---|---|---|---|']
        L += [f"| {c} | {v['targets']} | {v['caught']} | {v['k2_flags']} | {v['false_alarms']} |" for c, v in e['P3'].items()]
        L += ['', f'## {s}: source loss', '', '| source doc | repeat | catches lost | flags removed |', '|---|---|---|---|']
        L += [f"| {r['source_doc']} | {r['repeat']} | {r['catches_lost']} | {r['flags_removed']} |" for r in res['sets'][s]['source_loss']]
        L.append(f"\nMissing sources: {res['sets'][s]['missing_sources'] or 'none'}")
        L += ['', f'## {s}: per packet', '', '| packet | unique targets | caught | K2 flags | K2 false alarms |', '|---|---|---|---|---|']
        L += [f"| {p} | {v['unique_targets']} | {v['unique_caught']} | {v['k2_flags']} | {v['k2_false_alarms']} |" for p, v in e['per_packet'].items()]
    return '\n'.join(L) + '\n'


def smoke(runs, corpus):
    """K1 and K2 counts per base C run, against layer A (label_a) of the run records."""
    for run in runs:
        month = json.loads((pathlib.Path(run) / 'month.json').read_text())
        texts, _ = doc_texts(run, corpus)
        arms, _ = discover(run)
        print(f'{run}: K2 sources {K.k2_sources(month)}')
        for r in arms.get('C', []):
            ul = [dict(node=k[0], subject=k[1], final=u['final'], abstain=u['abstain']) for k, u in r['units'].items()]
            lab = {k: u['la'] for k, u in r['units'].items()}
            t = targets(r, lab, set())
            wrong = sum(status(u, k, lab, set()) == 'wrong' for k, u in r['units'].items())
            for name, fl in (('K1', K.k1_flags(ul, month)), ('K2', K.k2_flags(ul, month, texts))):
                hit, fa = flag_split(r, set(fl), lab, set())
                extra = f', afe_number targets {len(t)}, caught {len(t & hit)}' if name == 'K2' else ''
                print(f'  {r["name"]} {name}: flags {len(fl)}, hits {len(hit)} (of {wrong} confident wrong), '
                      f'false alarms {len(fa)}{extra}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--corpus', required=True)
    ap.add_argument('--run-clean'); ap.add_argument('--run-scan')
    ap.add_argument('--cases'); ap.add_argument('--doi')
    ap.add_argument('--audit', action='append'); ap.add_argument('--audit2', action='append')
    ap.add_argument('--out'); ap.add_argument('--md')
    ap.add_argument('--arms', help="orchestrator arms.json: repeat numbers by out-dir name (P5 pairing)")
    ap.add_argument('--smoke', action='append', help='print K1/K2 counts for this run folder and stop')
    a = ap.parse_args()
    corpus = pathlib.Path(a.corpus)
    if a.smoke:
        return smoke(a.smoke, corpus)
    runs = {s: pathlib.Path(r) for s, r in (('clean', a.run_clean), ('scan', a.run_scan)) if r}
    if not runs or not a.out:
        raise SystemExit('give --out and at least one of --run-clean / --run-scan')
    cases = load_cases(a.cases or corpus / 'cases.json')
    doi_path = pathlib.Path(a.doi) if a.doi else corpus / 'reference' / 'doi.json'
    doi = json.loads(doi_path.read_text()) if doi_path.exists() else None
    res = score(corpus, runs, cases, doi, load_audit(a.audit), load_audit(a.audit2), load_arms(a.arms))
    pathlib.Path(a.out).write_text(json.dumps(res, indent=1) + '\n')
    md = pathlib.Path(a.md) if a.md else pathlib.Path(a.out).with_suffix('.md')
    md.write_text(markdown(res))
    if not a.arms:
        print('WARNING: no --arms given: arm inventory, report errors, and unit coverage are not checked')
    print(json.dumps(res['verdict']))
    print(f'-> {a.out}, {md}')
    if res['verdict'].get('Overall') == INVALID:
        print('INVALID: ' + '; '.join(res['verdict'].get('invalid_reasons', [])), file=sys.stderr)
        sys.exit(3)                      # an INVALID verdict is not a result: the caller must stop


if __name__ == '__main__':
    main()
