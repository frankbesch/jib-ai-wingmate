#!/usr/bin/env python3
"""Held-out run 2 orchestrator (BUILD-SPEC H3; plan 06-control-test-plan.md v4, sections 2, 7, 8, 9).

One Frank-started command runs every stage in order. Python does the work; `heldout2/run-heldout2.sh` is the
launcher that checks the two keys by length and the Claude sign-in, then execs this file.

Usage (from the repo root):
  python3 heldout2/run_heldout2.py --dry-run            # stage list with commands and deadlines; writes nothing
  python3 heldout2/run_heldout2.py --stub               # every external command replaced by a fast fake
  python3 heldout2/run_heldout2.py                      # LIVE (Frank only, through run-heldout2.sh)
  python3 heldout2/run_heldout2.py --resume <stamp>     # continue a stopped run; mode comes from its state.json
Test hooks (with --stub only): --stub-faults <json>, --deadline-scale <f>.  Any mode: --stop-after <stage id>.

Run folder: runs/heldout2/<stamp>/ (stub: <stamp>-stub, with corpus and Pulse runs under its work/ folder):
  state.json (stage status, attempts, retry pools, input and output hashes), ledger.json (R5), status.log (one
  line per stage event), frozen-code.json, frozen-truth.json, arms.json, logs/, records/ (one per Codex session),
  sessions/<stage>/ (Codex session folders), stages/ (script stage folders), private/ (unblinded comparisons),
  quarantine/ (failed attempts, moved, never deleted).

Out-of-folder scan (R4). After each Codex session the script collects the commands the session ran from two
sources: the Codex rollout file for that session (<CODEX_HOME>/sessions/**/rollout-*.jsonl whose session_meta
cwd is the session folder; tool calls of type function_call, custom_tool_call, local_shell_call, and
exec_command_begin events) and the saved stdout log (lines after an `exec` marker, with their `in <cwd>`
suffix). Each command is split into tokens on whitespace, quotes, and shell operators; literal \\n escapes are
spaces first; `cd <dir>` moves the working directory for the rest of that command. A token is a path when it
starts with `/`, `~`, `$HOME`, or `${HOME}`, or when it has a `..` path segment (resolved against the working
directory). A path outside the session folder (lexical and realpath both checked) is a hit unless it sits under
ALLOWED_OUTSIDE (system program and library prefixes, /dev streams, and Codex's own plugin and skill cache); a
command's working directory outside the folder is a hit too. One hit marks the stage INVALID and stops the run.
Known blind spots: paths built at run time (string joins, globs like /Use*, variables other than HOME); reads
through a symlink the session creates inside its folder; a bare `/`; reads done by Codex itself outside a tool
call; apply_patch calls are not scanned (they write, and the sandbox blocks writes outside); MCP or web tools;
a rollout file Codex does not write (then only stdout is scanned and status.log says so). False positives are
possible on regex literals such as '/pattern/'. The scan detects; it does not prevent (plan section 2, R4).
"""
import argparse, ast, datetime, fcntl, hashlib, json, math, os, pathlib, re, shutil, signal, subprocess, sys, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = pathlib.Path(__file__).resolve()

# ================================================================== external commands (correct here)
PY = 'python3'
CORPUS = 'synth-heldout2'
SETS = ('clean', 'scan')
MODEL = 'claude-fable-5-1'            # D-239 Q5 pin, plan section 3
RUN_ID = 'live-heldout2-{set}-01'     # Pulse run id per set; a retry quarantines the folder and reuses the id
COMMANDS = {
    'codex':         ['codex', 'exec', '--skip-git-repo-check', '-s', 'workspace-write', '-C', '{folder}', '{prompt}'],
    'render':        ['sandbox-exec', '-f', '{profile}', PY, 'src/build.py', '--render-only'],
    'page_images':   ['pdftoppm', '-r', '110', '-png', '{pdf}', '{prefix}'],
    'pulse':         [PY, 'pipeline.py', '--mode', 'live', '--corpus', CORPUS, '--variant', '{set}', '--run-id', '{run_id}'],
    'arm':           ['bash', 'typed/run-typed-redo.sh', '--backend', '{backend}', '--run', 'runs/{run_id}',
                      '--repeats', '1', '--set', CORPUS, '--truth-b', CORPUS + '/layerB/{set}/truth-b',
                      '--max-wall', '{max_wall}', '--yes'],   # + --model, --max-spend, and `--` extras per arm
    'make_layerb':   [PY, 'synth-heldout/tools/make_layerb.py', '--run', 'runs/{run_id}', '--corpus', CORPUS,
                      '--out', CORPUS + '/layerB/{set}'],
    'freeze_hashes': [PY, 'synth-heldout/tools/freeze_hashes.py', '--dir', CORPUS + '/layerB/{set}/truth-b',
                      '--out', CORPUS + '/layerB/{set}/truth-b.sha256'],
    'make_audit2':   [PY, 'heldout2/make_audit2.py', '--run', 'runs/{run_id}', '--corpus', CORPUS, '--out', CORPUS + '/audit/{set}',
                      '--out-secondary', CORPUS + '/audit2/{set}', '--record', '{root}/private/audit-record-{set}.json'],
    'score':         [PY, 'heldout2/score_heldout2.py', '--corpus', CORPUS, '--run-clean', 'runs/{run_clean}',
                      '--run-scan', 'runs/{run_scan}', '--arms', '{root}/arms.json', '--out', '{root}/score.json',
                      '--md', '{root}/score.md'],
    # score also gets --audit <set>=<primary audit json> per set, and --audit2 <set>=<json> for each set whose
    # secondary (alias/batched-only) audit ran; the JSON paths are AUDIT_JSON below.
}
# Expected unit set per set (review 2, C): the runner's own request builder (typed_questions.make_requests) on the
# frozen corpus, no network, in the parity shape every arm shares (rows 1,4,5,8; field-desc short; option-desc
# verbatim). Checked against run 1: equal to the unit set of all 7 recorded arm runs (797 units).
EXPECT_UNITS_PY = r'''import json, pathlib, sys
demo = pathlib.Path(sys.argv[1]); sys.path.insert(0, str(demo / 'typed')); sys.path.insert(0, str(demo))
import typed_questions as tq
run, corpus, truth_b, out = sys.argv[2:6]
man_path, truth_dir = tq.set_paths(corpus)
manifest = tq.load(man_path)
docs, packets, page_text, truth = tq.build_inputs(demo / run, manifest, truth_dir)
tb = tq.load_truth(docs, demo / truth_b) if truth_b else None
reqs = tq.make_requests({1, 4, 5, 8}, docs, packets, page_text, truth, 'per-field', 'short', 'verbatim', 'none', 'model', tb, 'none')
keys = set()
for r in reqs:
    if r.get('shape') == 'noul-batch':
        keys |= {f"{r['node']}:{r['subject']}.{f}" for f in r['fields']}
    else:
        keys.add(f"{r['node']}:{r['subject']}")
json.dump(sorted(keys), open(out, 'w'))
print(f'{len(keys)} expected units')
'''
COMMANDS['expect_units'] = [PY, '-c', '<EXPECT_UNITS_PY>', '{demo}', 'runs/{run_id}', CORPUS, CORPUS + '/layerB/{set}/truth-b',
                            '{root}/expected-units-{set}.json']
GATE_IDS = ('documents_packets_pages', 'page_counts', 'sha256', 'required_keys', 'unit_arithmetic', 'clean_text_nonempty',
            'no_earlier_proper_nouns', 'cases_truth_agreement')   # every id must be in key_a's gates.json and pass
SESSIONS_HOME = '~/heldout2-sessions'   # live Codex session folders and the render folder: <this>/<stamp>/<stage>/
# arm, backend, runs per set, deadline min, args after `--` (plan section 5 order; run 1 recipe R5)
ARMS = [
    # Deadlines re-set 2026-10-03 after live start 20261002T233111Z: Claude calls ran at p50 3.1 to 3.5 s against
    # 0.7 s in run 1 (no status incident, no errors), so an A run needs about 82 min and a cascade run, with about
    # 434 Claude calls, about 45 min. Each deadline is about 1.8x that pace; the runner gets it as --max-wall.
    ('A',         'claude',  2, 150, []),
    ('B',         'jev',     3, 5,   []),
    ('C',         'cascade', 2, 90,  ['--escalate-below', '0.80']),
    ('B-alias',   'jev',     1, 5,   ['--alias', 'afe_number']),
    ('C-alias',   'cascade', 2, 90,  ['--escalate-below', '0.80', '--alias', 'afe_number']),
    ('A-batched', 'claude',  2, 90,  ['--claude-row8', 'per-document']),
]
RENDER_ENV = {'CHROME_EXTRA_FLAGS': '--no-sandbox --disable-crash-reporter'}
# R = real path of the render folder, T = real path of `getconf DARWIN_USER_TEMP_DIR` (no trailing slash),
# D = real path of ~/Documents. TMPDIR is left alone (a TMPDIR inside R makes Chrome's socket path too long).
RENDER_PROFILE = '''(version 1)
(allow default)
(deny network*)
(allow network* (local unix) (remote unix))
(deny file-write*)
(allow file-write* (subpath "{R}") (subpath "{T}") (literal "/dev/null") (literal "/dev/dtracehelper") (regex #"^/dev/tty"))
(deny file-read* (subpath "{D}"))
'''
RENDER_DOC_RE = r'^(\d+_)?{doc}\.pdf$'          # <set>/<NN>_<doc_id>.pdf, run 1 layout
RENDER_PACKET = '{set}/packets/{packet}.pdf'

# ================================================================== frozen rules (R4 to R11, section 9 table)
CAPS = {'pulse_credits': 800.0, 'jev_usd': 0.50}                     # R5
PULSE_CREDITS_PER_PAGE_BOUND = 5.0   # run 1 measured 360 credits / 80 pages = 4.5 (runs/live-heldout-clean-01/month.json)
PULSE_FALLBACK_BOUND = 400.0         # used when the manifest page count cannot be read
JEV_MAX_SPEND_PER_RUN = 0.045        # passed as --max-spend; the runner stops before passing it (run 1 bound 0.026 to 0.027)
PULSE_RETRY_NOTE = ('Pulse retry is whole-set only (pipeline.py has no per-document retry); after both sets succeed the '
                    '800-credit cap has no room for another set, so a Pulse failure on the second set stops the run '
                    'for Frank to decide and --resume')
R6_MAX_EXCLUDED = 10
COMPOSITION = {'packets': 39, 'documents': 71, 'pages': 80}           # plan section 4
BRIEFS = ('critic', 'designer', 'generator', 'key_a', 'rekey', 'adjudicate', 'layerb', 'audit')
FREEZE_FILES = ['heldout2/controls.py', 'heldout2/score_heldout2.py', 'heldout2/make_audit2.py'] + \
               [f'heldout2/briefs/{b}.md' for b in BRIEFS]
FREEZE_GLOBS = ['heldout2/inputs/*']
FREEZE_EXTRA = ['reconcile.py']   # K1's REQUIRED source; its parsed value is frozen too (frozen-code.json 'required')
ALIAS_SOURCE, ALIAS_NAME = 'typed/typed_questions.py', 'ALIAS_AFE_NUMBER'
FLATTEN_PREFIXES = ('heldout2/inputs/',)   # these inputs arrive by file name; every other path keeps its relative path
SECRET_MARKERS = ('KEY', 'TOKEN', 'SECRET')
KEY_ENVS = {'pulse': 'PULSE_API_KEY', 'jev': 'TYPESAFE_API_KEY'}
KEY_MIN = 16
USAGE_LIMIT_RE = re.compile(r'(?i)(usage limit|limit reached|hit your (usage )?limit|out of extra usage)')
GRACE_S = 5.0
COVERAGE, CASE_SPEC = CORPUS + '/design/coverage.json', CORPUS + '/design/case_spec.json'
ADJ, ADJ2 = CORPUS + '/adjudication', CORPUS + '/adjudication2'
AUDIT_DIR = {'primary': CORPUS + '/audit/{set}', 'secondary': CORPUS + '/audit2/{set}'}        # make_audit2 --out / --out-secondary
AUDIT_JSON = {'primary': ADJ + '/{set}/audit.json', 'secondary': ADJ2 + '/{set}/audit.json'}    # scorer --audit / --audit2
STUB_REAL_OK = ('make_layerb', 'make_audit2', 'score')   # local tools --stub-real may run for real (needs --stub-in-place)
SCALAR_FIELDS = {   # scored scalar fields per class, from heldout2/inputs/rekey_fields.md (list fields excluded)
    'afe_cover': ['letter_date', 'operator_name', 'addressee', 'afe_number', 'well_name', 'response_due_date',
                  'wi_decimal_stated', 'net_share_stated'],
    'afe': ['afe_number', 'operator_name', 'well_name', 'api_number', 'county', 'state', 'afe_date', 'afe_type', 'total_estimate'],
    'field_ticket': ['ticket_number', 'vendor_name', 'service_date', 'well_name', 'afe_number', 'total', 'customer_signature_present'],
    'hauling_log': ['log_number', 'hauler_name', 'log_date', 'well_name', 'total_barrels'],
    'invoice': ['invoice_number', 'vendor_name', 'invoice_date', 'afe_number', 'well_name', 'subtotal', 'tax', 'total'],
    'jib_statement': ['statement_period', 'operator_name', 'property_number', 'well_name', 'owner_name', 'owner_number',
                      'wi_decimal', 'gross_total', 'net_total', 'due_date'],
}


def allowed_outside(home):
    return ['/bin/', '/sbin/', '/usr/', '/System/', '/Library/', '/Applications/', '/opt/homebrew/', '/etc/', '/private/etc/',
            '/dev/null', '/dev/stdin', '/dev/stdout', '/dev/stderr', '/dev/tty', '/dev/fd/',
            home + '/.codex/plugins/cache/', home + '/.codex/skills/']


# ================================================================== small helpers
def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def under(path, root):
    path, root = str(path), str(root).rstrip(os.sep)
    return path == root or path.startswith(root + os.sep)


def skip_special(dirname, names):
    """copytree ignore: sockets, fifos, and dangling symlinks. A rendered folder carries Chrome's profile, whose
    SingletonSocket and SingletonLock entries killed the orchestrator mid-copy (live start 20261002T221735Z)."""
    out = []
    for n in names:
        q = pathlib.Path(dirname) / n
        if not (q.is_file() or q.is_dir()):   # both follow symlinks: a dangling link is neither
            out.append(n)
    return out


def hash_path(p, exclude=()):
    """sha256 of a file, or of a dir as sorted '<rel>\\0<sha>' lines; None when missing. Skips excluded subpaths."""
    p = pathlib.Path(p)
    if p.is_file():
        return sha_file(p)
    if not p.is_dir():
        return None
    ex = [str(e) for e in exclude]
    lines = []
    for f in sorted(x for x in p.rglob('*') if x.is_file()):
        if any(under(f, e) for e in ex):
            continue
        lines.append(f'{f.relative_to(p).as_posix()}\0{sha_file(f)}\n')
    return sha_bytes(''.join(lines).encode())


def read_json(p, default=None):
    try:
        return json.loads(pathlib.Path(p).read_text())
    except (OSError, ValueError):
        return default


# ---- redaction: every value of a KEY/TOKEN/SECRET variable in the launcher environment (8+ chars, not a path)
REDACT = []
REDACT_MIN = 8
REDACTED = b'[REDACTED]'


def load_secrets(env=None):
    vals = {v for k, v in (os.environ if env is None else env).items()
            if any(m in k.upper() for m in SECRET_MARKERS) and len(v) >= REDACT_MIN and not v.startswith(('/', '~'))}
    REDACT[:] = sorted((v.encode() for v in vals), key=len, reverse=True)


def redact_bytes(b):
    for sec in REDACT:
        b = b.replace(sec, REDACTED)
    return b


def redact(text):
    return redact_bytes(str(text).encode()).decode(errors='replace')


def write_json(p, obj):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(redact(json.dumps(obj, indent=1, sort_keys=True, default=str)) + '\n')
    os.replace(tmp, p)


def parse_required(path):
    """REQUIRED {class: [field, ...]} from reconcile.py with ast (never imported); None when absent."""
    try:
        tree = ast.parse(pathlib.Path(path).read_text())
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'REQUIRED' for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


NOUN_RUN = re.compile(r"[A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|[0-9]+-[A-Z]+|LLC|LP|Inc))+")


def earlier_nouns(code):
    """Proper nouns of the earlier corpus: multi-word capitalised runs in synth-heldout/manifest.json `story` (e.g.
    'Lumereth County', 'Pellwick 3-RH') plus every *_name string value in synth-heldout/reference/*.json. Returns the
    full names and their distinctive first words (4+ letters); None when the story cannot be read."""
    man = read_json(pathlib.Path(code) / 'synth-heldout' / 'manifest.json')
    story = man.get('story') if isinstance(man, dict) else None
    if not isinstance(story, str) or not story.strip():
        return None
    names = set(NOUN_RUN.findall(story))

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and k.endswith('_name') and v.strip():
                    names.add(v.strip())
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    for f in sorted((pathlib.Path(code) / 'synth-heldout' / 'reference').glob('*.json')):
        walk(read_json(f))
    terms = set(names) | {n.split()[0] for n in names if len(n.split()[0]) >= 4}
    return sorted(terms)


def darwin_temp_dir():
    """Real path of `getconf DARWIN_USER_TEMP_DIR` without the trailing slash; '' when unavailable."""
    try:
        out = subprocess.run(['getconf', 'DARWIN_USER_TEMP_DIR'], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''
    return os.path.realpath(out).rstrip('/') if out else ''


def pdf_pages(path, timeout=60.0):
    """Page count with pdfinfo, else by rendering at 10 dpi with pdftoppm into a temp dir; None when unknown."""
    try:
        if shutil.which('pdfinfo'):
            out = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True, timeout=max(timeout, 0.01), env=strip_env()).stdout
            m = re.search(r'^Pages:\s+(\d+)', out, re.M)
            return int(m.group(1)) if m else None
        if shutil.which('pdftoppm'):
            with tempfile.TemporaryDirectory() as td:
                subprocess.run(['pdftoppm', '-r', '10', '-png', str(path), os.path.join(td, 'p')], capture_output=True,
                               timeout=max(timeout, 0.01), env=strip_env())
                return len(os.listdir(td)) or None
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def strip_env(allow=(), extra=None, base=None):
    """Child environment: every variable whose name contains KEY, TOKEN, or SECRET (any case) is removed,
    except the names in `allow`. Values are never logged."""
    src = os.environ if base is None else base
    env = {k: v for k, v in src.items() if k in allow or not any(m in k.upper() for m in SECRET_MARKERS)}
    env['PYTHONUNBUFFERED'] = '1'
    env.update(extra or {})
    return env


