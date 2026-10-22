#!/usr/bin/env python3
"""Typed-question runner for the operator's month (rows 1, 4, 5, 8 of the 2026-09-28 decomposition).

Replays a recorded Pulse run (`runs/<id>/raw/*__extract.json` + `month.json`) through typed
questions answered by a model, and scores each node against labels that already exist in the kit
(`synth/manifest.json` for class, pages, packet; `truth/synth/*.json` for field presence).
Zero Pulse spend: nothing here calls the parser API.

Question shapes (D-210/D-211):
  row 1  choice  "Which document class is this document?"           set = 7 classes + needs_review
  row 4  choice  "Which topic does this page belong to?"             set = 7 topics  + needs_review
  row 5  noul    "Does this packet contain a second field ticket?"   p(true), abstain band
  row 8  noul    "Is field <f> printed in this document?" one per required field, batched per
                 document by default (--row8 per-document) or one call per field (--row8 per-field)

Fail-closed, declared before the first live run and frozen in this file:
  choice: max option probability < CHOICE_FLOOR  -> needs_review
  noul:   NOUL_LO < p(true) < NOUL_HI            -> abstain
The "probability" is the model's self-reported number per option. It is NOT calibrated; the
report says so. Calibration is a later measurement, not a claim this runner makes.

Modes:
  --mode fixture   synthetic answers (labels with planted one abstain + one wrong); no network
  --mode dry-run   builds every request, prints the count and estimated size, makes no calls
  --mode live      Frank runs this: shells out to `claude -p --output-format json` per request,
                   capped by --cap, envelope usage logged per call (headless-claude-preflight).
                   The claude backend refuses to start without --model (the model is pinned); the
                   served model is logged per call from the envelope's modelUsage keys.
  --mode parity-check  builds every unit for both backends, no network, prints `parity N of N`

Redo flags (2026-09-30, plan reviews/2026-09-30-pulse-typed-redo-plan.md sections 2-4; all off by default):
  --set <dir>       corpus dir with its own manifest.json and truth/; default synth/manifest.json + truth/synth
  --truth-b <dir>   layer-B truth (keyed from the Pulse extract). Row 8 is scored against B; A present and
                    B absent is Pulse-dropped (own column, excluded from correct/abstain/wrong); A absent
                    and B present is listed as extract-invented.
  --parity          --field-desc short --option-desc verbatim for both backends, row 8 per field for claude
                    (jev keeps its request shape), disagree no longer forces an abstain; parity_sha256 per unit
  --compare-hashes <calls.jsonl>  dry-run: compare every request hash with a recorded run (cascade: every Jev
                    request in order, plus the Claude prompt of every unit the recorded run escalated)

Held-out run 2 flags (2026-10-02, heldout2/BUILD-SPEC.md H1; both off by default, default requests byte-identical):
  --claude-row8 per-document  under --parity with the claude backend, row 8 is one call per document (the
                    batched arm); everything else stays parity. Cascade ignores it (an escalation is one field).
  --alias afe_number  appends ALIAS_AFE_NUMBER to the afe_number field description in row 8, every backend,
                    allowed under --parity. Out-dir tags: -c8-per-document, -alias-afe_number.

Backends (--backend), the two arms of the comparison. Same questions, labels, thresholds, scoring:
  claude  `claude -p`, the Claude-only arm. Envelope cost is a list-price estimate, not billed
          under the subscription.
  jev     TypeSafe System One (`typed/jev_backend.py`), the Jev arm. METERED spend; live is
          Frank-run (D-218), needs TYPESAFE_API_KEY, and stops at --max-spend.
  cascade Jev answers every unit first; a unit whose Jev top probability is under --escalate-below (0.80)
          goes to Claude as one per-field parity call; Claude's thresholds decide; an abstain goes to a
          person. One run, one calls.jsonl, one report. Parity mode by construction; live needs --model.
In fixture and dry-run the jev and cascade backends install a socket guard: zero network calls.

Backend note: no Anthropic SDK or ANTHROPIC_API_KEY exists on this machine (checked 2026-09-29);
the Claude Code CLI is logged in, so live mode uses `claude -p`. Swapping in the SDK is a
one-function change (`ask_model`).

Outputs under runs/<id>/typed/<mode>-<UTC stamp>/: calls.jsonl, report.json, report.md.
"""
import argparse, datetime, hashlib, json, os, pathlib, re, statistics, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from reconcile import REQUIRED  # noqa: E402  (the same required-field lists the rules use)
from typed import jev_backend as jev  # noqa: E402

CLASSES = ['afe_cover', 'afe', 'field_ticket', 'hauling_log', 'invoice', 'jib_statement', 'unrecognized']
# Row 4 collapsed 2026-09-29 (Frank): one field_ticket topic; the ticket ordinal is page order, assigned by software (row 6).
TOPICS = ['afe_cover', 'afe', 'field_ticket', 'hauling_log', 'invoice', 'jib_statement', 'other']
NEEDS_REVIEW = 'needs_review'
BOOL_FIELDS = {'customer_signature_present'}   # selection marks: a different question, excluded from row 8
DECOYS = {   # fields that are NOT printed on this class; row 8 negatives, label False (added 2026-09-29, review finding 4)
    'afe_cover': ['invoice_number', 'log_number'], 'afe': ['ticket_number', 'statement_period'],
    'field_ticket': ['invoice_number', 'log_number'], 'hauling_log': ['invoice_number', 'statement_period'],
    'invoice': ['log_number', 'statement_period'], 'jib_statement': ['ticket_number', 'log_number'],
}
MAX_CONSECUTIVE_ERRORS = 3
CHOICE_FLOOR = 0.60     # declared 2026-09-29, before the first live run; never edit after
NOUL_LO, NOUL_HI = 0.35, 0.65
MAX_PAGE_CHARS = 12000

# ---------------------------------------------------------------- inputs

def load(p):
    return json.loads(pathlib.Path(p).read_text())

def pages_from_extract(raw):
    """Split Pulse extract markdown on its PageBreak markers -> {page_no: text}."""
    md = raw['markdown']
    parts = re.split(r'<!-- PageBreak \[(\d+)\] -->', md)
    pages, n = {}, 1
    # parts = [text_p1, '1', text_p2, '2', ..., text_last]
    markers = [int(x) for x in parts[1::2]]
    if markers != list(range(1, len(markers) + 1)):
        raise SystemExit(f'PageBreak markers out of sequence: {markers}')
    for i in range(0, len(parts), 2):
        pages[n] = parts[i].strip()
        n += 1
    return pages

def build_inputs(run_dir, manifest, truth_dir):
    docs = manifest['documents']
    packets = {p['packet_id']: p for p in manifest['packets']}
    page_text = {}
    for pid in packets:
        raw = load(run_dir / 'raw' / f'{pid}__extract.json')
        page_text[pid] = pages_from_extract(raw)
        if len(page_text[pid]) != packets[pid]['pages']:
            raise SystemExit(f'{pid}: extract has {len(page_text[pid])} pages, manifest says {packets[pid]["pages"]}')
    truth = {d['doc_id']: load(truth_dir / f"{d['doc_id']}.json")['values'] for d in docs}
    return docs, packets, page_text, truth

def set_paths(corpus):
    """(manifest path, layer-A truth dir). No --set keeps the fixed paths the 2026-09-29 runs used."""
    if corpus is None:
        return ROOT / 'synth' / 'manifest.json', ROOT / 'truth' / 'synth'
    d = pathlib.Path(corpus)
    d = d if d.is_absolute() else ROOT / d
    if d.resolve() == (ROOT / 'synth').resolve():
        return ROOT / 'synth' / 'manifest.json', ROOT / 'truth' / 'synth'
    return d / 'manifest.json', d / 'truth'

def load_truth(docs, truth_dir):
    return {d['doc_id']: load(pathlib.Path(truth_dir) / f"{d['doc_id']}.json")['values'] for d in docs}

def doc_text(d, page_text):
    return '\n\n'.join(page_text[d['packet']][p] for p in d['pages'])[:MAX_PAGE_CHARS]

# ---------------------------------------------------------------- field descriptions (row 8, optional)

def field_descriptions(mode):
    """{field: description} from the Pulse schemas in schemas/<class>.json (committed 2026-09-05, before any
    typed run). Nothing is hand-written here. A field keeps the description from the class that defines it;
    a field defined by several classes must carry one description per class, so the map is keyed by class too.
    mode 'verbatim' = the schema text; mode 'short' = the same text cut at its first comma or full stop,
    which drops the extraction instructions (digits only, never sum, null if absent)."""
    out = {}
    for c in REQUIRED:
        props = load(ROOT / 'schemas' / f'{c}.json')['properties']
        for f, v in props.items():
            d = v.get('description')
            if not d:
                raise SystemExit(f'schemas/{c}.json: field {f} has no description')
            out[(c, f)] = _short(d) if mode == 'short' else d
    return out

def _short(d):
    return re.split(r'[,.](?:\s|$)', d, maxsplit=1)[0].strip()

