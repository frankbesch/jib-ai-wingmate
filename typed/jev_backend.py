"""Jev backend for the typed-question runner: TypeSafe System One over raw HTTP, stdlib only.

The runner keeps one answer contract (see typed_questions.score). This module translates a
runner request into a Jev request body, and a Jev response body back into that contract:
  choice       -> {'answer': <choice>, 'probabilities': {...}}
  noul         -> {'answer': <noul >= 0.5>, 'p_true': <noul>}
  noul-batch   -> {'fields': {<field>: {'answer': ..., 'p_true': ...}}}   one noul question per field
Validation of probabilities and the abstain thresholds stay in the runner, the same code for both
backends.

API shape relied on (docs quoted in a private source review,
fetched 2026-09-28):
  POST https://api.typesafe.ai/v1/systemone, "Authorization: Bearer <API_KEY>"
  request: "state", "model", "questions" (map<string, Question>)
  choice question: "type", "instructions", "criteria" map<string, string | object | array | null>
  choice answer: "choice", "probabilities", "confidence"; noul answer: {"type": "noul", "noul": 0..1}
  response: "model", "answers", "usage" with "input_tokens"
  price: $0.042 per million input tokens, output free; 32k tokens for state plus the longest question

UNVERIFIED (the live path fails loudly, never guesses):
  V1 Whether a null criteria value is accepted for every option but one; a 422 is an error unit.
  V2 Whether many noul questions in one request change any answer (docs: "Every answer is independent").
  V3 Tokenizer: tokens are estimated as chars/3; the spend cap uses UTF-8 bytes as the upper bound.
  V4 Whether GET /v1/models is billed; assumed free.
  V5 Whether the probabilities map always carries every option; required here, else an error unit.
  V6 Whether billing counts the state once per request or once per question. The runner stops if
     usage.input_tokens passes the UTF-8 byte bound of the body ("bound falsified").

The key is read from env TYPESAFE_API_KEY. It is never printed, logged, or written.
Load it: export TYPESAFE_API_KEY=... (see .env.example)
"""
import json, math, os, re, socket, ssl, time, urllib.error, urllib.request  # noqa: F401  (ssl before the guard)
from http.client import HTTPException

API_URL = 'https://api.typesafe.ai/v1/systemone'
MODELS_URL = 'https://api.typesafe.ai/v1/models'
MODEL = 'jev-1.13.0'            # pinned: "An alias moves when a new release ships"
USD_PER_MTOK = 0.042
STATE_TOKEN_LIMIT = 32000
REQUEST_TOKEN_LIMIT = 64000
DOMAIN = 'The document is from a joint-interest billing month. '   # the same domain sentence the claude prompt opens with
KEY_ENV = 'TYPESAFE_API_KEY'
KEY_MIN_LEN = 20
QID = 'q'
NEEDS_REVIEW = 'needs_review'
GUARD = {'installed': False, 'blocked': 0}
GUARD_MSG = 'SOCKET GUARD: network call blocked (fixture and dry-run make zero network calls)'


class JevShape(ValueError):
    """The response does not match the documented shape. Scored as an error, never as an answer."""


def install_socket_guard():
    def _blocked(*a, **k):
        GUARD['blocked'] += 1
        raise RuntimeError(GUARD_MSG)
    socket.socket = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    GUARD['installed'] = True


def est_tokens(obj):
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return (len(s) + 2) // 3


def max_tokens(obj):
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return len(s.encode('utf-8'))


def usd(tokens):
    return tokens * USD_PER_MTOK / 1e6


def field_question(f, desc=None):
    q = f'Is a value for the field "{f}" printed in this document?'
    return q + (f' The field means: {desc}' if desc else '')


