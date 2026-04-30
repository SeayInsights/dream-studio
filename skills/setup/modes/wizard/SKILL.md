---
name: wizard
description: "Interactive install wizard — detects all 6 registered tools, shows what each missing tool unlocks, prompts the user per tool (install / skip), runs the platform-appropriate install command, verifies post-install, and saves final states to setup-prefs.json"
pack: setup
---

# Wizard Mode

## Imports
- core/setup.md — tool detection, preference persistence (detectTool, savePreference, loadPreference)

## Before you start

1. Read `skills/setup/tool-registry.yml` completely — this is the SSOT for all tool metadata including install commands, detect commands, and what each tool unlocks.
2. Identify the current platform (Windows / Mac / Linux) so you run the correct detect and install commands.
3. Load `.dream-studio/setup-prefs.json` via `loadPreference()` if it exists — use as initial state, but always live-detect to get current truth before prompting.

## Process

### Step 1 — Detect platform

Determine OS from environment context:
- Windows → use `where <tool>` commands
- Mac/Linux → use `which <tool>` commands

Refer to each tool's `detect_command` in `tool-registry.yml` for the exact command per platform.

### Step 2 — Detect all 6 tools

Run `detectTool(toolName)` for each of the 6 tools in `tool-registry.yml` (gh, firecrawl, playwright, npm, python, node):

1. Run the platform-appropriate detect command (e.g., `where gh` on Windows).
2. If the command succeeds (exit code 0), the tool is present — also run the `version_command` to capture the version string.
3. If the command fails (exit code non-zero or command not found), mark as `missing`.

**Special cases (from core/setup.md):**
- **Python on Windows:** Run `where py` (Windows Python Launcher), not `where python`.
- **Python on Mac/Linux:** Run `which python3`, not `which python`.
- **Playwright:** If the CLI is found but `playwright list-browsers` fails or returns empty, mark status as `partial` (CLI installed, browsers missing). Run `playwright install` as the repair command in this case.
- **npm/node:** Detect each separately even though node ships with npm.

### Step 3 — Identify tools needing action

After detection, partition the tool list into two groups:

- **Already installed / fully functional:** Status is `installed` — skip these, no prompt needed.
- **Needs action:** Status is `missing` or `partial` — present each to the user one at a time.

If all tools are already `installed`, skip to Step 6 with a fully-installed message.

### Step 4 — Interactive per-tool prompts

For each tool with status `missing` or `partial`, present the following prompt block (one tool at a time):

```
─────────────────────────────────────────
Tool:     <human-readable name from registry>
Status:   missing | partial
Unlocks:  <what_it_unlocks entries, joined with " · ">
Command:  <platform-appropriate install_command from registry>
Docs:     <docs_url from registry>

Install <tool name>? [y / n / skip]
```

**Response handling:**
- `y` (yes) → Proceed to Step 5 (install + verify).
- `n` (no) → Mark as `skipped` in session state. Do not install. Continue to next tool.
- `skip` → Same as `n` — mark `skipped`, continue.
- Any other input → Re-prompt once with: `Please enter y, n, or skip:`. If still invalid, treat as `skip`.

**Partial tools:** For `partial` status (Playwright browsers missing), adjust the prompt text:
```
Status:   partial (CLI installed, browsers missing)
Command:  playwright install
```

### Step 5 — Install and verify

For each tool where the user responded `y`:

#### 5a — Run install command

Run the platform-appropriate `install_command` from `tool-registry.yml`. Stream output to the user so they can see progress.

```
Installing <tool name>...
> <install command>
<live output>
```

If the install command exits with a non-zero code:
- Print: `Install failed for <tool>. Exit code: <N>. <stderr output>`
- Mark tool as `failed` in session state.
- Continue to the next tool — do not abort the wizard.

#### 5b — Verify post-install

After a successful install command (exit code 0), re-run `detectTool(toolName)`:

- If now `installed`: print `<tool name> installed successfully. Version: <version string>`
- If still `missing` or `partial` after install: print `Warning: <tool name> install reported success but tool is still not detected. You may need to restart your terminal.` Mark as `verify_failed` in session state.

### Step 6 — Save state to setup-prefs.json

After all prompts are complete (or if all tools were already installed), call `savePreference()` to write the final state for all 6 tools to `.dream-studio/setup-prefs.json`.

The saved state object must include, for each tool:
```json
{
  "<toolKey>": {
    "status": "installed | missing | partial | skipped | failed | verify_failed",
    "version": "<version string or null>",
    "last_checked": "<ISO 8601 timestamp>"
  }
}
```

Where `<toolKey>` matches the key in `tool-registry.yml` (e.g., `gh`, `firecrawl`, `playwright`, `npm`, `python`, `node`).

**Status assignment rules for saving:**
- Tools that were `installed` at detection time → status `installed`, include version.
- Tools where user responded `y` and install + verify succeeded → status `installed`, include version.
- Tools where user responded `y` but verify failed after install → status `verify_failed`, version `null`.
- Tools where install command itself failed → status `failed`, version `null`.
- Tools where user responded `n` or `skip` → status `skipped`, version `null`.
- Tools that were `partial` at detection and not repaired → status `partial`, version from initial detection.

### Step 7 — Render completion summary

After saving, print a completion summary:

```
─────────────────────────────────────────
Setup Wizard Complete
─────────────────────────────────────────
<N> installed  ·  <N> skipped  ·  <N> failed  ·  <N> verify_failed

Tool            Result
──────────────  ──────────────────────────────
<tool name>     ✓ installed  (v<version>)
<tool name>     ✓ installed  (v<version>)
<tool name>     — skipped
<tool name>     ✗ failed
<tool name>     ⚠ verify_failed — restart terminal and re-run wizard
<tool name>     ✓ installed  (v<version>)

Preferences saved → .dream-studio/setup-prefs.json
─────────────────────────────────────────
```

If any tools ended in `failed` or `verify_failed`, append:
```
Next steps:
- For failed installs: check that the install tool (choco / brew / pip) is available and re-run `dream-studio:setup wizard`.
- For verify_failed: restart your terminal, then run `dream-studio:setup status` to confirm detection.
```

If all tools are installed (no skipped/failed), append:
```
All tools installed. Your dream-studio environment is fully operational.
```

## Output format

- Present prompts and install output as plain text — no markdown tables during the interactive phase.
- Use the completion summary table only at the end (Step 7).
- Do not suppress install command output — stream it so the user sees what is happening.
- All prompts are single-line with a clear `[y / n / skip]` marker.
- The final summary is the only markdown-formatted block.

## Error handling

- If `tool-registry.yml` cannot be read: output `Error: could not read skills/setup/tool-registry.yml — run from the dream-studio project root.` and abort.
- If `savePreference()` fails: print a warning `Warning: could not save setup-prefs.json — <error>`. Do not treat as a fatal error; still print the summary.
- If detection for a single tool throws an unexpected error (not simply "not found"), mark that tool as `missing` and continue — do not abort the full wizard.
- Never skip the save step even if one or more installs failed — always write whatever state is known.
