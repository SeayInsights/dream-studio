# Setup — First-Run Experience & Tool Management

## Mode dispatch

0. **Progressive disclosure check:** Before dispatching to a mode, check if it's available by running:
   ```python
   py "../../hooks/lib/skill_calibration.py" check-mode setup <mode> "<user-message>"
   ```
   If exit code is non-zero, the mode is locked. Show the unlock message (from stdout) and stop.
   If exit code is zero, continue to step 1. If unlock notifications are printed, show them to the user.

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

---

## Mode: wizard

**Trigger:** `dream-studio:setup wizard` | keywords: `setup:`, `wizard:`, `install tools:`, `full setup:`

**What it does:**
Runs a full interactive setup session. Detects all tools defined in `tool-registry.yml`, maps each to the capabilities it unlocks, shows a summary table, and offers guided installation for anything missing.

**Behavior steps:**
1. Run `isFirstRun()` — if false, confirm the user wants to re-run setup.
2. Detect all tools in the registry (gh, firecrawl, playwright, npm, node, python).
3. Display a capability table: tool name | status (installed/missing) | what it unlocks.
4. Prompt: "Would you like to install missing tools now?" (guided path) or "Skip for now" (deferred path).
5. For each tool the user elects to install, show the install command and confirm before running.
6. After installation, re-detect and confirm success.
7. Write final tool states to `.dream-studio/setup-prefs.json` with `onboarding_path: wizard`.
8. Confirm setup complete and list any tools still missing with fallback notes.

**Capability map (what each tool unlocks):**
| Tool | Unlocks |
|---|---|
| gh CLI | GitHub issue/PR workflow, branch automation |
| firecrawl | Deep web research, site crawl |
| playwright | Browser automation, DAST scanning, screenshots |
| npm / node | SaaS builds, MCP server development |
| python | Power BI scripting, data analysis, career PDF generation |

**Example invocations:**
- `setup:` — infer wizard mode on first run
- `wizard:` — explicit wizard trigger
- `install tools:` — jump straight to guided installation
- `full setup:` — synonym for wizard

---

## Mode: status

**Trigger:** `dream-studio:setup status` | keywords: `status:`, `setup status:`, `which tools:`

**What it does:**
Reads current tool states from `.dream-studio/setup-prefs.json` and live-detects each tool. Displays a concise table of what is installed, what is missing, and what each tool unlocks. No installation is performed.

**Behavior steps:**
1. Load persisted states from `.dream-studio/setup-prefs.json` (if it exists).
2. For each tool in `tool-registry.yml`, run `getToolStatus()` to get a live reading.
3. Render a status table: tool name | status | version (if detected) | what it unlocks.
4. If any tools are missing, append: "Run `dream-studio:setup wizard` to install missing tools."
5. Do not write any files or make any changes.

**Example invocations:**
- `status:` — show current tool state
- `setup status:` — explicit status trigger
- `which tools do I have?` — natural language trigger
- `what's installed?` — natural language trigger

---

## Mode: jit

**Trigger:** `dream-studio:setup jit` | keywords: `jit:`, `just-in-time:`, `as-needed:`

**What it does:**
Just-in-time prompting for a single missing tool. Called internally by other skills when they detect a required tool is absent. Asks the user whether to install now, skip once, or never prompt again. Not typically invoked directly by users.

**Behavior steps:**
1. Receive the tool name from the calling skill (e.g., `jit: firecrawl`).
2. Check `setup-prefs.json` for a `never_prompt` flag on that tool — if set, return `skipped` silently.
3. If not suppressed, display a one-line prompt: "Tool `<name>` is required for this action but is not installed. Install now? (yes / skip / never ask again)"
4. On `yes`: run the install command for that tool, re-detect, update `setup-prefs.json`, return `installed`.
5. On `skip`: return `skipped` — the calling skill proceeds with fallback behavior.
6. On `never`: write `never_prompt: true` for that tool in `setup-prefs.json`, return `skipped`.

**Example invocations (internal):**
- `jit: firecrawl` — called by `dream-studio:core` web research when Firecrawl is missing
- `jit: playwright` — called by `dream-studio:security` DAST when Playwright is missing
- `jit: gh` — called by any skill needing the GitHub CLI

**Direct user invocations (rare):**
- `jit:` — user can invoke directly to prompt for a specific tool by name

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
  return promptForSetupPath();  // runs wizard or deferred path
}
```

### JIT prompt for a missing tool

When a skill needs a specific tool and it is not installed, call `promptForSetupPath()` with the tool name:

```
const status = getToolStatus("firecrawl");
if (status !== "installed") {
  const result = await Skill("dream-studio:setup", "jit: firecrawl");
  if (result === "skipped") {
    // fall back to scraper-mcp or WebSearch
  }
}
```

### Detection helpers (from `skills/core/setup.md`)

| Function | Returns | Description |
|---|---|---|
| `isFirstRun()` | `boolean` | True if `setup-prefs.json` does not exist or `onboarding_path` is unset |
| `getToolStatus(name)` | `"installed" \| "missing"` | Live detection for the named tool |
| `shouldPromptForTool(name)` | `boolean` | False if `never_prompt` is set for that tool |
| `promptForSetupPath()` | `"wizard" \| "deferred"` | Shows the wizard/defer choice; returns user's selection |

---

## First-run behavior

When any dream-studio skill runs and `isFirstRun()` returns `true`:

1. The skill pauses before executing its main logic.
2. The user sees: "It looks like this is your first time. Would you like a quick setup to unlock all features? (yes — run wizard / no — continue without setup)"
3. On `yes`: `dream-studio:setup wizard` runs to completion, then the original skill resumes.
4. On `no`: `onboarding_path: deferred` is written to `setup-prefs.json` and the skill proceeds. JIT prompts may still fire for missing tools unless suppressed.
5. Once `setup-prefs.json` exists with any `onboarding_path` value, `isFirstRun()` returns `false` and the first-run prompt never fires again.
