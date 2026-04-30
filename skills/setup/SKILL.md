---
name: setup
description: "First-run setup and tool management: wizard, status, jit (just-in-time prompts)"
argument-hint: "wizard | status | jit"
user_invocable: true
args: mode
---

# Setup — First-Run Experience & Tool Management

## Mode dispatch

1. Parse the mode from the argument (first word).
2. If no mode given, infer from the user's message using the keyword table below.
3. If still ambiguous, list available modes and ask.
4. Read `modes/<mode>/SKILL.md` completely.
5. If `modes/<mode>/gotchas.yml` exists, read it before executing.
6. Follow the mode's instructions exactly as written.

| Mode | File | Keywords |
|---|---|---|
| wizard | modes/wizard/SKILL.md | setup:, wizard:, install tools:, full setup: |
| status | modes/status/SKILL.md | status:, setup status:, which tools: |
| jit | modes/jit/SKILL.md | jit:, just-in-time:, as-needed: |

## Shared resources

Setup-specific modules:
- `tool-registry.yml` — metadata for all detectable tools (gh, firecrawl, playwright, npm, python, node)
- `skill.ts` — implementation of first-run detection, preference management, tool detection
- `.dream-studio/setup-prefs.json` — user preferences (onboarding_path, tool states, never_prompt flags)

Core shared modules available to all modes:
- `skills/core/setup.md` — tool detection functions (detectTool, getToolStatus, shouldPromptForTool)
- `skills/core/web.md` — web access fallbacks (Firecrawl → scraper-mcp → WebSearch)
- `skills/core/git.md` — gh CLI detection and GitHub API fallback
