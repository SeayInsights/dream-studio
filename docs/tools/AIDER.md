# Aider — Dream Studio Integration

Aider reads `AGENTS.md` natively. Dream Studio installs its generated
universal AGENTS.md so the full skill routing table, work-order types, and gate
definitions are available.

## Installation

```bash
ds integrate install aider --execute
```

This writes the generated AGENTS.md to project-root `AGENTS.md`. Regenerate after canonical changes
with `py -m integrations.compiler.agents_md --write` (a drift gate enforces freshness).

## What works

- `AGENTS.md` at the project root provides conventions/routing.
- Full skill set + `ds` CLI lifecycle.

## Limitations

- No Dream Studio hooks (Claude-Code-only).
- No MCP integration.
- No automatic telemetry capture.

## See also

- `docs/TOOL_CAPABILITIES.md` — full per-tool capability matrix.
- `AGENTS.md` — the generated universal instructions this tool consumes.