def alias_constant(path):
    """Value of ALIAS_AFE_NUMBER in typed_questions.py, read with ast (never imported); None when absent."""
    try:
        tree = ast.parse(pathlib.Path(path).read_text())
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == ALIAS_NAME for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    return None


def parse_brief(path):
    """Header lines INPUTS / OUTPUTS / COPY_OUT, a blank line, then the prompt body."""
    text = pathlib.Path(path).read_text()
    lines = text.split('\n')
    head, i = {}, 0
    while i < len(lines) and lines[i].strip():
        k, sep, v = lines[i].partition(':')
        if not sep or k.strip() not in ('INPUTS', 'OUTPUTS', 'COPY_OUT'):
            raise ValueError(f'{path}: header line {i + 1} is not INPUTS/OUTPUTS/COPY_OUT: {lines[i][:60]!r}')
        head[k.strip()] = v.strip()
        i += 1
    for k in ('INPUTS', 'OUTPUTS', 'COPY_OUT'):
        if k not in head:
            raise ValueError(f'{path}: header {k} missing')
    body = '\n'.join(lines[i + 1:]).strip('\n') + '\n'
    split = lambda s: [x.strip() for x in s.split(',') if x.strip()]
    return {'inputs': split(head['INPUTS']), 'outputs': split(head['OUTPUTS']), 'copy_out': head['COPY_OUT'].strip(),
            'body': body, 'sha256': sha_bytes(text.encode())}


def norm_cmp(x):
    """compare_layer_a.py's normalisation: strings trimmed and casefolded, numeric strings as floats."""
    if isinstance(x, str):
        s = x.strip()
        try:
            return float(s.replace(',', '').replace('$', ''))
        except ValueError:
            return s.lower()
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return float(x)
    return x


# ================================================================== R4 session-log scan
TOKEN_SPLIT = re.compile(r"""[\s'"`;|&<>(){}\[\],=:\\]+""")
SEGMENT_SPLIT = re.compile(r'&&|\|\||;|\||\n')
# A closing HTML tag such as </span> is one tag name, never a path; without this, a generator that writes templates
# in a heredoc reads as 65 absolute paths (live start 20261002T193409Z). `</etc/passwd` keeps its slash and still hits.
HTML_CLOSE_TAG = re.compile(r'</[A-Za-z][A-Za-z0-9-]*\s*>')


def _strings(obj, skip=()):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in skip:
                yield from _strings(v, skip)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v, skip)


def commands_from_rollout(path):
    """(session cwd, [(command text, workdir or None)]) from a Codex rollout JSONL file."""
    meta_cwd, cmds = None, []
    wd_keys = ('workdir', 'cwd', 'working_directory')
    with open(path, errors='replace') as fh:
        lines = fh.readlines()
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        p = r.get('payload') if isinstance(r, dict) else None
        if not isinstance(p, dict):
            continue
        if r.get('type') == 'session_meta':
            meta_cwd = p.get('cwd')
            continue
        t = p.get('type')
        if t in ('function_call', 'custom_tool_call', 'local_shell_call'):
            if 'apply_patch' in str(p.get('name') or ''):
                continue
            raw = p.get('arguments') if t == 'function_call' else p.get('input') if t == 'custom_tool_call' else p.get('action')
            obj = raw
            if isinstance(raw, str):
                try:
                    obj = json.loads(raw)
                except ValueError:
                    obj = None
            if isinstance(obj, (dict, list)):
                wd = next((obj.get(k) for k in wd_keys if isinstance(obj, dict) and obj.get(k)), None)
                cmds.append((' '.join(_strings(obj, wd_keys)), wd))
            else:
                cmds.append((str(raw), None))
        elif t == 'exec_command_begin':
            c = p.get('command')
            cmds.append((' '.join(c) if isinstance(c, list) else str(c), p.get('cwd')))
    return meta_cwd, cmds


def commands_from_stdout(path):
    """[(command text, cwd or None)] from `codex exec` human output: `exec` then `<cmd> in <cwd>`."""
    try:
        lines = pathlib.Path(path).read_text(errors='replace').splitlines()
    except OSError:
        return []
    cmds, i = [], 0
    while i < len(lines):
        m = re.match(r'^(?:\[[^\]]*\]\s*)?exec(?:\s+(.*))?$', lines[i].strip())
        if m:
            cmd = (m.group(1) or '').strip()
            if not cmd and i + 1 < len(lines):
                i += 1
                cmd = lines[i].strip()
            m2 = re.match(r'^(.*)\s+in\s+(/\S.*)$', cmd)
            cmds.append((m2.group(1), m2.group(2).strip()) if m2 else (cmd, None))
        i += 1
    return cmds


def scan_commands(cmds, folder, home=None, allow=None, exists=os.path.exists):
    """[(kind, path, command excerpt)] for every path outside `folder`; kind 'hit' or 'allowed'. `exists` decides
    whether a mentioned path is real (tests with made-up paths pass a stub)."""
    home = home or os.path.expanduser('~')
    allow = allowed_outside(home) if allow is None else allow
    roots = {os.path.normpath(str(folder)), os.path.realpath(str(folder))}

    def inside(p):
        return any(under(c, r) for c in {p, os.path.realpath(p)} for r in roots)

    def permitted(p):
        return any((a.endswith('/') and (c + '/').startswith(a)) or c == a.rstrip('/') for a in allow
                   for c in {p, os.path.realpath(p)})

    # A temp file this session creates itself (first mention is a redirect target: `> /tmp/x`, `cat > /tmp/x <<EOF`)
    # carries nothing from outside the folder, so later reads of it are allowed. A temp path first seen in any other
    # position was written by someone else and stays a hit (live start 20261002T220308Z: /tmp/build_case_spec.py).
    tmp_roots = tuple(os.path.normpath(p) + '/' for p in {'/tmp', '/private/tmp', os.path.realpath('/tmp'),
                                                           tempfile.gettempdir(), os.path.realpath(tempfile.gettempdir())})
    own_tmp = set()

    def own_temp(path, seg, tok):
        c = {path, os.path.realpath(path)}
        if not any(x.startswith(tmp_roots) for x in c):
            return False
        if c & own_tmp:
            return True
        if re.search(r'>>?\s*' + re.escape(tok) + r'(?=[\s\'"`;|&<>)]|$)', seg):
            own_tmp.update(c)
            return True
        return False

    out = []
    for text, wd in cmds:
        cwd = os.path.normpath(wd) if wd else os.path.normpath(str(folder))
        excerpt = str(text)[:160]
        if wd and not inside(cwd):
            out.append(('allowed' if permitted(cwd) else 'hit', cwd, 'workdir: ' + excerpt))
        text = re.sub(r'\\[ntr]', ' ', str(text))
        for seg in SEGMENT_SPLIT.split(text):
            toks = [t for t in TOKEN_SPLIT.split(HTML_CLOSE_TAG.sub(' ', seg)) if t]
            for j, tok in enumerate(toks):
                t = tok
                if t.startswith('~'):
                    t = home + t[1:] if (t == '~' or t.startswith('~/')) else '/~' + t[1:]
                t = t.replace('${HOME}', home).replace('$HOME', home)
                if t.startswith('/'):
                    if t.startswith('//') or not t.strip('/'):
                        continue
                    path = os.path.normpath(t)
                    # Python's ROOT/'src'/f'{x}' and a CSS /* comment */ split into "/f" and "/*": a top-level name
                    # that does not exist on this machine cannot be read, so it is noise, not a path.
                    if not os.path.exists('/' + path.split('/')[1]):
                        continue
                elif '..' in t.split('/'):
                    path = os.path.normpath(os.path.join(cwd, t))
                else:
                    path = None
                if path is not None and not inside(path):
                    # A path that does not exist when the session is over moved no information: a read of it found
                    # nothing and a write would have created it (live start 20261002T224400Z: the prose string
                    # "See ../REPORT.md", resolved against the wrong directory). A glob pattern may still match real
                    # files, so it stays a hit.
                    if not exists(path) and not any(c in tok for c in '*?[') and not permitted(path):
                        continue
                    out.append(('allowed' if permitted(path) or own_temp(path, seg, tok) else 'hit', path, excerpt))
                if j == 1 and toks[0] == 'cd':
                    cwd = path if path is not None else os.path.normpath(os.path.join(cwd, t))
    return out


def find_rollouts(codex_home, folder, since):
    base = pathlib.Path(codex_home) / 'sessions'
    if not base.is_dir():
        return []
    want = {os.path.normpath(str(folder)), os.path.realpath(str(folder))}
    found = []
    for f in base.glob('*/*/*/rollout-*.jsonl'):
        try:
            if f.stat().st_mtime < since - 2:
                continue
            with open(f, errors='replace') as fh:
                first = json.loads(fh.readline())
        except (OSError, ValueError):
            continue
        cwd = (first.get('payload') or {}).get('cwd') if isinstance(first, dict) else None
        if cwd and {os.path.normpath(cwd), os.path.realpath(cwd)} & want:
            found.append(f)
    return sorted(found)


def instruction_files(codex_home, folder):
    rec = []
    ch = pathlib.Path(codex_home)
    for name in ('AGENTS.md', 'AGENTS.override.md', 'instructions.md', 'config.toml'):
        p = ch / name
        if p.is_file():
            rec.append({'path': str(p), 'sha256': sha_file(p)})
    for name in ('prompts', 'rules', 'skills'):
        p = ch / name
        if p.is_dir():
            rec.append({'path': str(p), 'dir_entries': sum(1 for _ in p.iterdir())})
    for anc in [pathlib.Path(folder)] + list(pathlib.Path(folder).parents):
        for name in ('AGENTS.md', 'AGENTS.override.md'):
            p = anc / name
            if p.is_file():
                rec.append({'path': str(p), 'sha256': sha_file(p), 'inherited_by_folder': True})
    return rec


# ================================================================== ledger (R5)
class Stop(Exception):
    code = 1


class Invalid(Stop):
    code = 3


class UsageLimit(Exception):
    pass


class Interrupted(Exception):
    pass


class Ledger:
    """Persistent spend ledger. A reservation counts at its bound until settled with a known actual;
    a reservation whose outcome is unknown stays at its bound for good."""

    def __init__(self, path, must_exist=False):
        self.path = pathlib.Path(path)
        if self.path.exists() or must_exist:
            d = read_json(self.path)
            ok = isinstance(d, dict) and isinstance(d.get('caps'), dict) and isinstance(d.get('entries'), list) and \
                all(isinstance(e, dict) and {'resource', 'bound', 'state'} <= set(e) for e in d['entries'])
            if not ok:
                raise Stop(f'{self.path} is missing, unreadable, or malformed; refusing to reset the spend ledger')
            self.d = d
        else:
            self.d = {'caps': dict(CAPS), 'entries': []}

    def save(self):
        write_json(self.path, self.d)

    def spent(self, res):
        return sum((e['actual'] if e['state'] == 'settled' else e['bound']) for e in self.d['entries'] if e['resource'] == res)

    def would_pass(self, res, bound):
        return self.spent(res) + bound > self.d['caps'][res] + 1e-9

    def reserve(self, stage, attempt, res, bound):
        self.d['entries'].append({'stage': stage, 'attempt': attempt, 'resource': res, 'bound': bound, 'actual': None,
                                  'state': 'reserved', 'at': now()})
        self.save()

    def _entry(self, stage, attempt, res):
        for e in reversed(self.d['entries']):
            if e['stage'] == stage and e['attempt'] == attempt and e['resource'] == res:
                return e
        return None

    def settle(self, stage, attempt, res, actual):
        e = self._entry(stage, attempt, res)
        if e and e['state'] == 'reserved':
            e.update(state='settled', actual=float(actual), settled_at=now())
            self.save()

    def mark_unknown(self, stage, attempt, res, floor=0.0):
        """Outcome unknown: the charge stays at its bound, or at the spend observed so far when that is higher."""
        e = self._entry(stage, attempt, res)
        if e and e['state'] == 'reserved':
            e.update(state='unknown', settled_at=now(), bound=max(float(e['bound']), float(floor or 0)))
            self.save()

    def summary(self):
        return {r: round(self.spent(r), 6) for r in self.d['caps']}


# ================================================================== stage plan
def build_plan():
    plan = []

    def add(sid, kind, minutes, pool=None, budget=0, **kw):
        plan.append(dict(id=sid, kind=kind, deadline=minutes * 60, pool=pool or sid, budget=budget, **kw))

    add('freeze_code', 'freeze_code', 2)
    add('critic', 'codex', 30, pool='design', budget=1, brief='critic')
    add('designer', 'codex', 30, pool='design', budget=1, brief='designer', post='quota')
    add('generator_source', 'codex', 60, pool='build', budget=2, group='build', brief='generator')
    add('render', 'render', 45, pool='build', budget=2, group='build')
    add('key_a', 'codex', 60, pool='build', budget=2, group='build', brief='key_a', post='build_gates')
    add('rekey', 'codex', 45, budget=1, brief='rekey', post='blind_complete')
    add('compare', 'compare', 5)
    add('adjudicate', 'codex', 45, budget=1, brief='adjudicate', post='rulings', refs={'compare': 'compare'}, variant='clean')
    add('apply_rulings', 'apply_rulings', 5)
    for s in SETS:
        add(f'pulse.{s}', 'pulse', 90, budget=1, set=s)    # run 1 measured about 63 min per set
    for s in SETS:
        add(f'make_layerb.{s}', 'local', 10, set=s, tool='make_layerb')
        add(f'layerb.{s}', 'codex', 45, budget=1, set=s, brief='layerb', post='truth_b_complete')
    add('freeze_truth', 'freeze_truth', 5)
    add('expect_units', 'expect', 10)
    for s in SETS:
        for arm, backend, reps, minutes, extra in ARMS:
            for r in range(1, reps + 1):
                add(f'arm.{s}.{arm}.r{r}', 'arm', minutes, pool=f'arm.{s}.{arm}', budget=2, set=s, arm=arm,   # R8 as amended 2026-10-03
                    backend=backend, rep=r, extra=extra)
    add('verify_arms', 'verify_arms', 2)
    for s in SETS:
        add(f'make_audit2.{s}', 'local', 15, set=s, tool='make_audit2')
    for s in SETS:
        add(f'audit.{s}', 'codex', 45, budget=1, set=s, brief='audit', post='answers', tier='primary')
    for s in SETS:   # the separate alias/batched-only audit; skipped when make_audit2 wrote no secondary item
        add(f'audit2.{s}', 'codex', 45, budget=1, set=s, brief='audit', post='answers', tier='secondary',
            refs={'make_audit2': f'make_audit2.{s}#secondary'}, copy_out='synth-heldout2/audit2/', skip_if='secondary_empty')
    for s in SETS:
        add(f'audit_compare.{s}', 'audit_compare', 5, set=s, tier='primary')
        add(f'adjudicate_audit.{s}', 'codex', 45, budget=1, set=s, brief='adjudicate', post='rulings',
            refs={'compare': f'audit_compare.{s}'}, variant=s)
        add(f'apply_audit.{s}', 'apply_audit', 5, set=s, tier='primary')
        add(f'audit2_compare.{s}', 'audit_compare', 5, set=s, tier='secondary', skip_if='secondary_empty')
        add(f'adjudicate_audit2.{s}', 'codex', 45, budget=1, set=s, brief='adjudicate', post='rulings',
            refs={'compare': f'audit2_compare.{s}'}, copy_out='synth-heldout2/adjudication2/', skip_if='secondary_empty', variant=s)
        add(f'apply_audit2.{s}', 'apply_audit', 5, set=s, tier='secondary', skip_if='secondary_empty')
    add('verify_freeze', 'verify_freeze', 2)
    add('score', 'local', 15, tool='score')
    return plan


