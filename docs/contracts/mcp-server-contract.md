# MCP Server Contract

Status: active
Command: `ds mcp serve` / `ds mcp token` / `ds mcp client add|list|revoke|rotate`
Engine: `integrations.mcp` (`server.py` protocol handler, `app.py` Streamable HTTP
transport, `tools.py` tool registry, `auth.py` root token + named clients)

## Purpose

Exposes a curated slice of Dream Studio's SQLite authority (reads, plus the writes in
"Capability-gated tools" below) as an MCP
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
the network is not a watched terminal, so every tool in the registry
(`integrations/mcp/tools.py`) is, as of this writing, a read path. See that module's
own docstring for the reasoning; `tests/unit/integrations/test_mcp_server.py`'s
`test_no_tool_name_suggests_a_write_or_destructive_action` is a cheap standing guard
against a write-shaped tool slipping in unreviewed, not a substitute for reading the
registry before adding to it.

A tool is *allowed* to mutate authority state — the mechanism below exists precisely
so one eventually can — but only by declaring a `required_capability` from
`auth.KNOWN_CAPABILITIES` and passing the same deliberate review every tool here
already gets. Declaring a capability is necessary for a mutating tool to exist at all;
it is never sufficient on its own for one to be added.

## Root token vs. named clients

Two distinct kinds of caller authenticate against this server:

- **The root token** (`ds mcp token`) is the operator's own machine-local secret,
  unrestricted — the same "operator at a terminal" trust `ds` has always assumed,
  just reachable over the network too. It satisfies every capability check,
  including one no tool declares yet.
- **A named client** (`ds mcp client add <name> --capabilities ...`) is a specific,
  nameable, revocable caller — Fulcrum, a gateway, an individual agent — limited to
  exactly the capabilities it was issued. Its token is generated once, shown once,
  and only its sha256 hash is ever persisted (`~/.dream-studio/state/mcp-token.json`,
  alongside the root token), the same "generate, hash, hand back the plaintext
  exactly once" shape `core.work_orders.review_answers.record_dispatch` already uses
  for a review lane's per-reviewer credentials.

A tool with `required_capability=None` (the read-only tools) is reachable by the root
token **or any authenticated named client**, including a read-only client with no
capability at all: capabilities only ever gate a tool that declares one, they never
narrow what is already open. The root token satisfies every capability.

### Capability-gated tools

Each of these writes to the authority and is refused to a named client that does not
hold its capability:

| Tool | Capability |
| --- | --- |
| `ds_project_create` | `project:create` |
| `ds_milestone_create` | `milestone:create` |
| `ds_work_order_create` | `work_order:create` |
| `ds_work_order_add_task` | `work_order:add_task` |
| `ds_work_order_start` | `work_order:start` |
| `ds_work_order_task_start` | `work_order:task_mutate` |
| `ds_work_order_task_done` | `work_order:task_mutate` |
| `ds_work_order_advance` | `work_order:advance` |
| `ds_work_order_close` | `work_order:close` |
| `ds_review_dispatch` | `review:dispatch` |
| `ds_review_run` | `review:run` |
| `ds_review_record` | `review:record` |

