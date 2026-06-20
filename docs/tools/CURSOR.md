# Cursor — Dream Studio Integration

Cursor reads `AGENTS.md` natively. Dream Studio installs its generated
universal AGENTS.md so the full skill routing table, work-order types, and gate
definitions are available.

## Installation

```bash
ds integrate install cursor --execute
```

This writes the generated AGENTS.md to `~/.cursor/rules/AGENTS.md`. Regenerate after canonical changes
with `py -m integrations.compiler.agents_md --write` (a drift gate enforces freshness).

## What works

- Skill routing via AGENTS.md (installed to `~/.cursor/rules/AGENTS.md`).
- The full Dream Studio skill set is discoverable and routable.
- Project/work-order/milestone lifecycle via the `ds` CLI.

## Limitations

- No Dream Studio hooks (Claude-Code-only).
- No automatic token/telemetry capture (hooks-dependent).
- MCP servers configured separately in Cursor settings if desired.

## See also

- `docs/TOOL_CAPABILITIES.md` — full per-tool capability matrix.
- `AGENTS.md` — the generated universal instructions this tool consumes.
