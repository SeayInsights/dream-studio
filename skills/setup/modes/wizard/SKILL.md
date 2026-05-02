# Wizard Mode

## Imports
- core/setup.md — tool detection, preference persistence (detectTool, savePreference, loadPreference)

## Before you start

1. Read `skills/setup/tool-registry.yml` completely — this is the SSOT for all tool metadata including install commands, detect commands, and what each tool unlocks.
2. Identify the current platform (Windows / Mac / Linux) so you run the correct detect and install commands.
3. Load `.dream-studio/setup-prefs.json` via `loadPreference()` if it exists — use as initial state, but always live-detect to get current truth before prompting.

## Process

1. **Detect platform** (Step 1) — identify Windows/Mac/Linux for platform-specific commands
2. **Create folder structure** (Step 1b) — create builds/, claude_mcp/, shared/ folders with READMEs
3. **Detect tools** (Step 2) — run detection for all 6 tools in tool-registry.yml
4. **Auth checks** (Step 2b) — verify Firecrawl API key and gh CLI auth for installed tools
5. **Check resume state** (Step 2c) — load _wizard_progress to skip already-completed tools
6. **Identify tools needing action** (Step 3) — partition into installed vs. needs-action
7. **Interactive prompts** (Step 4) — present per-tool install prompts one at a time
8. **Install and verify** (Step 5) — run install command, verify, save incremental progress
9. **Save final state** (Step 6) — write complete setup-prefs.json with wizard_interrupted: false
10. **Render summary** (Step 7) — show completion table with installed/skipped/failed counts

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
