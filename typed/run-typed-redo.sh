#!/usr/bin/env bash
# Pulse typed-question redo: live runner (D-218 shape, D-220 watchdog, D-239 caps).
# Frank starts this from his own terminal for every paid or subscription run. Agents never run it live.
#
# Usage (from the repo root, or anywhere; the script cds to the repo root):
#   bash typed/run-typed-redo.sh --backend claude|jev|cascade --run <run dir> [--run <run dir> ...]
#        [--repeats N] [--model <id>] [--max-spend <usd>] [--set <corpus dir>] [--truth-b <dir>]
#        [--parity | --no-parity] [--max-wall <secs>] [--stub] [--dry-run-only] [--yes]
#        [-- <extra typed_questions.py args>]
#   bash typed/run-typed-redo.sh --backend jev|claude|cascade --receipt-only <live out dir>   # test hook
#
#   --backend     claude (claude -p, subscription), jev (TypeSafe, metered), cascade (jev, escalating to claude)
#   --run         run dir, relative to the repo root or absolute; repeatable; runs execute one at a time
#   --repeats N   live runs per run dir (default 1); all runs are sequential, never concurrent
#   --model       required for claude and cascade (D-239 Q5 pin: claude-fable-5-1); not passed for jev
#   --max-spend   USD ceiling per run (jev, cascade). The python runner refuses when the dry-run's byte bound
#                 (bound_cost_usd, about 3x the estimate) exceeds it. Omitted: derived per run as
#                 bound_cost_usd x 1.2 rounded up to 4 decimals. Given below that: a warning, not a stop.
#   --set, --truth-b, --parity   passed through unchanged (parity is on by default; --no-parity drops it)
#   --max-wall    per-run wall limit in seconds, enforced by the watchdog (default 10800)
#   --stub        no network, no python call: same phases against a fake command (STUB_SLEEP secs, default 3)
#   --dry-run-only  stop after the dry-run phase (no auth check, no watchdog, no live call)
#   --receipt-only  print the receipt line for an existing out dir (reads report.json) and exit
#   --yes         skip the confirm prompt
#   Everything after `--` goes to typed/typed_questions.py verbatim (e.g. `-- --escalate-below 0.80`).
#
# Secrets come only from the environment (TYPESAFE_API_KEY for jev and cascade). The script checks the
# key's length and never prints, logs, or passes it on the command line. `set -x` is never used.
# Load it in your own Terminal first:
#   export TYPESAFE_API_KEY=... (see .env.example)
#
# Phases: args -> venv/deps -> auth preflight -> dry-run per run dir -> cap = ceil(calls x 1.2), where calls
#         is calls_upper_bound for cascade and requests otherwise; max-spend check or derivation
#         -> confirm -> watchdog handshake -> live runs, one at a time -> receipt per run -> cleanup.
# Logs: runs/typed-redo/<UTC stamp>/ (runs/ is gitignored): runner.log, watchdog.log, NN-<run>-rK.log,
#       NN-<run>-rK.status (RUNNING, COMPLETE, FAILED, or INCOMPLETE), state/ (handshake files).
# Watchdog (D-220): a python3 double fork + setsid, outside the terminal's process tree. It writes
# state/armed before the first live call. If the runner dies without a clean teardown it kills any child
# still running, writes INCOMPLETE into the run's status marker, and appends its cleanup line to runner.log.
# A clean exit ends runner.log with the line `cleanup complete`.
# shellcheck disable=SC2329  # cleanup, on_signal, kill_tree are invoked from traps
set -euo pipefail
export PYTHONUNBUFFERED=1

HERE="$(cd "$(dirname "$0")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
cd "$DEMO"
PY="${PY:-python3}"
RUNNER="$HERE/typed_questions.py"
KEY_ENV="TYPESAFE_API_KEY"
KEY_MIN=16
STUB_SLEEP="${STUB_SLEEP:-3}"
STUB_REQUESTS="${STUB_REQUESTS:-26}"
STUB_BOUND="${STUB_BOUND:-0.002991}"   # stub-only placeholder; not a measurement
SPEND=""

