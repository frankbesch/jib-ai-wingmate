#!/usr/bin/env bash
# preflight.sh — run the morning of any live Pulse MCP showing; prints PASS/FAIL per gate, never a secret.
cd "$(dirname "$0")/.." || exit 1
ok(){ printf '  PASS  %s\n' "$1"; } ; bad(){ printf '  FAIL  %s\n' "$1"; FAIL=1; }
FAIL=0
echo "Pulse live-demo preflight $(date '+%Y-%m-%d %H:%M')"
if [ -z "${PULSE_API_KEY:-}" ]; then bad "PULSE_API_KEY not in shell: export PULSE_API_KEY=... (see .env.example)"
elif [ "${#PULSE_API_KEY}" -lt 16 ]; then bad "PULSE_API_KEY is ${#PULSE_API_KEY} chars — truncated store (09-05 incident); re-export the full key"
else ok "PULSE_API_KEY exported in this shell (${#PULSE_API_KEY} chars)"; fi
echo hi | claude -p >/dev/null 2>&1 && ok "claude CLI auth alive" || bad "claude auth login needed"
python3 score.py --selftest >/dev/null 2>&1 && ok "scorer selftest" || bad "score.py --selftest"
[ "$(ls corpus/packets/clean 2>/dev/null | wc -l | tr -d ' ')" = "9" ] && ok "clean corpus 9 packets" || bad "corpus/packets/clean != 9 (rebuild with build_corpus.py)"
[ -f console/index.html ] && grep -q 'LIVE' console/index.html && ok "console packed from a live run" || bad "console banner not LIVE (rebuild from the latest live run)"
if [ -z "${PARSER_MCP_URL:-}" ]; then code=unset; else code=$(curl -s -o /dev/null -w '%{http_code}' -m 8 -X POST "$PARSER_MCP_URL" -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' -H "x-api-key: ${PULSE_API_KEY:-none}" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"preflight","version":"0"}}}' 2>/dev/null); fi
case "$code" in 200|201|202) ok "MCP endpoint reachable (initialize → $code; key is checked at tools/call)";; 401|403) bad "MCP endpoint rejected the key ($code)";; unset) bad "PARSER_MCP_URL not set (see .env.example)";; *) bad "MCP endpoint unreachable or unexpected ($code)";; esac
python3 mcp/ask.py --run runs/live-clean-02 --permit 918133 "mud weight" 2>/dev/null | grep -q 'Not in this document' && ok "no-key analyst fallback answers with a refusal" || bad "mcp/ask.py fallback"
[ $FAIL -eq 0 ] && echo "ALL GATES PASS" || { echo "GATES FAILED — fix before showing"; exit 1; }