def option_descriptions(mode):
    """({class: description} for row 1, {topic: description} for row 4), from the Pulse configs committed
    2026-09-05: schemas/synth_classify_config.json and schemas/synth_split_config.json. Nothing is
    hand-written. Row 4 has one derived text: the split config describes field_ticket_1 and field_ticket_2,
    and row 4 now has a single field_ticket topic, so it takes the field_ticket_1 text from
    'A field ticket has' onward (the ordinal sentence is dropped). needs_review keeps its one sentence."""
    cc = load(ROOT / 'schemas' / 'synth_classify_config.json')['classifications']
    row1 = {c: cc[c]['description'] for c in CLASSES}
    sc = {t['name']: t['description'] for t in load(ROOT / 'schemas' / 'synth_split_config.json')['split_input']}
    t1 = sc['field_ticket_1']
    if 'A field ticket has' not in t1:
        raise SystemExit('synth_split_config.json: field_ticket_1 text changed; the row-4 derivation no longer applies')
    sc['field_ticket'] = t1[t1.index('A field ticket has'):]
    row4 = {t: sc[t] for t in TOPICS}
    if mode == 'short':
        row1, row4 = {k: _short(v) for k, v in row1.items()}, {k: _short(v) for k, v in row4.items()}
    for m in (row1, row4):
        if not all(m.values()):
            raise SystemExit('an option has an empty description')
        m[NEEDS_REVIEW] = 'The evidence is thin.'
    return row1, row4

# Item 2 (declared 2026-09-29): tell the model that an unlabelled value still counts as printed.
UNLABELLED_GENERIC = (' A value counts as printed when it appears without a label, for example in a letterhead, '
                      'a title, or a signature block.')
# The one hand-written text in this file. It follows the wording the afe_cover schema already uses for
# operator_name ("from the letterhead or signature block"). Written after the confirming run, for one field.
UNLABELLED_TARGETED = {('invoice', 'vendor_name'): 'Vendor issuing the invoice, from the letterhead at the top of the page'}
# Held-out run 2 (declared 2026-10-02, before its corpus exists): --alias afe_number appends this sentence, byte for
# byte, to the afe_number description. One constant so the run can freeze it by hash.
# The short description is cut before its first full stop, so the sentence carries its own (run 2 plan, frozen).
ALIAS_AFE_NUMBER = '. The approval reference may appear under a different label.'

# Item 3 (declared 2026-09-29): a continuation page is a structural fact, so software decides it.
CONTINUATION = re.compile(r'\bpage\s+(\d+)\s+of\s+(\d+)\b', re.I)
CONTINUATION_WINDOW = 200     # the banner is a page header; a match deeper in the page is body text

def is_continuation(text):
    """True when the page header says 'page N of M' with N >= 2."""
    m = CONTINUATION.search(text[:CONTINUATION_WINDOW])
    return bool(m) and int(m.group(1)) >= 2 and int(m.group(2)) >= int(m.group(1))

def describe(cls, fields, desc):
    """Own-class description first; a decoy takes the description from the class that defines it."""
    m = {}
    for f in fields:
        if (cls, f) in desc:
            m[f] = desc[(cls, f)]
        else:
            homes = sorted(c for (c, g) in desc if g == f)
            if not homes:
                raise SystemExit(f'no schema describes field {f}')
            m[f] = desc[(homes[0], f)]
    return m

# ---------------------------------------------------------------- requests

def topic_labels(docs):
    """Manifest page -> topic (the document class). No ticket ordinal: that is page order, not a judgment."""
    return {(d['packet'], p): d['class'] for d in docs for p in d['pages']}

def make_requests(rows, docs, packets, page_text, truth, row8_mode, field_desc='none', option_desc='none',
                  unlabelled='none', continuation='model', truth_b=None, alias='none'):
    """truth_b: optional layer-B values {doc_id: values}. When given, row-8 labels come from B and each
    row-8 request also carries label_a (layer A), so the report can split out Pulse-dropped units.
    alias: 'afe_number' appends ALIAS_AFE_NUMBER to that field's row-8 description, in every request that asks it."""
    reqs = []
    od1, od4 = option_descriptions(option_desc) if option_desc != 'none' else (None, None)
    desc = field_descriptions(field_desc) if field_desc != 'none' else None
    if 1 in rows:
        for d in docs:
            reqs.append(dict(node='row1', shape='choice', subject=d['doc_id'],
                             options=CLASSES + [NEEDS_REVIEW], label=d['class'], option_descriptions=od1,
                             question='Which document class is this document?',
                             text=doc_text(d, page_text)))
    if 4 in rows:
        tl = topic_labels(docs)
        for pid, pk in packets.items():
            for p in range(1, pk['pages'] + 1):
                if continuation == 'software' and p > 1 and is_continuation(page_text[pid][p]):
                    # no model call: the page takes the decision made for the page before it
                    reqs.append(dict(node='row4', shape='choice', subject=f'{pid}:p{p}', software=True,
                                     inherit=f'{pid}:p{p - 1}', label=tl.get((pid, p), 'other')))
                    continue
                reqs.append(dict(node='row4', shape='choice', subject=f'{pid}:p{p}',
                                 options=TOPICS + [NEEDS_REVIEW], label=tl.get((pid, p), 'other'), option_descriptions=od4,
                                 question='Which topic does this page belong to?',
                                 text=page_text[pid][p][:MAX_PAGE_CHARS]))
    if 5 in rows:
        for pid, pk in packets.items():
            n_tickets = sum(1 for d in docs if d['packet'] == pid and d['class'] == 'field_ticket')
            reqs.append(dict(node='row5', shape='noul', subject=pid, label=n_tickets >= 2,
                             question='Does this packet contain a second field ticket?',
                             text='\n\n'.join(page_text[pid][p] for p in sorted(page_text[pid]))[:MAX_PAGE_CHARS]))
    if 8 in rows:
        for d in docs:
            fields = [f for f in REQUIRED[d['class']] if f not in BOOL_FIELDS] + DECOYS[d['class']]
            labels = {f: (truth[d['doc_id']].get(f) is not None and f not in DECOYS[d['class']]) for f in fields}
            layer = {}
            if truth_b is not None:
                layer_a = labels
                labels = {f: (truth_b[d['doc_id']].get(f) is not None and f not in DECOYS[d['class']]) for f in fields}
            dm = describe(d['class'], fields, desc) if desc else None
            if unlabelled == 'targeted':
                if not dm:
                    raise SystemExit('--unlabelled targeted needs --field-desc verbatim or short')
                dm.update({f: t for (c, f), t in UNLABELLED_TARGETED.items() if c == d['class'] and f in dm})
            if alias == 'afe_number':
                if not dm:
                    raise SystemExit('--alias afe_number needs --field-desc verbatim or short')
                if 'afe_number' in dm:
                    dm['afe_number'] += ALIAS_AFE_NUMBER     # dm is this document's own copy; desc is untouched
            hint = UNLABELLED_GENERIC if unlabelled in ('generic', 'generic-fixed') else ''
            # 'generic' ran the description into the sentence (no full stop after a short description). It is kept
            # byte-identical so the 2026-09-29 run stays reproducible. 'generic-fixed' closes the description first.
            join = unlabelled == 'generic-fixed'
            if row8_mode == 'per-document':
                if truth_b is not None:
                    layer = dict(label_a=layer_a)
                reqs.append(dict(node='row8', shape='noul-batch', subject=d['doc_id'], fields=fields, label=labels, descriptions=dm,
                                 question='For each named field, is a value for it printed in this document?' + hint, hint=hint, hint_join=join,
                                 text=doc_text(d, page_text), **layer))
            else:
                for f in fields:
                    if truth_b is not None:
                        layer = dict(label_a=layer_a[f])
                    reqs.append(dict(node='row8', shape='noul', subject=f'{d["doc_id"]}.{f}', label=labels[f],
                                     question=f'Is a value for the field "{f}" printed in this document?' + (f' The field means: {dm[f]}' if dm else '') + ('.' if join and dm and not dm[f].endswith('.') else '') + hint,
                                     text=doc_text(d, page_text), **layer))
    return reqs

def prompt_for(r):
    head = ('You answer one typed question about a document from a joint-interest billing month. '
            'Reply with ONLY a JSON object, no prose, no code fence.\n\n')
    if r['shape'] == 'choice':
        opts = (f'Options (unordered), with what each one means: {json.dumps(r["option_descriptions"])}' if r.get('option_descriptions')
                else f'Options (unordered): {json.dumps(r["options"])}')
        return (head + f'Question: {r["question"]}\n{opts}\n'
                'Return {"answer": <one option>, "probabilities": {<every option>: <number 0-1>}} with probabilities summing to 1. '
                'Use "needs_review" when the evidence is thin.\n\nDocument text:\n' + r['text'])
    if r['shape'] == 'noul':
        return (head + f'Question: {r["question"]}\nReturn {{"answer": true|false, "p_true": <number 0-1>}}.\n\nDocument text:\n' + r['text'])
    listing = (f'Fields, with what each one means: {json.dumps(r["descriptions"])}' if r.get('descriptions')
               else f'Fields: {json.dumps(r["fields"])}')
    return (head + f'Question: {r["question"]}\n{listing}\n'
            'Return {"fields": {<field>: {"answer": true|false, "p_true": <number 0-1>}}} with every field present.\n\nDocument text:\n' + r['text'])

# ---------------------------------------------------------------- parity (redo plan section 3)

DOC_MARK = '\n\nDocument text:\n'