BACKEND="" ; MODEL="" ; MAX_SPEND="" ; SET_DIR="" ; TRUTH_B="" ; PARITY=1 ; STUB=0 ; YES=0
DRY_ONLY=0 ; RECEIPT_ONLY=""
REPEATS=1 ; MAX_WALL=10800
RUNS=() ; EXTRA=()

die() { printf 'STOP: %s\n' "$*" >&2; exit 2; }
while [ $# -gt 0 ]; do
  case "$1" in
    --backend)   [ $# -ge 2 ] || die "--backend needs a value"; BACKEND="$2"; shift 2 ;;
    --run)       [ $# -ge 2 ] || die "--run needs a value"; RUNS+=("$2"); shift 2 ;;
    --repeats)   [ $# -ge 2 ] || die "--repeats needs a value"; REPEATS="$2"; shift 2 ;;
    --model)     [ $# -ge 2 ] || die "--model needs a value"; MODEL="$2"; shift 2 ;;
    --max-spend) [ $# -ge 2 ] || die "--max-spend needs a value"; MAX_SPEND="$2"; shift 2 ;;
    --set)       [ $# -ge 2 ] || die "--set needs a value"; SET_DIR="$2"; shift 2 ;;
    --truth-b)   [ $# -ge 2 ] || die "--truth-b needs a value"; TRUTH_B="$2"; shift 2 ;;
    --max-wall)  [ $# -ge 2 ] || die "--max-wall needs a value"; MAX_WALL="$2"; shift 2 ;;
    --parity)    PARITY=1; shift ;;
    --no-parity) PARITY=0; shift ;;
    --stub)      STUB=1; shift ;;
    --yes)       YES=1; shift ;;
    --dry-run-only) DRY_ONLY=1; shift ;;
    --receipt-only) [ $# -ge 2 ] || die "--receipt-only needs an out dir"; RECEIPT_ONLY="$2"; shift 2 ;;
    --)          shift; EXTRA=("$@"); break ;;
    -h|--help)   sed -n '2,/^# A clean exit/p' "$0"; exit 0 ;;
    *)           die "unknown argument: $1 (see --help)" ;;
  esac
done

# ------------------------------------------------------------------ receipt (reads the run's report.json)
# args: backend, out dir, stub (0/1); stdin: the run's final JSON line (may be empty)
# shellcheck disable=SC2016  # the single-quoted text is python, not shell
RCPT_PY='
import json, sys, os
backend, out, stub = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
raw = sys.stdin.read().strip()
d = json.loads(raw) if raw else {}
rp = os.path.join(out, "report.json")
r = json.load(open(rp)) if os.path.exists(rp) else {}
nodes = d.get("nodes") or r.get("nodes") or {}
wna = sum(v.get("wrong_not_abstained", 0) for v in nodes.values())
calls, units, errs = (d.get(k, r.get(k, "?")) for k in ("calls", "units", "errors"))
cas = r.get("cascade") or {}
cost = r.get("cost_usd") or 0
jerr, reasons = cas.get("jev_errors", "?"), json.dumps(cas.get("escalated_by_reason"), sort_keys=True)
if stub:
    billed = "$0 (stub)"
elif not r:
    billed = "billed UNVERIFIED (no report.json)"
elif backend == "jev":
    tag = "SYNTHETIC, no spend" if r.get("mode") == "fixture" else "metered"
    billed = f"jev ${cost:.6f} billed ({tag})"
elif backend == "claude":
    billed = f"subscription, $0 billed; list-price estimate ${cost:.4f}"
else:
    tag = "SYNTHETIC, no spend" if "SYNTHETIC" in str(cas.get("jev_basis", "")) else "metered"
    jb, ce = cas.get("jev_billed_usd") or 0, cas.get("claude_cost_estimate_usd") or 0
    billed = (f"jev ${jb:.6f} billed ({tag}); claude subscription, $0 billed; list-price estimate ${ce:.4f}; "
              f"jev_errors={jerr} escalated_by_reason={reasons}")