# ================================================================== orchestrator
class Orchestrator:
    def __init__(self, code_root, root, mode, work_root, faults=None, scale=1.0, codex_home=None, stop_after=None,
                 sessions=None, stub_real=()):
        self.code = pathlib.Path(code_root).resolve()
        self.root = pathlib.Path(root)
        # Codex session folders live outside the repo (no inherited repo AGENTS.md); stub runs keep them in the run folder
        self.sessions = pathlib.Path(sessions) if sessions else (
            self.root / 'stub-sessions' if mode == 'stub' else pathlib.Path(os.path.expanduser(SESSIONS_HOME)) / self.root.name)
        self.stub_real = tuple(stub_real)
        self.mode = mode
        self.stub = mode == 'stub'
        self.work = pathlib.Path(work_root)
        self.faults = faults
        self.scale = scale
        self.codex_home = pathlib.Path(codex_home or os.environ.get('CODEX_HOME') or os.path.expanduser('~/.codex'))
        if self.stub:
            self.codex_home = self.root / 'stub-codex-home'
        self.stop_after = stop_after
        self.plan = build_plan()
        self.ids = [s['id'] for s in self.plan]
        self.by_id = {s['id']: s for s in self.plan}
        self.signal_seen = None
        self.briefs = {}
        self.state = None
        self.ledger = None

    # ---------------------------------------------------------- paths
    def w(self, rel):
        return self.work / rel

    def run_id(self, s):
        return RUN_ID.format(set=s)

    def brief(self, stage):
        name = stage['brief']
        if name not in self.briefs:
            self.briefs[name] = parse_brief(self.code / 'heldout2' / 'briefs' / f'{name}.md')
        return self.briefs[name]

    def copy_base(self, stage):
        b = (stage.get('copy_out') or self.brief(stage)['copy_out']).rstrip('/')
        return self.w(b + (f"/{stage['set']}" if stage.get('set') else ''))

    def audit_dir(self, s, tier):
        return self.w(AUDIT_DIR[tier].format(set=s))

    def audit_json(self, s, tier):
        return self.w(AUDIT_JSON[tier].format(set=s))

    def record_path(self, s):
        return self.root / 'private' / f'audit-record-{s}.json'

    def stage_folder(self, sid):
        if sid.endswith('#secondary'):                      # make_audit2's --out-secondary folder
            return self.audit_dir(self.by_id[sid.split('#')[0]]['set'], 'secondary')
        st = self.by_id[sid]
        k = st['kind']
        if k == 'codex':
            return self.sessions / sid
        if k == 'render':
            return self.stage_folder('generator_source')
        if k == 'local' and st['tool'] == 'make_layerb':
            return self.w(f"{CORPUS}/layerB/{st['set']}")
        if k == 'local' and st['tool'] == 'make_audit2':
            return self.w(f"{CORPUS}/audit/{st['set']}")
        return self.root / 'stages' / sid

    def ref_stage(self, stage, name):
        refs = stage.get('refs') or {}
        if name in refs:
            return refs[name]
        if stage.get('set') and f"{name}.{stage['set']}" in self.by_id:
            return f"{name}.{stage['set']}"
        if name in self.by_id:
            return name
        raise Stop(f"{stage['id']}: brief input @{name}/ names no stage")

    def resolve_input(self, stage, entry):
        entry = entry.replace('{variant}', stage.get('variant') or 'clean')   # adjudication sees one rendering only
        is_dir = entry.endswith('/')
        if entry.startswith('@'):
            name, _, rest = entry[1:].partition('/')
            ref = self.ref_stage(stage, name)
            rest = rest.rstrip('/')
            base = self.stage_folder(ref)
            return (base / rest if rest else base), rest, is_dir, ref
        rel = entry.rstrip('/')
        src = self.w(rel) if self.w(rel).exists() else self.code / rel
        dest = rel
        for pre in FLATTEN_PREFIXES:
            if rel.startswith(pre):
                dest = rel[len(pre):]
        return src, dest, is_dir, None

    def outputs(self, stage):
        """Declared output paths (hashed at DONE, verified on resume)."""
        k, s = stage['kind'], stage.get('set')
        if k == 'freeze_code':
            return [self.root / 'frozen-code.json']
        if k == 'codex':
            base = self.copy_base(stage)
            return [base / o.rstrip('/') for o in self.brief(stage)['outputs']]
        if k == 'render':
            return [self.w(f'{CORPUS}/clean'), self.w(f'{CORPUS}/scan'), self.stage_folder('render') / 'page-images']
        if k == 'compare' or k == 'audit_compare':
            return [self.root / 'stages' / stage['id'] / 'disagreements.json', self.root / 'private' / f"{stage['id']}-full.json"]
        if k == 'apply_rulings':
            return [self.w(f'{CORPUS}/truth'), self.w(f'{CORPUS}/truth-original'), self.w(f'{ADJ}/changes.json'),
                    self.w(f'{ADJ}/excluded.json')]
        if k == 'apply_audit':
            j = self.audit_json(s, stage['tier'])
            return [j, j.with_name('excluded.json'), j.with_name('label-changes.json')]
        if k == 'pulse':
            r = self.w(f'runs/{self.run_id(s)}')
            return [r / 'month.json', r / 'run.json', r / 'raw']
        if k == 'freeze_truth':
            return [self.w(f'{CORPUS}/layerB/{x}/truth-b.sha256') for x in SETS] + [self.root / 'frozen-truth.json']
        if k == 'expect':
            return [self.root / 'expected-units.json']
        if k == 'arm':
            st = self.state['stages'][stage['id']]
            return [pathlib.Path(st['out_dir'])] if st.get('out_dir') else []
        if k == 'local' and stage['tool'] == 'make_layerb':
            b = self.stage_folder(stage['id'])
            return [b / 'pages', b / 'BRIEF.md', b / 'truth-a.sha256']
        if k == 'local' and stage['tool'] == 'make_audit2':
            return [self.audit_dir(s, 'primary'), self.audit_dir(s, 'secondary'), self.record_path(s)]
        if k == 'local' and stage['tool'] == 'score':
            return [self.root / 'score.json', self.root / 'score.md']
        return []

    def inputs(self, stage):
        k, s = stage['kind'], stage.get('set')
        if k == 'codex':
            b = self.brief(stage)
            paths = [self.code / 'heldout2' / 'briefs' / f"{stage['brief']}.md"]
            for e in b['inputs']:
                paths.append(self.resolve_input(stage, e)[0])
            return paths
        if k == 'render':
            return self.outputs(self.by_id['generator_source'])
        if k == 'pulse':
            return self.outputs(self.by_id['render'])[:2] + [self.w(f'{CORPUS}/manifest.json')]
        if k == 'compare':
            return [self.w(f'{CORPUS}/truth'), self.w(f'{CORPUS}/blind/truth-blind'), self.w(f'{CORPUS}/manifest.json')]
        if k == 'apply_rulings':
            return [self.w(f'{ADJ}/rulings.json'), self.root / 'stages' / 'compare' / 'disagreements.json']
        if k == 'audit_compare':
            return [self.audit_dir(s, stage['tier']), self.record_path(s), self.root / 'arms.json']
        if k == 'apply_audit':
            cid = ('audit_compare' if stage['tier'] == 'primary' else 'audit2_compare') + f'.{s}'
            return [self.audit_json(s, stage['tier']).with_name('rulings.json'), self.root / 'private' / f'{cid}-full.json']
        if k == 'freeze_truth':
            return [self.w(f'{CORPUS}/truth')] + [self.w(f'{CORPUS}/layerB/{x}/truth-b') for x in SETS]
        if k == 'expect':
            return [self.w(f'{CORPUS}/manifest.json'), self.w(f'{CORPUS}/truth')] + \
                [q for x in SETS for q in (self.w(f'runs/{self.run_id(x)}/raw'), self.w(f'{CORPUS}/layerB/{x}/truth-b'))]
        if k == 'arm':
            r = self.w(f'runs/{self.run_id(s)}')
            return [r / 'month.json', r / 'raw', self.w(f'{CORPUS}/layerB/{s}/truth-b')]
        if k == 'local' and stage['tool'] == 'make_layerb':
            r = self.w(f'runs/{self.run_id(s)}')
            return [r / 'month.json', r / 'raw', self.w(f'{CORPUS}/manifest.json'), self.w(f'{CORPUS}/truth')]
        if k == 'local' and stage['tool'] == 'make_audit2':
            r = self.w(f'runs/{self.run_id(s)}')
            return [r / 'month.json', r / 'typed', self.w(f'{CORPUS}/manifest.json'), self.w(f'{CORPUS}/truth')]
        return []

    def later_claims(self, stage):
        i = self.ids.index(stage['id'])
        out = []
        for later in self.plan[i + 1:]:
            if later['kind'] == 'arm':
                continue
            try:
                out += self.outputs(later)
            except (OSError, ValueError, Stop):
                pass
        return out

    def hashes(self, stage, paths, own=False):
        """own=True (input hashes): the stage's own outputs inside an input folder (e.g. an audit's answers/) are
        excluded too, so the checkpoint covers only the immutable inputs."""
        ex = self.later_claims(stage) + (self.outputs(stage) if own else [])
        i = self.ids.index(stage['id'])
        res = {}
        for p in paths:
            q = pathlib.Path(p)
            alias = (self.state.get('aliases') or {}).get(str(q))
            if alias and i < alias['before_index']:
                q = pathlib.Path(alias['to'])
            res[str(p)] = hash_path(q, [e for e in ex if str(e) != str(q)])   # later stages' outputs inside q
        return res

    # ---------------------------------------------------------- commands
    def argv(self, stage, attempt=1, prompt='<prompt>', profile='<profile>'):
        """(argv, cwd, env_allow, extra_env) of the real command; stub wraps the same argv."""
        k, s = stage['kind'], stage.get('set')
        fmt = lambda tpl, **kw: [a.format(**kw) for a in tpl]
        if k == 'codex':
            folder = self.stage_folder(stage['id'])
            return [a.replace('{folder}', str(folder)).replace('{prompt}', prompt) for a in COMMANDS['codex']], folder, (), {}
        if k == 'render':
            return fmt(COMMANDS['render'], profile=profile), self.stage_folder('render'), (), dict(RENDER_ENV)
        if k == 'pulse':
            return fmt(COMMANDS['pulse'], set=s, run_id=self.run_id(s)), self.work, (KEY_ENVS['pulse'],), {}
        if k == 'arm':
            a = fmt(COMMANDS['arm'], backend=stage['backend'], run_id=self.run_id(s), set=s,
                    max_wall=str(int(min(stage['deadline'] * self.scale, self.remaining())) or 1))
            if stage['backend'] != 'jev':
                a += ['--model', MODEL]
            if stage['backend'] != 'claude':
                a += ['--max-spend', f'{JEV_MAX_SPEND_PER_RUN:.4f}']
            if stage['extra']:
                a += ['--'] + stage['extra']
            allow = (KEY_ENVS['jev'],) if stage['backend'] != 'claude' else ()
            return a, self.code, allow, {}
        if k == 'local':
            t = stage['tool']
            a = fmt(COMMANDS[t], set=s or '', run_id=self.run_id(s) if s else '', run_clean=self.run_id('clean'),
                    run_scan=self.run_id('scan'), root=str(self.root))
            if t == 'score':
                for x in SETS:
                    for flag, tier, sid in (('--audit', 'primary', f'apply_audit.{x}'), ('--audit2', 'secondary', f'apply_audit2.{x}')):
                        if self.state is None:
                            a += [flag, f'{x}=<{AUDIT_JSON[tier].format(set=x)}>' + (' (if that set ran)' if tier == 'secondary' else '')]
                        elif self.st(sid)['status'] == 'DONE':
                            a += [flag, f'{x}={self.audit_json(x, tier)}']
            return a, self.work, (), {}
        return None, None, (), {}

    def wrap(self, stage, attempt, argv, extra_meta=None):
        if not self.stub or (stage['kind'] == 'local' and stage['tool'] in self.stub_real):
            return argv
        meta = {'kind': stage['kind'] if stage['kind'] != 'local' else stage['tool'], 'stage': stage['id'],
                'attempt': attempt, 'root': str(self.root), 'work': str(self.work), 'code': str(self.code),
                'faults': self.faults, 'codex_home': str(self.codex_home)}
        meta.update(extra_meta or {})
        return [sys.executable, str(SCRIPT), '_fake', json.dumps(meta), '--'] + argv

    # ---------------------------------------------------------- state
    def st(self, sid):
        return self.state['stages'].setdefault(sid, {'status': 'PENDING', 'attempts': 0})

    def save(self):
        write_json(self.root / 'state.json', self.state)

    def status(self, sid, status, attempt, detail=''):
        line = redact(f'{now()}  {sid:<26} {status:<11} a={attempt}  {detail}'.rstrip())
        with open(self.root / 'status.log', 'a') as fh:
            fh.write(line + '\n')
        print(line, flush=True)

    # ---------------------------------------------------------- processes
    def run_proc(self, argv, cwd, env, log_path, deadline_s, watch_usage=False, monitor=None):
        """Run argv in its own process group. Output goes through a pipe and is redacted before it reaches the log
        (a tail of max-secret-length bytes is held back so a secret split across reads is still caught).
        monitor: optional callable polled about once a second; a non-empty return kills the stage (outcome 'monitor')."""
        log_path = pathlib.Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if deadline_s <= 0:
            return 'deadline', None                      # the stage deadline is already spent: do not start
        lf = open(log_path, 'ab')
        p = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, start_new_session=True)
        fd = p.stdout.fileno()
        os.set_blocking(fd, False)
        keep = max((len(x) for x in REDACT), default=1) - 1
        buf, recent = [b''], [b'']     # recent: last bytes written, so a pattern split across the hold-back is still seen

        def pump(final=False):
            while True:
                try:
                    chunk = os.read(fd, 65536)
                except BlockingIOError:
                    break
                if not chunk:
                    break
                buf[0] += chunk
            data = redact_bytes(buf[0])
            if final or keep <= 0 or len(data) <= keep:
                out, buf[0] = (data, b'') if (final or keep <= 0) else (b'', data)
            else:
                out, buf[0] = data[:-keep], data[-keep:]
            if out:
                lf.write(out)
                lf.flush()
                recent[0] = (recent[0] + out)[-512:]
        self.state['current_child'] = p.pid
        self.save()
        t_end = time.monotonic() + deadline_s
        outcome, pos, next_mon = 'exit', 0, 0.0
        self.monitor_reason = ''
        while p.poll() is None:
            pump()
            if self.signal_seen:
                outcome = 'interrupted'
                break
            if time.monotonic() > t_end:
                outcome = 'deadline'
                break
            if watch_usage and USAGE_LIMIT_RE.search(redact_bytes(recent[0] + buf[0]).decode(errors='replace')):
                outcome = 'usage_limit'
                break
            if monitor and time.monotonic() >= next_mon:
                next_mon = time.monotonic() + 1.0
                why = monitor()
                if why:
                    self.monitor_reason, outcome = why, 'monitor'
                    break
            time.sleep(0.1)
        pump()
        self.kill_group(p.pid, p)
        pump(final=True)
        p.stdout.close()
        lf.close()
        if outcome == 'exit' and watch_usage and self.usage_hit(log_path, 0)[0]:
            outcome = 'usage_limit'
        self.state['current_child'] = None
        self.save()
        return outcome, p.returncode

    @staticmethod
    def usage_hit(path, pos):
        try:
            with open(path, 'rb') as fh:
                fh.seek(pos)
                data = fh.read()
        except OSError:
            return False, pos
        return bool(USAGE_LIMIT_RE.search(data.decode(errors='replace'))), pos + len(data)

    @staticmethod
    def group_alive(pgid):
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    @staticmethod
    def group_pids(pgid):
        out = subprocess.run(['ps', '-A', '-o', 'pid=,pgid=,stat='], capture_output=True, text=True).stdout
        return [int(a) for a, b, st in (l.split()[:3] for l in out.splitlines() if len(l.split()) >= 3)
                if int(b) == pgid and not st.startswith('Z')]

    def kill_group(self, pgid, p=None):
        """Whatever the leader's exit status: TERM the group, wait up to GRACE_S, KILL, then verify it is gone.
        Survivors are reported in status.log by pid. Descendants that left the group (setsid) are not covered."""
        def gone():
            if p is not None:
                p.poll()
            return not self.group_alive(pgid) or not self.group_pids(pgid)
        if not gone():
            try:
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            t = time.monotonic() + GRACE_S
            while not gone() and time.monotonic() < t:
                time.sleep(0.1)
            if not gone():
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                t = time.monotonic() + 2
                while not gone() and time.monotonic() < t:
                    time.sleep(0.1)
        if p is not None:
            p.wait()
        left = self.group_pids(pgid) if self.group_alive(pgid) else []
        if left:
            self.status(getattr(self, 'cur_sid', '?'), 'WARN', 0, f'process group {pgid}: pid(s) {left} survived SIGKILL')
        return left

    def quarantine(self, sid, attempt, paths):
        q = self.root / 'quarantine' / f'{sid}-a{attempt}'
        moved = []
        for p in paths:
            p = pathlib.Path(p)
            if not p.exists():
                continue
            base = self.work if under(p, self.work) else self.root if under(p, self.root) else self.sessions if under(p, self.sessions) else p.parent
            rel = os.path.relpath(p, base).replace(os.sep, '__')
            q.mkdir(parents=True, exist_ok=True)
            target = q / rel
            n = 1
            while target.exists():
                target = q / f'{rel}.{n}'
                n += 1
            shutil.move(str(p), str(target))
            moved.append(str(target))
        return moved

    def quarantine_targets(self, stage):
        k, st = stage['kind'], self.st(stage['id'])
        if k == 'codex':
            return [self.stage_folder(stage['id'])] + self.outputs(stage)
        if k == 'render':
            f = self.stage_folder('render')
            return [self.w(f'{CORPUS}/clean'), self.w(f'{CORPUS}/scan'), f / 'clean', f / 'scan', f / 'page-images']
        if k == 'pulse':
            return [self.w(f"runs/{self.run_id(stage['set'])}")]
        if k == 'arm':
            typed = self.w(f"runs/{self.run_id(stage['set'])}/typed")
            if st.get('pre_listing') is None or not typed.is_dir():
                return []
            pre = set(st['pre_listing'])
            return [typed / name for name in sorted(os.listdir(typed)) if name not in pre]   # this attempt's out dir
        if k in ('local', 'compare', 'audit_compare'):
            return self.outputs(stage)
        return []

    # ---------------------------------------------------------- freeze
    def freeze_listing(self):
        files = list(FREEZE_FILES)
        for g in FREEZE_GLOBS:
            files += sorted(str(p.relative_to(self.code)) for p in self.code.glob(g) if p.is_file())
        return files + list(FREEZE_EXTRA)

    def freeze_snapshot(self):
        snap = {'files': {}, 'missing': []}
        for rel in self.freeze_listing():
            p = self.code / rel
            if p.is_file():
                snap['files'][rel] = sha_file(p)
            else:
                snap['missing'].append(rel)
        v = alias_constant(self.code / ALIAS_SOURCE)
        snap['alias'] = None if v is None else {'value': v, 'sha256': sha_bytes(v.encode())}
        req = parse_required(self.code / 'reconcile.py')
        snap['required'] = None if req is None else {
            'sha256': sha_bytes(json.dumps(req, sort_keys=True, separators=(',', ':')).encode()), 'classes': len(req)}
        return snap

    def verify_code(self, where):
        frozen = read_json(self.root / 'frozen-code.json')
        if not frozen:
            raise Stop(f'{where}: frozen-code.json missing; FREEZE-MISMATCH')
        cur = self.freeze_snapshot()
        bad = [rel for rel, h in frozen['files'].items() if cur['files'].get(rel) != h]
        if (frozen.get('alias') or {}).get('sha256') != (cur.get('alias') or {}).get('sha256'):
            bad.append(f'{ALIAS_SOURCE}:{ALIAS_NAME}')
        if (frozen.get('required') or {}).get('sha256') != (cur.get('required') or {}).get('sha256'):
            bad.append('reconcile.py:REQUIRED (parsed value)')
        if bad:
            raise Stop(f'{where}: FREEZE-MISMATCH: {", ".join(bad)} changed after the freeze')

    def verify_truth(self, where):
        fz = read_json(self.root / 'frozen-truth.json')
        if not fz:
            raise Stop(f'{where}: frozen-truth.json missing; FREEZE-MISMATCH')
        bad = [p for p, h in fz['dirs'].items() if hash_path(p) != h]
        for s in SETS:
            f = self.w(f'{CORPUS}/layerB/{s}/truth-b.sha256')
            if not f.is_file() or f.read_text().strip() != fz['truth_b_sha256'].get(s):
                bad.append(str(f))
        if bad:
            raise Stop(f'{where}: FREEZE-MISMATCH: {", ".join(bad)} changed after the truth freeze')

    # ---------------------------------------------------------- main loop
    def take_lock(self):
        """Exclusive lock on <run>/.lock for this process's lifetime; a second orchestrator stops here."""
        if getattr(self, 'lock_fh', None):
            return
        fh = open(self.root / '.lock', 'a')
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            raise Stop(f'another orchestrator process holds {self.root}/.lock; refusing to run two on one run folder')
        self.lock_fh = fh

    def setup_new(self, stamp):
        # A new run must start on a clean tree: outputs left by an earlier run would fail a copy-out and burn a retry.
        left = [str(p) for p in [self.w(CORPUS)] + [self.w('runs') / self.run_id(s) for s in SETS] if p.exists()]
        if left:
            raise Stop(f'new run refused, outputs of an earlier run exist: {", ".join(left)}; continue that run with '
                       f'--resume <stamp>, or move them aside first; nothing started')
        self.root.mkdir(parents=True, exist_ok=False)
        self.take_lock()
        self.state = {'version': 1, 'stamp': stamp, 'mode': self.mode, 'code_root': str(self.code), 'work_root': str(self.work),
                      'created': now(), 'stage_order': self.ids, 'stages': {}, 'pools': {}, 'aliases': {},
                      'orchestrator_sha256': sha_file(SCRIPT), 'current_child': None, 'sessions': str(self.sessions),
                      'stub_real': list(self.stub_real)}
        self.ledger = Ledger(self.root / 'ledger.json')
        self.ledger.save()
        self.save()

    def setup_resume(self):
        self.take_lock()
        self.state = read_json(self.root / 'state.json')
        if not isinstance(self.state, dict) or not {'stage_order', 'stages', 'pools', 'mode'} <= set(self.state):
            raise Stop(f'resume: {self.root}/state.json is missing, unreadable, or malformed; refusing to guess')
        if self.state['stage_order'] != self.ids:
            raise Stop('resume: the stage plan differs from the one this run started with; refusing')
        self.ledger = Ledger(self.root / 'ledger.json', must_exist=True)
        with open(self.root / 'status.log', 'a') as fh:
            fh.write(f'{now()}  RESUME by pid {os.getpid()}; ledger {json.dumps(self.ledger.summary())}\n')
        if self.st('freeze_code')['status'] == 'DONE':
            self.verify_code('resume')
        for stage in self.plan:
            st = self.st(stage['id'])
            if st['status'] != 'DONE':
                continue
            for kind in ('inputs', 'outputs'):
                rec = st.get(kind) or {}
                cur = self.hashes(stage, list(rec.keys()), own=kind == 'inputs')
                diff = [p for p in rec if cur.get(p) != rec[p]]
                if diff:
                    raise Stop(f"resume: {stage['id']} {kind} changed since it finished ({diff[0]}); HASH-MISMATCH, refusing")

    def preflight_live(self):
        missing = [c for c in ('codex', 'claude', 'sandbox-exec', 'pdftoppm', 'bash') if not shutil.which(c)]
        if missing:
            raise Stop(f'preflight: not on PATH: {", ".join(missing)}')
        for name in KEY_ENVS.values():
            self.key_check(name)

    def key_check(self, name):
        n = len(os.environ.get(name, ''))
        if n < KEY_MIN:
            raise Stop(f'{name} missing or shorter than {KEY_MIN} chars ({n}); value not shown')

    def run(self):
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda signum, frame: setattr(self, 'signal_seen', signal.Signals(signum).name))
        i = 0
        while i < len(self.plan):
            if self.signal_seen:
                raise Stop(f'stopped by {self.signal_seen} between stages')
            stage = self.plan[i]
            res = self.drive(stage)
            if res == 'done':
                if self.stop_after and stage['id'] == self.stop_after:
                    self.status(stage['id'], 'STOP-AFTER', self.st(stage['id'])['attempts'], 'stopped as asked; --resume continues')
                    return 0
                i += 1
            else:
                i = res
        v = getattr(self, 'verdict', None) or ((read_json(self.root / 'score.json') or {}).get('verdict') or {})
        self.status('run', 'COMPLETE', 0, f"verdict Overall {v.get('Overall')}; ledger {json.dumps(self.ledger.summary())}")
        return 0

    def drive(self, stage):
        sid, st = stage['id'], self.st(stage['id'])
        if st['status'] in ('DONE', 'SKIPPED'):
            return 'done'
        if stage.get('skip_if') and st['status'] == 'PENDING':
            why = getattr(self, 'skip_' + stage['skip_if'])(stage)
            if why:
                st.update(status='SKIPPED', detail=why)
                self.save()
                self.status(sid, 'SKIPPED', 0, why)
                return 'done'
        if st['status'] == 'INVALID':
            raise Invalid(f'{sid} is INVALID ({st.get("detail")}); the run cannot continue')
        if st['status'] == 'RUNNING':
            self.interrupted_leftover(stage, st)
        while True:
            if st['status'] in ('FAILED', 'USAGE-LIMIT'):
                pool, used = stage['pool'], self.state['pools'].get(stage['pool'], 0)
                if used >= stage['budget']:
                    self.status(sid, 'STOP', st['attempts'], f'retry budget for {pool} used ({used}/{stage["budget"]})')
                    raise Stop(f'{sid}: failed; retry budget for {pool} used ({used}/{stage["budget"]})')
                self.state['pools'][pool] = used + 1
                self.save()
                if stage.get('group'):
                    first = next(i for i, s in enumerate(self.plan) if s.get('group') == stage['group'])
                    for g in self.plan:
                        if g.get('group') == stage['group']:
                            gst = self.st(g['id'])
                            self.quarantine(g['id'], gst['attempts'], self.quarantine_targets(g))
                            gst['status'] = 'PENDING'
                    self.status(sid, 'RETRY', st['attempts'], f'R7 group {stage["group"]}: rerun from {self.ids[first]} '
                                f'(pool {pool} {used + 1}/{stage["budget"]})')
                    self.save()
                    return first
                self.quarantine(sid, st['attempts'], self.quarantine_targets(stage))
                self.status(sid, 'RETRY', st['attempts'], f'pool {pool} {used + 1}/{stage["budget"]}')
            if self.attempt(stage) == 'DONE':
                return 'done'

    def interrupted_leftover(self, stage, st):
        """A stage left RUNNING by a dead orchestrator: its attempt failed with an unknown outcome."""
        pid = self.state.get('current_child')
        if pid:
            self.cur_sid = stage['id']
            self.kill_group(pid)
        res = self.bound(stage)
        if res:
            self.ledger.mark_unknown(stage['id'], st['attempts'], res[0])
        st['status'] = 'FAILED'
        st['detail'] = 'interrupted: orchestrator ended mid-stage; outcome unknown'
        self.status(stage['id'], 'FAILED', st['attempts'], st['detail'])
        self.save()

    def bound(self, stage):
        if stage['kind'] == 'pulse':
            man = read_json(self.w(f'{CORPUS}/manifest.json')) or {}
            try:
                pages = sum(int(p['pages']) for p in man['packets'])
                return 'pulse_credits', float(math.ceil(pages * PULSE_CREDITS_PER_PAGE_BOUND))
            except (KeyError, TypeError, ValueError):
                return 'pulse_credits', PULSE_FALLBACK_BOUND
        if stage['kind'] == 'arm' and stage['backend'] != 'claude':
            return 'jev_usd', JEV_MAX_SPEND_PER_RUN
        return None

    def attempt(self, stage):
        sid, st = stage['id'], self.st(stage['id'])
        n = st['attempts'] + 1
        res = self.bound(stage)
        if res and self.ledger.would_pass(*res):
            st['status'], st['detail'] = 'REFUSED', (f'CAP: {res[0]} spent {self.ledger.spent(res[0]):g} + bound {res[1]:g} '
                                                     f'would pass cap {self.ledger.d["caps"][res[0]]:g}'
                                                     + (f'. {PULSE_RETRY_NOTE}' if stage['kind'] == 'pulse' else ''))
            self.save()
            self.status(sid, 'REFUSED', n, st['detail'])
            raise Stop(f'{sid}: {st["detail"]}')
        if not self.stub and stage['kind'] in ('pulse', 'arm'):
            if stage['kind'] == 'pulse':
                self.key_check(KEY_ENVS['pulse'])
            elif stage['backend'] != 'claude':
                self.key_check(KEY_ENVS['jev'])
        st.update(status='RUNNING', attempts=n, started=now(), detail='')
        st.pop('out_dir', None)
        self.cur_sid, self.spend_floor = sid, 0.0
        self.stage_end = time.monotonic() + stage['deadline'] * self.scale     # one deadline for the whole stage
        st['inputs'] = self.hashes(stage, self.inputs(stage), own=True)
        self.save()
        if res:
            self.ledger.reserve(sid, n, res[0], res[1])
        self.status(sid, 'START', n, f'deadline {stage["deadline"] * self.scale:g}s' + (f'; bound {res[0]} {res[1]:g}' if res else '')
                    + (f'; NOTE {PULSE_RETRY_NOTE}' if stage['kind'] == 'pulse' else ''))
        t0 = time.monotonic()
        actual = None
        try:
            ok, detail, actual = getattr(self, 'do_' + stage['kind'])(stage, n)
        except Invalid as e:
            self.settle(stage, n, res, actual)
            st.update(status='INVALID', detail=str(e))
            self.save()
            self.status(sid, 'INVALID', n, str(e))
            raise
        except UsageLimit as e:
            self.settle(stage, n, res, None)
            st.update(status='USAGE-LIMIT', detail=str(e))
            self.save()
            self.status(sid, 'USAGE-LIMIT', n, str(e))
            raise Stop(f'{sid}: R11 usage-limit message seen; stopped without waiting ({e})')
        except Interrupted as e:
            self.settle(stage, n, res, None)
            st.update(status='FAILED', detail=f'interrupted: {e}')
            self.save()
            self.status(sid, 'FAILED', n, f'interrupted: {e}')
            raise Stop(f'{sid}: interrupted by {e}; --resume continues (this attempt counts)')
        except Stop as e:
            self.settle(stage, n, res, None)
            st.update(status='FAILED', detail=str(e))
            self.save()
            self.status(sid, 'STOP', n, str(e))
            raise
        self.settle(stage, n, res, actual)
        wall = f'wall {time.monotonic() - t0:.1f}s'
        if ok:
            st.update(status='DONE', finished=now(), detail=detail)
            st['outputs'] = self.hashes(stage, self.outputs(stage))
            self.save()
            if stage['kind'] == 'arm':
                self.write_registry()
            self.status(sid, 'DONE', n, f'{wall}; {detail}')
            return 'DONE'
        st.update(status='FAILED', detail=detail)
        self.save()
        self.status(sid, 'FAILED', n, f'{wall}; {detail}')
        return 'FAILED'

    def settle(self, stage, n, res, actual):
        if not res:
            return
        if actual is None:
            self.ledger.mark_unknown(stage['id'], n, res[0], floor=getattr(self, 'spend_floor', 0.0))
        else:
            self.ledger.settle(stage['id'], n, res[0], actual)

    def remaining(self):
        return max(0.0, getattr(self, 'stage_end', float('inf')) - time.monotonic())

    def outcome_check(self, outcome, rc):
        if outcome == 'interrupted':
            raise Interrupted(self.signal_seen or 'signal')
        if outcome == 'usage_limit':
            raise UsageLimit('usage-limit text in the stage log')
        if outcome == 'deadline':
            return False, 'DEADLINE: process group killed at the deadline'
        if rc != 0:
            return False, f'exit {rc}'
        return True, ''

    # ---------------------------------------------------------- stage kinds
    def do_freeze_code(self, stage, n):
        snap = self.freeze_snapshot()
        if snap['missing'] or snap['alias'] is None or snap['required'] is None:
            miss = snap['missing'] + ([f'{ALIAS_SOURCE}:{ALIAS_NAME}'] if snap['alias'] is None else []) + \
                (['reconcile.py:REQUIRED'] if snap['required'] is None else [])
            raise Stop(f'freeze: cannot freeze, missing: {", ".join(miss)}')
        for b in BRIEFS:
            parse_brief(self.code / 'heldout2' / 'briefs' / f'{b}.md')
        snap['created'] = now()
        write_json(self.root / 'frozen-code.json', snap)
        return True, f'{len(snap["files"])} files + {ALIAS_NAME} frozen', None

    def do_verify_freeze(self, stage, n):
        self.verify_code('verify_freeze')
        self.verify_truth('verify_freeze')
        self.verify_registry('verify_freeze')
        return True, 'code, briefs, alias constant, and truth hashes match the freeze', None

    def do_codex(self, stage, n):
        sid = stage['id']
        b = self.brief(stage)
        frozen = read_json(self.root / 'frozen-code.json') or {'files': {}}
        brel = f"heldout2/briefs/{stage['brief']}.md"
        if sha_file(self.code / brel) != frozen['files'].get(brel):
            raise Stop(f'{sid}: FREEZE-MISMATCH: {brel} changed after the freeze')
        folder = self.stage_folder(sid)
        if folder.exists():
            self.quarantine(sid, n - 1, [folder])
        folder.mkdir(parents=True)
        rec = {'stage': sid, 'attempt': n, 'folder': str(folder), 'brief': brel, 'brief_sha256': b['sha256'],
               'prompt_sha256': sha_bytes(b['body'].encode()), 'prompt_chars': len(b['body']), 'inputs': [], 'started': now()}
        for entry in b['inputs']:
            src, dest, is_dir, ref = self.resolve_input(stage, entry)
            if ref and self.st(ref.split('#')[0])['status'] != 'DONE':
                raise Stop(f'{sid}: input {entry} needs stage {ref} DONE')
            if not src.exists():
                return False, f'input missing: {entry} ({src})', None
            if entry.startswith('heldout2/') and not entry.startswith('@'):
                for f in ([src] if src.is_file() else [x for x in src.rglob('*') if x.is_file()]):
                    rel = str(f.relative_to(self.code))
                    if rel in frozen['files'] and sha_file(f) != frozen['files'][rel]:
                        raise Stop(f'{sid}: FREEZE-MISMATCH: {rel} changed after the freeze')
            self.copy_in(src, folder, dest, sid)
            rec['inputs'].append({'entry': entry, 'src': str(src), 'dest': dest or '.', 'sha256': hash_path(src)})
        dis = read_json(folder / 'disagreements.json')
        if isinstance(dis, list):                   # an adjudicator must be able to open every image it is pointed at
            missing = [i for x in dis for i in (x.get('images') or [None]) if not i or not (folder / i).is_file()]
            if missing:
                return False, f'adjudication evidence: {len(missing)} image path(s) missing in the session folder, first {missing[0]}', None
        (folder / f'PROMPT-{sid}.md').write_text(b['body'])
        rec['instruction_files'] = instruction_files(self.codex_home, folder)
        inh = [i['path'].replace(os.path.expanduser('~'), '~') for i in rec['instruction_files']
               if pathlib.Path(i['path']).name in ('AGENTS.md', 'AGENTS.override.md', 'instructions.md')]
        self.status(sid, 'INHERITS', n, ('Codex instruction files this session inherits: ' + ', '.join(inh)) if inh
                    else 'no inherited Codex instruction file found')
        env = strip_env()
        rec['env_names_removed'] = sum(1 for k in os.environ if k not in env)
        argv, cwd, _, _ = self.argv(stage, n, prompt=b['body'])
        rec['argv'] = argv[:-1] + [f'<prompt sha256 {rec["prompt_sha256"][:16]}>']
        log = self.root / 'logs' / f'{sid}-a{n}.log'
        since = time.time()
        outcome, rc = self.run_proc(self.wrap(stage, n, argv, {'outputs': b['outputs']}), folder, env, log,
                                    self.remaining())
        rec.update(finished=now(), outcome=outcome, rc=rc, log=str(log))
        # R4 scan, before anything else is trusted
        rolls = find_rollouts(self.codex_home, folder, since)
        cmds = commands_from_stdout(log)
        saved = []
        for i, r in enumerate(rolls):
            dst = self.root / 'logs' / f'{sid}-a{n}.rollout{i + 1}.jsonl'
            dst.write_bytes(redact_bytes(pathlib.Path(r).read_bytes()))
            saved.append(str(dst))
            cmds += commands_from_rollout(r)[1]
        found = scan_commands(cmds, folder)
        hits = [h for h in found if h[0] == 'hit']
        rec['scan'] = {'sources': (['rollout'] if rolls else []) + ['stdout'], 'rollouts': saved, 'commands': len(cmds),
                       'hits': hits, 'allowed': [h for h in found if h[0] == 'allowed']}
        write_json(self.root / 'records' / f'{sid}-a{n}.json', rec)
        if not rolls:
            self.status(sid, 'WARN', n, 'no Codex rollout file found for this folder; scan used stdout only')
        if hits:
            raise Invalid(f'R4 out-of-folder read: {hits[0][1]} (in: {hits[0][2][:80]}); {len(hits)} hit(s)')
        ok, detail = self.outcome_check(outcome, rc)
        if not ok:
            return False, detail, None
        missing = [o for o in b['outputs'] if not (folder / o.rstrip('/')).exists()]
        if missing:
            return False, f'OUTPUTS missing: {", ".join(missing)}', None
        base = self.copy_base(stage)
        clash = [str(base / o.rstrip('/')) for o in b['outputs'] if (base / o.rstrip('/')).exists()]
        if clash:
            return False, f'copy-out refused, destination exists: {clash[0]}', None
        for o in b['outputs']:
            src, dst = folder / o.rstrip('/'), base / o.rstrip('/')
            dst.parent.mkdir(parents=True, exist_ok=True)
            (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
        post = stage.get('post')
        if post:
            ok, detail = getattr(self, 'post_' + post)(stage, folder)
            if not ok:
                return False, detail, None
        if self.remaining() <= 0:
            return False, 'DEADLINE: copy-out and validation passed the stage deadline', None
        return True, f'{len(b["outputs"])} output(s) copied to {os.path.relpath(base, self.work)}; scan {len(cmds)} command(s), 0 hits' \
            + (f'; {detail}' if post else ''), None

    def copy_in(self, src, folder, dest, sid):
        if not dest:
            for child in sorted(src.iterdir()):
                self.copy_in(child, folder, child.name, sid)
            return
        dst = folder / dest
        if dst.exists():
            if hash_path(dst) == hash_path(src):
                return   # the same bytes already arrived through another input (e.g. composition.md inside @render/)
            raise Stop(f'{sid}: input name collision in the session folder: {dest}')
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, symlinks=False, ignore=skip_special)
        else:
            shutil.copy2(src, dst)

    # ---------- post checks (counts only; the agent never sees class names or cases)
    def post_quota(self, stage, folder):
        cov, spec = read_json(self.w(COVERAGE)), read_json(self.w(CASE_SPEC))
        if not isinstance(cov, dict) or not isinstance(spec, dict):
            return False, 'quota check: coverage.json or case_spec.json unreadable'
        classes = {c.get('class_id'): int(c.get('min_documents') or 0) for c in cov.get('classes') or []}
        docs = spec.get('documents') or []
        counts = {}
        for d in docs:
            for c in d.get('class_ids') or []:
                counts[c] = counts.get(c, 0) + 1
        unmet = [c for c, m in classes.items() if counts.get(c, 0) < m]
        plain = sum(1 for d in docs if not d.get('class_ids') and d.get('afe_number_is_printed') is True)
        plain_ok = plain >= int(cov.get('plain_controls_min') or 0)
        ok = bool(classes) and not unmet and plain_ok and len(docs) == COMPOSITION['documents']
        return ok, (f'quotas: {len(classes) - len(unmet)} of {len(classes)} classes met; plain controls '
                    f'{"met" if plain_ok else "SHORT"}; documents {len(docs)} of {COMPOSITION["documents"]}')

    def post_build_gates(self, stage, folder):
        """Independent build gates before any Pulse spend (review finding 6). A failure fails the build group (R7).
        Detail names documents and files, never case classes (the rule author must not learn them)."""
        bad = []
        g = read_json(folder / 'gates.json')
        gates = g.get('gates') if isinstance(g, dict) else None
        if not isinstance(gates, list) or not gates:
            bad.append('gates.json missing or without a gates list')
        else:
            failed = [str(x.get('id')) for x in gates if not (isinstance(x, dict) and x.get('pass') is True)]
            if failed:
                bad.append(f'gates.json reports failed gate(s): {", ".join(failed[:5])}')
            ids = {x.get('id') for x in gates if isinstance(x, dict)}
            missing = [g for g in GATE_IDS if g not in ids]
            if missing:
                bad.append(f'gates.json lacks mandatory gate(s): {", ".join(missing)}')
        man = read_json(self.w(f'{CORPUS}/manifest.json'))
        if not isinstance(man, dict) or not isinstance(man.get('documents'), list) or not isinstance(man.get('packets'), list):
            return False, 'build gates: manifest.json unreadable'
        docs, packets = man['documents'], man['packets']
        try:
            pages = sum(int(p['pages']) for p in packets)
            doc_pages = sum(int(d['page_count']) for d in docs)
        except (KeyError, TypeError, ValueError):
            return False, 'build gates: manifest pages or page_count missing'
        got = {'packets': len(packets), 'documents': len(docs), 'pages': pages}
        if got != COMPOSITION or doc_pages != COMPOSITION['pages']:
            bad.append(f'composition {got} (document pages {doc_pages}), want {COMPOSITION}')
        files = 0
        for s, fk, hk in (('clean', 'file', 'sha256'), ('scan', 'scan_file', 'scan_sha256')):
            for e, want_pages in [(d, d.get('page_count')) for d in docs] + [(p, p.get('pages')) for p in packets]:
                name = e.get('doc_id') or e.get('packet_id')
                f = self.w(str(e.get(fk) or ''))
                if not e.get(fk) or not f.is_file():
                    bad.append(f'{s} {name}: PDF missing ({e.get(fk)})')
                    continue
                files += 1
                if sha_file(f) != e.get(hk):
                    bad.append(f'{s} {name}: sha256 differs from the manifest')
                if self.remaining() <= 0:
                    return False, 'DEADLINE: build-gate validation passed the stage deadline'
                n = pdf_pages(f, timeout=self.remaining())
                if n is None or n != int(want_pages or -1):
                    bad.append(f'{s} {name}: {n} page(s), manifest says {want_pages}')
        required = parse_required(self.code / 'reconcile.py') or {}
        truth = {}
        for d in docs:
            t = read_json(self.w(f"{CORPUS}/truth/{d['doc_id']}.json"))
            vals = t.get('values') if isinstance(t, dict) else None
            if not isinstance(vals, dict):
                bad.append(f"truth {d['doc_id']}: missing or without values")
                continue
            truth[d['doc_id']] = vals
            miss = [k for k in required.get(d.get('class'), []) if k not in vals]
            if miss:
                bad.append(f"truth {d['doc_id']}: required key(s) missing: {', '.join(miss)}")
        cases = read_json(self.w(f'{CORPUS}/cases.json'))
        if not isinstance(cases, list):
            bad.append('cases.json unreadable')
            cases = []
        by_doc = {}
        for c in cases:
            if isinstance(c, dict):
                by_doc.setdefault(c.get('doc_id'), []).append(c)
        ids = {d['doc_id'] for d in docs}
        if set(by_doc) != ids:
            bad.append(f'cases.json covers {len(set(by_doc) & ids)} of {len(ids)} documents'
                       + (f'; unknown ids {sorted(set(by_doc) - ids)[:3]}' if set(by_doc) - ids else ''))
        for d in docs:
            if 'afe_number' not in required.get(d.get('class'), []) or d['doc_id'] not in truth:
                continue
            printed = truth[d['doc_id']].get('afe_number') is not None
            if any(c.get('flag_would_be_false_alarm') is not (not printed) for c in by_doc.get(d['doc_id'], [])):
                bad.append(f"cases.json {d['doc_id']}: flag_would_be_false_alarm disagrees with layer A (afe_number "
                           f"{'printed' if printed else 'not printed'})")
        cov = read_json(self.w(COVERAGE))
        if isinstance(cov, dict):
            mins = {c.get('class_id'): int(c.get('min_documents') or 0) for c in cov.get('classes') or []}
            have = {k: len({c.get('doc_id') for c in cases if c.get('class_id') == k}) for k in mins}
            unmet = sum(1 for k, m in mins.items() if have[k] < m)
            plain = sum(1 for d, cs in by_doc.items() if cs and all(c.get('class_id') in ('baseline', None) for c in cs)
                        and truth.get(d, {}).get('afe_number') is not None)
            if unmet or plain < int(cov.get('plain_controls_min') or 0):
                bad.append(f'quota check against cases.json: {unmet} class quota(s) unmet; plain controls {plain} of '
                           f'{cov.get("plain_controls_min")} needed')
        else:
            bad.append('coverage.json unreadable for the quota check')
        # (a) every clean page has text, checked here with pdftotext (not taken from the session's attestation)
        empty = []
        for d in docs:
            f = self.w(str(d.get('file') or ''))
            if not f.is_file():
                continue
            if self.remaining() <= 0:
                return False, 'DEADLINE: build-gate validation passed the stage deadline'
            try:
                txt = subprocess.run(['pdftotext', '-layout', str(f), '-'], capture_output=True, text=True,
                                     timeout=max(self.remaining(), 0.01), env=strip_env()).stdout
            except (OSError, subprocess.SubprocessError) as e:
                bad.append(f"clean {d['doc_id']}: pdftotext failed ({type(e).__name__})")
                continue
            pages = txt.split('\f')[:int(d.get('page_count') or 1)]
            empty += [f"{d['doc_id']} p{i}" for i, t in enumerate(pages, 1) if not t.strip()]
            if len(pages) < int(d.get('page_count') or 1):
                empty.append(f"{d['doc_id']} (pdftotext returned {len(pages)} page(s))")
        if empty:
            bad.append(f'clean pages without extractable text: {len(empty)}, first {empty[0]}')
        # (b) no proper noun of the earlier corpus in src/, truth/, reference/ (case-insensitive, whole word)
        terms = earlier_nouns(self.code)
        if terms is None:
            bad.append('earlier corpus proper nouns unreadable (synth-heldout/manifest.json story)')
        else:
            rx = re.compile(r'(?<![A-Za-z0-9])(' + '|'.join(re.escape(t) for t in sorted(terms, key=len, reverse=True)) + r')(?![A-Za-z0-9])', re.I)
            hits = []
            for sub in ('src', 'truth', 'reference'):
                for f in sorted(self.w(f'{CORPUS}/{sub}').rglob('*')) if self.w(f'{CORPUS}/{sub}').is_dir() else []:
                    if f.is_file():
                        m = rx.search(f.read_text(errors='replace'))
                        if m:
                            hits.append(f'{sub}/{f.relative_to(self.w(f"{CORPUS}/{sub}"))}: {m.group(1)}')
            if hits:
                bad.append(f'earlier-corpus proper noun(s) in the new corpus: {len(hits)} file(s), first {hits[0]}')
        if bad:
            return False, f'build gates: {len(bad)} failure(s): ' + ' | '.join(bad[:4])
        return True, (f'build gates: gates.json all pass; {files} PDFs hash and page-count checked; 71/39/80; truth keys; '
                      f'cases; quotas; clean text on every page; no earlier proper noun ({len(terms)} terms)')

    def _per_doc(self, d, label):
        man = read_json(self.w(f'{CORPUS}/manifest.json')) or {}
        docs = [x['doc_id'] for x in man.get('documents') or []]
        miss = [x for x in docs if not (pathlib.Path(d) / f'{x}.json').is_file()]
        return bool(docs) and not miss, f'{label}: {len(docs) - len(miss)} of {len(docs)} documents'

    def post_blind_complete(self, stage, folder):
        return self._per_doc(self.w(f'{CORPUS}/blind/truth-blind'), 'blind re-key')

    def post_truth_b_complete(self, stage, folder):
        return self._per_doc(self.w(f"{CORPUS}/layerB/{stage['set']}/truth-b"), 'layer B')

    def post_rulings(self, stage, folder):
        r = read_json(folder / 'rulings.json')
        return isinstance(r, list), f'rulings: {len(r) if isinstance(r, list) else "unreadable"}'

    def post_answers(self, stage, folder):
        a = read_json(folder / 'answers' / 'answers.json')
        return isinstance(a, (list, dict)), 'answers.json readable' if isinstance(a, (list, dict)) else 'answers.json unreadable'

    # ---------- render (script, not Codex)
    def do_render(self, stage, n):
        folder = self.stage_folder('render')
        R = os.path.realpath(folder)
        D = os.path.realpath(os.path.expanduser('~/Documents'))
        T = darwin_temp_dir()
        if not T:
            return False, 'render: getconf DARWIN_USER_TEMP_DIR gave no path; profile not written', None
        prof = self.root / f'render-profile-a{n}.sb'
        prof.write_text(RENDER_PROFILE.replace('{R}', R).replace('{T}', T).replace('{D}', D))
        argv, cwd, allow, extra = self.argv(stage, n, profile=str(prof))
        log = self.root / 'logs' / f'render-a{n}.log'
        t0 = time.monotonic()
        outcome, rc = self.run_proc(self.wrap(stage, n, argv), cwd, strip_env(allow, extra), log, self.remaining())
        ok, detail = self.outcome_check(outcome, rc)
        if not ok:
            return False, detail, None
        spec = read_json(self.w(CASE_SPEC)) or {}
        docs = [(d['doc_id'], d.get('packet')) for d in spec.get('documents') or []]
        if not docs:
            return False, 'render: case_spec.json has no documents to check', None
        missing, pdfs = [], {}
        for s in SETS:
            names = os.listdir(folder / s) if (folder / s).is_dir() else []
            for doc, packet in docs:
                hit = [x for x in names if re.match(RENDER_DOC_RE.format(doc=re.escape(doc)), x)]
                if hit:
                    pdfs[(s, doc)] = folder / s / hit[0]
                else:
                    missing.append(f'{s}/{doc}')
            for packet in sorted({p for _, p in docs if p}):
                if not (folder / RENDER_PACKET.format(set=s, packet=packet)).is_file():
                    missing.append(RENDER_PACKET.format(set=s, packet=packet))
        if missing:
            return False, f'render: {len(missing)} PDF(s) missing, first {missing[0]}', None
        t_end = self.stage_end                               # page images share the render deadline
        for (s, doc), pdf in sorted(pdfs.items()):
            out = folder / 'page-images' / s
            out.mkdir(parents=True, exist_ok=True)
            if self.stub:
                if (read_json(self.faults) or {}).get('render', {}).get('drop_image') == doc if self.faults else False:
                    continue
                for pg in range(1, (pdf_pages(pdf, timeout=max(self.remaining(), 0.01)) or 1) + 1):
                    (out / f'{doc}-{pg}.png').write_bytes(b'\x89PNG stub\n')
                continue
            a = [x.format(pdf=str(pdf), prefix=str(out / doc)) for x in COMMANDS['page_images']]
            o, r = self.run_proc(a, folder, strip_env(), log, max(t_end - time.monotonic(), 0))
            ok, detail = self.outcome_check(o, r)
            if not ok:
                return False, f'page images {s}/{doc}: {detail}', None
        for s in SETS:
            dst = self.w(f'{CORPUS}/{s}')
            if dst.exists():
                return False, f'copy-out refused, destination exists: {dst}', None
        for s in SETS:
            shutil.copytree(folder / s, self.w(f'{CORPUS}/{s}'))
        return True, f'{len(pdfs)} document PDFs and page images; clean/ and scan/ copied to {CORPUS}/', None

    # ---------- compare and adjudication (script, not Codex)
    def do_compare(self, stage, n):
        man = read_json(self.w(f'{CORPUS}/manifest.json')) or {}
        full, blind = [], []
        for d in man.get('documents') or []:
            doc = d['doc_id']
            A = read_json(self.w(f'{CORPUS}/truth/{doc}.json')) or {}
            B = read_json(self.w(f'{CORPUS}/blind/truth-blind/{doc}.json')) or {}
            av, bv = A.get('values') or {}, B.get('values') or {}
            fields = SCALAR_FIELDS.get(d.get('class')) or sorted(
                k for k in set(av) | set(bv) if not isinstance(av.get(k, bv.get(k)), (dict, list)))
            for f in fields:
                a, b = av.get(f), bv.get(f)
                if isinstance(a, (dict, list)) or isinstance(b, (dict, list)) or norm_cmp(a) == norm_cmp(b):
                    continue
                page = (A.get('page_of') or {}).get(f) or (B.get('page_of') or {}).get(f)
                full.append({'doc_id': doc, 'field': f, 'page': page, 'layer_a': a, 'blind': b, 'blind_file': bool(B)})
                blind.append({'doc_id': doc, 'field': f, 'page': page, 'images': self.images(doc, page, 'clean', man)})
        write_json(self.root / 'private' / f'{stage["id"]}-full.json', full)
        write_json(self.root / 'stages' / stage['id'] / 'disagreements.json', blind)
        return True, f'{len(blind)} disagreement(s) on scored scalar fields; blinded list has doc_id, field, page only', None

    def _rulings(self, path, items):
        rulings = read_json(path)
        if not isinstance(rulings, list):
            raise Stop(f'rulings unreadable: {path}')
        idx = {}
        for r in rulings:
            if isinstance(r, dict):
                idx.setdefault((r.get('doc_id'), r.get('field')), r)
        decided, excluded = [], []
        for it in items:
            r = idx.get((it['doc_id'], it['field']))
            if r and r.get('status') == 'decided':
                decided.append((it, r.get('value')))
            else:
                excluded.append({'doc_id': it['doc_id'], 'field': it['field'], 'key': it.get('key'),
                                 'reason': 'undecidable' if r else 'no ruling'})
        return decided, excluded

    def do_apply_rulings(self, stage, n):
        items = read_json(self.root / 'stages' / 'compare' / 'disagreements.json') or []
        decided, excluded = self._rulings(self.w(f'{ADJ}/rulings.json'), items)
        truth, orig = self.w(f'{CORPUS}/truth'), self.w(f'{CORPUS}/truth-original')
        if not orig.exists():
            shutil.copytree(truth, orig)
        self.state['aliases'][str(truth)] = {'to': str(orig), 'before_index': self.ids.index(stage['id'])}
        self.save()
        changes, docs = [], {}
        for it, value in decided:
            doc = it['doc_id']
            if doc not in docs:
                docs[doc] = read_json(orig / f'{doc}.json')
            rec = docs[doc]
            if rec is None:
                excluded.append({'doc_id': doc, 'field': it['field'], 'reason': 'no layer A file'})
                continue
            old = (rec.get('values') or {}).get(it['field'])
            if norm_cmp(old) != norm_cmp(value):
                rec.setdefault('values', {})[it['field']] = value
                changes.append({'doc_id': doc, 'field': it['field'], 'old': old, 'new': value})
        for doc, rec in docs.items():
            src = orig / f'{doc}.json'
            dst = truth / f'{doc}.json'
            if any(c['doc_id'] == doc for c in changes):
                dst.write_text(json.dumps(rec, indent=2) + '\n')
            else:
                shutil.copy2(src, dst)
        write_json(self.w(f'{ADJ}/changes.json'), changes)
        write_json(self.w(f'{ADJ}/excluded.json'), excluded)
        detail = f'{len(changes)} layer A value(s) changed (log {ADJ}/changes.json); {len(excluded)} unit(s) excluded'
        if len(excluded) > R6_MAX_EXCLUDED:
            raise Invalid(f'R6: {len(excluded)} excluded units in the corpus (more than {R6_MAX_EXCLUDED})')
        return True, detail, None

    def unit_labels(self, s):
        """{(node, subject): layer A label} from the arm records of set s (arms.json), read like
        score_heldout2.load_units: `label_a` when the record is layered, else `label`; row-8 batches per field."""
        labels = {}
        for runs in ((read_json(self.root / 'arms.json') or {}).get(s) or {}).values():
            for r in runs:
                f = pathlib.Path(r['out']) / 'calls.jsonl'
                for line in (f.read_text().splitlines() if f.is_file() else []):
                    try:
                        c = json.loads(line)
                    except ValueError:
                        continue
                    if 'score' not in c or c.get('kind', 'unit') != 'unit':
                        continue
                    lab = c.get('label_a') if 'label_a' in c else c.get('label')
                    if isinstance(c['score'], dict) and 'fields' in c['score']:
                        for fld in c['score']['fields']:
                            labels.setdefault((c['node'], f"{c['subject']}.{fld}"), (lab or {}).get(fld))
                    else:
                        labels.setdefault((c['node'], c['subject']), lab)
        return labels

    def images(self, doc_id, page, variant, man):
        """Image file(s) the adjudicator uses for an item: page-images/<variant>/<doc_id>-<page>.png."""
        d = next((d for d in man.get('documents') or [] if d.get('doc_id') == doc_id), None)
        pages = [page] if page else list(range(1, int((d or {}).get('page_count') or 1) + 1))
        return [f'page-images/{variant}/{doc_id}-{p}.png' for p in pages]

    def blind_item(self, node, subject, item, answer, man):
        """The adjudicator's view of one audit disagreement: {doc_id, field, page}, plus question and options for
        non-row-8 nodes. Never the key or the auditor's answer."""
        if node == 'row8':
            doc, field = subject.split('.', 1)
            return {'doc_id': doc, 'field': field, 'page': (answer or {}).get('page')}
        if node == 'row1':
            out = {'doc_id': subject, 'field': 'document_class', 'page': 1}
        elif node == 'row4':
            pid, _, p = subject.partition(':p')
            d = next((d for d in man.get('documents') or [] if d.get('packet') == pid and int(p) in (d.get('pages') or [])), None)
            out = ({'doc_id': d['doc_id'], 'field': f'page_topic_p{d["pages"].index(int(p)) + 1}', 'page': d['pages'].index(int(p)) + 1}
                   if d else {'doc_id': pid, 'field': f'page_topic_p{p}', 'page': None})
        else:
            out = {'doc_id': subject, 'field': 'second_field_ticket', 'page': None}
        out.update(question=item.get('question'), options=item.get('options'))
        if node == 'row5':
            out['packet'] = subject                     # images: every page of every document in the packet, in order
        return out

    def item_images(self, b, variant, man):
        """Row 5 (packet item): every page of every document in the packet, in packet order; otherwise the item's
        document page, or all its pages when no page is named (row 1)."""
        if b.get('packet'):
            return self.packet_images(b['packet'], variant, man)
        return self.images(b['doc_id'], b.get('page'), variant, man)

    def packet_images(self, pid, variant, man):
        docs = sorted((d for d in man.get('documents') or [] if d.get('packet') == pid), key=lambda d: (d.get('pages') or [0])[0])
        return [f'page-images/{variant}/{d["doc_id"]}-{p}.png' for d in docs for p in range(1, int(d.get('page_count') or 1) + 1)]

    def do_audit_compare(self, stage, n):
        """Audit answers against the layer A key for every node make_audit2 emits (row 8, 1, 4, 5). The item to
        unit map comes from make_audit2's --record (outside the audit folders); labels from the arm records."""
        s, tier = stage['set'], stage['tier']
        base = self.audit_dir(s, tier)
        items = read_json(base / 'items.json')
        answers = read_json(base / 'answers' / 'answers.json')
        rec = read_json(self.record_path(s)) or {}
        idmap = (rec.get(tier) or {}).get('id_to_unit') or {}
        if not isinstance(items, list) or answers is None:
            return False, f'{tier} audit items.json or answers/answers.json unreadable', None
        if isinstance(answers, dict):
            answers = answers.get('answers') if isinstance(answers.get('answers'), list) else \
                [dict(v, id=k) for k, v in answers.items() if isinstance(v, dict)]
        by_id = {a.get('id'): a for a in answers if isinstance(a, dict)}
        labels = self.unit_labels(s)
        man = read_json(self.w(f'{CORPUS}/manifest.json')) or {}
        full, blind, skipped, nodes = [], [], 0, {}
        for it in items:
            key = idmap.get(it.get('id'))
            node, _, subject = (key or '').partition(':')
            if not key or (node, subject) not in labels:
                skipped += 1
                continue
            nodes[node] = nodes.get(node, 0) + 1
            lab, a = labels[(node, subject)], by_id.get(it.get('id'))
            got = None if a is None else (a.get('printed') if node == 'row8' else a.get('answer'))
            if a is None or got is None or norm_cmp(got) != norm_cmp(lab):
                b = self.blind_item(node, subject, it, a, man)
                b['images'] = self.item_images(b, s, man)                          # this set's rendering only
                blind.append(b)
                full.append(dict(b, key=key, label_a=lab, audit=got, answered=a is not None))
        write_json(self.root / 'private' / f'{stage["id"]}-full.json', full)
        write_json(self.root / 'stages' / stage['id'] / 'disagreements.json', blind)
        return True, (f'{tier}: {len(items)} item(s) {json.dumps(nodes, sort_keys=True)}; {len(blind)} disagreement(s) '
                      f'with the key; {skipped} item(s) without a unit or label'), None

    def do_apply_audit(self, stage, n):
        """Adjudicated audit -> the scorer's audit JSON: decided rulings that differ from the key go to corrections
        (row 8: printed = value is not null); undecidable or unruled items go to excluded; for the primary audit
        the layer A adjudication exclusions of this corpus are added as row-8 units of this set. Truth is not edited."""
        s, tier = stage['set'], stage['tier']
        cid = ('audit_compare' if tier == 'primary' else 'audit2_compare') + f'.{s}'
        items = read_json(self.root / 'private' / f'{cid}-full.json') or []
        out = self.audit_json(s, tier)
        decided, excluded = self._rulings(out.with_name('rulings.json'), items)
        corrections, changes = {}, []
        for it, value in decided:
            label = (value is not None) if it['key'].startswith('row8:') else value
            if norm_cmp(label) != norm_cmp(it['label_a']):
                corrections[it['key']] = label
                changes.append({'key': it['key'], 'label_a': it['label_a'], 'ruled': label})
        ex_audit = sorted({e['key'] for e in excluded})
        ex_layer_a = []
        if tier == 'primary':
            for e in read_json(self.w(f'{ADJ}/excluded.json')) or []:
                ex_layer_a.append(f"row8:{e.get('doc_id')}.{e.get('field')}")
        union = sorted(set(ex_audit) | set(ex_layer_a))
        write_json(out, {'corrections': corrections, 'excluded': union})
        write_json(out.with_name('label-changes.json'), changes)
        write_json(out.with_name('excluded.json'), excluded)
        if tier == 'primary' and len(union) > R6_MAX_EXCLUDED:   # R6 on the union: layer A plus primary audit, per set
            raise Invalid(f'R6: {len(union)} unique excluded units on set {s} (layer A {len(set(ex_layer_a))} + primary audit '
                          f'{len(ex_audit)}; more than {R6_MAX_EXCLUDED})')
        if tier == 'secondary' and len(ex_audit) > R6_MAX_EXCLUDED:
            raise Invalid(f'R6: {len(ex_audit)} excluded secondary audit units on set {s} (more than {R6_MAX_EXCLUDED})')
        return True, (f'{tier}: {len(corrections)} correction(s), {len(ex_audit)} audit exclusion(s), '
                      f'{len(ex_layer_a)} layer A exclusion(s) -> {os.path.relpath(out, self.work)}'), None

    def skip_secondary_empty(self, stage):
        items = read_json(self.audit_dir(stage['set'], 'secondary') / 'items.json')
        if isinstance(items, list) and items:
            return ''
        return f"secondary audit set for {stage['set']} is empty (no unit only an alias or batched run missed); skipped"

    # ---------- Pulse
    def pulse_observed(self, run):
        """(credits seen so far, response files without a numeric credits_used) from runs/<id>/raw/*.json. pipeline.py
        writes each API response there as soon as it returns; the per-packet <packet>.json files with their credits
        appear only after the whole set, so they cannot drive enforcement during the run."""
        cache = self.__dict__.setdefault('_pulse_cache', {})
        total, unknown = 0.0, 0
        for f in sorted((run / 'raw').glob('*.json')) if (run / 'raw').is_dir() else []:
            try:
                key = (str(f), f.stat().st_mtime_ns, f.stat().st_size)
            except OSError:
                continue
            if key not in cache:
                d = read_json(f)
                c = d.get('credits_used') if isinstance(d, dict) else None
                cache[key] = float(c) if isinstance(c, (int, float)) and not isinstance(c, bool) else None
            if cache[key] is None:
                unknown += 1
            else:
                total += cache[key]
        return total, unknown

    def do_pulse(self, stage, n):
        """Pulse for one set. Spend is enforced by observation: about once a second the script sums credits_used
        over the responses written so far; if other spend plus that sum passes the cap, the stage is killed and the
        run stops. This lags by the call in flight, so it is not a per-call guarantee."""
        s = stage['set']
        argv, cwd, allow, extra = self.argv(stage, n)
        log = self.root / 'logs' / f"{stage['id']}-a{n}.log"
        run = self.w(f'runs/{self.run_id(s)}')
        own = self.ledger._entry(stage['id'], n, 'pulse_credits')
        other = self.ledger.spent('pulse_credits') - (float(own['bound']) if own else 0.0)
        cap = self.ledger.d['caps']['pulse_credits']

        def monitor():
            seen, _ = self.pulse_observed(run)
            self.spend_floor = seen
            if other + seen > cap + 1e-9:
                return f'observed Pulse credits {seen:g} + other spend {other:g} pass the cap {cap:g}'
            return ''
        outcome, rc = self.run_proc(self.wrap(stage, n, argv), cwd, strip_env(allow, extra), log,
                                    self.remaining(), monitor=monitor)
        seen, unknown_files = self.pulse_observed(run)
        self.spend_floor = seen
        if outcome == 'monitor':
            raise Stop(f'CAP-KILLED {stage["id"]}: {self.monitor_reason}; spend recorded as the larger of bound and '
                       f'observed. {PULSE_RETRY_NOTE}')
        month = read_json(run / 'month.json')
        c = ((month or {}).get('credits') or {}).get('total') if isinstance(month, dict) else None
        trusted = (outcome == 'exit' and rc == 0 and isinstance(c, (int, float)) and c > 0 and unknown_files == 0 and seen > 0)
        credits = max(float(c), seen) if trusted else None
        if outcome != 'exit':
            self.outcome_check(outcome, rc)
            return False, 'DEADLINE: process group killed at the deadline', None
        if rc != 0:
            return False, f'exit {rc}; observed credits {seen:g}', credits
        man = read_json(self.w(f'{CORPUS}/manifest.json')) or {}
        ndocs = len(man.get('documents') or [])
        cls = len((month or {}).get('classify') or [])
        miss = [p['packet_id'] for p in man.get('packets') or [] if not (run / 'raw' / f"{p['packet_id']}__extract.json").is_file()]
        ok = isinstance(month, dict) and cls == ndocs and not miss
        why = '' if trusted else (f'; credits UNTRUSTED (month total {c!r}, {unknown_files} response(s) without credits_used, '
                                  f'observed {seen:g}): the reservation stays at its bound')
        return ok, (f'classify {cls} of {ndocs}; extracts missing {len(miss)}; credits '
                    f'{credits if credits is not None else "UNKNOWN"}' + why), credits

    # ---------- arms
    def arm_cost(self, stage, rep, outcome, rc):
        """Settle a Jev or cascade run only when it ended cleanly and its report carries a positive numeric cost;
        anything else keeps the reservation at its bound (review finding 2)."""
        if outcome != 'exit' or rc != 0 or not isinstance(rep, dict) or rep.get('errors') != 0 or rep.get('stopped'):
            return None
        v = rep.get('cost_usd') if stage['backend'] == 'jev' else (rep.get('cascade') or {}).get('jev_billed_usd')
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not v > 0:
            return None
        if stage['backend'] == 'cascade':
            je = (rep.get('cascade') or {}).get('jev_errors')     # Jev failures Claude recovered (typed_questions n_jev_err)
            if isinstance(je, bool) or not isinstance(je, int) or je != 0:
                return None
        return float(v)

    def registry_entry(self, stage, out):
        rp = pathlib.Path(out) / 'report.json'
        return {'arm': stage['arm'], 'repeat': stage['rep'], 'stage': stage['id'], 'out': str(out),
                'report_sha256': sha_file(rp) if rp.is_file() else None}

    def write_registry(self):
        """arms.json from the DONE arm stages; its sha256 is checkpointed in state.json."""
        reg = {'_expected_units': read_json(self.root / 'expected-units.json') or {}}
        for x in self.plan:
            st = self.state['stages'].get(x['id']) or {}
            if x['kind'] == 'arm' and st.get('status') == 'DONE':
                reg.setdefault(x['set'], {}).setdefault(x['arm'], []).append(self.registry_entry(x, st['out_dir']))
        write_json(self.root / 'arms.json', reg)
        self.state['arms_sha256'] = sha_file(self.root / 'arms.json')
        self.save()

    def verify_registry(self, where):
        p = self.root / 'arms.json'
        reg = read_json(p)
        bad = []
        if not isinstance(reg, dict) or sha_file(p) != self.state.get('arms_sha256'):
            bad.append('arms.json differs from its checkpointed sha256')
        want = {'_expected_units': read_json(self.root / 'expected-units.json') or {}}
        for x in self.plan:
            st = self.state['stages'].get(x['id']) or {}
            if x['kind'] == 'arm':
                if st.get('status') != 'DONE':
                    bad.append(f"{x['id']} not DONE")
                    continue
                want.setdefault(x['set'], {}).setdefault(x['arm'], []).append(self.registry_entry(x, st['out_dir']))
        if isinstance(reg, dict) and reg != want:
            bad.append('arms.json does not match the finished arm stages (path, arm, repeat, or report hash)')
        if bad:
            raise Stop(f'{where}: ARM-REGISTRY mismatch: {"; ".join(bad[:3])}')

    def do_verify_arms(self, stage, n):
        self.verify_registry(stage['id'])
        return True, 'arms.json matches its checkpoint and every finished arm run (path, arm, repeat, report hash)', None

    def do_arm(self, stage, n):
        s, sid, st = stage['set'], stage['id'], self.st(stage['id'])
        typed = self.w(f'runs/{self.run_id(s)}/typed')
        st['pre_listing'] = sorted(os.listdir(typed)) if typed.is_dir() else []
        self.save()
        argv, cwd, allow, extra = self.argv(stage, n)
        log = self.root / 'logs' / f'{sid}-a{n}.log'
        watch = stage['backend'] in ('claude', 'cascade')
        outcome, rc = self.run_proc(self.wrap(stage, n, argv, {'arm': stage['arm'], 'rep': stage['rep']}), cwd,
                                    strip_env(allow, extra), log, self.remaining(), watch_usage=watch)
        text = log.read_text(errors='replace') if log.is_file() else ''
        m = re.findall(r'RECEIPT \S+: rc=(\d+) .* out=(\S+)\s*$', text, re.M)
        out = pathlib.Path(m[-1][1]) if m else None
        if out is None and typed.is_dir():
            new = sorted(x for x in os.listdir(typed) if x not in set(st['pre_listing']))
            out = typed / new[-1] if new else None
        if out is not None:
            st['out_dir'] = str(out)
        self.save()
        rep = read_json(out / 'report.json') if out else None
        actual = self.arm_cost(stage, rep, outcome, rc) if stage['backend'] != 'claude' else None
        if outcome != 'exit':
            self.outcome_check(outcome, rc)
            return False, 'DEADLINE: process group killed at the deadline', None
        if rc != 0:
            return False, f'exit {rc}; out {out}', actual
        if not isinstance(rep, dict):
            return False, f'report.json missing in {out}', actual
        if rep.get('errors') not in (0, None) or rep.get('stopped'):
            return False, f"errors={rep.get('errors')} stopped={rep.get('stopped')!r} (R8: quarantine and rerun whole)", actual
        want_alias = 'afe_number' if '--alias' in stage['extra'] else 'none'
        want_c8 = 'per-document' if '--claude-row8' in stage['extra'] else 'per-field'
        got_alias, got_c8 = rep.get('alias'), rep.get('claude_row8')
        warn = ''
        if got_alias is None or got_c8 is None:
            warn = '; WARN report.json lacks alias/claude_row8'
        elif got_alias != want_alias or (stage['backend'] == 'claude' and got_c8 != want_c8):
            return False, f'config mismatch: alias={got_alias} claude_row8={got_c8}, wanted {want_alias}/{want_c8}', actual
        return True, f"calls={rep.get('calls')} errors=0 out={os.path.relpath(out, self.work)}" + \
            (f' jev ${actual:.6f}' if actual is not None else '') + warn, actual

    # ---------- local tools
    def do_local(self, stage, n):
        argv, cwd, allow, extra = self.argv(stage, n)
        log = self.root / 'logs' / f"{stage['id']}-a{n}.log"
        outcome, rc = self.run_proc(self.wrap(stage, n, argv), cwd, strip_env(allow, extra), log, self.remaining())
        if stage['tool'] == 'score' and outcome == 'exit':
            res = read_json(self.root / 'score.json')
            v = res.get('verdict') if isinstance(res, dict) else None
            overall = v.get('Overall') if isinstance(v, dict) else None
            if overall == 'INVALID':
                raise Invalid('score verdict INVALID: ' + '; '.join((v.get('invalid_reasons') or [])[:5]))
            if overall not in ('PASS', 'FAIL', 'INCONCLUSIVE'):
                raise Invalid(f'score.json missing or without a verdict (Overall {overall!r}; scorer exit {rc})')
            self.verdict = v
        ok, detail = self.outcome_check(outcome, rc)
        if not ok:
            return False, detail, None
        miss = [str(p) for p in self.outputs(stage) if not p.exists()]
        if miss:
            return False, f'outputs missing: {miss[0]}', None
        how = '' if not self.stub else (' (REAL tool inside a stub run)' if stage['tool'] in self.stub_real else ' (stub fake)')
        verdict = f"; verdict Overall {(getattr(self, 'verdict', None) or {}).get('Overall')}" if stage['tool'] == 'score' else ''
        return True, f"{stage['tool']} exit 0{how}{verdict}", None

    def do_expect(self, stage, n):
        """Expected unit set per set, from the runner's request builder (no network), before the first arm."""
        log = self.root / 'logs' / f'expect_units-a{n}.log'
        out = {}
        for x in SETS:
            argv = [EXPECT_UNITS_PY if a == '<EXPECT_UNITS_PY>' else
                    a.format(demo=str(self.work), run_id=self.run_id(x), set=x, root=str(self.root)) for a in COMMANDS['expect_units']]
            if self.stub:
                argv = self.wrap(dict(stage, kind='expect'), n, argv, {'set': x})
            o, rc = self.run_proc(argv, self.code, strip_env(), log, self.remaining())
            ok, detail = self.outcome_check(o, rc)
            keys = read_json(self.root / f'expected-units-{x}.json')
            if not ok or not isinstance(keys, list) or not keys:
                return False, f'expected units {x}: {detail or "no keys written"}', None
            out[x] = sorted(keys)
        write_json(self.root / 'expected-units.json', out)
        return True, 'expected units ' + ', '.join(f'{x} {len(v)}' for x, v in out.items()), None

    def do_freeze_truth(self, stage, n):
        log = self.root / 'logs' / f'freeze_truth-a{n}.log'
        for s in SETS:
            argv = [a.format(set=s) for a in COMMANDS['freeze_hashes']]
            argv[1] = str(self.code / argv[1])
            outcome, rc = self.run_proc(argv, self.work, strip_env(), log, self.remaining())
            ok, detail = self.outcome_check(outcome, rc)
            if not ok:
                return False, f'freeze_hashes {s}: {detail}', None
        fz = {'created': now(), 'dirs': {}, 'truth_b_sha256': {}}
        for p in self.inputs(stage):
            fz['dirs'][str(p)] = hash_path(p)
        for s in SETS:
            fz['truth_b_sha256'][s] = self.w(f'{CORPUS}/layerB/{s}/truth-b.sha256').read_text().strip()
        write_json(self.root / 'frozen-truth.json', fz)
        return True, 'truth-b.sha256 per set written; truth and truth-b dirs frozen', None


