---
name: wizard
model_tier: haiku
description: "Interactive install wizard — detects all 6 registered tools, shows what each missing tool unlocks, prompts the user per tool (install / skip), runs the platform-appropriate install command, verifies post-install, and saves final states to setup-prefs.json"
pack: setup
chain_suggests: []
---

# Wizard Mode

## Imports
- core/setup.md — tool detection, preference persistence (detectTool, savePreference, loadPreference)

## Before you start

1. Read `skills/setup/tool-registry.yml` completely — this is the SSOT for all tool metadata including install commands, detect commands, and what each tool unlocks.
2. Identify the current platform (Windows / Mac / Linux) so you run the correct detect and install commands.
3. Load `.dream-studio/setup-prefs.json` via `loadPreference()` if it exists — use as initial state, but always live-detect to get current truth before prompting.

## Process

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
