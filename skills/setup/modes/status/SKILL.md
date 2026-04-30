---
name: status
description: "Live tool detection across all 6 registered tools — outputs a formatted table with install status, version, what each tool unlocks, and the install command for anything missing"
pack: setup
---

# Status Mode

## Imports
- core/setup.md — tool detection & setup preferences

## Before you start

1. Read `skills/setup/tool-registry.yml` completely — this is the SSOT for all tool metadata.
2. Identify the current platform (Windows / Mac / Linux) so you run the correct detection command.
3. Check whether `.dream-studio/setup-prefs.json` exists — load it if present, but do not rely on cached states; always live-detect.

## Process

### Step 1 — Detect platform

Determine OS from environment context:
- Windows → use `where <tool>` commands
- Mac/Linux → use `which <tool>` commands

Refer to each tool's `detect_command` in `tool-registry.yml` for the exact command per platform.

### Step 2 — Run detectTool() for each of the 6 tools

For every tool in `tool-registry.yml` (gh, firecrawl, playwright, npm, python, node), call `detectTool(toolName)` from `core/setup.md`:

1. Run the platform-appropriate detect command (e.g., `where gh` on Windows).
2. If the command succeeds (exit code 0), the tool is present — also run the `version_command` to capture the version string.
3. If the command fails (exit code non-zero or command not found), mark as missing.

**Special cases (from core/setup.md):**
- **Python on Windows:** Run `where py` (Windows Python Launcher), not `where python`.
- **Python on Mac/Linux:** Run `which python3`, not `which python`.
- **Playwright:** If the CLI is found but `playwright list-browsers` fails or returns empty, mark status as `partial` (CLI installed, browsers missing). Otherwise `installed`.
- **npm/node:** Treat these as independent tools even though node ships with npm. Detect each separately.

### Step 3 — Map status for each tool

Use `getToolStatus(toolName)` semantics (from `core/setup.md`):

| Return value | Meaning |
|---|---|
| `installed` | Tool detected and fully functional |
| `missing` | Tool not found on system |
| `partial` | Tool found but dependencies absent (playwright only) |

### Step 4 — Render the status table

Output a markdown table with these columns:

| Tool | Status | Version | What It Unlocks | Install Command |
|---|---|---|---|---|

**Column rules:**
- **Tool**: Use the human-readable `name` from `tool-registry.yml` (e.g., "GitHub CLI", not "gh").
- **Status**: Show `installed`, `missing`, or `partial` — use visual indicators: `installed` → checkmark symbol, `missing` → X symbol, `partial` → warning symbol.
- **Version**: Show detected version string if installed; show `—` if missing.
- **What It Unlocks**: List the `what_it_unlocks` entries from `tool-registry.yml`, joined with ` · ` separator. Abbreviate long lists to the first 2–3 entries if more than 3 exist, then add `+ N more`.
- **Install Command**: Show the platform-appropriate `install_command` from `tool-registry.yml` if missing or partial; show `—` if already installed.

**Example output (Windows, mixed state):**

```
Tool               | Status      | Version     | What It Unlocks                                              | Install Command
GitHub CLI         | ✓ installed | gh version 2.45.0 | dream-studio:core · dream-studio:domains             | —
Firecrawl          | ✗ missing   | —           | dream-studio:core · dream-studio:domains · dream-studio:security | pip install firecrawl-py
Playwright         | ⚠ partial   | 1.42.0      | dream-studio:quality · dream-studio:security                 | playwright install
Node Package Manager | ✓ installed | 10.2.4    | dream-studio:domains · dream-studio:workflow                 | —
Python             | ✓ installed | Python 3.12.0 | dream-studio:core · dream-studio:quality + 2 more          | —
Node.js            | ✓ installed | v20.11.0    | dream-studio:domains · dream-studio:workflow                 | —
```

### Step 5 — Append summary and next step

After the table:

1. Count installed, partial, and missing tools.
2. Print a one-line summary: e.g., `4 installed · 1 partial · 1 missing`
3. If any tools are `missing` or `partial`, append:
   > Run `dream-studio:setup wizard` to install or repair missing tools.
4. If all tools are `installed`, append:
   > All tools are installed. Your dream-studio environment is fully operational.

## Output format

- Render as a clean markdown table (pipe-delimited, header row, separator row).
- Do not use HTML or JSON output — plaintext markdown only.
- Do not write any files, modify preferences, or run any install commands.
- Do not prompt the user for input; this mode is read-only and non-interactive.
- Output the table immediately — no preamble paragraph before the table.
- After the table, print the summary line and conditional next-step message.

## Error handling

- If `tool-registry.yml` cannot be read, output: `Error: could not read skills/setup/tool-registry.yml — run from the dream-studio project root.`
- If detection for a single tool throws an unexpected error (not simply "not found"), mark that tool as `missing` and append a footnote: `* Detection error for <tool>: <error message>`
- Never abort the full table because one tool fails to detect — continue to the next tool.