# ================================================================== dry run
def dry_run(o, stub):
    print('heldout2 orchestrator DRY RUN: nothing runs, nothing is written.')
    print(f'mode if started: {"STUB (fakes)" if stub else "LIVE"}; code root {o.code}; run folder runs/heldout2/<stamp>{"-stub" if stub else ""}/')
    print(f'caps (R5): Pulse {CAPS["pulse_credits"]:g} credits, Jev ${CAPS["jev_usd"]:.2f}; Pulse bound {PULSE_CREDITS_PER_PAGE_BOUND} '
          f'credits/page x manifest pages (fallback {PULSE_FALLBACK_BOUND:g}); Jev bound ${JEV_MAX_SPEND_PER_RUN} per Jev or cascade run')
    print(f'sessions: Codex session folders and the render folder under {SESSIONS_HOME}/<stamp>/<stage>/ (outside the repo); '
          f'each still inherits ~/.codex/AGENTS.md if present, recorded per session and noted in status.log')
    print(f'NOTE: {PULSE_RETRY_NOTE}.')
    snap = o.freeze_snapshot()
    print(f'freeze set: {len(snap["files"])} files present, missing: {", ".join(snap["missing"]) or "none"}; '
          f'{ALIAS_NAME}: {"present" if snap["alias"] else "MISSING"}')
    total = 0
    pools = {}
    for i, s in enumerate(o.plan, 1):
        total += s['deadline']
        pools.setdefault(s['pool'], s['budget'])
        retry = f"{s['budget']} ({s['pool']})" if s['budget'] else '0'
        skip = '   skipped when the secondary audit set is empty' if s.get('skip_if') else ''
        print(f"\n{i:>2}. {s['id']:<24} deadline {s['deadline'] // 60:>3} min   retry {retry}{skip}")
        k = s['kind']
        if k == 'codex':
            try:
                b = o.brief(s)
                argv, _, _, _ = o.argv(s, prompt=f'<body of heldout2/briefs/{s["brief"]}.md: {len(b["body"])} chars, '
                                                  f'sha256 {sha_bytes(b["body"].encode())[:12]}>')
                print('    ' + ' '.join(argv) + ' </dev/null')
                print(f"    INPUTS {', '.join(e.replace('{variant}', s.get('variant') or 'clean') for e in b['inputs'])}")
                print(f"    OUTPUTS {', '.join(b['outputs'])} -> {os.path.relpath(o.copy_base(s), o.work)}/")
                print('    env: KEY/TOKEN/SECRET names stripped; then R4 scan of rollout + stdout' + (f"; post-check {s['post']}" if s.get('post') else ''))
            except (OSError, ValueError, Stop) as e:
                print(f'    BRIEF PROBLEM: {e}')
        elif k == 'render':
            argv, _, _, extra = o.argv(s, profile='runs/heldout2/<stamp>/render-profile-aN.sb')
            print(f"    cd sessions/generator_source && {' '.join(f'{a}={v!r}' for a, v in extra.items())} " + ' '.join(argv))
            print('    then: ' + ' '.join(COMMANDS['page_images']) + ' per document PDF -> page-images/{clean,scan}/<doc_id>-<page>.png;'
                  f' copy clean/ scan/ -> {CORPUS}/')
        elif k in ('pulse', 'arm', 'local'):
            argv, cwd, allow, _ = o.argv(s)
            print('    ' + ' '.join(argv))
            res = o.bound(s)
            print(f"    env keeps: {', '.join(allow) or 'no secret'}" + (f'; ledger bound {res[0]} {res[1]:g}' if res else ''))
        elif k == 'freeze_truth':
            for x in SETS:
                print('    ' + ' '.join(a.format(set=x) for a in COMMANDS['freeze_hashes']))
        else:
            print('    (in-process) ' + {
                'freeze_code': 'sha256 of controls.py, score_heldout2.py, make_audit2.py, 8 briefs, heldout2/inputs/*, ALIAS_AFE_NUMBER',
                'compare': f'layer A truth/ vs blind/truth-blind/ on scored scalar fields; blinded disagreements.json (doc_id, field, page)',
                'apply_rulings': f'decided -> layer A value (truth-original/ kept, changes.json); undecidable excluded; R6 > {R6_MAX_EXCLUDED} INVALID',
                'audit_compare': 'audit answers vs layer A key; blinded disagreements.json for the adjudicator',
                'apply_audit': f'decided -> label-changes.json for the score (truth not edited); R6 > {R6_MAX_EXCLUDED} per set INVALID',
                'verify_freeze': 'recompute frozen code, REQUIRED, truth hashes, and the arm registry; any mismatch stops before scoring',
                'verify_arms': 'arms.json against its checkpoint and every finished arm run (path, arm, repeat, report hash)',
                'expect': 'runner request builder (no network) -> expected unit set per set, stored in arms.json',
            }[k])
    extra = 0       # every retry used: a group pool reruns its whole group; other pools rerun their longest stage
    for pool, b in pools.items():
        members = [x for x in o.plan if x['pool'] == pool]
        if b:
            extra += b * (sum(x['deadline'] for x in members) if members[0].get('group') else max(x['deadline'] for x in members))
    skippable = sum(x['deadline'] for x in o.plan if x.get('skip_if'))
    print(f'\n{len(o.plan)} stages; deadlines without retries sum to {total / 3600:.2f} h '
          f'({(total - skippable) / 3600:.2f} h if both secondary audits are skipped); with every retry used '
          f'{(total + extra) / 3600:.2f} h')
    print('retry pools: ' + ', '.join(f'{p}={b}' for p, b in pools.items() if b))
    print('accepted residual risks (heldout2/RESIDUAL-RISKS.md): Pulse cap is observed-spend enforcement with one call in '
          'flight; a child that detaches with setsid can survive cleanup; the render profile allows writes to the user '
          'temp folder and Unix-domain sockets (Chrome needs both); the R4 log scan has known blind spots.')
    return 0


