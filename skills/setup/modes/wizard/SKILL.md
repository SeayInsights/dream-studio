---
name: wizard
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

### Step 2b — Auth checks for installed tools

After detection, for any tool with status `installed` or `partial`, run the following auth checks **before** prompting for missing tools. These checks are separate from install prompts — they target configuration gaps, not missing binaries.

#### Firecrawl API key check

If Firecrawl's status is `installed` or `partial`:

1. Check whether `FIRECRAWL_API_KEY` is set in the current environment (env var) **or** present in `.env` in the project root.
2. If the key is found and non-empty: skip — no action needed.
3. If the key is **not** found or empty, present:

```
─────────────────────────────────────────
Tool:     Firecrawl
Issue:    installed but no API key found
Action:   Firecrawl needs an API key to function.

Enter key, open browser to sign up, or skip?
  key     → paste your API key now
  browser → open https://firecrawl.dev in your browser to sign up / get a key
  skip    → mark as partial and continue

Choice: [key / browser / skip]
```

**Response handling:**
- `key` → Prompt: `Paste your Firecrawl API key:`. Read the input. Write `FIRECRAWL_API_KEY=<value>` to `.env` (append if file exists, create if not). Print `API key saved to .env`. Update Firecrawl's session state status to `installed`.
- `browser` → Open `https://firecrawl.dev` in the system default browser (use `start https://firecrawl.dev` on Windows, `open https://firecrawl.dev` on Mac, `xdg-open https://firecrawl.dev` on Linux). Print `Browser opened. After you get your key, re-run the wizard or set FIRECRAWL_API_KEY=<key> in your .env.` Mark Firecrawl status as `partial` with note `auth_pending`.
- `skip` → Mark Firecrawl status as `partial` with note `no_api_key`. Continue.
- Any other input → Re-prompt once with `Please enter key, browser, or skip:`. If still invalid, treat as `skip`.

#### gh CLI auth check

If `gh` status is `installed`:

1. Run `gh auth status` (exit code 0 = authenticated, non-zero = not authenticated).
2. If authenticated: skip — no action needed.
3. If **not** authenticated, present:

```
─────────────────────────────────────────
Tool:     gh (GitHub CLI)
Issue:    installed but not authenticated
Action:   gh needs to be authenticated to manage PRs and issues.

Run gh auth login now? [y / n]
```

**Response handling:**
- `y` → Run `gh auth login` and stream output to the user. After completion, re-run `gh auth status` to verify. If now authenticated: print `gh authenticated successfully.` Update `gh` session status to `installed`. If still not authenticated: print `Warning: gh auth login completed but auth status still shows unauthenticated.` Mark `gh` as `verify_failed`.
- `n` → Mark `gh` as `skipped_auth`. Print `Skipping gh auth — you can run gh auth login later.`
- Any other input → Re-prompt once. If still invalid, treat as `n`.

### Step 2c — Check for partial wizard progress (resume logic)

Before Step 3, load `.dream-studio/setup-prefs.json` via `loadPreference()` and check for a `_wizard_progress` key:

```json
{
  "_wizard_progress": {
    "completed_tools": ["gh", "npm"],
    "wizard_started_at": "<ISO 8601 timestamp>",
    "wizard_interrupted": true
  }
}
```

- If `_wizard_progress.wizard_interrupted` is `true`, the previous wizard run was cancelled mid-flight.
- Count the tools listed in `completed_tools` — these have already been processed (installed, skipped, or failed) and must not be re-prompted.
- Display a resume banner before Step 3:

```
─────────────────────────────────────────
Resuming wizard — <N> of 6 tools already configured
─────────────────────────────────────────
```

Where `<N>` = the number of entries in `completed_tools`.

- If `_wizard_progress` is absent or `wizard_interrupted` is `false`, this is a fresh run — no banner, no tools to skip.

### Step 3 — Identify tools needing action

After detection (and after applying resume logic from Step 2c), partition the tool list into two groups:

