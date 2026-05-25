# adapter-projections/

This directory holds **generated adapter projection artifacts** — one file per AI adapter Dream Studio supports. Each file is the active context surface that adapter reads when running against a Dream Studio install.

| Adapter | File | Read by |
|---|---|---|
| Claude Code | `claude/CLAUDE.md` | `integrations/compiler/claude_code.py` |
| Codex (OpenAI models) | `codex/AGENTS.md` | adapter-specific compilers (when implemented) |
| ChatGPT | `chatgpt/context_packet.md` | adapter-specific compilers |
| GitHub Copilot | `copilot/instructions.md` | adapter-specific compilers |
| Cursor | `cursor/rules` | adapter-specific compilers |
| Local model | `local-model/context_packet.md` | adapter-specific compilers |
| MCP | `mcp/server-policy.json` | MCP integration layer |
| Shell | `shell/command-policy.json` | shell adapter |

**This directory is NOT deprecated.** A prior `_SUPERSEDED.md` claimed the directory was scheduled for deletion in Slice 3, but the original projection model was superseded by `integrations/` + `emitters/` while the directory itself was repurposed as the output target for the replacement model. The compiler reads from here; the workspace hygiene module (`core/release/adapter_workspace_hygiene.py`) classifies these files as `generated_adapter_projection` and marks them `repo_tracked: True`.

To regenerate any of these files, re-run the installer (`ds integrate install claude_code --execute` for the Claude variant).