# ================================================================== stub fakes (no network, no spend)
# The stub world is realistic enough for the REAL make_layerb.py, make_audit2.py, and score_heldout2.py: 71 documents,
# 39 packets, 80 pages; Pulse folders with month.json and PageBreak extracts; arm runs whose calls.jsonl and report.json
# are written by H2's heldout2/tests/fixtures/build_fixture.write_run. Fakes never call a network or a model.
STUB_VARIANTS = ['AFE No', 'Ref', 'Approval', 'Auth']
STUB_PDF = {1: 'synth-heldout/{set}/01_ticket_01.pdf', 2: 'synth-heldout/{set}/60_afe_01.pdf'}   # run 1 pages, reused if present
STUB_PACKET_PDF = {1: 'synth-heldout/{set}/packets/ticket_16.pdf', 2: 'synth-heldout/{set}/packets/jib_01.pdf',
                   3: 'synth-heldout/{set}/packets/afe_01.pdf'}


def fake_composition():
    kinds = [('ticket', 'field_ticket', 45), ('invoice', 'invoice', 4), ('cover', 'afe_cover', 4), ('afe', 'afe', 4),
             ('haul', 'hauling_log', 9), ('jib', 'jib_statement', 5)]
    docs = []
    for prefix, cls, count in kinds:
        docs += [{'doc_id': f'{prefix}_{i:02d}', 'class': cls} for i in range(1, count + 1)]
    packets = []
    for i, d in enumerate(docs):
        d['packet'] = f'pk_{(i // 2) + 1:02d}' if i < 64 else f'pk_{i - 32 + 1:02d}'
        d['page_count'] = 2 if (i < 18 and i % 2 == 0) else 1   # 9 two-page docs; every packet 1 to 3 pages
    for d in docs:
        if not packets or packets[-1]['packet_id'] != d['packet']:
            packets.append({'packet_id': d['packet'], 'pages': 0})
        packets[-1]['pages'] += d['page_count']
    return docs, packets


