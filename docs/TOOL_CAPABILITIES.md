# Dream Studio — Tool Capability Matrix

Dream Studio's **core SDLC works everywhere** a tool can read `AGENTS.md` and run
the `ds` CLI. The **full feature set** (hooks, automatic telemetry, the plugin
marketplace channel) is available on Claude Code. This matrix is the honest story
of what each integration target supports today.

| Tool | Skills / AGENTS.md routing | Hooks | MCP | Subagents | Plugin marketplace |
|------|:--:|:--:|:--:|:--:|:--:|
| **Claude Code** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Codex CLI** | ✅ | ❌ | ➖ | ❌ | ✅ (namespaced) |
| **Gemini CLI** | ✅ | ❌ | ➖ | ❌ | ❌ |
| **Cursor** | ✅ | ❌ | ➖ | ❌ | ❌ |
| **Windsurf** | ✅ | ❌ | ➖ | ❌ | ❌ |
| **Aider** | ✅ | ❌ | ❌ | ❌ | ❌ |

Legend: ✅ supported · ❌ not supported · ➖ available via the tool's own MCP config
(Dream Studio ships no MCP server today — see `.mcp.json`).

## What each column means

- **Skills / AGENTS.md routing** — the tool reads the generated `AGENTS.md`, so the
  pack-based skill routing table, work-order types, and gate definitions are
  available. This is the core of Dream Studio and works on every target.
- **Hooks** — automatic lifecycle hooks (PostToolUse token capture, on-stop handoff,
  milestone events, etc.). **Claude Code only** — these depend on Claude Code's hook
  system. Without hooks, the SDLC still works; it just isn't auto-instrumented.
- **MCP** — Model Context Protocol servers. Dream Studio is CLI-based and ships **no
  MCP server today** (`.mcp.json` declares an empty server map); tools that support
  MCP can still be configured independently.
- **Subagents** — parallel sub-agent orchestration. Claude Code only.
- **Plugin marketplace** — discovery/install via the Claude plugin marketplace
  (`.claude-plugin/`), with namespaced skill IDs (`dream-studio:ds-core:build`).

## Telemetry note

Automatic token/telemetry capture is hooks-dependent, so dashboards are populated
only when working through Claude Code. On other tools the lifecycle is fully usable;
it is simply not auto-instrumented.

## Per-tool guides

- [Codex CLI](tools/CODEX.md)
- [Gemini CLI](tools/GEMINI_CLI.md)
- [Cursor](tools/CURSOR.md)
- [Windsurf](tools/WINDSURF.md)
- [Aider](tools/AIDER.md)