def parity_sha256(parts):
    """sha256 over the four logical parts (question text, ordered options, definitions, document text).
    Same function for both backends; the parts are read back from what each backend sends."""
    q, opts, defs, doc = parts
    return hashlib.sha256(json.dumps([q, list(opts), defs, doc], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def claude_parity_parts(r):
    """{unit subject: parts} parsed from the claude prompt string. The head line, the output contract, and
    the 'Question:'/'Options'/'Fields' labels are wrapping and are dropped."""
    body, _, doc = prompt_for(r).partition(DOC_MARK)
    lines = body.split('\n')
    q = next(l for l in lines if l.startswith('Question: '))[len('Question: '):]
    if r['shape'] == 'choice':
        m = json.loads(next(l for l in lines if l.startswith('Options (unordered)')).split(': ', 1)[1])
        opts = list(m)
        return {r['subject']: (q, opts, [m[o] for o in opts] if isinstance(m, dict) else [None] * len(opts), doc)}
    if r['shape'] == 'noul':
        head, _, d = q.partition(jev.FIELD_MEANS)
        return {r['subject']: (head, [], d, doc)}
    m = json.loads(next(l for l in lines if l.startswith('Fields')).split(': ', 1)[1])
    return {f"{r['subject']}.{f}": (q, [], (m[f] if isinstance(m, dict) else ''), doc) for f in (list(m))}

def parity_hashes(r, backend, model=jev.MODEL):
    parts = jev.parity_parts(r, jev.build_request(r, model)) if backend == 'jev' else claude_parity_parts(r)
    return {k: parity_sha256(v) for k, v in parts.items()}

# ---------------------------------------------------------------- backends

def fixture_answer(r):
    """SYNTHETIC: the label with p=0.9, plus two plants that exercise the fail-closed and wrong paths."""
    if r['shape'] == 'choice':
        probs = {o: 0.0 for o in r['options']}
        ans = r['label']
        if r['node'] == 'row1' and r['subject'] == 'ticket_b':          # planted abstain
            probs[ans] = 0.55; probs[NEEDS_REVIEW] = 0.45
        elif r['node'] == 'row1' and r['subject'] == 'afe_cover':       # planted wrong, confident
            ans = 'afe'; probs['afe'] = 0.7; probs['afe_cover'] = 0.3
        else:
            probs[ans] = 0.9; probs[NEEDS_REVIEW] = 0.1
        return {'answer': ans, 'probabilities': probs}
    if r['shape'] == 'noul':
        if r['node'] == 'row5' and r['subject'] == 'day01':                # planted abstain
            return {'answer': False, 'p_true': 0.5}
        if r['node'] == 'row5' and r['subject'] == 'day30':                # planted wrong, confident
            return {'answer': True, 'p_true': 0.9}
        return {'answer': bool(r['label']), 'p_true': 0.9 if r['label'] else 0.1}
    return {'fields': {f: {'answer': bool(v), 'p_true': 0.9 if v else 0.1} for f, v in r['label'].items()}}

SYSTEM_PROMPT = ('You are a typed-question answerer inside a document pipeline. You have no tools. '
                 'Reply with only the JSON object requested; never prose, never a code fence.')

def ask_model(prompt, model=None, timeout=180, cwd=None):
    """One `claude -p` call, isolated: no tools, no settings sources, no session persistence, empty cwd.
    Returns (parsed_json_or_None, envelope_dict, error_str). Errors live in the stdout envelope."""
    cmd = ['claude', '-p', '--output-format', 'json', '--tools', '', '--setting-sources', '',
           '--no-session-persistence', '--system-prompt', SYSTEM_PROMPT]
    if model:
        cmd += ['--model', model]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                              env={k: v for k, v in os.environ.items() if k != jev.KEY_ENV})   # the Jev key never reaches claude
    except subprocess.TimeoutExpired:
        return None, {'duration_ms': int((time.time() - t0) * 1000)}, f'timeout after {timeout}s'
    except FileNotFoundError:
        return None, {'duration_ms': 0}, 'claude CLI not found on PATH'
    env = None
    try:
        env = json.loads(proc.stdout)
    except Exception:
        pass
    if not isinstance(env, dict):
        return None, {'raw_stdout': proc.stdout[-500:], 'stderr': proc.stderr[-500:], 'duration_ms': int((time.time() - t0) * 1000)}, 'unparseable envelope'
    env.setdefault('duration_ms', int((time.time() - t0) * 1000))
    if proc.returncode != 0 or env.get('is_error'):
        return None, env, str(env.get('result') or proc.stderr or 'exit %d' % proc.returncode)
    if (env.get('num_turns') or 1) > 1:
        return None, env, f'num_turns {env.get("num_turns")}: the model took a turn it should not have'
    text = (env.get('result') or '').strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    try:
        return json.loads(text), env, None
    except Exception:
        return None, env, 'model returned no JSON: ' + text[:200]

# ---------------------------------------------------------------- scoring

class Malformed(ValueError):
    """A model reply that does not meet the contract. Scored as an error, never as an answer."""

def _prob(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x or not (0.0 <= x <= 1.0):
        raise Malformed(f'probability not a real number in [0,1]: {x!r}')
    return float(x)

def _unit(final, p, abstain, label, top=None, **extra):
    """top = the model's top answer before any threshold (best option; p >= 0.5 for a noul). top_correct is the
    plan's threshold-free headline (section 3): top answer equals the label."""
    return dict(final=final, p=p, abstain=abstain, correct=(not abstain and final == label),
                wrong_not_abstained=(not abstain and final != label), error=False,
                top=top, top_correct=(top is not None and top == label), **extra)

ERROR_UNIT = dict(final=None, p=None, abstain=False, correct=False, wrong_not_abstained=False, error=True,
                  top=None, top_correct=False)

def score_choice(ans, options, label, disagree_abstain=True):
    if not isinstance(ans, dict):
        raise Malformed('reply is not an object')
    probs = ans.get('probabilities')
    if not isinstance(probs, dict) or not probs:
        raise Malformed('probabilities missing or empty')
    if set(probs) - set(options):
        raise Malformed(f'keys outside the option set: {sorted(set(probs) - set(options))}')
    probs = {k: _prob(v) for k, v in probs.items()}
    if abs(sum(probs.values()) - 1.0) > 0.05:
        raise Malformed(f'probabilities sum to {sum(probs.values()):.3f}')
    best = max(probs, key=probs.get)
    pmax = probs[best]
    disagree = ans.get('answer') is not None and ans.get('answer') != best
    abstain = best == NEEDS_REVIEW or pmax < CHOICE_FLOOR or (disagree and disagree_abstain)
    final = NEEDS_REVIEW if abstain else best
    return _unit(final, pmax, abstain, label, top=best, disagree=disagree)

def score_noul(a, label, disagree_abstain=True):
    if not isinstance(a, dict):
        raise Malformed('reply is not an object')
    p = _prob(a.get('p_true'))
    ans = a.get('answer')
    if not isinstance(ans, bool):
        raise Malformed(f'answer not a boolean: {ans!r}')
    disagree = ans != (p >= 0.5)
    abstain = (NOUL_LO < p < NOUL_HI) or (disagree and disagree_abstain)
    final = None if abstain else (p >= NOUL_HI)
    return _unit(final, p, abstain, label, top=(p >= 0.5), disagree=disagree)

def score(r, ans, disagree_abstain=True):
    """Deterministic code owns validation and the threshold; the model only supplied numbers.
    Raises Malformed on any contract breach; the caller records an error unit, never an answer.
    disagree_abstain=False (parity mode) keeps the disagree flag but no longer forces an abstain."""
    if r['shape'] == 'choice':
        return score_choice(ans, r['options'], r['label'], disagree_abstain)
    if r['shape'] == 'noul':
        return score_noul(ans, r['label'], disagree_abstain)
    if not isinstance(ans, dict) or not isinstance(ans.get('fields'), dict):
        raise Malformed('fields object missing')
    per = {}
    for f, lab in r['label'].items():
        a = ans['fields'].get(f)
        if a is None:
            per[f] = dict(ERROR_UNIT, missing=True)
            continue
        try:
            per[f] = score_noul(a, lab, disagree_abstain)
        except Malformed as e:
            per[f] = dict(ERROR_UNIT, reason=str(e))
    return dict(fields=per)

def flatten(calls):
    """One scored unit per question (row8 batches expand to one unit per field)."""
    units = []
    for c in calls:
        s = c['score']
        if 'fields' in s:
            la = c.get('label_a')
            for f, u in s['fields'].items():
                units.append(_layers(dict(node=c['node'], subject=f"{c['subject']}.{f}", **u),
                                     la.get(f) if la is not None else None, c['label'].get(f)))
        else:
            units.append(_layers(dict(node=c['node'], subject=c['subject'], **s), c.get('label_a'), c.get('label')))
    return units

def _layers(u, la, lb):
    """Layer A (keyed from the page) against layer B (keyed from the Pulse extract). A present and B absent:
    Pulse dropped the value, so the unit leaves correct/abstain/wrong. A absent and B present: flagged."""
    if la is None:
        return u
    if la and not lb:
        if u.get('error'):
            u['dropped_error'] = u.get('reason') or True      # kept for the record; no gate counts it
        u.update(pulse_dropped=True, correct=False, abstain=False, wrong_not_abstained=False, error=False, top_correct=False)
    elif lb and not la:
        u['extract_invented'] = True
    return u

def report(calls, mode, meta):
    units = flatten(calls)
    layered = any('label_a' in c for c in calls)
    nodes = {}
    for u in units:
        n = nodes.setdefault(u['node'], dict(n=0, correct=0, abstain=0, wrong_not_abstained=0, error=0, top_correct=0,
                                             **(dict(pulse_dropped=0, scored=0) if layered else {})))
        n['n'] += 1; n['correct'] += u['correct']; n['abstain'] += u['abstain']
        n['wrong_not_abstained'] += u['wrong_not_abstained']; n['error'] += int(bool(u.get('error')))
        n['top_correct'] += int(bool(u.get('top_correct')))
        if layered:
            n['pulse_dropped'] += int(bool(u.get('pulse_dropped')))
            n['scored'] = n['n'] - n['pulse_dropped']
    if layered:
        meta = dict(meta, pulse_dropped=[u['subject'] for u in units if u.get('pulse_dropped')],
                    extract_invented=[u['subject'] for u in units if u.get('extract_invented')])
    lat = [c['latency_ms'] for c in calls if c.get('latency_ms') is not None]
    toks_in = sum((c.get('usage') or {}).get('input_tokens', 0) for c in calls)
    toks_out = sum((c.get('usage') or {}).get('output_tokens', 0) for c in calls)
    cost = sum(c.get('cost_usd') or 0 for c in calls)
    rep = dict(mode=mode, synthetic=(mode == 'fixture'), calls=len(calls), units=len(units), nodes=nodes,
               latency_ms_p50=(statistics.median(lat) if lat else None), latency_ms_max=(max(lat) if lat else None),
               tokens_in=toks_in, tokens_out=toks_out, cost_usd=cost,
               thresholds=dict(choice_floor=CHOICE_FLOOR, noul_lo=NOUL_LO, noul_hi=NOUL_HI), **meta)
    return rep, units

def report_md(rep):
    is_jev = str(rep.get('backend', '')).startswith('jev')
    cas = rep.get('cascade')
    banner = ('**SYNTHETIC — fixture answers prove the code paths, not any model.**' if rep['synthetic']
              else f"**Live {rep.get('backend')} run — model-reported probabilities, uncalibrated.**")
    basis = ('SYNTHETIC, no spend' if rep['synthetic']
             else 'Jev half METERED, `usage.input_tokens` at $0.042 per million; Claude half below' if cas
             else 'METERED: `usage.input_tokens` at $0.042 per million, docs.typesafe.ai/models' if is_jev
             else 'envelope `total_cost_usd`: list-price estimate, not billed under a subscription')
    if rep.get('stopped'):
        banner += f"\n\n**INCOMPLETE: stopped early ({rep['stopped']}); {rep['calls']} of {rep.get('planned_calls')} calls ran.**"
    L = [f"# Typed questions — {rep['run_id']} ({rep['mode']}, {rep['stamp']})", '', banner, '',
         f"Calls {rep['calls']} · scored units {rep['units']} · latency p50 {rep['latency_ms_p50']} ms · "
         f"tokens in/out {rep['tokens_in']}/{rep['tokens_out']} · cost ${rep['cost_usd']:.6f} ({basis}) · "
         f"**errors {rep['errors']}** (malformed replies or backend failures; scored as neither answer nor abstain)", '',
         'Row 1 uses manifest document boundaries (oracle segmentation), so it is easier than a pipeline where row 4 feeds it. '
         'Row 8 negatives are decoy fields from other document classes; boolean selection-mark fields are excluded.', '',
         f"Thresholds (frozen 2026-09-29): choice floor {CHOICE_FLOOR}, noul abstain band ({NOUL_LO}, {NOUL_HI}).", '']
    layered = 'pulse_dropped' in rep
    if rep.get('parity'):
        L += ['Parity mode: short field text, verbatim option text, row 8 one field per call for claude, '
              'disagree no longer forces an abstain; `parity_sha256` per unit in calls.jsonl.', '']
        if rep.get('claude_row8') == 'per-document':
            L += ['**Batched arm (`--claude-row8 per-document`): claude answers row 8 one call per document, not per field.**', '']
    if rep.get('alias', 'none') != 'none':
        L += [f"**Alias arm (`--alias {rep['alias']}`): the afe_number description ends with \"{ALIAS_AFE_NUMBER[2:]}\"**", '']
    if layered:
        L += [f"Row 8 scored against layer-B truth (`{rep.get('truth_b')}`). Pulse-dropped units (layer A present, "
              'layer B absent) are excluded from correct, abstain, and wrong.', '']
    L += ['| Node | Shape | n | correct | abstain | wrong, not abstained | error | top = label |' + (' Pulse-dropped | scored |' if layered else ''),
          '|---|---|---|---|---|---|---|---|' + ('---|---|' if layered else '')]
    shapes = {'row1': 'choice', 'row4': 'choice', 'row5': 'noul', 'row8': 'noul'}
    for k in sorted(rep['nodes']):
        v = rep['nodes'][k]
        L.append(f"| {k} | {shapes.get(k, '')} | {v['n']} | {v['correct']} | {v['abstain']} | {v['wrong_not_abstained']} | {v['error']} | {v['top_correct']} |"
                 + (f" {v['pulse_dropped']} | {v['scored']} |" if layered else ''))
    if layered:
        L += ['', f"Pulse-dropped ({len(rep['pulse_dropped'])}): {', '.join(rep['pulse_dropped']) or 'none'}",
              f"Extract-invented ({len(rep['extract_invented'])}, layer A absent, layer B present): {', '.join(rep['extract_invented']) or 'none'}"]
    if cas:
        w, lat = cas['wrong_not_abstained_by'], cas['latency_ms_sum']
        L += ['', '## Cascade (one run: Jev first, Claude on escalation, a person on abstain)', '',
              f"Escalate when Jev's top probability < {cas['escalate_below']} ({cas['escalate_metric']}).", '',
              '| Measure | Value |', '|---|---|',
              f"| Units answered by Jev | {cas['units_answered_by_jev']} |",
              f"| Units escalated to Claude | {cas['units_escalated']} ({', '.join(f'{k} {v}' for k, v in sorted(cas['escalated_by_node'].items())) or 'none'}) |",
              f"| Escalated by reason | {', '.join(f'{k} {v}' for k, v in sorted(cas['escalated_by_reason'].items())) or 'none'} |",
              f"| Jev requests that errored | {cas['jev_errors']} |",
              f"| Claude calls made | {cas['claude_calls']} |",
              f"| Top answer = label, Jev half / Claude half | {cas['top_correct_by_half']['jev']} of {cas['top_correct_by_half']['jev_n']} / "
              f"{cas['top_correct_by_half']['claude']} of {cas['top_correct_by_half']['claude_n']} |",
              f"| Jev requests made | {cas['jev_requests']} |",
              f"| Wrong, not abstained: answered by Jev / by Claude | {w['jev']} / {w['claude']} |",
              f"| Units sent to a person (abstain + error) | {cas['units_to_person']} ({cas['units_to_person_abstain']} + {cas['units_to_person_error']}) |",
              f"| Escalated units Claude abstained on | {cas['escalated_abstain']} |",
              f"| Typed-call latency sum, Jev / Claude | {lat['jev']} ms / {lat['claude']} ms |",
              f"| Jev billed | {cas['jev_billed_tokens']} tokens, ${cas['jev_billed_usd']:.6f} ({cas['jev_basis']}) |", '',
              f"Claude cost basis: {cas['claude_cost_basis']}", '', cas['h4']]
    L += ['', '`top = label` is the threshold-free headline: the top answer (best option; p >= 0.5 for yes/no) equals '
          'the label, whatever the thresholds decide. Pulse-dropped units are excluded from it and from every other column but n.']
    L += ['', 'Reading: `correct` requires a non-abstained answer equal to the label; `abstain` is the fail-closed path; '
          '`wrong, not abstained` is the number that matters, because it is what a silent pipeline would have passed through.']
    return '\n'.join(L) + '\n'

# ---------------------------------------------------------------- cascade (redo plan section 2, arm C; D-239)

ESCALATE_BELOW = 0.80    # declared in the plan before any run, read off the 2026-09-29 data; frozen
def model_mismatch(requested, served):
    """Loose served-model check: log, never fail (an alias may differ from the served id). A mismatch means
    served is known and, for every served id, neither string contains the other after lower-casing and dropping
    a date suffix like -20251001. served may join several modelUsage keys with commas."""
    if not served or not requested:
        return False
    norm = lambda m: re.sub(r'-\d{8}$', '', m.strip().lower())
    r = norm(requested)
    return not any(r in norm(m) or norm(m) in r for m in served.split(','))

ESCALATE_METRIC = 'top probability: highest option probability (choice); max(p, 1 - p) (noul)'
# SYNTHETIC cascade plants on the Jev half only: one row-8 escalation (0.75) and one unit on the line (0.80, not escalated).
# Row 1 (ticket_b 0.55, afe_cover 0.70) and row 5 (day01 0.50) escalate from the shared fixture plants.
CASCADE_PLANTS = {('invoice', 'vendor_name'): 0.75, ('invoice', 'total'): 0.80}

def top_probability(shape, s):
    """From a scored unit (s['p'] is the validated max option probability for a choice, p_true for a noul)."""
    return s['p'] if shape == 'choice' else max(s['p'], 1.0 - s['p'])

def escalates(top, line):
    return top < line        # strictly under the line: 0.79 escalates, 0.80 does not

def cascade_fixture_answer(r):
    ans = fixture_answer(r)
    if r['shape'] == 'noul-batch':
        for f in r['fields']:
            p = CASCADE_PLANTS.get((r['subject'], f))
            if p is not None:
                ans['fields'][f] = {'answer': p >= 0.5, 'p_true': p}
    elif r['node'] == 'row8' and tuple(r['subject'].split('.', 1)) in CASCADE_PLANTS:
        p = CASCADE_PLANTS[tuple(r['subject'].split('.', 1))]
        ans = {'answer': p >= 0.5, 'p_true': p}
    return ans

def jev_units(r, ans):
    """[(unit subject, shape, label, label_a or None, scored unit or error unit)] from one Jev reply (None = request error)."""
    out = []
    if r['shape'] == 'noul-batch':
        for f in r['fields']:
            la = r['label_a'][f] if 'label_a' in r else None
            a = (ans or {}).get('fields', {}).get(f) if ans is not None else None
            try:
                s = score_noul(a, r['label'][f], False) if a is not None else dict(ERROR_UNIT, reason='jev: no answer for field')
            except Malformed as e:
                s = dict(ERROR_UNIT, reason=f'jev malformed: {e}')
            out.append((f"{r['subject']}.{f}", 'noul', r['label'][f], la, s))
        return out
    try:
        s = score(r, ans, disagree_abstain=False) if ans is not None else dict(ERROR_UNIT, reason='jev: no answer')
    except Malformed as e:
        s = dict(ERROR_UNIT, reason=f'jev malformed: {e}')
    return [(r['subject'], r['shape'], r['label'], r.get('label_a'), s)]

def cascade_compare_hashes(path, jreqs, bodies, creqs):
    """(summary dict, all equal) against a recorded cascade calls.jsonl: every Jev request body in order, and the
    Claude prompt of every unit the recorded run escalated (only those were sent). Dry-run only; no network."""
    recs = [json.loads(l) for l in open(path)]
    rj = [c['prompt_sha256'] for c in recs if c.get('kind') == 'jev_request']
    mj = [hashlib.sha256(json.dumps(b, sort_keys=True).encode()).hexdigest() for b in bodies]
    jm = sum(1 for x, y in zip(mj, rj) if x == y)
    asked = [c for c in recs if c.get('kind') == 'unit' and (c.get('claude') or {}).get('asked')]
    cm = sum(1 for c in asked if (c['node'], c['subject']) in creqs and c['claude'].get('prompt_sha256') ==
             hashlib.sha256(prompt_for(creqs[(c['node'], c['subject'])]).encode()).hexdigest())
    return (dict(hash_match=f'{jm} of {max(len(mj), len(rj))}', claude_hash_match=f'{cm} of {len(asked)}', hash_source=path),
            jm == len(mj) == len(rj) and cm == len(asked))

def run_cascade(a, jall, call, run_dir, rows):
    """Arm C as one run: Jev answers every unit; a unit whose Jev top probability is under the line (or whose Jev
    answer is an error) goes to Claude as one per-field parity call; Claude's frozen thresholds decide; an abstain
    or an error goes to a person. --cap counts Jev requests plus Claude calls together."""
    import tempfile
    line, live = a.escalate_below, a.mode == 'live'
    if not live:
        jev.install_socket_guard()
    soft = [r for r in jall if r.get('software')]
    jreqs = [r for r in jall if not r.get('software')]
    # keyed by (node, subject): a packet id may equal a document id (row 5 vs row 1), as in synth-pilot
    creqs = {(r['node'], r['subject']): r for r in call if not r.get('software')}
    try:
        bodies = [jev.build_request(r, a.jev_model) for r in jreqs]
    except jev.JevShape as e:
        print(f'refusing: {e}', file=sys.stderr); return 2
    jh = {}
    for r, b in zip(jreqs, bodies):
        jh.update({(r['node'], k): parity_sha256(v) for k, v in jev.parity_parts(r, b).items()})
    chh = {(n, s): parity_sha256(claude_parity_parts(r)[s]) for (n, s), r in creqs.items()}
    bad = sorted(s for s in set(jh) | set(chh) if jh.get(s) != chh.get(s))
    if bad:
        print(f'refusing: parity broken on {len(bad)} units, first {bad[0]}', file=sys.stderr); return 2
    if not (a.max_spend == a.max_spend and 0 <= a.max_spend < float('inf')):
        print(f'refusing: --max-spend {a.max_spend!r} is not a finite non-negative number', file=sys.stderr); return 2
    est, bound = sum(jev.est_tokens(b) for b in bodies), sum(jev.max_tokens(b) for b in bodies)
    if jev.usd(bound) > a.max_spend:
        print(f'refusing: Jev upper-bound cost ${jev.usd(bound):.6f} exceeds --max-spend ${a.max_spend:.4f}', file=sys.stderr); return 2
    alias_tag = f'-alias-{a.alias}' if a.alias != 'none' else ''      # --claude-row8 is ignored here, so it has no tag
    if a.mode == 'dry-run':
        cmp, same = cascade_compare_hashes(a.compare_hashes, jreqs, bodies, creqs) if a.compare_hashes else ({}, True)
        print(json.dumps(dict(mode='dry-run', backend='cascade', jev_model=a.jev_model, model_requested=a.model,
                              escalate_below=line, escalate_metric=ESCALATE_METRIC, requests=len(jreqs),
                              questions=sum(len(b['questions']) for b in bodies), est_input_tokens=est,
                              est_cost_usd=round(jev.usd(est), 6), bound_input_tokens=bound, bound_cost_usd=round(jev.usd(bound), 6),
                              claude_calls_upper_bound=len(creqs), calls_upper_bound=len(jreqs) + len(creqs),
                              parity=f'{len(jh)} of {len(jh)}', software_units=len(soft), max_spend=a.max_spend, cap=a.cap,
                              key_ready=jev.key_status()[0], socket_guard=jev.GUARD['installed'], network_calls=0,
                              alias=a.alias, tag=f'cascade-{line:.2f}{alias_tag}', **cmp)))
        return 0 if same else 1
    key = None
    if live:
        if len(jreqs) > a.cap:
            print(f'refusing: {len(jreqs)} Jev requests alone exceed --cap {a.cap}', file=sys.stderr); return 2
        ok, msg = jev.key_status()
        print(f'preflight: {msg}', file=sys.stderr)
        if not ok:
            return 2
        key = os.environ[jev.KEY_ENV]
        ok, msg = jev.auth_check(key)
        print(f'preflight: {msg}', file=sys.stderr)
        if not ok:
            return 2
        st = subprocess.run(['claude', 'auth', 'status'], capture_output=True, text=True,
                            env={k: v for k, v in os.environ.items() if k != jev.KEY_ENV})
        try:
            if not json.loads(st.stdout).get('loggedIn'):
                raise ValueError
        except Exception:
            print('preflight failed: `claude auth status` does not report loggedIn; run `claude auth login`', file=sys.stderr); return 2
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = pathlib.Path(a.out) if a.out else run_dir / 'typed' / f'{a.mode}-cascade-{line:.2f}{alias_tag}-{stamp}'
    out.mkdir(parents=True, exist_ok=True)
    iso_cwd = tempfile.mkdtemp(prefix='typed-iso-')
    units, made, n_jev, n_claude, spent, jtoks, stop = [], 0, 0, 0, 0.0, 0, None
    # one breaker per half: a Claude success must never reset a run of Jev failures, and the reverse (review finding 1)
    cons = dict(jev=0, claude=0)
    n_jev_err = 0
    lat = dict(jev=0, claude=0)
    claude_est, jcost = 0.0, 0.0
    with open(out / 'calls.jsonl', 'w') as fh, open(out / 'prompts.jsonl', 'w') as pf:
        def emit(rec):
            fh.write(json.dumps(rec) + '\n'); fh.flush(); pf.flush()     # a TERM from the watchdog loses nothing written
        for i, (r, body) in enumerate(zip(jreqs, bodies), 1):
            if stop:
                break
            if max(cons.values()) >= MAX_CONSECUTIVE_ERRORS:
                break
            if made >= a.cap:
                stop = f'cap: {made} calls made (Jev requests plus Claude calls) reached --cap {a.cap}'; break
            if live and spent + jev.usd(jev.max_tokens(body)) > a.max_spend:
                stop = f'spend cap: Jev request {i} could pass --max-spend ${a.max_spend:.4f} (spent ${spent:.6f})'; break
            sent = json.dumps(body, sort_keys=True)
            pf.write(json.dumps(dict(backend='jev', request=i, prompt=sent)) + '\n')
            if live:
                ans, env, err = jev.ask(r, key, a.jev_model)
                spent += env.get('total_cost_usd') or 0
            else:
                try:
                    ans, toks, _ = jev.parse_response(r, jev.fixture_response(r, cascade_fixture_answer(r), a.jev_model))
                    env, err = {'duration_ms': 0, 'synthetic': True, 'usage': {'input_tokens': toks, 'output_tokens': 0}}, None
                except jev.JevShape as e:
                    ans, env, err = None, {'duration_ms': 0, 'synthetic': True}, f'API SHAPE MISMATCH: {e}'
            made += 1; n_jev += 1
            lat['jev'] += env.get('duration_ms') or 0
            jtoks += (env.get('usage') or {}).get('input_tokens', 0)
            jcost += env.get('total_cost_usd') or 0
            if err or ans is None:
                cons['jev'] += 1; n_jev_err += 1
                if cons['jev'] >= MAX_CONSECUTIVE_ERRORS:
                    stop = f'circuit breaker: {cons["jev"]} consecutive Jev errors'
            else:
                cons['jev'] = 0
            emit(dict(kind='jev_request', request=i, node=r['node'], subject=r['subject'], prompt_sha256=hashlib.sha256(sent.encode()).hexdigest(),
                      latency_ms=env.get('duration_ms'), usage=env.get('usage'), cost_usd=env.get('total_cost_usd'),
                      http_status=env.get('http_status'), served_model=env.get('model'), response=env.get('response'), error=err))
            if live:
                print(f'[jev {i}/{len(jreqs)}] {r["node"]} {r["subject"]} {"ERR " + err if err else "ok"}', file=sys.stderr, flush=True)
                billed = (env.get('usage') or {}).get('input_tokens', 0)
                if billed > env.get('request_bound_tokens', float('inf')):
                    stop = f'bound falsified: billed {billed} tokens > body bound {env["request_bound_tokens"]}'
                if spent > a.max_spend:
                    stop = stop or f'spend cap: spent ${spent:.6f} passed --max-spend ${a.max_spend:.4f}'
            for subj, shape, label, la, js in jev_units(r, None if err else ans):
                top = None if js.get('error') else top_probability(shape, js)
                esc = js.get('error') or escalates(top, line)
                rec = dict(kind='unit', node=r['node'], shape=shape, subject=subj, label=label, jev_request=i,
                           jev=dict(p_top=top, decision=('error' if js.get('error') else 'abstain' if js['abstain'] else 'answer'),
                                    final=js.get('final'), p=js.get('p'), top=js.get('top'), top_correct=js.get('top_correct'),
                                    escalated=bool(esc),
                                    escalate_reason=('jev_error' if js.get('error') else 'below_line' if esc else None),
                                    error=js.get('reason')),
                           parity_sha256=dict(jev=jh[(r['node'], subj)], claude=chh[(r['node'], subj)]))
                if la is not None:
                    rec['label_a'] = la
                if not esc:
                    rec.update(answered_by='jev', score=dict(js, answered_by='jev'))
                elif stop or made >= a.cap:
                    stop = stop or f'cap: {made} calls made (Jev requests plus Claude calls) reached --cap {a.cap}'
                    rec.update(answered_by='claude', score=dict(ERROR_UNIT, reason='not asked: run stopped', answered_by='claude'),
                               claude=dict(asked=False))
                else:
                    cr = creqs[(r['node'], subj)]
                    prompt = prompt_for(cr)
                    pf.write(json.dumps(dict(backend='claude', unit=subj, prompt=prompt)) + '\n')
                    if live:
                        cans, cenv, cerr = ask_model(prompt, a.model, cwd=iso_cwd)
                        print(f'[claude] {r["node"]} {subj} {"ERR " + cerr if cerr else "ok"}', file=sys.stderr, flush=True)
                    else:
                        cans, cenv, cerr = fixture_answer(cr), {'duration_ms': 0, 'synthetic': True}, None
                    made += 1; n_claude += 1
                    lat['claude'] += cenv.get('duration_ms') or 0
                    claude_est += cenv.get('total_cost_usd') or 0
                    if cerr or cans is None:
                        cs = dict(ERROR_UNIT, reason=cerr or 'no answer'); cons['claude'] += 1
                    else:
                        try:
                            cs = score(cr, cans, disagree_abstain=False); cons['claude'] = 0
                        except Malformed as e:
                            cs = dict(ERROR_UNIT, reason=f'malformed: {e}'); cons['claude'] += 1
                    mu = cenv.get('modelUsage')
                    rec.update(answered_by='claude', score=dict(cs, answered_by='claude'),
                               claude=dict(asked=True, answer=cans, final=cs.get('final'), p=cs.get('p'), abstain=cs.get('abstain'),
                                           top=cs.get('top'), top_correct=cs.get('top_correct'),
                                           error=cerr or cs.get('reason'), latency_ms=cenv.get('duration_ms'), usage=cenv.get('usage'),
                                           cost_usd_estimate=cenv.get('total_cost_usd'), model_requested=a.model,
                                           served_model=(','.join(sorted(mu)) if isinstance(mu, dict) and mu else None),
                                           prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest()))
                    if model_mismatch(a.model, rec['claude']['served_model']):
                        rec['claude']['model_mismatch'] = True
                    if cons['claude'] >= MAX_CONSECUTIVE_ERRORS:
                        stop = stop or f'circuit breaker: {cons["claude"]} consecutive Claude errors'
                units.append(rec); emit(rec)
        for r in soft:
            prev = next((u for u in units if u['node'] == r['node'] and u['subject'] == r['inherit']), None)
            ps = prev['score'] if prev else None
            sc = (dict(ERROR_UNIT, reason=f'nothing to inherit from {r["inherit"]}') if not ps or ps.get('error')
                  else _unit(ps['final'], ps['p'], ps['abstain'], r['label'], top=ps.get('top'), inherited=r['inherit']))
            rec = dict(kind='unit', node=r['node'], shape=r['shape'], subject=r['subject'], label=r['label'], software=True,
                       inherit=r['inherit'], answered_by='software', score=dict(sc, answered_by='software'))
            units.append(rec); emit(rec)
    if stop:
        print(f'{stop}; stopping', file=sys.stderr)
    planned = sum(len(b['questions']) for b in bodies) + len(soft)
    errors = sum(1 for u in units if u['score'].get('error'))
    rep, flat = report(units, a.mode, dict(run_id=run_dir.name, stamp=stamp, rows=sorted(rows), row8_mode='jev per-document, claude per-field',
                                           backend=f'cascade jev {a.jev_model} -> claude -p' + (f' --model {a.model}' if a.model else ''),
                                           errors=errors, planned_calls=planned, stopped=stop, field_desc=a.field_desc, option_desc=a.option_desc,
                                           unlabelled=a.unlabelled, continuation=a.continuation, model_calls=made, software_units=len(soft),
                                           parity=True, disagree_abstain=False, corpus_set=str(a.set) if a.set else 'synth', truth_b=a.truth_b,
                                           model_requested=a.model, jev_model=a.jev_model, alias=a.alias, claude_row8='per-field',
                                           served_models=sorted({u['claude']['served_model'] for u in units if (u.get('claude') or {}).get('served_model')}),
                                           model_mismatches=sum(1 for u in units if (u.get('claude') or {}).get('model_mismatch'))))
    by = lambda who, k: sum(1 for u in flat if u.get('answered_by') == who and u.get(k))
    esc_units = [u for u in units if u.get('jev', {}).get('escalated')]
    alone = len(creqs)
    fk = {(u['node'], u['subject']): u for u in flat}           # layered view: a Pulse-dropped unit counts in no gate
    live_u = lambda u: not fk[(u['node'], u['subject'])].get('pulse_dropped')
    esc_reason = {}
    for u in esc_units:
        esc_reason[u['jev']['escalate_reason']] = esc_reason.get(u['jev']['escalate_reason'], 0) + 1
    jev_half = [u for u in units if 'jev' in u and u['jev']['decision'] != 'error' and live_u(u)]
    claude_half = [u for u in esc_units if (u.get('claude') or {}).get('asked') and live_u(u)]
    billed_toks = jtoks if a.mode == 'live' else 0     # fixture tokens are an estimate, never a bill
    rep.update(calls=made, tokens_in=jtoks, tokens_out=0, cost_usd=jcost,
               latency_ms_p50=None, latency_ms_max=None,
               cascade=dict(escalate_below=line, escalate_metric=ESCALATE_METRIC,
                            units_answered_by_jev=sum(1 for u in units if u.get('answered_by') == 'jev'),
                            units_escalated=len(esc_units),
                            escalated_by_node={n: sum(1 for u in esc_units if u['node'] == n) for n in sorted({u['node'] for u in esc_units})},
                            escalated_units=[u['subject'] for u in esc_units],
                            claude_calls=n_claude, jev_requests=n_jev,
                            wrong_not_abstained_by=dict(jev=by('jev', 'wrong_not_abstained'), claude=by('claude', 'wrong_not_abstained'),
                                                        software=by('software', 'wrong_not_abstained')),
                            units_to_person=sum(1 for u in flat if u.get('abstain') or u.get('error')),
                            units_to_person_abstain=sum(1 for u in flat if u.get('abstain')),
                            units_to_person_error=sum(1 for u in flat if u.get('error')),
                            escalated_abstain=sum(1 for u in esc_units if fk[(u['node'], u['subject'])].get('abstain')),
                            escalated_by_reason=esc_reason, jev_errors=n_jev_err,
                            top_correct_by_half=dict(jev=sum(1 for u in jev_half if u['jev'].get('top_correct')), jev_n=len(jev_half),
                                                     claude=sum(1 for u in claude_half if u['claude'].get('top_correct')), claude_n=len(claude_half)),
                            latency_ms_sum=lat, jev_billed_tokens=billed_toks, jev_billed_usd=jcost,
                            jev_basis=('SYNTHETIC, no spend (tokens_in is the fixture estimate)' if a.mode == 'fixture'
                                       else 'METERED: usage.input_tokens at $0.042 per million'),
                            claude_cost_basis=('SYNTHETIC, no spend' if a.mode == 'fixture' else
                                               f'`claude -p` on the subscription, $0 billed; envelope `total_cost_usd` sums to '
                                               f'${claude_est:.6f}, a list-price estimate, not billed under a subscription'),
                            claude_cost_estimate_usd=claude_est, claude_alone_calls=alone,
                            h4=f'H4: Claude calls in cascade = {n_claude}, Claude-alone calls would be {alone}'))
    (out / 'report.json').write_text(json.dumps(rep, indent=1))
    (out / 'report.md').write_text(report_md(rep))
    c = rep['cascade']
    print(json.dumps(dict(out=str(out), calls=made, units=len(flat), errors=errors, nodes=rep['nodes'],
                          escalated=c['escalated_by_node'], escalated_by_reason=c['escalated_by_reason'], jev_errors=c['jev_errors'],
                          top_correct={k: v['top_correct'] for k, v in rep['nodes'].items()}, top_correct_by_half=c['top_correct_by_half'],
                          escalated_abstain=c['escalated_abstain'], claude_calls=n_claude,
                          jev_requests=n_jev, h4=c['h4'])))
    return 3 if stop else 0

# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default='runs/live-synth-03')
    ap.add_argument('--mode', choices=['fixture', 'dry-run', 'live', 'parity-check'], default='fixture')
    ap.add_argument('--set', default=None, help='corpus dir holding manifest.json and truth/; default: synth/manifest.json + truth/synth')
    ap.add_argument('--truth-b', default=None, help='layer-B truth dir (keyed from the Pulse extract); row 8 is scored against it')
    ap.add_argument('--parity', action='store_true',
                    help='parity contract: --field-desc short --option-desc verbatim, row 8 per field for claude, disagree-abstain off')
    ap.add_argument('--compare-hashes', default=None, help='dry-run: compare every request hash with prompt_sha256 in this calls.jsonl')
    ap.add_argument('--rows', default='1,4,5,8')
    ap.add_argument('--row8', choices=['per-document', 'per-field'], default='per-document')
    ap.add_argument('--cap', type=int, default=40, help='live: refuse to make more calls than this')
    ap.add_argument('--model', default=None, help='live: passed to claude -p --model; default = CLI default')
    ap.add_argument('--field-desc', choices=['none', 'verbatim', 'short'], default='none',
                    help='row 8: send each field\'s schema description with the question')
    ap.add_argument('--option-desc', choices=['none', 'verbatim', 'short'], default='none',
                    help='rows 1 and 4: send each option\'s config description with the question')
    ap.add_argument('--unlabelled', choices=['none', 'generic', 'generic-fixed', 'targeted'], default='none',
                    help='row 8: say that an unlabelled value counts as printed (generic), or name the place for one field (targeted)')
    ap.add_argument('--continuation', choices=['model', 'software'], default='model',
                    help='row 4: software decides a page whose header says page N of M, N >= 2')
    ap.add_argument('--claude-row8', choices=['per-field', 'per-document'], default='per-field',
                    help='--parity, claude backend: row 8 one call per field (parity) or per document (batched); cascade ignores it')
    ap.add_argument('--alias', choices=['none', 'afe_number'], default='none',
                    help='row 8: append ALIAS_AFE_NUMBER to the afe_number description, every backend; allowed under --parity')
    ap.add_argument('--backend', choices=['claude', 'jev', 'cascade'], default='claude')
    ap.add_argument('--escalate-below', type=float, default=ESCALATE_BELOW,
                    help='cascade: Claude answers a unit when Jev\'s top probability is strictly under this line')
    ap.add_argument('--jev-model', default=jev.MODEL, help='jev: pinned model id')
    ap.add_argument('--max-spend', type=float, default=0.01, help='jev: refuse to spend more than this many USD')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    # Model pin (redo plan section 3): checked before any input is read and before any subprocess or socket.
    if a.mode == 'live' and a.backend in ('claude', 'cascade') and not a.model:
        print(f'refusing: --mode live with the {a.backend} backend needs --model <id> (the model is pinned and logged)', file=sys.stderr)
        return 2
    if a.backend == 'cascade':
        a.parity = True          # the cascade is parity mode by construction (plan section 3)
        if not 0 < a.escalate_below <= 1:
            print(f'refusing: --escalate-below {a.escalate_below!r} is not in (0, 1]', file=sys.stderr); return 2
    if a.parity:
        if a.field_desc not in ('none', 'short') or a.option_desc not in ('none', 'verbatim'):
            print('refusing: --parity fixes --field-desc short and --option-desc verbatim', file=sys.stderr); return 2
        a.field_desc, a.option_desc = 'short', 'verbatim'
    if a.claude_row8 != 'per-field' and not a.parity:
        print('refusing: --claude-row8 applies under --parity; without it --row8 sets the claude shape', file=sys.stderr); return 2
    # the cascade's Claude half answers one escalated field per call, so it ignores --claude-row8 (BUILD-SPEC H1)
    claude_row8 = a.claude_row8 if a.backend == 'claude' else 'per-field'
    row8_asked = a.row8
    row8_for = lambda backend: claude_row8 if (a.parity and backend == 'claude') else row8_asked   # jev keeps its shape
    a.row8 = row8_for(a.backend)

    run_dir = (ROOT / a.run) if not pathlib.Path(a.run).is_absolute() else pathlib.Path(a.run)
    manifest_path, truth_dir = set_paths(a.set)
    manifest = load(manifest_path)
    docs, packets, page_text, truth = build_inputs(run_dir, manifest, truth_dir)
    truth_b = load_truth(docs, a.truth_b if pathlib.Path(a.truth_b).is_absolute() else ROOT / a.truth_b) if a.truth_b else None
    rows = {int(x) for x in a.rows.split(',') if x}
    build = lambda row8: make_requests(rows, docs, packets, page_text, truth, row8, a.field_desc, a.option_desc,
                                       a.unlabelled, a.continuation, truth_b, a.alias)
    reqs = build(a.row8)

    if a.mode == 'parity-check':
        # no network: the socket guard is on and no claude subprocess is started
        jev.install_socket_guard()
        side = {}
        for backend in ('claude', 'jev'):
            h = {}
            for r in build(row8_for(backend)):
                if not r.get('software'):
                    # node-qualified key: a packet id may equal a document id (row 5 vs row 1)
                    h.update({f"{r['node']}/{k}": v for k, v in parity_hashes(r, backend, a.jev_model).items()})
            side[backend] = h
        keys = sorted(set(side['claude']) | set(side['jev']))
        bad = [k for k in keys if side['claude'].get(k) is None or side['claude'].get(k) != side['jev'].get(k)]
        print(f'parity {len(keys) - len(bad)} of {len(keys)}')
        for k in bad:
            print(f'  mismatch {k}: claude {side["claude"].get(k, "missing")[:12]} jev {side["jev"].get(k, "missing")[:12]}')
        print(json.dumps(dict(mode='parity-check', parity=a.parity, units=len(keys), equal=len(keys) - len(bad),
                              mismatches=bad, row8=dict(claude=row8_for('claude'), jev=row8_for('jev')),
                              field_desc=a.field_desc, option_desc=a.option_desc, alias=a.alias, socket_guard=jev.GUARD['installed'],
                              network_calls=0)))
        return 0 if not bad else 1

    if a.backend == 'cascade':
        return run_cascade(a, build(row8_for('jev')), build(row8_for('claude')), run_dir, rows)

    soft = [r for r in reqs if r.get('software')]      # decided by software after the model calls
    reqs = [r for r in reqs if not r.get('software')]
    tag = ''.join(f'-{n}-{v}' for n, v in (('desc', a.field_desc), ('opt', a.option_desc), ('unl', a.unlabelled),
                                            ('alias', a.alias)) if v != 'none')
    tag += '-cont-software' if a.continuation == 'software' else ''
    tag += '-c8-per-document' if a.parity and claude_row8 == 'per-document' else ''   # effective only for claude
    tag = ('-parity' if a.parity else '') + tag
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    is_jev = a.backend == 'jev'
    key = None

    def compare_hashes(sent):
        """(match, total, first mismatch index or None) against prompt_sha256 in a recorded calls.jsonl."""
        rec = [c['prompt_sha256'] for c in map(json.loads, open(a.compare_hashes)) if not c.get('software')]
        mine = [hashlib.sha256(s.encode()).hexdigest() for s in sent]
        match = sum(1 for x, y in zip(mine, rec) if x == y)
        return dict(hash_match=f'{match} of {max(len(mine), len(rec))}', hash_source=a.compare_hashes), match == len(mine) == len(rec)

    if is_jev:
        if a.mode != 'live':
            jev.install_socket_guard()
        if not (a.max_spend == a.max_spend and 0 <= a.max_spend < float('inf')):
            print(f'refusing: --max-spend {a.max_spend!r} is not a finite non-negative number', file=sys.stderr); return 2
        try:
            bodies = [jev.build_request(r, a.jev_model) for r in reqs]
        except jev.JevShape as e:
            print(f'refusing: {e}', file=sys.stderr); return 2
        est, bound = sum(jev.est_tokens(b) for b in bodies), sum(jev.max_tokens(b) for b in bodies)
        if jev.usd(bound) > a.max_spend:
            print(f'refusing: upper-bound cost ${jev.usd(bound):.6f} exceeds --max-spend ${a.max_spend:.4f}', file=sys.stderr); return 2

    if a.mode == 'dry-run' and is_jev:
        out = pathlib.Path(a.out) if a.out else run_dir / 'typed' / f'dry-run-jev{tag}-{stamp}'
        (out / 'requests').mkdir(parents=True, exist_ok=True)
        for i, b in enumerate(bodies, 1):
            (out / 'requests' / f'{i:02d}.json').write_text(json.dumps(b, indent=1))   # bodies only: no headers, no key
        by = {}
        for r in reqs:
            by[r['node']] = by.get(r['node'], 0) + 1
        cmp, same = compare_hashes([json.dumps(b, sort_keys=True) for b in bodies]) if a.compare_hashes else ({}, True)
        print(json.dumps(dict(mode='dry-run', backend='jev', model=a.jev_model, requests=len(reqs), by_node=by,
                              questions=sum(len(b['questions']) for b in bodies),
                              est_input_tokens=est, est_cost_usd=round(jev.usd(est), 6),
                              bound_input_tokens=bound, bound_cost_usd=round(jev.usd(bound), 6),
                              software_units=len(soft), max_spend=a.max_spend, cap=a.cap, key_ready=jev.key_status()[0],
                              socket_guard=jev.GUARD['installed'], network_calls=0, out=str(out), alias=a.alias, tag=f'jev{tag}', **cmp)))
        return 0 if same else 1

    if a.mode == 'live' and is_jev:
        if len(reqs) > a.cap:
            print(f'refusing: {len(reqs)} requests exceed --cap {a.cap}', file=sys.stderr); return 2
        ok, msg = jev.key_status()
        print(f'preflight: {msg}', file=sys.stderr)
        if not ok:
            return 2
        key = os.environ[jev.KEY_ENV]
        ok, msg = jev.auth_check(key)
        print(f'preflight: {msg}', file=sys.stderr)
        if not ok:
            return 2

    if a.mode == 'dry-run':
        by = {}
        for r in reqs:
            by[r['node']] = by.get(r['node'], 0) + 1
        chars = sum(len(prompt_for(r)) for r in reqs)
        cmp, same = compare_hashes([prompt_for(r) for r in reqs]) if a.compare_hashes else ({}, True)
        print(json.dumps(dict(mode='dry-run', requests=len(reqs), by_node=by, prompt_chars_total=chars,
                              approx_input_tokens=chars // 4, cap=a.cap, network_calls=0, row8=a.row8, alias=a.alias,
                              tag=tag.lstrip('-'), **cmp)))
        return 0 if same else 1

    if a.mode == 'live' and not is_jev:
        if len(reqs) > a.cap:
            print(f'refusing: {len(reqs)} requests exceed --cap {a.cap}', file=sys.stderr); return 2
        st = subprocess.run(['claude', 'auth', 'status'], capture_output=True, text=True,
                            env={k: v for k, v in os.environ.items() if k != jev.KEY_ENV})
        try:
            if not json.loads(st.stdout).get('loggedIn'):
                raise ValueError
        except Exception:
            print('preflight failed: `claude auth status` does not report loggedIn; run `claude auth login`', file=sys.stderr); return 2

    out = pathlib.Path(a.out) if a.out else run_dir / 'typed' / f"{a.mode}{'-jev' if is_jev else ''}{tag}-{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    calls, errors, consecutive, spent, stop = [], 0, 0, 0.0, None
    import tempfile
    iso_cwd = tempfile.mkdtemp(prefix='typed-iso-')   # empty cwd for claude -p: no truth, no plants, no repo files
    (out / 'prompts.jsonl').write_text('')
    with open(out / 'calls.jsonl', 'w') as fh, open(out / 'prompts.jsonl', 'a') as pf:
        for i, r in enumerate(reqs, 1):
            if consecutive >= MAX_CONSECUTIVE_ERRORS:
                stop = f'circuit breaker: {consecutive} consecutive errors'
                print(f'{stop}, stopping before call {i}', file=sys.stderr)
                break
            # what was sent: the claude prompt, or the Jev request body (no headers, no key)
            prompt = json.dumps(bodies[i - 1], sort_keys=True) if is_jev else prompt_for(r)
            rec = dict(i=i, node=r['node'], shape=r['shape'], subject=r['subject'], label=r['label'],
                       prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(), prompt_chars=len(prompt))
            if 'label_a' in r:
                rec['label_a'] = r['label_a']
            if a.parity:
                ph = parity_hashes(r, a.backend, a.jev_model)
                # a batch record keys its hashes by field, like score['fields']; unit subject = <doc>.<field>
                rec['parity_sha256'] = ({k[len(r['subject']) + 1:]: v for k, v in ph.items()} if r['shape'] == 'noul-batch'
                                        else ph[r['subject']])
            pf.write(json.dumps(dict(i=i, prompt=prompt)) + '\n')
            if is_jev and a.mode == 'live' and spent + jev.usd(jev.max_tokens(bodies[i - 1])) > a.max_spend:
                stop = f'spend cap: call {i} could pass --max-spend ${a.max_spend:.4f} (spent ${spent:.6f})'
                print(f'{stop}; stopping', file=sys.stderr)
                break
            if a.mode == 'fixture' and is_jev:
                # SYNTHETIC response in the API shape, pushed through the real parser
                try:
                    ans, toks, _ = jev.parse_response(r, jev.fixture_response(r, fixture_answer(r), a.jev_model))
                    env, err = {'duration_ms': 0, 'synthetic': True, 'usage': {'input_tokens': toks, 'output_tokens': 0}}, None
                except jev.JevShape as e:
                    ans, env, err = None, {'duration_ms': 0, 'synthetic': True}, f'API SHAPE MISMATCH: {e}'
            elif a.mode == 'fixture':
                ans, env, err = fixture_answer(r), {'duration_ms': 0, 'synthetic': True}, None
            elif is_jev:
                ans, env, err = jev.ask(r, key, a.jev_model)
                spent += env.get('total_cost_usd') or 0
                rec.update(http_status=env.get('http_status'), served_model=env.get('model'), response=env.get('response'),
                           cost_basis=env.get('cost_basis', 'usage.input_tokens'))
                billed = (env.get('usage') or {}).get('input_tokens', 0)
                if billed > env.get('request_bound_tokens', float('inf')):
                    stop = f'bound falsified: billed {billed} tokens > body bound {env["request_bound_tokens"]}'
                print(f'[{i}/{len(reqs)}] {r["node"]} {r["subject"]} {"ERR " + err if err else "ok"}', file=sys.stderr, flush=True)
            else:
                ans, env, err = ask_model(prompt, a.model, cwd=iso_cwd)
                # served model: the keys of the envelope's modelUsage map (None when the envelope lacks it)
                mu = env.get('modelUsage')
                rec.update(model_requested=a.model,
                           served_model=(','.join(sorted(mu)) if isinstance(mu, dict) and mu else None))
                if model_mismatch(a.model, rec['served_model']):
                    rec['model_mismatch'] = True       # logged, never an error
                print(f'[{i}/{len(reqs)}] {r["node"]} {r["subject"]} {"ERR " + err if err else "ok"}', file=sys.stderr, flush=True)
            rec.update(latency_ms=env.get('duration_ms'), usage=env.get('usage'), cost_usd=env.get('total_cost_usd'),
                       answer=ans, error=err)
            def error_score(reason):
                rec['error'] = reason
                return dict(ERROR_UNIT, reason=reason) if r['shape'] != 'noul-batch' else \
                    dict(fields={f: dict(ERROR_UNIT, reason=reason) for f in r['fields']})
            if err or ans is None:
                errors += 1; consecutive += 1
                rec['score'] = error_score(err or 'no answer')
            else:
                try:
                    rec['score'] = score(r, ans, disagree_abstain=not a.parity)
                    consecutive = 0
                    if 'fields' in rec['score'] and any(u.get('error') for u in rec['score']['fields'].values()):
                        errors += sum(1 for u in rec['score']['fields'].values() if u.get('error'))
                except Malformed as e:
                    errors += 1; consecutive += 1
                    rec['score'] = error_score(f'malformed: {e}')
            calls.append(rec)
            fh.write(json.dumps(rec) + '\n'); fh.flush(); pf.flush()     # a TERM from the watchdog loses nothing written
            if stop or (is_jev and spent > a.max_spend):
                stop = stop or f'spend cap: spent ${spent:.6f} passed --max-spend ${a.max_spend:.4f}'
                print(f'{stop}; stopping after call {i}', file=sys.stderr)
                break
    with open(out / 'calls.jsonl', 'a') as fh:
        for r in soft:
            prev = next((c for c in calls if c['node'] == r['node'] and c['subject'] == r['inherit']), None)
            ps = prev['score'] if prev else None
            if not ps or ps.get('error'):
                sc = dict(ERROR_UNIT, reason=f'nothing to inherit from {r["inherit"]}')
                errors += 1
            else:
                sc = _unit(ps['final'], ps['p'], ps['abstain'], r['label'], top=ps.get('top'), inherited=r['inherit'])
            rec = dict(i=len(calls) + 1, node=r['node'], shape=r['shape'], subject=r['subject'], label=r['label'],
                       software=True, inherit=r['inherit'], latency_ms=None, usage=None, cost_usd=None, answer=None,
                       error=sc.get('reason'), score=sc)
            calls.append(rec)
            fh.write(json.dumps(rec) + '\n'); fh.flush()
    rep, units = report(calls, a.mode, dict(run_id=run_dir.name, stamp=stamp, rows=sorted(rows), row8_mode=a.row8,
                                              backend=(f'jev {a.jev_model}' if is_jev else 'fixture' if a.mode == 'fixture' else f'claude -p{(" --model " + a.model) if a.model else ""}'),
                                              errors=errors, planned_calls=len(reqs), stopped=stop, field_desc=a.field_desc, option_desc=a.option_desc,
                                              unlabelled=a.unlabelled, continuation=a.continuation, alias=a.alias,
                                              claude_row8=(None if is_jev else claude_row8),
                                              model_calls=len(calls) - len(soft), software_units=len(soft),
                                              parity=a.parity, disagree_abstain=not a.parity,
                                              corpus_set=str(a.set) if a.set else 'synth', truth_b=a.truth_b,
                                              model_requested=(a.jev_model if is_jev else a.model),
                                              served_models=sorted({c['served_model'] for c in calls if c.get('served_model')}),
                                              model_mismatches=sum(1 for c in calls if c.get('model_mismatch'))))
    (out / 'report.json').write_text(json.dumps(rep, indent=1))
    (out / 'report.md').write_text(report_md(rep))
    print(json.dumps(dict(out=str(out), calls=len(calls), units=len(units), errors=errors, nodes=rep['nodes'])))
    return 3 if stop else 0

if __name__ == '__main__':
    sys.exit(main())