**`review:dispatch` and `review:record` can never be granted to the same client.**
`record_dispatch()` mints every reviewer's credential in one call and returns all of
them, in plaintext, to whoever calls dispatch — that is the round table's chair. A
client that could also call `record` (spend a specific reviewer's credential) would
be, in one identity, simultaneously the chair and every reviewer — exactly what
`record_dispatch()`'s own credential scheme exists to make impossible ("a local tool
without an identity system cannot prove the chair did not answer as a seat"). This is
enforced in code (`auth.add_client` raises), not merely documented. It closes the
single-identity case specifically; it cannot and does not stop one human operator
holding two separate client tokens from manually relaying a credential between them —
no local, identity-less tool can. `review:run` is not part of this rule: it consumes
no reviewer credential (`ds review --run` only requires that a dispatch exists for
the work order), and the recording door re-executes any claimed reproduction
independently regardless of who submitted it — but it is still, on its own,
an uncredentialed "run a command in a fresh container for any dispatched work order"
capability, worth scoping deliberately on its own terms.

`tools/list` is **not** filtered by capability — every authenticated caller, root or
named, sees the full registry (names, descriptions, schemas), including any tool it
cannot actually call. Enforcement happens only at `tools/call` time, with a clear
`forbidden: missing capability <name>` error rather than folding a permission
question into "unknown tool."

## Transport

Streamable HTTP (one endpoint, `POST /mcp`), matching the current MCP spec's
recommended transport for a network-reachable server. No SSE server-push stream is
implemented — every tool here is a single request/response read, so there is nothing
for the server to push. `GET /health` is unauthenticated, matching the dashboard
API's own `/api/health`; every other request on this server requires auth.

## Auth

Every `/mcp` request requires `Authorization: Bearer <token>`, checked against the
root token first and then every named client (`integrations/mcp/auth.py::authenticate`).
The root token is generated on first use (`ds mcp token`, or automatically on first
`ds mcp serve`) and stored at `~/.dream-studio/state/mcp-token.json` (`0o600` where
the platform supports it), alongside a `clients` map of every named client's sha256
token hash and capabilities — never the plaintext. `ds mcp token --rotate` invalidates
the old root token immediately without touching any provisioned client; `ds mcp client
rotate <name>` does the same for one client without touching the root token or any
other client. Neither the root token nor a client's token is ever returned by any tool
call or logged; only `ds mcp token` and `ds mcp client add|rotate`'s own stdout carry a
plaintext token, on the operator's own terminal, once, at issuance.

## Starting it

```
ds mcp serve                      # http://127.0.0.1:8788/mcp
ds mcp serve --port 9000          # any other free port
```

The default port is 8788. It was 8765 until 2026-10, a port other local MCP tooling
commonly uses, so on a machine running both whichever started second failed to bind.
The server runs in the foreground until stopped; run it from the installed app's
launcher (`<home>/bin/ds.cmd mcp serve`, written by `ds self-install`) so it serves the
installed code, not a checkout.

## Connecting a client

A client that is not the operator's own terminal (a gateway, an agent, another tool)
gets its own named, scoped credential, never the root token:

```
ds mcp client add <name> --capabilities <only what it calls>
```

The token is printed once. Read-only tools need no capability: a client that only
reads is added with `ds mcp client add <name> --read-only`. Otherwise grant the smallest
capability set its calls require, and never `review:dispatch` together with
`review:record` (`auth.add_client` refuses that pair). A refused `client add`, `revoke`
or `rotate` exits 1. `ds mcp client revoke <name>`
ends one client's access without touching any other.

## Network exposure

`ds mcp serve` binds `127.0.0.1` by default, which every process on the same machine
can reach. Passing `--host 0.0.0.0` is needed only for a client on another machine; it
exposes the server to the network and prints an explicit warning on start. Binding beyond
localhost does not relax auth — every `/mcp` call still requires the bearer token
regardless of bind address.

## Invariants

1. A tool with `required_capability=None` is read-only, reachable by any
   authenticated identity. A tool that mutates authority state MUST declare a
   capability from `auth.KNOWN_CAPABILITIES` — and still requires the same
   deliberate review every tool here gets before it joins the registry; declaring a
   capability is necessary, never sufficient.
2. A tool handler's exception is reported as an `isError` tool result, never allowed
   to raise out of the JSON-RPC layer — a network client cannot see a Python
   traceback, and the RPC layer must not crash the process on a bad call.
3. Neither the root token nor a client's token is ever included in a tool result, a
   log line, or an error message.
4. `/mcp` refuses every request without a valid bearer token (root or a named
   client) except `GET /health`.
5. Tool handlers call the same `core.*` pure functions the CLI itself calls — no
   `subprocess.run(["ds", ...])` — so this server and the CLI never drift into two
   different ways of answering the same question.
6. A single client is never granted both `review:dispatch` and `review:record` —
   enforced in `auth.add_client`, not just documented.