def stub_world():
    """(docs in build_fixture's shape plus page_count, packets). Tickets 4 to 7 print no approval number."""
    base, packets = fake_composition()
    docs, t = [], 0
    for d in base:
        cls = d['class']
        w = dict(doc_id=d['doc_id'], packet=d['packet'], cls=cls, page_count=d['page_count'], case='baseline', fa=False, variant=None)
        if cls == 'field_ticket':
            t += 1
            printed, var = not 4 <= t <= 7, STUB_VARIANTS[t % 4]
            w.update(text=f'Dispatch docket: **TK-{t:02d}**\n' + (f'{var}: **DB-26-901**' if printed else f'PO 44{t:02d}')
                     + '\nAsset: Pellwick 3-RH', values={'ticket_number': f'TK-{t:02d}'},
                     truth={'ticket_number': True, 'afe_number': printed}, variant=var if printed else None,
                     case='k1' if t <= 3 else 'k2' if t <= 7 else 'baseline', fa=not printed)
        elif cls in ('afe', 'afe_cover'):
            w.update(text='AUTHORITY FOR EXPENDITURE\nAFE Number: **DB-26-901**\nWell: Pellwick 3-RH',
                     values={'afe_number': 'DB-26-901', 'well_name': 'Pellwick 3-RH'}, truth={'afe_number': True, 'well_name': True})
        elif cls == 'invoice':
            w.update(text='INVOICE\nAFE: **DB-26-901**', values={}, truth={'afe_number': True})
        elif cls == 'hauling_log':
            w.update(text=f"HAULING LOG\nLog No: **HL-{d['doc_id'][-2:]}**", values={}, truth={'log_number': True})
        else:
            w.update(text='JOINT INTEREST BILLING\nOwner: **Corvane Holdings LLC**', values={}, truth={'owner_name': True})
        docs.append(w)
    return docs, packets