print(f"calls={calls} units={units} errors={errs} wrong_not_abstained={wna} {billed}")
'
receipt() { printf '%s' "$4" | "$PY" -c "$RCPT_PY" "$1" "$2" "$3"; }

# ------------------------------------------------------------------ argument checks (before any log)
case "$BACKEND" in claude|jev|cascade) ;; *) die "--backend must be claude, jev, or cascade" ;; esac
if [ -n "$RECEIPT_ONLY" ]; then
  [ -d "$RECEIPT_ONLY" ] || die "--receipt-only: not a directory: $RECEIPT_ONLY"
  receipt "$BACKEND" "$RECEIPT_ONLY" 0 ""; exit $?
fi
if [ "$BACKEND" != jev ] && [ -z "$MODEL" ]; then
  die "--backend $BACKEND requires --model <id> (D-239 Q5 pin: claude-fable-5-1); refusing"
fi
[ "${#RUNS[@]}" -ge 1 ] || die "give at least one --run <run dir>"
case "$REPEATS" in ''|*[!0-9]*) die "--repeats must be a positive integer" ;; esac
[ "$REPEATS" -ge 1 ] || die "--repeats must be at least 1"
case "$MAX_WALL" in ''|*[!0-9]*) die "--max-wall must be whole seconds" ;; esac
case "$STUB_SLEEP" in ''|*[!0-9]*) die "STUB_SLEEP must be whole seconds" ;; esac
if [ -n "$MAX_SPEND" ]; then
  printf '%s' "$MAX_SPEND" | grep -Eq '^[0-9]+(\.[0-9]+)?$' || die "--max-spend must be a plain number of USD"
fi
for r in "${RUNS[@]}"; do [ -d "$r" ] || die "run dir not found: $r"; done
# Held-out run 2 (heldout2/BUILD-SPEC.md H1): --alias and --claude-row8 reach the runner through `--` unchanged.
# They also name the live out dir (redo-<backend><variant>-<stamp>-rN), because --out below overrides the runner's
# own tag. Variant: -alias-<value> and, for claude only, -c8-per-document. Defaults add nothing.
variant_tag() {
  local alias=none c8=per-field i=0 n=${#EXTRA[@]}
  while [ "$i" -lt "$n" ]; do
    case "${EXTRA[$i]}" in
      --alias)         alias="${EXTRA[$((i+1))]:-}"; i=$((i+1)) ;;
      --alias=*)       alias="${EXTRA[$i]#--alias=}" ;;
      --claude-row8)   c8="${EXTRA[$((i+1))]:-}"; i=$((i+1)) ;;
      --claude-row8=*) c8="${EXTRA[$i]#--claude-row8=}" ;;
    esac
    i=$((i+1))
  done
  [ "$alias" != none ] && printf -- '-alias-%s' "$alias"
  [ "$c8" = per-document ] && [ "$BACKEND" = claude ] && printf -- '-c8-per-document'
  return 0
}
VARIANT="$(variant_tag)"

# ------------------------------------------------------------------ logs and helpers
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOGS="$DEMO/runs/typed-redo/$STAMP"
[ "$STUB" -eq 1 ] && LOGS="$LOGS-stub"
STATE="$LOGS/state"
mkdir -p "$STATE"
LOG="$LOGS/runner.log"
WDLOG="$LOGS/watchdog.log"
: >"$LOG"

ts() { date -u +%H:%M:%SZ; }
# File first, terminal second; a dead terminal never blocks the log line.
log() { local line; line="[$(ts)] $*"; printf '%s\n' "$line" >>"$LOG"; printf '%s\n' "$line" 2>/dev/null || true; }
phase() { log "=== PHASE $1 ==="; }

CHILD_PID="" ; TAIL_PID="" ; CUR_STATUS="" ; WD_PID="" ; SIGNALED=""

set_current() {   # the watchdog reads this file; write-then-rename so it never sees half a file
  printf 'child=%s\ntail=%s\nstatus=%s\nout=%s\ndeadline=%s\n' "$1" "$2" "$3" "$4" "$5" >"$STATE/current.tmp"
  mv -f "$STATE/current.tmp" "$STATE/current"
}

