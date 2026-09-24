# MCP Server Contract

Status: active
Command: `ds mcp serve` / `ds mcp token`
Engine: `integrations.mcp` (`server.py` protocol handler, `app.py` Streamable HTTP
transport, `tools.py` tool registry, `auth.py` bearer token)

## Purpose

Exposes a curated, read-only slice of Dream Studio's SQLite authority as an MCP
(Model Context Protocol) server, so a network client — Fulcrum, an MCP gateway, or
any other MCP-speaking tool — can read project, work-order, review, skill, memory,
and health state without shelling out to the `ds` CLI or touching SQLite directly.

This fills the `mcp` slot `adapter-projections/mcp/server-policy.json` already
declared (`adapter_role: projection`, `authority.source: dream_studio_sqlite`) but
that, before this, had no runtime behind it.

## Why curated, not the whole CLI

`ds` commands assume an operator at a terminal as their own confirmation step —
`uninstall --purge-state`, migration execution, `review --record`, anything that
mutates SQLite authority or the filesystem. An MCP client calling this server over
the network is not a watched terminal, so the tool registry
(`integrations/mcp/tools.py`) ships only read paths. See that module's own docstring
for the reasoning; `tests/unit/integrations/test_mcp_server.py`'s
`test_no_tool_name_suggests_a_write_or_destructive_action` is a cheap standing guard
against a write-shaped tool slipping in, not a substitute for reading the registry
before adding to it.

## Transport

Streamable HTTP (one endpoint, `POST /mcp`), matching the current MCP spec's
recommended transport for a network-reachable server. No SSE server-push stream is
implemented — every tool here is a single request/response read, so there is nothing
for the server to push. `GET /health` is unauthenticated, matching the dashboard
API's own `/api/health`; every other request on this server requires auth.

## Auth

Every `/mcp` request requires `Authorization: Bearer <token>`. The token is
generated on first use (`ds mcp token`, or automatically on first `ds mcp serve`)
and stored at `~/.dream-studio/state/mcp-token.json` (`0o600` where the platform
supports it). `ds mcp token --rotate` invalidates the old token immediately — nothing
holds the prior value once rotated. The token is never returned by any tool call and
never logged; only `ds mcp token`'s own stdout carries it, on the operator's own
terminal.

## Network exposure

`ds mcp serve` binds `127.0.0.1` by default. Passing `--host 0.0.0.0` exposes the
server to the network (required for Fulcrum or a gateway running as a separate
process to reach it) and prints an explicit warning on start. Binding beyond
localhost does not relax auth — every `/mcp` call still requires the bearer token
regardless of bind address.

## Invariants

1. Every tool in `integrations/mcp/tools.py` is read-only. A tool that mutates
   authority state does not belong in this registry.
2. A tool handler's exception is reported as an `isError` tool result, never allowed
   to raise out of the JSON-RPC layer — a network client cannot see a Python
   traceback, and the RPC layer must not crash the process on a bad call.
3. The bearer token is never included in a tool result, a log line, or an error
   message.
4. `/mcp` refuses every request without a valid bearer token except `GET /health`.
5. Tool handlers call the same `core.*` pure functions the CLI itself calls — no
   `subprocess.run(["ds", ...])` — so this server and the CLI never drift into two
   different ways of answering the same question.