- **Already installed / fully functional:** Status is `installed` — skip these, no prompt needed.
- **Already completed in a prior interrupted run:** Tool key is listed in `_wizard_progress.completed_tools` — skip these, no prompt needed (their saved state is already in `setup-prefs.json`).
- **Needs action:** Status is `missing` or `partial` AND not in `completed_tools` — present each to the user one at a time.

If all tools are already `installed` or `completed`, skip to Step 6 with a fully-installed message.

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

#### 5c — Save incremental progress after each tool

Immediately after each tool's outcome is determined (installed, skipped, failed, or verify_failed), call `savePreference()` with a partial state object that includes:

1. The current tool's final state entry (same format as Step 6).
2. An updated `_wizard_progress` block:

```json
{
  "_wizard_progress": {
    "completed_tools": ["<all tool keys processed so far>"],
    "wizard_started_at": "<ISO 8601 timestamp from when this wizard run began>",
    "wizard_interrupted": true
  }
}
```

This write happens synchronously before presenting the next tool's prompt. `wizard_interrupted` stays `true` throughout the active run — it is only set to `false` in the final save (Step 6).

**Cancellation handling:** If the user sends Ctrl+C, closes the terminal, or the session is otherwise interrupted after this point, the partial state on disk is valid. The next wizard run will read `_wizard_progress`, show the resume banner, and skip all `completed_tools`.

### Step 6 — Save state to setup-prefs.json

After all prompts are complete (or if all tools were already installed), call `savePreference()` to write the final state for all 6 tools to `.dream-studio/setup-prefs.json`. This is the completion save — it merges any partial state written during Step 5c with the remaining tools and marks the wizard run as complete.

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

In addition, include a `_wizard_progress` block with `wizard_interrupted: false` to signal that this run completed cleanly:

```json
{
  "_wizard_progress": {
    "completed_tools": ["gh", "firecrawl", "playwright", "npm", "python", "node"],
    "wizard_started_at": "<ISO 8601 timestamp>",
    "wizard_interrupted": false
  }
}
```

Setting `wizard_interrupted: false` ensures the next wizard run treats this as a fresh start rather than a resume.

**Status assignment rules for saving:**
- Tools that were `installed` at detection time → status `installed`, include version.
- Tools where user responded `y` and install + verify succeeded → status `installed`, include version.
- Tools where user responded `y` but verify failed after install → status `verify_failed`, version `null`.
- Tools where install command itself failed → status `failed`, version `null`.
- Tools where user responded `n` or `skip` → status `skipped`, version `null`.
- Tools that were `partial` at detection and not repaired → status `partial`, version from initial detection.
- Firecrawl with API key saved successfully → status `installed`, include `api_key_source: ".env"`.
- Firecrawl where user chose `browser` → status `partial`, include `auth_note: "auth_pending"`.
- Firecrawl where user chose `skip` on auth → status `partial`, include `auth_note: "no_api_key"`.
- `gh` where user skipped auth → status `skipped_auth`, version from initial detection.

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

## Cancellation and resume behaviour

- **Graceful cancel (Ctrl+C or mid-session exit):** Because Step 5c writes progress after every tool, partial work is never lost. The last incremental save captures all tools processed before the interrupt. `wizard_interrupted` remains `true` on disk, signalling that the next run should resume.
- **Re-run after cancel:** On next invocation, Step 2c reads `_wizard_progress`, identifies already-completed tools, and skips them entirely — including skipping their live-detection prompts. The resume banner tells the user exactly how many tools were already handled.
- **Full re-run (user wants to start over):** If the user explicitly asks to start the wizard from scratch, delete or ignore `_wizard_progress` by passing a `--reset` intent. When reset is requested, set `completed_tools: []` and `wizard_interrupted: false` before Step 2 and proceed as a fresh run.
- **Idempotent installs:** If a tool in `completed_tools` was recorded as `skipped` or `failed` and the user wants to retry it, they should run `dream-studio:setup wizard` with `--reset` or use `dream-studio:setup status` to manually re-trigger a single tool. The standard resume flow does not re-prompt completed tools regardless of their prior outcome.
