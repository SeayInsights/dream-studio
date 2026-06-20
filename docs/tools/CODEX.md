# Codex CLI — Dream Studio Integration

Codex CLI reads `AGENTS.md` natively. Dream Studio installs its generated
universal AGENTS.md so the full skill routing table, work-order types, and gate
definitions are available.

## Installation

```bash
ds integrate install codex --execute
```

This writes the generated AGENTS.md to project-root `AGENTS.md`. Regenerate after canonical changes
with `py -m integrations.compiler.agents_md --write` (a drift gate enforces freshness).

## What works

- Reads `AGENTS.md` natively from the project root — routing works out of the box.
- Full skill set + `ds` CLI lifecycle.
- Already the original AGENTS.md consumer; now the file is generated, not hand-written.

## Limitations

- No Dream Studio hooks (Claude-Code-only).
- No automatic telemetry capture.

## See also

- `docs/TOOL_CAPABILITIES.md` — full per-tool capability matrix.
- `AGENTS.md` — the generated universal instructions this tool consumes.
