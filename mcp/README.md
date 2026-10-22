# Analyst agent over the indexed well file (MCP pattern)

The document parser ships a nine-tool MCP server (extract, apply_schema, generate_schema, split_document, extract_tables,
extract_charts, batch_extract, run_pipeline, get_job; the parser's MCP documentation, 2026-09-01). That makes the document parser a
parser under an agent, not an agent. The demo puts the extraction behind an assistant that answers only from
cited fields and hands exceptions to a person.

## Wiring (needs PULSE_API_KEY; Frank creates the account, D-104)

Claude Code (`.mcp.json` in this directory, 2026-09-05: `pulse` = local `uvx pulse-mcp@latest` for files on disk, `pulse-hosted` = the hosted endpoint at `${PARSER_MCP_URL}` for URLs; both read `PULSE_API_KEY` from the shell — `export PULSE_API_KEY=... (see .env.example)`). Local server verified to install and start (it refuses without a key). Preflight: `bash mcp/preflight.sh`.

```json
{ "mcpServers": { "pulse": { "type": "http", "url": "${PARSER_MCP_URL}", "headers": { "x-api-key": "${PULSE_API_KEY}" } } } }
```

Claude Desktop: paste `claude-desktop-config.json` into `claude_desktop_config.json`, replacing the key placeholder.
Local server for files on disk: `uvx pulse-mcp@latest` with `PULSE_API_KEY` set (50 MB cap; bytes never enter the model context).

Security framing to say out loud: the hosted path routes documents by URL through the document parser's cloud and the connector
runtime; the local path keeps bytes off the model but still uploads to the parser API. Neither is on-prem unless
the base URL is redirected, which the MCP docs do not describe (NOT DOCUMENTED).

## Scripted questions (the demo asks these, in order)

1. "Index this permit packet. Which pages are the W-1 and which are plats?" → `run_pipeline` or `extract` + `split_document`.
2. "What is the API number, operator, lease, well number, county, and permitted total depth? Cite the page." → `apply_schema` with `schemas/w1_permit.json`.
3. "List the fields of anticipated completion with completion depth. Cite the row." → same schema, `fields[]`.
4. "How far is the surface location from the nearest lease line, and from what direction?" → `lease_perpendiculars`.
5. "What is the logging company and the mud weight on the last run?" → **must answer: not in this packet.** A W-1 permit carries no logging or mud data. The refusal is the point.
6. "Digitize the log curves." → **must answer: out of scope.** No curve digitization; the log vendor owns that boundary.

## Guardrails (system prompt for the analyst)

- Answer only from fields returned by `apply_schema`; quote the page and box for every value.
- If the field is absent or null, say "not in this document" and offer the reviewer queue.
- Never compute or infer across documents unless every input is cited.
- Results over ~350 KB arrive as a link the agent cannot fetch; hand that to a fetch step outside the agent.
- Classify is forced choice with no confidence; treat `unrecognized` as a refusal and route it.

## No-key fallback

`python3 mcp/ask.py --run runs/<id> --permit 918133 "lease line"` answers the same questions deterministically from
the stored schema output with citations, so the pattern demos without an API key. In fixture runs the banner says
SYNTHETIC. This is a lookup, not a model; say so.