def build_request(r, model=MODEL):
    """Same question text and option set the claude backend sends; the document is the state."""
    if r['shape'] == 'choice':
        od = r.get('option_descriptions') or {}
        criteria = {o: od.get(o) for o in r['options']}
        criteria[NEEDS_REVIEW] = 'The evidence is thin.'
        questions = {QID: {'type': 'choice', 'instructions': DOMAIN + r['question'], 'criteria': criteria}}
    elif r['shape'] == 'noul':
        questions = {QID: {'type': 'noul', 'instructions': DOMAIN + r['question']}}
    else:
        dm = r.get('descriptions') or {}
        def close(q):   # end the description with a full stop before the hint, when asked to
            return q + ('.' if r.get('hint_join') and not q.endswith(('.', '?')) else '')
        questions = {f: {'type': 'noul', 'instructions': DOMAIN + close(field_question(f, dm.get(f))) + r.get('hint', '')} for f in r['fields']}
    req = {'state': r['text'], 'model': model, 'questions': questions}
    toks = est_tokens(r['text']) + max(est_tokens(q) for q in questions.values())
    if toks > STATE_TOKEN_LIMIT:
        raise JevShape(f'estimated {toks} tokens > {STATE_TOKEN_LIMIT} (state plus longest question)')
    if est_tokens(req) > REQUEST_TOKEN_LIMIT:
        raise JevShape(f'estimated {est_tokens(req)} tokens > {REQUEST_TOKEN_LIMIT} per request')
    return req


FIELD_MEANS = ' The field means: '


def parity_parts(r, body):
    """{unit subject: (question, options, definitions, document)} read back from a built Jev body, so the
    parity hash covers what is sent. The domain sentence is wrapping and is dropped; a field definition is
    the text after FIELD_MEANS in the instructions."""
    out = {}
    for qid, q in body['questions'].items():
        ins = q['instructions']
        if not ins.startswith(DOMAIN):
            raise JevShape(f'question {qid} does not open with the domain sentence')
        ins = ins[len(DOMAIN):]
        if q['type'] == 'choice':
            opts = list(q['criteria'])
            parts = (ins, opts, [q['criteria'][o] for o in opts], body['state'])
        else:
            head, _, d = ins.partition(FIELD_MEANS)
            parts = (head, [], d, body['state'])
        out[r['subject'] if r['shape'] != 'noul-batch' else f"{r['subject']}.{qid}"] = parts
    return out


def _num(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1:
        raise JevShape(f'{what} {v!r} is not a finite number in [0,1]')
    return float(v)


def _noul(a, qid):
    if not isinstance(a, dict) or a.get('type') != 'noul':
        raise JevShape(f'answers.{qid} is not a noul answer')
    p = _num(a.get('noul'), f'answers.{qid}.noul')
    return {'answer': p >= 0.5, 'p_true': p}


def parse_response(r, body):
    """Jev response body -> (runner answer, input_tokens, model). Raises JevShape."""
    if not isinstance(body, dict):
        raise JevShape('response is not a JSON object')
    for k in ('model', 'answers', 'usage'):
        if k not in body:
            raise JevShape(f'missing top-level field {k!r}')
    answers, usage = body['answers'], body['usage']
    if not isinstance(answers, dict):
        raise JevShape('answers is not an object')
    toks = usage.get('input_tokens') if isinstance(usage, dict) else None
    if isinstance(toks, bool) or not isinstance(toks, int) or toks < 0:
        raise JevShape(f'usage.input_tokens {toks!r} is not a non-negative int')
    if r['shape'] == 'choice':
        a = answers.get(QID)
        if not isinstance(a, dict) or a.get('type') != 'choice':
            raise JevShape(f'answers.{QID} is not a choice answer')
        probs = a.get('probabilities')
        if not isinstance(probs, dict) or set(probs) != set(r['options']):
            raise JevShape('probabilities keys do not equal the option set')
        if a.get('choice') not in r['options']:
            raise JevShape(f'choice {a.get("choice")!r} is not an option')
        ans = {'answer': a['choice'], 'probabilities': {k: _num(v, f'probability {k}') for k, v in probs.items()},
               'confidence': a.get('confidence')}
    elif r['shape'] == 'noul':
        ans = _noul(answers.get(QID), QID)
    else:
        # a missing field stays missing: the runner scores it as one error unit, not a whole-call error
        ans = {'fields': {f: _noul(answers[f], f) for f in r['fields'] if f in answers}}
    return ans, toks, body['model']


def fixture_response(r, contract_answer, model=MODEL):
    """SYNTHETIC Jev response body built from the runner's fixture answer. Proves the translation
    and parse path, not Jev."""
    if r['shape'] == 'choice':
        probs = contract_answer['probabilities']
        peak, n = max(probs.values()), len(probs)
        ans = {QID: {'type': 'choice', 'choice': contract_answer['answer'], 'probabilities': probs,
                     'confidence': max(0.0, min(1.0, (n * peak - 1) / (n - 1)))}}
    elif r['shape'] == 'noul':
        ans = {QID: {'type': 'noul', 'noul': contract_answer['p_true']}}
    else:
        ans = {f: {'type': 'noul', 'noul': a['p_true']} for f, a in contract_answer['fields'].items()}
    return {'model': model, 'answers': ans,
            'usage': {'input_tokens': est_tokens(build_request(r, model)), 'output_tokens': 0}}


def key_status():
    """(ok, message). The message never carries the key."""
    key = os.environ.get(KEY_ENV)
    if not key:
        return False, (f'{KEY_ENV} is not set. In your own Terminal run: '
                       f'export {KEY_ENV}=... (see .env.example)')
    if len(key) < KEY_MIN_LEN or re.search(r'\s', key):
        return False, f'{KEY_ENV} looks truncated or malformed ({len(key)} chars; need >= {KEY_MIN_LEN}, no whitespace)'
    return True, f'{KEY_ENV} present ({len(key)} chars)'


def redact(obj, key):
    """Server-controlled content may echo the Authorization value; scrub before anything is stored."""
    if isinstance(obj, bytes):
        obj = obj.decode('utf-8', 'replace')
    if isinstance(obj, str):
        if key:
            obj = obj.replace(key, '[REDACTED]')
        return re.sub(r'Bearer\s+[A-Za-z0-9._\-]{8,}', 'Bearer [REDACTED]', obj)
    if isinstance(obj, dict):
        return {redact(k, key): redact(v, key) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v, key) for v in obj]
    return obj


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib copies Authorization onto a redirect, even to another host. Refuse every redirect."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http(method, url, key, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Authorization', 'Bearer ' + key)
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    t0 = time.monotonic()
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as resp:
            return resp.status, resp.read(), (time.monotonic() - t0) * 1000
    except urllib.error.HTTPError as e:
        return e.code, e.read(), (time.monotonic() - t0) * 1000
    except (urllib.error.URLError, HTTPException, OSError) as e:
        return 0, str(e).encode(), (time.monotonic() - t0) * 1000


