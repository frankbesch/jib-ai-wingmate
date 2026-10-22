#!/usr/bin/env bash
# Held-out run 2 launcher (BUILD-SPEC H3). Frank starts this; agents only run it with --dry-run or --stub.
#
#   bash heldout2/run-heldout2.sh               # LIVE: every stage, unattended (plan 06, section 7)
#   bash heldout2/run-heldout2.sh --resume <stamp>
#   bash heldout2/run-heldout2.sh --dry-run     # stage list, commands, deadlines; no check, no write
#   bash heldout2/run-heldout2.sh --stub        # fakes only; no network, no spend
#
# Live checks before python starts: PULSE_API_KEY and TYPESAFE_API_KEY present and at least 16 chars (length
# only; values are never printed or logged); `claude auth status` reports loggedIn under the same stripped
# environment the arms get (every KEY/TOKEN/SECRET variable removed); codex, sandbox-exec, pdftoppm on PATH.
# Load the keys first, e.g.:
#   export PULSE_API_KEY=... (see .env.example)
#   export TYPESAFE_API_KEY=... (see .env.example)
# R11: confirm in the Claude account settings that paid extra usage is off (or capped) before starting.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
cd "$DEMO"

live=1 ; prev=""
for a in "$@"; do
  case "$a" in --dry-run|--stub) live=0 ;; esac
  if [ "$prev" = "--resume" ]; then case "$a" in *-stub) live=0 ;; esac; fi
  prev="$a"
done

if [ "$live" -eq 1 ]; then
  for name in PULSE_API_KEY TYPESAFE_API_KEY; do
    n=0
    if [ -n "${!name:-}" ]; then v="${!name}"; n=${#v}; unset v; fi
    if [ "$n" -lt 16 ]; then echo "STOP: $name missing or shorter than 16 chars ($n); load it: export $name=... (see .env.example)" >&2; exit 1; fi
    echo "$name present ($n chars; value not shown)"
  done
  for c in python3 codex claude sandbox-exec pdftoppm; do
    command -v "$c" >/dev/null || { echo "STOP: $c not on PATH" >&2; exit 1; }
  done
  unsets=()
  while IFS= read -r v; do
    case "$v" in *[Kk][Ee][Yy]*|*[Tt][Oo][Kk][Ee][Nn]*|*[Ss][Ee][Cc][Rr][Ee][Tt]*) unsets+=(-u "$v") ;; esac
  done < <(compgen -e)
  # Bounded check (macOS has no `timeout`): perl forks the check into its own process group, and at the deadline
  # TERMs then KILLs that group, so a stalled sign-in check cannot hang the launcher. Output goes to a temp file,
  # not a pipe, so a straggler holding stdout cannot block either.
  AUTH_TIMEOUT="${HELDOUT2_AUTH_TIMEOUT:-30}"
  authout="$(mktemp "${TMPDIR:-/tmp}/heldout2-auth.XXXXXX")"
  rc=0
  perl -e 'my $t = shift; my $pid = fork(); die "fork failed\n" unless defined $pid;
           if ($pid == 0) { setpgrp(0, 0); exec(@ARGV) or exit 127; }
           local $SIG{ALRM} = sub { kill("TERM", -$pid); sleep 2; kill("KILL", -$pid); waitpid($pid, 0); exit 124; };
           alarm $t; waitpid($pid, 0); my $st = $?; alarm 0; kill("KILL", -$pid); exit($st >> 8);' \
    "$AUTH_TIMEOUT" env ${unsets[@]+"${unsets[@]}"} claude auth status >"$authout" 2>/dev/null </dev/null || rc=$?
  if [ "$rc" -eq 124 ]; then
    rm -f "$authout"
    echo "STOP: claude auth status did not answer within ${AUTH_TIMEOUT}s; its process group was killed; nothing started" >&2
    exit 1
  fi
  if grep -Eq '"loggedIn": *true' "$authout"; then
    rm -f "$authout"
    echo "claude auth status: loggedIn true (stripped environment)"
  else
    rm -f "$authout"
    echo "STOP: claude auth status does not report loggedIn without KEY/TOKEN/SECRET variables; run 'claude auth login'" >&2
    exit 1
  fi
else
  echo "dry-run or stub: key, sign-in, and tool checks skipped"
fi
exec python3 "$HERE/run_heldout2.py" "$@"