kill_tree() {     # $1 = pid; TERM its children and itself, then KILL after 5 s
  local p="$1" i=0
  [ -n "$p" ] || return 0
  kill -0 "$p" 2>/dev/null || return 0
  pkill -TERM -P "$p" 2>/dev/null || true
  kill -TERM "$p" 2>/dev/null || true
  while kill -0 "$p" 2>/dev/null && [ "$i" -lt 10 ]; do sleep 0.5; i=$((i+1)); done
  pkill -KILL -P "$p" 2>/dev/null || true
  kill -KILL "$p" 2>/dev/null || true
}

# EXIT trap: files only. Signal traps move stdio to a file first (lesson 125: a dead tty garbles bash 3.2 output).
cleanup() {
  local rc=$?
  set +e
  [ -n "$SIGNALED" ] && rc="$SIGNALED"
  if [ -n "$SIGNALED" ]; then exec >>"$LOGS/trap.out" 2>&1 </dev/null; fi
  [ -n "$TAIL_PID" ] && kill "$TAIL_PID" 2>/dev/null
  kill_tree "$CHILD_PID"
  if [ -n "$CUR_STATUS" ] && grep -q '^RUNNING' "$CUR_STATUS" 2>/dev/null; then
    printf 'INCOMPLETE runner exit rc=%s at %s\n' "$rc" "$(ts)" >"$CUR_STATUS"
    log "INCOMPLETE: $(basename "$CUR_STATUS" .status) did not finish (rc=$rc)"
  fi
  if [ -n "$CHILD_PID" ] && kill -0 "$CHILD_PID" 2>/dev/null; then
    log "cleanup: child $CHILD_PID still alive; watchdog takes over"
    exit "$rc"
  fi
  : >"$STATE/clean"
  log "EXIT rc=$rc logs $LOGS"
  printf '%s\n' "cleanup complete" >>"$LOG"
  printf '%s\n' "cleanup complete" 2>/dev/null || true
  exit "$rc"
}
on_signal() { SIGNALED="$2"; exec >>"$LOGS/trap.out" 2>&1 </dev/null; log "SIGNAL $1 received"; exit "$2"; }
trap cleanup EXIT
trap 'on_signal INT 130' INT
trap 'on_signal TERM 143' TERM
trap 'on_signal HUP 129' HUP

# ------------------------------------------------------------------ watchdog (python3 double fork + setsid)
WD_PY=$(cat <<'PYEOF'
import os, sys, time, signal, subprocess
runner, state, log, wdlog, lstart = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5].strip()
if os.fork(): os._exit(0)
os.setsid()
if os.fork(): os._exit(0)
os.chdir('/')
fd = os.open(os.devnull, os.O_RDONLY); os.dup2(fd, 0)
fd = os.open(wdlog, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644); os.dup2(fd, 1); os.dup2(fd, 2)
signal.signal(signal.SIGHUP, signal.SIG_IGN)
def ts(): return time.strftime('%H:%M:%SZ', time.gmtime())
def wd(msg): print(f'[{ts()}] watchdog: {msg}', flush=True)
def runlog(msg):
    with open(log, 'a') as fh: fh.write(f'[{ts()}] WATCHDOG: {msg}\n')
def alive(p):
    try: os.kill(p, 0); return True
    except ProcessLookupError: return False
    except PermissionError: return True
def runner_alive():
    # pid plus start time: a reused pid has a different lstart, so it counts as gone
    if not alive(runner): return False
    if not lstart: return True
    now = subprocess.run(['ps', '-o', 'lstart=', '-p', str(runner)], capture_output=True, text=True).stdout.strip()
    return now == lstart
def current():
    d = {}
    try:
        for line in open(os.path.join(state, 'current')):
            k, _, v = line.rstrip('\n').partition('='); d[k] = v
    except OSError: pass
    return d
