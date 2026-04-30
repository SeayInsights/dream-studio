---
name: jit
description: "Just-in-time tool prompt — called by other skills when a missing tool is detected mid-workflow. Checks whether the user has already chosen 'never' for this tool, displays a single targeted install prompt if not, saves the choice to setup-prefs.json, and returns whether the tool is now available"
pack: setup
chain_suggests: []
---

# JIT Mode (Just-in-Time Prompt)

## Imports
- core/setup.md — tool detection, preference persistence (detectTool, savePreference, loadPreference)

## When this mode is used

JIT mode is invoked by OTHER skills (e.g., dream-studio:core, dream-studio:domains) when they detect that a specific tool is absent at runtime. It is NOT called directly by the user — it fires inline during a workflow without requiring the full wizard.

Users who selected `as-needed` during onboarding (i.e., `onboarding_path: "as-needed"` in setup-prefs.json) will encounter JIT prompts as tools become relevant to their current task.

## Entry point

`promptForTool(toolName)` — called with the tool key (e.g., `"playwright"`, `"gh"`, `"firecrawl"`).

Returns: `{ available: boolean, status: "installed" | "skipped" | "never" | "failed" | "verify_failed" }`

---

## Process

### Step 1 — Load preferences

Call `loadPreference()` to read `.dream-studio/setup-prefs.json`.

- If the file does not exist: treat all `never_prompt` fields as `false` and all `installed` fields as `false`.
- If the file exists but the tool key is absent: treat as not-yet-prompted (default state).

### Step 2 — Check never_prompt flag

Look up `tools.<toolName>.never_prompt` in the loaded preferences.

- If `never_prompt` is `true`: **stop immediately**. Do not display any prompt. Return `{ available: false, status: "never" }`.
- If `never_prompt` is `false` (or field is absent): continue to Step 3.

### Step 3 — Check if already installed

Call `detectTool(toolName)` using the platform-appropriate detect command from `tool-registry.yml`.

- Windows: `where <tool>`
- Mac/Linux: `which <tool>`

**Special cases (same as wizard/status modes):**
- Python on Windows: `where py`
- Python on Mac/Linux: `which python3`
- Playwright: if CLI found but `playwright list-browsers` fails or returns empty → status `partial`

If detection result is `installed`:
- Update `tools.<toolName>.installed = true` in preferences via `savePreference()`.
- Return `{ available: true, status: "installed" }` without showing any prompt.

### Step 4 — Display JIT prompt

For tools with status `missing` or `partial`, display a compact single-line prompt. Load the tool's metadata from `tool-registry.yml` to fill in `<human-readable name>` and `<install_command>`.

```
─────────────────────────────────────────
This skill works better with <human-readable tool name>.
Unlocks: <what_it_unlocks entries joined with " · ">

Install now? [y / n / never]
  y      → install <tool> now
  n      → skip for this session
  never  → don't ask again for this tool
─────────────────────────────────────────
```

For `partial` status (Playwright browsers missing), adjust the first line:
```
This skill works better with Playwright (browsers missing).
```

Wait for user input. Valid responses: `y`, `n`, `never`.

- Any other input → Re-prompt once with: `Please enter y, n, or never:`. If still invalid, treat as `n`.

### Step 5 — Handle response

#### Response: `n`

- Do not install.
- Do NOT set `never_prompt`.
- Call `savePreference()` to record `tools.<toolName>.skipped = true` in setup-prefs.json (for session tracking only — does not suppress future prompts).
- Return `{ available: false, status: "skipped" }`.

#### Response: `never`

- Do not install.
- Call `savePreference()` to set `tools.<toolName>.never_prompt = true` in setup-prefs.json.
- Print: `Got it. You won't be prompted for <tool name> again.`
- Return `{ available: false, status: "never" }`.

#### Response: `y`

Proceed to Step 6.

### Step 6 — Install and verify (response was `y`)

#### 6a — Run install command

Run the platform-appropriate `install_command` from `tool-registry.yml`. Stream output to the user.

```
Installing <tool name>...
> <install command>
<live output>
```

If the install command exits with a non-zero code:
- Print: `Install failed for <tool name>. Exit code: <N>.`
- Call `savePreference()` to record `tools.<toolName>.installed = false` and add `last_install_failed: true`.
- Return `{ available: false, status: "failed" }`.

#### 6b — Verify post-install

After a successful exit code, re-run `detectTool(toolName)`:

- If now `installed`:
  - Print: `<tool name> installed successfully. Continuing...`
  - Call `savePreference()` to set `tools.<toolName>.installed = true`, `version: <version string>`, `last_checked: <ISO 8601 timestamp>`.
  - Return `{ available: true, status: "installed" }`.

- If still `missing` or `partial` after install:
  - Print: `Warning: <tool name> install reported success but tool is still not detected. You may need to restart your terminal.`
  - Call `savePreference()` to record `tools.<toolName>.installed = false` and `last_install_failed: true`.
  - Return `{ available: false, status: "verify_failed" }`.

---

## Preference schema (tools.<toolName> fields written by JIT)

```json
{
  "installed": true | false,
  "version": "<version string or null>",
  "last_checked": "<ISO 8601 timestamp or null>",
  "skipped": true | false,
  "never_prompt": true | false,
  "last_install_failed": true | false
}
```

Only fields that change are written — do not overwrite fields managed by other modes (wizard, status).

---

## Calling convention for other skills

When a skill detects a missing tool, invoke JIT mode inline before aborting:

```
result = promptForTool("<toolKey>")
if result.available:
    # continue with the tool
else:
    # gracefully degrade or note the limitation
```

The calling skill decides what to do with `result.available`. JIT does not abort the parent workflow — it returns the availability decision and lets the caller handle it.

---

## Output format

- Prompt block is plain text — no markdown tables or headers.
- Install output is streamed verbatim.
- Confirmation lines (`Got it. You won't be prompted...`, `installed successfully`) are plain text.
- JIT mode produces minimal output — it should feel like an inline nudge, not a full wizard.
- After returning, the calling skill resumes its own output style.

---

## Error handling

- If `tool-registry.yml` cannot be read: print `Error: could not read skills/setup/tool-registry.yml.` and return `{ available: false, status: "failed" }`.
- If `toolName` is not found in `tool-registry.yml`: print `Warning: unknown tool "<toolName>" — skipping JIT prompt.` and return `{ available: false, status: "skipped" }`.
- If `savePreference()` fails: print `Warning: could not save setup-prefs.json — <error>.` Continue — do not treat as fatal. The in-memory state is still valid for the current session.
- Never throw or abort the parent skill's workflow — always return a result object.
