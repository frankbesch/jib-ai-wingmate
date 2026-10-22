# Held-out run 2 orchestrator: accepted residual risks

These are known limits of `heldout2/run_heldout2.py`. They are documented, not fixed. The dry-run footer names them too.

1. **The parser cap is enforced by observing spend.** About once a second the script sums `credits_used` over the API responses `pipeline.py` has written to `runs/<id>/raw/`. It kills the stage when that sum plus other spend would pass 800 credits. The call in flight is not seen, so one call can land past the cap. This is not a per-call guarantee. Provider-side credit bounds are UNVERIFIED. (First review, finding 3.)
2. **A child that detaches can survive cleanup.** After every stage the script sends TERM, waits, sends KILL, and verifies that the child's process group is gone. A descendant that calls `setsid` leaves that group, so this does not cover it. The redo runner's own watchdog detaches on purpose and exits by itself. (First review, finding 5.)
3. **The render profile allows two things Chrome needs.** It allows writes to the user temp folder (`getconf DARWIN_USER_TEMP_DIR`) and Unix-domain sockets. Everything else follows the accepted template: default allow, all other network denied, writes denied outside the render folder, `/dev/null`, `/dev/dtracehelper`, and ttys, and reads under `~/Documents` denied. Code in the render folder could read or write other files in the user temp folder. (First review, finding 11.)
4. **The R4 log scan detects reads; it does not prevent them.** It reads the commands a Codex session ran, from the session rollout file and its stdout. Known blind spots:
   - paths built at run time (string joins, globs, variables other than HOME);
   - reads through a symlink the session creates inside its folder;
   - a bare `/`;
   - reads Codex makes outside a tool call;
   - `apply_patch` calls (not scanned; the sandbox blocks writes outside);
   - MCP or web tools;
   - a missing rollout file, in which case only stdout is scanned and status.log says so.

   Regex literals such as `'/pattern/'` can raise false hits. Path-like values (starting with `/` or `~`) and values under 8 characters are not redacted as secrets, so the scan is not blinded by them.