def kill_tree(p):
    if not p or not alive(p): return True
    for sig in (signal.SIGTERM, signal.SIGKILL):
        subprocess.run(['pkill', '-' + sig.name[3:], '-P', str(p)], check=False)
        try: os.kill(p, sig)
        except ProcessLookupError: return True
        for _ in range(10):
            if not alive(p): return True
            time.sleep(0.5)
    return not alive(p)
me = os.getpid()
tmp = os.path.join(state, 'armed.tmp')
with open(tmp, 'w') as fh: fh.write(f'pid={me} sid={os.getsid(0)} pgid={os.getpgid(0)} ppid={os.getppid()}\n')
os.replace(tmp, os.path.join(state, 'armed'))
wd(f'armed pid={me} sid={os.getsid(0)} watching runner {runner} started {lstart or "UNKNOWN"}')
clean = os.path.join(state, 'clean')
walled = None
while True:
    if os.path.exists(clean):
        wd('clean teardown seen; exiting'); sys.exit(0)
    if not runner_alive():
        time.sleep(1)
        if os.path.exists(clean):
            wd('clean teardown seen after runner exit; exiting'); sys.exit(0)
        cur = current()
        child = int(cur['child']) if cur.get('child') else None
        tail = int(cur['tail']) if cur.get('tail') else None
        runlog(f'runner pid {runner} gone without a clean teardown; taking over')
        ok = kill_tree(child)
        kill_tree(tail)
        st = cur.get('status')
        if st:
            try: running = open(st).read().startswith('RUNNING')
            except OSError: running = False
            if running:
                with open(st, 'w') as fh: fh.write(f'INCOMPLETE watchdog takeover at {ts()}\n')
                runlog(f'INCOMPLETE: {os.path.basename(st)[:-7]} marked by the watchdog')
        runlog(f'child {child} {"stopped" if ok else "STILL ALIVE"}; tail {tail} stopped')
        with open(log, 'a') as fh: fh.write('cleanup complete (watchdog)\n')
        open(os.path.join(state, 'watchdog-done'), 'w').close()
        wd('takeover done'); sys.exit(0)
    cur = current()
    if cur.get('child') and cur.get('deadline') and time.time() > float(cur['deadline']) and cur['child'] != walled:
        walled = cur['child']
        runlog(f'wall limit passed; stopping child {walled}')
        kill_tree(int(walled))
    time.sleep(1)
PYEOF
)

start_watchdog() {
  local i=0 armed our_pgid lstart
  lstart="$(ps -o lstart= -p $$ | sed 's/^ *//; s/ *$//')"
  "$PY" -c "$WD_PY" "$$" "$STATE" "$LOG" "$WDLOG" "$lstart" </dev/null >/dev/null 2>&1
  while [ ! -s "$STATE/armed" ] && [ "$i" -lt 20 ]; do sleep 0.5; i=$((i+1)); done
  [ -s "$STATE/armed" ] || { log "STOP: watchdog did not hand-shake within 10 s; no live call made"; exit 1; }
  armed="$(cat "$STATE/armed")"
  WD_PID="$(printf '%s' "$armed" | sed -E 's/^pid=([0-9]+).*/\1/')"
  our_pgid="$(ps -o pgid= -p $$ | tr -d ' ')"
  log "watchdog handshake OK: $armed (runner pid $$ pgid $our_pgid, started $lstart); file $STATE/armed"
  kill -0 "$WD_PID" 2>/dev/null || { log "STOP: watchdog pid $WD_PID not alive after handshake"; exit 1; }
}

