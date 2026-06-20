# Gemini CLI — Dream Studio Integration

Gemini CLI reads `AGENTS.md` natively. Dream Studio installs its generated
universal AGENTS.md so the full skill routing table, work-order types, and gate
definitions are available.

## Installation

```bash
ds integrate install gemini_cli --execute
```

This writes the generated AGENTS.md to project-root `AGENTS.md`. Regenerate after canonical changes
with `py -m integrations.compiler.agents_md --write` (a drift gate enforces freshness).

## What works

- Reads `AGENTS.md` from the project root for routing.
- Full skill set + `ds` CLI lifecycle.

## Limitations

- No Dream Studio hooks (Claude-Code-only).
- No automatic telemetry capture.
- Gemini also supports `GEMINI.md`; Dream Studio standardizes on AGENTS.md.

## See also

- `docs/TOOL_CAPABILITIES.md` — full per-tool capability matrix.
- `AGENTS.md` — the generated universal instructions this tool consumes.
