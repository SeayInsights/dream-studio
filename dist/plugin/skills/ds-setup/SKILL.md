---
name: ds-setup
description: 'Platform setup — interactive wizard, status reporting, and JIT tool installation. Use for: wizard:, status:, jit:'
---

# Setup — First-Run Experience & Tool Management

## Output Contract

`wizard`: a capability table (tool/status/what it unlocks) plus guided-install results,
written to `.dream-studio/setup-prefs.json`. `status`: a read-only capability/status table,
no writes. `jit`: an install/skip/never-ask-again result for one named tool, written to the
same prefs file.

## Mode dispatch

0. **Progressive disclosure check:** Before dispatching to a mode, apply the portable skill contract. If a current calibration interface is available in this checkout, use it; otherwise rely on the mode table below. If a mode is locked, show the unlock message and stop.

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
- `tool-registry.yml` — metadata for all detectable tools; read it at run time for the current list rather than hardcoding one here
- `skill.ts` — implementation of first-run detection, preference management, tool detection
- `.dream-studio/setup-prefs.json` — user preferences (onboarding_path, tool states, never_prompt flags)

Core shared modules available to all modes:
- `setup.md` in the ds-core pack — tool detection functions (detectTool, getToolStatus, shouldPromptForTool)
- `web.md` in the ds-core pack — web access fallbacks (Firecrawl → scraper-mcp → WebSearch)
- `git.md` in the ds-core pack — gh CLI detection and GitHub API fallback

---

## Examples

| User says | Mode inferred | Action |
|---|---|---|
| `setup:` (first run) | wizard | Full guided setup |
| `setup:` (already run) | wizard | Confirm and re-run |
| `wizard:` | wizard | Full guided setup |
| `which tools do I have?` | status | Show tool table, no changes |
| `setup status:` | status | Show tool table, no changes |
| `install firecrawl` | wizard | Guided single-tool install |
| `jit: playwright` | jit | One-tool prompt (usually called internally) |

---

## Integration — how other skills call setup

### First-run check at skill entry

Every skill should call `isFirstRun()` at the start of its execution flow. If it returns `true`, pause and call the setup wizard before proceeding.

```
// At the top of any skill's entry logic:
if (isFirstRun()) {
  return promptForSetupPath();  // returns "wizard" | "as-needed" | "read-docs"
}
```

### JIT prompt for a missing tool

When a skill needs a specific tool and it is not installed, call `promptForSetupPath()` with the tool name:

```
const status = getToolStatus("firecrawl");
if (status !== "installed") {
  const result = await Skill("ds-setup", "jit: firecrawl");
  if (result === "skipped") {
    // fall back to scraper-mcp or WebSearch
  }
}
```

### Detection helpers (from `setup.md` in the ds-core pack)

| Function | Returns | Description |
|---|---|---|
| `isFirstRun()` | `boolean` | True if `setup-prefs.json` does not exist or `onboarding_path` is unset |
| `getToolStatus(name)` | `"installed" \| "missing"` | Live detection for the named tool |
| `shouldPromptForTool(name)` | `boolean` | False if `never_prompt` is set for that tool |
| `promptForSetupPath()` | `"wizard" \| "as-needed" \| "read-docs"` | Shows the three-way onboarding choice; returns the user's selection |

---

## First-run behavior

When any dream-studio skill runs and `isFirstRun()` returns `true`:

1. The skill pauses before executing its main logic.
2. The user sees the real three-way choice `promptForSetupPath()` shows: `[1] wizard` (full guided setup now), `[2] as-needed` (no setup now, JIT-prompt when a skill needs a missing tool), `[3] read-docs` (never prompt — the user will read the README and install manually).
3. On `wizard`: `ds-setup wizard` runs to completion, then the original skill resumes.
4. On `as-needed`: `onboarding_path: "as-needed"` is written to `setup-prefs.json` and the skill proceeds. JIT prompts still fire for missing tools unless a specific tool has `never_prompt` set.
5. On `read-docs`: `onboarding_path: "read-docs"` is written and no further prompts — JIT or first-run — ever fire.
6. Once `setup-prefs.json` exists with any `onboarding_path` value, `isFirstRun()` returns `false` and the first-run prompt never fires again.