def stub_manifest(docs, packets):
    pos, mdocs = {}, []
    for i, d in enumerate(docs, 1):
        start = pos.get(d['packet'], 0)
        pos[d['packet']] = start + d['page_count']
        mdocs.append({'doc_id': d['doc_id'], 'packet': d['packet'], 'class': d['cls'], 'page_count': d['page_count'],
                      'pages': list(range(start + 1, start + d['page_count'] + 1)),
                      'file': f"{CORPUS}/clean/{i:02d}_{d['doc_id']}.pdf", 'scan_file': f"{CORPUS}/scan/{i:02d}_{d['doc_id']}.pdf"})
    return {'stub': True, 'documents': mdocs,
            'packets': [dict(p, file=f"{CORPUS}/clean/packets/{p['packet_id']}.pdf",
                             scan_file=f"{CORPUS}/scan/packets/{p['packet_id']}.pdf") for p in packets]}


def stub_answers(docs, arm, rep):
    """{(node, subject): (final, abstain)}: base C answers 'not printed' on 20 printed approval numbers."""
    right = {}
    for d in docs:
        right[('row1', d['doc_id'])] = (d['cls'], False)
        right.update({('row8', f"{d['doc_id']}.{f}"): (v, False) for f, v in d['truth'].items()})
    tk = [d['doc_id'] for d in docs if d['cls'] == 'field_ticket']
    c = dict(right)
    c.update({('row8', f'{x}.afe_number'): (False, False) for x in tk[7:27]})
    ans = dict(right)
    if arm == 'C':
        ans = c
    elif arm == 'C-alias':
        ans[('row8', f'{tk[3]}.afe_number')] = (True, False)
    elif arm in ('B', 'B-alias'):
        ans = dict(c)
        ans[('row8', f'{tk[30]}.ticket_number')] = (None, True)
    elif arm == 'A':
        ans.update({('row8', f'{x}.ticket_number'): (None, True) for x in tk[10:26]})
        if rep == 2:
            ans[('row8', f'{tk[40]}.ticket_number')] = (False, False)
    elif arm == 'A-batched':
        ans[('row8', f'{tk[20]}.ticket_number')] = (None, True)
    return ans


def fake_values(doc):
    cls = doc.get('class') or doc.get('cls')
    v = {f: (f'{doc["doc_id"]}-{f}'.upper() if f != 'customer_signature_present' else False) for f in SCALAR_FIELDS[cls]}
    if (doc.get('truth') or {}).get('afe_number') is False:
        v['afe_number'] = None                     # not printed: layer A keys null
    return v