# ------------------------------------------------------------------ command builder
build_args() {   # $1 = run dir, $2 = mode; fills ARGS
  ARGS=(--backend "$BACKEND" --run "$1" --mode "$2")
  [ "$BACKEND" != jev ] && ARGS+=(--model "$MODEL")
  [ -n "$SPEND" ] && [ "$BACKEND" != claude ] && ARGS+=(--max-spend "$SPEND")
  [ -n "$SET_DIR" ] && ARGS+=(--set "$SET_DIR")
  [ -n "$TRUTH_B" ] && ARGS+=(--truth-b "$TRUTH_B")
  [ "$PARITY" -eq 1 ] && ARGS+=(--parity)
  [ "${#EXTRA[@]}" -gt 0 ] && ARGS+=("${EXTRA[@]}")
  return 0
}
last_json() { "$PY" -c '
import json, sys
obj = None
for line in open(sys.argv[1], errors="replace"):
    line = line.strip()
    if line.startswith("{"):
        try: obj = json.loads(line)
        except ValueError: pass
print(json.dumps(obj) if obj is not None else "")' "$1"; }

# ------------------------------------------------------------------ phase: args
phase "args"
log "mode: $([ "$STUB" -eq 1 ] && echo 'STUB (no network, no python call)' || echo LIVE)"
log "backend=$BACKEND model=${MODEL:-n/a (jev pinned in jev_backend.py)} max_spend=${MAX_SPEND:-unset} repeats=$REPEATS max_wall=${MAX_WALL}s"
log "runs: ${RUNS[*]}; set=${SET_DIR:-default} truth_b=${TRUTH_B:-none} parity=$([ "$PARITY" -eq 1 ] && echo on || echo off) extra=${EXTRA[*]:-none}"
[ -n "$VARIANT" ] && log "variant: $VARIANT (live out dirs: <run>/typed/redo-$BACKEND$VARIANT-$STAMP-rN)"
[ "$BACKEND" != claude ] && [ -z "$MAX_SPEND" ] && log "max-spend: not given; derived per run from the dry-run bound (bound_cost_usd x 1.2)"
[ "$DRY_ONLY" -eq 1 ] && log "dry-run-only: stops after the dry-run phase; no auth check, no watchdog, no live call"
log "logs: $LOGS"

# ------------------------------------------------------------------ phase: venv/deps
phase "venv/deps"
command -v "$PY" >/dev/null || { log "STOP: $PY not found"; exit 1; }
log "python: $("$PY" -c 'import sys; print(sys.executable, sys.version.split()[0])')"
[ -f "$RUNNER" ] || { log "STOP: $RUNNER missing"; exit 1; }
"$PY" -c 'import ast, sys; ast.parse(open(sys.argv[1]).read())' "$RUNNER" || { log "STOP: $RUNNER does not parse"; exit 1; }
"$PY" -c 'import json, ssl, http.client, subprocess' || { log "STOP: python stdlib modules missing"; exit 1; }
log "typed_questions.py parses; stdlib imports OK (the runner needs no venv)"
if [ "$BACKEND" != jev ]; then
  command -v claude >/dev/null || { log "STOP: claude CLI not on PATH"; exit 1; }
  log "claude CLI: $(command -v claude)"
  # Version and resolved binary, so a later diagnosis need not infer them from install mtimes (08-heldout2-diagnosis
  # Q2). Local only, no network. Each `claude -p` call execs the symlink, so an auto-update mid-arm is not caught here.
  cver="$(claude --version 2>/dev/null | head -1)"
  log "claude --version: ${cver:-UNKNOWN}; binary: $(readlink "$(command -v claude)" 2>/dev/null || echo 'not a symlink')"
fi

# ------------------------------------------------------------------ phase: auth preflight
phase "auth preflight"
if [ "$DRY_ONLY" -eq 1 ]; then
  log "dry-run-only: auth checks skipped (the dry-run makes no network call)"
elif [ "$STUB" -eq 1 ]; then
  log "STUB: auth checks skipped (no network); live checks: claude auth status (claude, cascade); $KEY_ENV length (jev, cascade)"
else
  if [ "$BACKEND" != jev ]; then
    if claude auth status 2>/dev/null | grep -Eq '"loggedIn": *true'; then log "claude auth status: loggedIn true"
    else log "STOP: claude auth status does not report loggedIn; run 'claude auth login'"; exit 1; fi
  fi
  if [ "$BACKEND" != claude ]; then
    keylen=0
    if [ -n "${!KEY_ENV:-}" ]; then keyval="${!KEY_ENV}"; keylen=${#keyval}; unset keyval; fi
    [ "$keylen" -ge "$KEY_MIN" ] || { log "STOP: $KEY_ENV missing or shorter than $KEY_MIN chars ($keylen); load it: export $KEY_ENV=... (see .env.example)"; exit 1; }
    log "$KEY_ENV present ($keylen chars; value not shown). GET /v1/models runs inside the python runner."
  fi
fi

# ------------------------------------------------------------------ phase: dry-run and caps
phase "dry-run"
CAPS=() ; SPENDS=() ; TOTAL=0 ; n=0
DRY_SPEND_PLACEHOLDER=1000   # dry-run only, no network: keeps the runner's bound refusal from hiding the bound
for r in "${RUNS[@]}"; do
  n=$((n+1))
  dlog="$LOGS/dry-$(printf '%02d' "$n")-$(basename "$r").log"
  if [ "$STUB" -eq 1 ]; then
    printf '{"mode": "dry-run", "stub": true, "requests": %s, "bound_cost_usd": %s, "network_calls": 0}\n' \
      "$STUB_REQUESTS" "$STUB_BOUND" >"$dlog"
  else
    SPEND="$DRY_SPEND_PLACEHOLDER"   # the dry-run always gets the placeholder; the live run gets the checked value
    build_args "$r" dry-run
    ARGS+=(--out "$LOGS/dry-$(printf '%02d' "$n")-$(basename "$r")")
    "$PY" "$RUNNER" "${ARGS[@]}" >"$dlog" 2>&1 || { log "STOP: dry-run failed for $r (see $dlog)"; tail -n 5 "$dlog" | sed 's/^/  /' >>"$LOG"; exit 1; }
  fi
  js="$(last_json "$dlog")"
  [ -n "$js" ] || { log "STOP: no JSON summary in $dlog"; exit 1; }
  # cascade dry-runs print calls_upper_bound (Jev requests + every unit Claude may answer); the cap counts both halves
  req="$(printf '%s' "$js" | "$PY" -c 'import json,sys; d=json.load(sys.stdin); print(int(d.get("calls_upper_bound", d["requests"])))')" || { log "STOP: no request count in $dlog"; exit 1; }
  est="$(printf '%s' "$js" | "$PY" -c 'import json,sys; d=json.load(sys.stdin); print(" ".join(f"{k}={d[k]}" for k in d if k.startswith(("est","bound","approx","network"))) or "none")')"
  cap=$(( (req * 6 + 4) / 5 ))
  CAPS+=("$cap"); TOTAL=$((TOTAL + req * REPEATS))
  log "dry-run $r: calls=$req; estimate: $est; cap=ceil($req x 1.2)=$cap"
  spend=""
  if [ "$BACKEND" != claude ]; then
    need="$(printf '%s' "$js" | "$PY" -c 'import json,math,sys; b=json.load(sys.stdin).get("bound_cost_usd"); print("" if b is None else f"{math.ceil(round(b*1.2*10000, 6))/10000:.4f}")')"
    if [ -z "$need" ]; then
      [ -n "$MAX_SPEND" ] || { log "STOP: dry-run for $r has no bound_cost_usd, and no --max-spend was given"; exit 1; }
      spend="$MAX_SPEND"; log "max-spend $r: \$$spend given; no bound_cost_usd to check it against"
    elif [ -z "$MAX_SPEND" ]; then
      spend="$need"; log "max-spend derived from bound: $r bound_cost_usd x 1.2 rounded up = \$$spend"
    else
      spend="$MAX_SPEND"
      if "$PY" -c 'import sys; sys.exit(0 if float(sys.argv[1]) < float(sys.argv[2]) else 1)' "$MAX_SPEND" "$need"; then
        log "WARN: --max-spend \$$MAX_SPEND is below bound x 1.2 (\$$need) for $r; the runner refuses if the bound exceeds it"
      else
        log "max-spend $r: \$$spend given; covers bound x 1.2 (\$$need)"
      fi
    fi
  fi
  SPENDS+=("${spend:-none}")
done
log "planned: ${#RUNS[@]} run dir(s) x $REPEATS repeat(s); $TOTAL calls in total (upper bound for cascade)"
if [ "$DRY_ONLY" -eq 1 ]; then log "dry-run-only: stopping before confirm; no live call made"; exit 0; fi

# ------------------------------------------------------------------ phase: confirm
phase "confirm"
if [ "$YES" -eq 1 ]; then
  log "confirm skipped (--yes)"
else
  [ -t 0 ] || { log "STOP: no terminal to confirm on; rerun with --yes"; exit 1; }
  printf 'Start %s live run(s) on %s? Type yes to continue: ' "$(( ${#RUNS[@]} * REPEATS ))" "$BACKEND"
  read -r ok
  [ "$ok" = "yes" ] || { log "stopped at confirm; no live call made"; exit 0; }
  log "confirmed by operator"
fi

# ------------------------------------------------------------------ phase: watchdog + live runs
phase "watchdog"
start_watchdog

phase "live"
n=0 ; k=0
for r in "${RUNS[@]}"; do
  cap="${CAPS[$k]}"; SPEND="${SPENDS[$k]}"; [ "$SPEND" = none ] && SPEND=""; k=$((k+1))
  rep=1
  while [ "$rep" -le "$REPEATS" ]; do
    n=$((n+1))
    label="$(printf '%02d' "$n")-$(basename "$r")-r$rep"
    rlog="$LOGS/$label.log"; CUR_STATUS="$LOGS/$label.status"
    if [ "$STUB" -eq 1 ]; then out="$LOGS/$label-out"; else out="$DEMO/$r/typed/redo-$BACKEND$VARIANT-$STAMP-r$rep"; fi
    printf 'RUNNING since %s\n' "$(ts)" >"$CUR_STATUS"
    : >"$rlog"
    t0=$(date +%s)
    if [ "$STUB" -eq 1 ]; then
      log "run $label: STUB fake command, sleep ${STUB_SLEEP}s (no network)"
      bash -c 'echo "stub run $1: sleeping $2 s"; sleep "$2"; printf "{\"out\": \"%s\", \"calls\": %s, \"units\": 0, \"errors\": 0, \"nodes\": {}, \"stub\": true}\n" "$3" "$4"' \
        _ "$label" "$STUB_SLEEP" "$out" "$STUB_REQUESTS" >"$rlog" 2>&1 </dev/null &
    else
      build_args "$r" live
      ARGS+=(--cap "$cap" --out "$out")
      log "run $label: python3 typed/typed_questions.py ${ARGS[*]}"
      "$PY" "$RUNNER" "${ARGS[@]}" >"$rlog" 2>&1 </dev/null &
    fi
    CHILD_PID=$!
    tail -n +1 -f "$rlog" 2>/dev/null &
    TAIL_PID=$!
    set_current "$CHILD_PID" "$TAIL_PID" "$CUR_STATUS" "$out" "$((t0 + MAX_WALL))"
    rc=0; wait "$CHILD_PID" || rc=$?
    sleep 0.3; kill "$TAIL_PID" 2>/dev/null || true; wait "$TAIL_PID" 2>/dev/null || true
    wall=$(( $(date +%s) - t0 ))
    CHILD_PID=""; TAIL_PID=""
    set_current "" "" "" "" ""
    # ------------------------------------------------------ receipt
    js="$(last_json "$rlog")"
    rcpt="$(receipt "$BACKEND" "$out" "$STUB" "$js")" || rcpt="receipt parse failed; see $rlog"
    if [ "$rc" -eq 0 ]; then printf 'COMPLETE rc=0 at %s\n' "$(ts)" >"$CUR_STATUS"
    else printf 'FAILED rc=%s at %s\n' "$rc" "$(ts)" >"$CUR_STATUS"; fi
    log "RECEIPT $label: rc=$rc $rcpt wall=${wall}s out=$out"
    CUR_STATUS=""
    [ "$rc" -eq 0 ] || { log "STOP: $label exited rc=$rc; remaining runs not started"; exit "$rc"; }
    rep=$((rep+1))
  done
done

phase "cleanup"
exit 0