def auth_check(key):
    """(ok, message). One GET /v1/models before any billed call."""
    st, body, _ = http('GET', MODELS_URL, key)
    if st == 401:
        return False, 'key rejected (401) by GET /v1/models'
    if st != 200:
        return False, f'GET /v1/models returned {st}: {redact(body, key)[:300]!r}'
    try:
        json.loads(body)
    except ValueError:
        return False, 'GET /v1/models did not return JSON'
    return True, 'GET /v1/models 200'


def ask(r, key, model=MODEL, retries=4, sleep=time.sleep):
    """One POST. Returns (answer_or_None, env, error_str) in the shape the runner's claude backend returns.
    env['total_cost_usd'] is metered spend: usage.input_tokens at the docs price."""
    try:
        req = build_request(r, model)
    except JevShape as e:
        return None, {'duration_ms': 0}, str(e)
    st, body, ms = 0, b'', 0.0
    for attempt in range(retries + 1):
        st, body, ms = http('POST', API_URL, key, req)
        if st in (429, 529) and attempt < retries:
            sleep(2 ** attempt)
            continue
        break
    env = {'duration_ms': int(round(ms)), 'http_status': st, 'request_bound_tokens': max_tokens(req)}
    if st != 200:
        if st == 0:   # timeout or dropped connection: the request may have been billed, so charge the bound
            env.update(total_cost_usd=usd(max_tokens(req)), cost_basis='bound: no response')
        return None, env, f'HTTP {st}: {redact(body, key)[:300]}'
    try:
        parsed = json.loads(body)
    except ValueError:
        return None, env, 'response body is not JSON'
    env['response'] = redact(parsed, key)
    try:
        ans, toks, served = parse_response(r, parsed)
    except JevShape as e:
        # the call was billed even though it cannot be scored; keep the tokens if they are readable
        u = parsed.get('usage') if isinstance(parsed, dict) else None
        t = u.get('input_tokens') if isinstance(u, dict) else None
        if isinstance(t, int) and not isinstance(t, bool) and t >= 0:
            env.update(usage={'input_tokens': t, 'output_tokens': 0}, total_cost_usd=usd(t))
        return None, env, f'API SHAPE MISMATCH: {e}'
    env.update(usage={'input_tokens': toks, 'output_tokens': 0}, total_cost_usd=usd(toks), model=served)
    if served != model:
        return None, env, f'served model {served!r} is not the pinned {model!r}'
    return ans, env, None
