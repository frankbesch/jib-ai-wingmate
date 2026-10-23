#!/usr/bin/env bash
# F2 runner (D-218 shape): measure the Claude API cost per typed-question call.
# Frank starts this from his own terminal. It spends metered API money, capped by MAX_USD.
#
#   export ANTHROPIC_API_KEY=...        # a Console key; never pasted into chat
#   bash typed/run-claude-api-cost.sh            # preflight, then asks before live
#   MODEL=claude-opus-5-5 MAX_USD=5 bash .../run-claude-api-cost.sh
#
# Phases: venv -> dry-run (no network) -> preflight (free count_tokens) -> confirm -> live -> receipt.
set -euo pipefail
export PYTHONUNBUFFERED=1

HERE="$(cd "$(dirname "$0")" && pwd)"
MODEL="${MODEL:-claude-fable-5-1}"
MAX_USD="${MAX_USD:-15}"
MAX_TOKENS="${MAX_TOKENS:-4096}"
WATCHDOG_SECS="${WATCHDOG_SECS:-1800}"
VENV="${VENV:-$HERE/.venv-claude-api}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOGS="$HERE/../runs/claude-api-cost/$STAMP"      # runs/ is gitignored
mkdir -p "$LOGS"
LOG="$LOGS/runner.log"
WATCHDOG_PID=""

phase() { printf '\n=== PHASE %s  %s ===\n' "$1" "$(date -u +%H:%M:%SZ)" | tee -a "$LOG"; }
cleanup() {
  rc=$?
  [ -n "$WATCHDOG_PID" ] && kill "$WATCHDOG_PID" 2>/dev/null || true
  [ -n "${REPLAY_PID:-}" ] && kill "$REPLAY_PID" 2>/dev/null || true
  printf '\n=== EXIT rc=%s  logs %s ===\n' "$rc" "$LOGS" | tee -a "$LOG"
}
trap cleanup EXIT
trap 'echo "INTERRUPTED" | tee -a "$LOG"; exit 130' INT TERM

phase "preflight"
command -v python3 >/dev/null || { echo "STOP: python3 not found"; exit 1; }
if [ -z "${ANTHROPIC_API_KEY:-}" ] && ! command -v ant >/dev/null; then
  echo "STOP: set ANTHROPIC_API_KEY (Console key) or log in with 'ant auth login' first."; exit 1
fi
[ -n "${ANTHROPIC_API_KEY:-}" ] && echo "key: ANTHROPIC_API_KEY is set (${#ANTHROPIC_API_KEY} chars; value not shown)" | tee -a "$LOG"
echo "model=$MODEL max_usd=$MAX_USD max_tokens=$MAX_TOKENS watchdog=${WATCHDOG_SECS}s" | tee -a "$LOG"

phase "venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet 'anthropic==1.9.0'
fi
"$VENV/bin/python" -c "import anthropic, sys; v = anthropic.__version__; print('anthropic', v); sys.exit(0 if v == '1.9.0' else 3)" | tee -a "$LOG"
PY="$VENV/bin/python"
ARGS=(--model "$MODEL" --max-usd "$MAX_USD" --max-tokens "$MAX_TOKENS")

phase "dry-run"
"$PY" "$HERE/claude_api_replay.py" --mode dry-run "${ARGS[@]}" 2>&1 | tee -a "$LOG"

phase "count-tokens"
"$PY" "$HERE/claude_api_replay.py" --mode preflight "${ARGS[@]}" 2>&1 | tee -a "$LOG"

read -r -p "Spend real API money on the live replay? Type 'yes' to continue: " ok
[ "$ok" = "yes" ] || { echo "Stopped before any billed call." | tee -a "$LOG"; exit 0; }

phase "live"
"$PY" "$HERE/claude_api_replay.py" --mode live "${ARGS[@]}" > >(tee -a "$LOG") 2>&1 &
REPLAY_PID=$!
( i=0; while [ "$i" -lt "$WATCHDOG_SECS" ] && kill -0 "$REPLAY_PID" 2>/dev/null; do sleep 5; i=$((i+5)); done
  kill -0 "$REPLAY_PID" 2>/dev/null && { echo "WATCHDOG: ${WATCHDOG_SECS}s passed, stopping the replay" | tee -a "$LOG"; kill "$REPLAY_PID"; } ) &
WATCHDOG_PID=$!
wait "$REPLAY_PID"

phase "receipt"
echo "Results: artifacts/typed-questions-2026-09-28/live-results/claude-api-replay/ (report.md, report.json, calls.jsonl per set)" | tee -a "$LOG"
echo "Hand the RESULTS line above to the next session for the metrics-table update." | tee -a "$LOG"