def load_build_fixture(code):
    import importlib.util
    path = pathlib.Path(code) / 'heldout2' / 'tests' / 'fixtures' / 'build_fixture.py'
    spec = importlib.util.spec_from_file_location('build_fixture', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_main(argv):
    meta = json.loads(argv[0])
    real = argv[2:] if len(argv) > 1 and argv[1] == '--' else []
    root, work, stage, attempt = pathlib.Path(meta['root']), pathlib.Path(meta['work']), meta['stage'], meta['attempt']
    faults = (read_json(meta['faults']) or {}) if meta.get('faults') else {}
    f = faults.get(stage, {})
    (root / 'logs').mkdir(parents=True, exist_ok=True)
    with open(root / 'stub-calls.jsonl', 'a') as fh:
        fh.write(json.dumps({'stage': stage, 'attempt': attempt, 'kind': meta['kind'], 'pid': os.getpid()}) + '\n')
    write_json(root / 'logs' / f'env-{stage}-a{attempt}.json', sorted(os.environ))   # names only, never values
    print(f'[stub] {meta["kind"]} {stage} attempt {attempt}: ' + ' '.join(real[:8] if meta['kind'] == 'codex' else real), flush=True)
    if attempt in f.get('kill_parent', []):
        os.kill(os.getppid(), signal.SIGTERM)
        time.sleep(60)
    if str(attempt) in (f.get('sleep') or {}):
        (root / 'logs' / f'sleeper-{stage}-a{attempt}.pid').write_text(str(os.getpid()))
        time.sleep(float(f['sleep'][str(attempt)]))
    if attempt in f.get('usage_limit', []):
        print('Claude AI usage limit reached|1760000000', flush=True)
        time.sleep(60)
    if f.get('touch_code'):
        with open(pathlib.Path(meta['code']) / f['touch_code'], 'a') as fh:
            fh.write('\n# touched after the freeze by a stub fault\n')
    if f.get('orphan'):
        g = subprocess.Popen([sys.executable, '-c', 'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)'])
        (root / 'logs' / f'orphan-{stage}.pid').write_text(str(g.pid))
    if attempt in f.get('fail', []):
        print('[stub] forced failure', flush=True)
        return 1
    k = meta['kind']
    docs, packets = stub_world()
    if k == 'codex':
        return fake_codex(meta, real, f, docs, packets)
    if k == 'render':
        spec = read_json('case_spec.json') or {}
        pc = {d['doc_id']: d['page_count'] for d in docs}
        for s in SETS:
            pathlib.Path(s, 'packets').mkdir(parents=True, exist_ok=True)
            for i, d in enumerate(spec.get('documents') or [], 1):
                if f.get('missing_pdf') and d['doc_id'] == f['missing_pdf']:
                    continue
                src = pathlib.Path(meta['code']) / STUB_PDF[pc.get(d['doc_id'], 1)].format(
                    set='scan' if (f.get('blank_clean') == d['doc_id']) else s)          # a scan page has no text
                dst = pathlib.Path(s, f"{i:02d}_{d['doc_id']}.pdf")
                shutil.copy2(src, dst) if src.is_file() else dst.write_bytes(b'%PDF-1.4 stub\n')
            ppages = {}
            for d in docs:
                ppages[d['packet']] = ppages.get(d['packet'], 0) + d['page_count']
            for p in sorted({d['packet'] for d in spec.get('documents') or []}):
                src = pathlib.Path(meta['code']) / STUB_PACKET_PDF.get(ppages.get(p, 1), STUB_PACKET_PDF[1]).format(set=s)
                dst = pathlib.Path(s, 'packets', f'{p}.pdf')
                shutil.copy2(src, dst) if src.is_file() else dst.write_bytes(b'%PDF-1.4 stub packet\n')
        return 0
    if k == 'pulse':
        a = dict(zip(real, real[1:]))
        man = read_json(work / a['--corpus'] / 'manifest.json')
        run = work / 'runs' / a['--run-id']
        (run / 'raw').mkdir(parents=True, exist_ok=True)
        text = {d['doc_id']: d['text'] for d in docs}
        if f.get('echo_key'):
            print('server said: bad header Authorization: Bearer ' + os.environ.get('PULSE_API_KEY', ''), flush=True)
        per = float(f.get('credits', 360)) / max(len(man['packets']), 1)
        for p in man['packets']:
            if f.get('progressive'):
                time.sleep(float(f['progressive']))
            pages = []
            for d in sorted((d for d in man['documents'] if d['packet'] == p['packet_id']), key=lambda d: d['pages'][0]):
                pages += [text.get(d['doc_id'], 'stub page')] + ['(continued)'] * (len(d['pages']) - 1)
            md = ''.join(t + (f'\n<!-- PageBreak [{n}] -->\n' if n < len(pages) else '') for n, t in enumerate(pages, 1))
            write_json(run / 'raw' / f"{p['packet_id']}__extract.json", {'markdown': md, 'stub': True, 'credits_used': per})
        vals = {d['doc_id']: d['values'] for d in docs}
        month = {'stub': True, 'classify': [{'doc_id': d['doc_id'], 'predicted': d['class']} for d in man['documents']],
                 'documents': {d['doc_id']: {'class': d['class'], 'packet': d['packet'], 'values': vals.get(d['doc_id'], {}),
                                             'citations': {}} for d in man['documents']},
                 'credits': {'total': float(f.get('credits', 360))}}
        write_json(run / 'month.json', month)
        write_json(run / 'run.json', {'stub': True, 'run_id': a['--run-id'], 'variant': a['--variant']})
        return 0
    if k == 'arm':
        return fake_arm(meta, real, f, work, docs)
    if k == 'expect':
        keys = {f"row1:{d['doc_id']}" for d in docs} | {f"row8:{d['doc_id']}.{x}" for d in docs for x in d['truth']}
        if f.get('drop_unit'):
            keys.discard(f.get('drop_unit'))
        write_json(real[-1], sorted(keys))
        return 0
    if k in ('make_layerb', 'make_audit2', 'score'):
        a = dict(zip(real, real[1:]))
        absw = lambda x: pathlib.Path(x) if pathlib.Path(x).is_absolute() else work / x
        out = absw(a['--out'])
        man = read_json(work / CORPUS / 'manifest.json') or {}
        if k == 'make_layerb':
            (out / 'pages').mkdir(parents=True, exist_ok=True)
            for d in man['documents']:
                for p in range(1, int(d.get('page_count', 1)) + 1):
                    (out / 'pages' / f"{d['doc_id']}__p{p}.txt").write_text('stub page text\n')
            (out / 'BRIEF.md').write_text('stub layer B brief\n')
            (out / 'truth-a.sha256').write_text(hash_path(work / CORPUS / 'truth') + '\n')
        elif k == 'make_audit2':
            tk = [d['doc_id'] for d in docs if d['cls'] == 'field_ticket']
            sets = {'primary': [('row8', f'{x}.afe_number') for x in tk[8:14]] + [('row8', f'{tk[14]}.ticket_number'),
                                                                                  ('row1', tk[15])],
                    'secondary': [] if f.get('secondary_empty') else [('row8', f'{tk[3]}.afe_number')]}
            record = {'stub': True, 'run': a['--run']}
            for tier, d in (('primary', out), ('secondary', absw(a['--out-secondary']))):
                (d / 'pages').mkdir(parents=True, exist_ok=True)
                items = []
                for n, (node, subject) in enumerate(sets[tier], 1):
                    it = {'id': f'item-{n:03d}', 'pages': [f'pages/page-{n:04d}.png']}
                    it.update({'document': subject.split('.')[0], 'field': subject.split('.')[1]} if node == 'row8' else
                              {'node': node, 'question': 'Which document class is this document?', 'options': sorted({x['cls'] for x in docs})})
                    items.append(it)
                write_json(d / 'items.json', items)
                (d / 'BRIEF.md').write_text('stub audit brief\n')
                record[tier] = {'out': str(d), 'items': len(items), 'id_to_unit': {it['id']: f'{u[0]}:{u[1]}' for it, u in zip(items, sets[tier])}}
            write_json(absw(a['--record']), record)
        else:
            v = 'INVALID' if f.get('invalid') else 'INCONCLUSIVE'
            write_json(out, {'stub': True, 'verdict': {'P1': v, 'P2': v, 'P5': v, 'Overall': v, 'invalid_reasons': ['stub fault'] if v == 'INVALID' else []}})
            absw(a['--md']).write_text('# STUB score, not a result\n')
            if v == 'INVALID' and not f.get('invalid_exit0'):
                return 3
        return 0
    print(f'[stub] unknown fake kind {k}', flush=True)
    return 2


def fake_codex(meta, real, f, docs, packets):
    folder = pathlib.Path(real[real.index('-C') + 1])
    home = pathlib.Path(meta['codex_home'])
    stamp = datetime.datetime.now().strftime('%Y-%m-%dT%H-%M-%S-%f')
    rdir = home / 'sessions' / datetime.date.today().strftime('%Y/%m/%d')
    rdir.mkdir(parents=True, exist_ok=True)
    cmds = [('ls -la', str(folder))]
    if meta['attempt'] in f.get('read_outside', []):     # real paths: a mention of a path that does not exist is no read
        cmds.append((f'ls {rdir}', str(folder)))
    if meta['attempt'] in f.get('read_dotdot', []):
        cmds.append(('cd truth && ls ../..', str(folder)))
    with open(rdir / f'rollout-{stamp}-stub.jsonl', 'w') as fh:
        fh.write(json.dumps({'type': 'session_meta', 'payload': {'cwd': str(folder), 'id': 'stub'}}) + '\n')
        for c, wd in cmds:
            fh.write(json.dumps({'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'exec_command',
                                                                      'arguments': json.dumps({'cmd': c, 'workdir': wd})}}) + '\n')
    print(f'OpenAI Codex (stub)\nworkdir: {folder}\nexec\n/bin/zsh -lc \'ls -la\' in {folder}\n succeeded in 3ms:', flush=True)
    truth = {('row8', f"{d['doc_id']}.{k}"): v for d in docs for k, v in d['truth'].items()}
    truth.update({('row1', d['doc_id']): d['cls'] for d in docs})
    for o in meta.get('outputs') or []:
        name = o.rstrip('/')
        p = folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if name == 'coverage.json':
            write_json(p, {'classes': [{'class_id': 'k1', 'min_documents': 2, 'afe_number_is_printed': True},
                                       {'class_id': 'k2', 'min_documents': 3, 'afe_number_is_printed': False}],
                           'plain_controls_min': 5})
        elif name == 'case_spec.json':
            out = []
            for i, d in enumerate(docs):
                cid = ['k1'] if i < (1 if f.get('quota_short') else 3) else ['k2'] if 3 <= i < 7 else []
                out.append({'doc_id': d['doc_id'], 'packet': d['packet'], 'class_ids': cid,
                            'afe_number_is_printed': bool(d['truth'].get('afe_number', False))})
            write_json(p, {'seed': 1, 'documents': out})
        elif name == 'cases.json':
            write_json(p, [{'doc_id': d['doc_id'], 'packet': d['packet'], 'class_id': d['case'], 'label_variant': d['variant'],
                            'flag_would_be_false_alarm': (not d['fa']) if (f.get('flag_flip') and d['doc_id'] == 'ticket_04') else d['fa'],
                            'overlaps': []} for d in docs])
        elif name == 'reference/doi.json' and f.get('leak_noun'):
            write_json(p, {'property_number': 'DS-1', 'well_name': 'Pellwick 3-RH', 'operator_name': 'BRELQUOR field services llc'})
        elif name == 'reference/doi.json':
            write_json(p, {'property_number': 'DS-8093', 'well_name': 'Pellwick 3-RH',
                           'owners': [{'owner_name': 'Corvane Holdings LLC', 'owner_number': 'CH-411'}]})
        elif name == 'manifest.json':
            man = stub_manifest(docs, packets)
            for e in man['documents'] + man['packets']:
                for fk, hk in (('file', 'sha256'), ('scan_file', 'scan_sha256')):
                    pf = folder / e[fk].split('/', 1)[1]
                    e[hk] = sha_file(pf) if pf.is_file() else None
            if f.get('bad_sha'):
                man['documents'][0]['sha256'] = '0' * 64
            write_json(p, man)
        elif name == 'gates.json':
            write_json(p, {'gates': [{'id': g, 'pass': not (g == 'sha256' and f.get('gate_fail')), 'detail': 'stub'}
                                     for g in GATE_IDS if g != f.get('gate_missing')]})
        elif name in ('truth', 'truth-blind', 'truth-b'):
            p.mkdir(parents=True, exist_ok=True)
            bad = int(f.get('disagree', 0)) if name == 'truth-blind' else 0
            for i, d in enumerate(docs):
                v = fake_values(d)
                if i < bad and 'afe_number' in v:
                    v['afe_number'] = 'BLIND-DIFFERS'
                write_json(p / f"{d['doc_id']}.json", {'doc_id': d['doc_id'], 'values': v, 'page_of': {k: 1 for k in v}})
        elif name == 'rulings.json':
            dis = read_json(folder / 'disagreements.json') or []
            und = int(f.get('undecidable', 0))
            write_json(p, [{'doc_id': x['doc_id'], 'field': x['field'], 'value': None,
                            'status': 'undecidable' if i < und else 'decided', 'reason': 'stub'} for i, x in enumerate(dis)])
        elif name == 'answers/answers.json':
            # A blind auditor cannot see units; this fake reads the private record so its answers match the key.
            items = read_json(folder / 'items.json') or []
            tier = 'secondary' if meta['stage'].startswith('audit2.') else 'primary'
            rec = read_json(pathlib.Path(meta['root']) / 'private' / f"audit-record-{meta['stage'].split('.')[1]}.json") or {}
            idmap = (rec.get(tier) or {}).get('id_to_unit') or {}
            flip = int(f.get('audit_flip', 0))
            ans = []
            for i, it in enumerate(items):
                node, _, subject = idmap.get(it['id'], 'row8:?').partition(':')
                lab = truth.get((node, subject), True)
                if node == 'row8':
                    ans.append({'id': it['id'], 'printed': (not lab) if i < flip else bool(lab), 'page': 1, 'where': 'stub',
                                'confidence': 'high'})
                else:
                    ans.append({'id': it['id'], 'answer': 'unrecognized' if i < flip else lab, 'page': 1, 'where': 'stub',
                                'confidence': 'high'})
            write_json(p, ans)
        elif o.endswith('/'):
            p.mkdir(parents=True, exist_ok=True)
            write_json(p / 'stub.json', {'stub': True})
        elif name.endswith('.json'):
            write_json(p, {'stub': True})
        else:
            p.write_text(f'stub output {name}\n')
    return 0


def fake_arm(meta, real, f, work, docs):
    a = real[real.index('--backend'):]
    backend = a[a.index('--backend') + 1]
    run = a[a.index('--run') + 1]
    extra = a[a.index('--') + 1:] if '--' in a else []
    alias = extra[extra.index('--alias') + 1] if '--alias' in extra else 'none'
    c8 = extra[extra.index('--claude-row8') + 1] if '--claude-row8' in extra else 'per-field'
    variant = (f'-alias-{alias}' if alias != 'none' else '') + ('-c8-per-document' if c8 == 'per-document' and backend == 'claude' else '')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    logs = work / 'runs' / 'typed-redo' / f'{stamp}-fake'
    logs.mkdir(parents=True, exist_ok=True)
    name = f'redo-{backend}{variant}-{stamp}-r1'
    out = work / run / 'typed' / name
    bf = load_build_fixture(meta['code'])
    scratch = pathlib.Path(meta['root']) / 'stub-scratch' / f"{meta['stage']}-a{meta['attempt']}"
    rv = (read_json(work / run / 'run.json') or {}).get('variant', 'clean')
    bf.write_run(scratch / 'r', docs, {name: stub_answers(docs, meta['arm'], meta['rep'])}, rv)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(scratch / 'r' / 'typed' / name), str(out))
    errors = 2 if meta['attempt'] in f.get('errors', []) else 0
    jev = float(f.get('jev_cost', 0.0106)) if backend != 'claude' else 0.0
    rep = read_json(out / 'report.json') or {}
    rep.update(mode='stub', stub=True, errors=errors, stopped=None, alias=alias,
               claude_row8=c8 if backend == 'claude' else 'per-field', cost_usd=jev if backend == 'jev' else 0.0)
    if backend == 'cascade':
        rep.setdefault('cascade', {})['jev_billed_usd'] = jev
        rep['cascade']['jev_errors'] = int(f.get('jev_errors', 0))
    if f.get('jev_cost_missing'):
        rep.pop('cost_usd', None)
        (rep.get('cascade') or {}).pop('jev_billed_usd', None)
    write_json(out / 'report.json', rep)
    print(f'[00:00:00Z] logs: {logs}', flush=True)
    print(f"[00:00:01Z] RECEIPT 01-{pathlib.Path(run).name}-r1: rc=0 calls={rep.get('calls')} errors={errors} stub wall=0s out={out}",
          flush=True)
    return 0


# ================================================================== entry
def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == '_fake':
        return fake_main(argv[1:])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true', help='print the stage list with commands and deadlines; write nothing')
    ap.add_argument('--stub', action='store_true', help='replace every external command with a fast fake (no network, no spend)')
    ap.add_argument('--resume', metavar='STAMP', help='continue runs/heldout2/<STAMP>/ (mode comes from its state.json)')
    ap.add_argument('--demo', default=str(HERE.parent), help='repo root (tests point this at a fixture tree)')
    ap.add_argument('--stop-after', metavar='STAGE', help='stop cleanly after this stage id finishes')
    ap.add_argument('--stub-faults', metavar='JSON', help='stub only: fault injection file')
    ap.add_argument('--deadline-scale', type=float, default=1.0, help='stub only: multiply every deadline')
    ap.add_argument('--stub-in-place', action='store_true',
                    help='stub only: write corpus and runs into --demo itself (a throwaway tree; refused on the real demo)')
    ap.add_argument('--stub-real', default='', help=f'stub only, with --stub-in-place: comma list of local tools to run for '
                                                    f'real, from {", ".join(STUB_REAL_OK)}')
    a = ap.parse_args(argv)
    load_secrets()
    code = pathlib.Path(a.demo).resolve()
    real = tuple(x for x in a.stub_real.split(',') if x)
    if [x for x in real if x not in STUB_REAL_OK]:
        ap.error(f'--stub-real accepts only {", ".join(STUB_REAL_OK)}')
    if (a.stub_in_place or real) and not a.stub:
        ap.error('--stub-in-place and --stub-real need --stub')
    if real and not a.stub_in_place:
        ap.error('--stub-real needs --stub-in-place (the real tools resolve paths against their own demo root)')
    if a.stub_in_place and code == HERE.parent.resolve():
        ap.error('--stub-in-place is refused on the real demo tree; point --demo at a throwaway copy')
    if (a.stub_faults or a.deadline_scale != 1.0) and not a.stub and not a.resume:
        ap.error('--stub-faults and --deadline-scale need --stub')
    if a.dry_run:
        o = Orchestrator(code, code / 'runs' / 'heldout2' / '<stamp>', 'stub' if a.stub else 'live', code)
        return dry_run(o, a.stub)
    if a.resume:
        root = code / 'runs' / 'heldout2' / a.resume
        if not root.is_dir():
            print(f'STOP: no run folder {root}', file=sys.stderr)
            return 1
        lock_fh = open(root / '.lock', 'a')
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)      # before any state is read (R9, review finding 4)
        except OSError:
            print(f'STOP: another orchestrator process holds {root}/.lock; refusing to run two on one run folder', file=sys.stderr)
            return 1
        st = read_json(root / 'state.json')
        if not isinstance(st, dict) or not {'mode', 'work_root'} <= set(st):
            print(f'STOP: {root}/state.json is missing, unreadable, or malformed; refusing to guess', file=sys.stderr)
            return 1
        mode = st['mode']
        if a.stub and mode != 'stub':
            ap.error('--stub given, but this run is live')
        if (a.stub_faults or a.deadline_scale != 1.0) and mode != 'stub':
            ap.error('--stub-faults and --deadline-scale need a stub run')
        o = Orchestrator(code, root, mode, st['work_root'], faults=a.stub_faults and str(pathlib.Path(a.stub_faults).resolve()),
                         scale=a.deadline_scale, stop_after=a.stop_after, sessions=st.get('sessions'),
                         stub_real=st.get('stub_real') or ())
        o.lock_fh = lock_fh
    else:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + ('-stub' if a.stub else '')
        root = code / 'runs' / 'heldout2' / stamp
        work = code if (not a.stub or a.stub_in_place) else root / 'work'
        o = Orchestrator(code, root, 'stub' if a.stub else 'live', work,
                         faults=a.stub_faults and str(pathlib.Path(a.stub_faults).resolve()), scale=a.deadline_scale,
                         stop_after=a.stop_after, stub_real=real)
    try:
        if a.resume:
            o.setup_resume()
        else:
            if not o.stub:
                o.preflight_live()
            o.setup_new(root.name)
            if not o.stub:
                print(f'LIVE run {root.name}: every stage runs unattended; status lines follow', flush=True)
        if not o.stub and a.resume:
            o.preflight_live()
        print(f'run folder: {o.root}', flush=True)
        rc = o.run()
        print(f'ledger: {json.dumps(o.ledger.summary())}', flush=True)
        return rc
    except Stop as e:
        if o.state is not None and (o.root / 'status.log').parent.exists():
            with open(o.root / 'status.log', 'a') as fh:
                fh.write(redact(f'{now()}  STOPPED: {e}') + '\n')
        print(redact(f'STOPPED: {e}'), file=sys.stderr, flush=True)
        if o.ledger:
            print(f'ledger: {json.dumps(o.ledger.summary())}', file=sys.stderr)
        return e.code
    except Exception as e:   # a bug in this script: leave a stop line, not just a traceback in a terminal
        if o.state is not None and (o.root / 'status.log').parent.exists():
            with open(o.root / 'status.log', 'a') as fh:
                fh.write(redact(f'{now()}  CRASHED: {type(e).__name__}: {str(e)[:300]}; --resume continues') + '\n')
        raise


if __name__ == '__main__':
    sys.exit(main())
