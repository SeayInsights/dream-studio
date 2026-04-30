# Tool Detection & Setup — Core Module

Reusable tool detection patterns used across dream-studio skills for cross-platform compatibility.

## Usage

When a skill needs tool detection, reference this module in the skill's SKILL.md with:
```
## Imports
- core/setup.md — tool detection & setup preferences
```

## Functions

### detectTool(toolName)

Cross-platform detection to check if a command-line tool is installed.

**Parameters:**
- `toolName` (string) — name of the tool to detect (gh, firecrawl, playwright, npm, python, node)

**Returns:**
```typescript
{
  installed: boolean,
  version: string | null,
  path: string | null
}
```

**Platform differences:**

| Platform | Detection command |
|----------|------------------|
| Windows  | `where <toolName>` |
| Mac      | `which <toolName>` |
| Linux    | `which <toolName>` |

**Example:**
```bash
# Windows detection
where gh
# Output: C:\Program Files\GitHub CLI\gh.exe (if installed)
# Exit code: 0 if found, 1 if not found

# Mac/Linux detection
which gh
# Output: /usr/local/bin/gh (if installed)
# Exit code: 0 if found, 1 if not found
```

**Implementation pattern:**
```typescript
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);
const isWindows = process.platform === "win32";
const detectCommand = isWindows ? "where" : "which";

try {
  const { stdout } = await execAsync(`${detectCommand} ${toolName}`);
  const toolPath = stdout.trim().split('\n')[0]; // First line
  
  // Get version if available
  const { stdout: versionOutput } = await execAsync(`${toolName} --version`);
  const version = versionOutput.trim();
  
  return { installed: true, version, path: toolPath };
} catch {
  return { installed: false, version: null, path: null };
}
```

**Special cases:**

For tools with non-standard detection:
- **Python (Windows):** Use `where py` instead of `where python` (Windows Python Launcher)
- **Python (Unix):** Use `which python3` instead of `which python` (avoid Python 2)
- **npm/node:** Check both are installed (npm often bundled with node)

See `skills/setup/tool-registry.yml` for full command matrix per tool.

---

### getToolStatus(toolName)

Returns human-readable status: `installed`, `missing`, or `partial`.

**Parameters:**
- `toolName` (string) — name of the tool to check

**Returns:**
- `"installed"` — tool detected and fully functional
- `"missing"` — tool not found on system
- `"partial"` — tool found but missing dependencies (e.g., playwright without browsers)

**Implementation pattern:**
```typescript
const status = await detectTool(toolName);

if (!status.installed) {
  return "missing";
}

// Check for partial installations (tool-specific logic)
if (toolName === "playwright") {
  // Check if browsers are installed
  try {
    await execAsync("playwright list-browsers");
    return "installed";
  } catch {
    return "partial"; // CLI found but browsers not installed
  }
}

return "installed";
```

**Usage in skills:**
```typescript
const ghStatus = await getToolStatus("gh");

if (ghStatus === "missing") {
  // Prompt for installation or use fallback
} else if (ghStatus === "partial") {
  // Attempt to complete installation
} else {
  // Proceed with tool
}
```

---

### shouldPromptForTool(toolName)

Checks user preferences to determine if we should prompt for tool installation.

**Parameters:**
- `toolName` (string) — name of the tool

**Returns:**
- `true` — should prompt the user (tool missing + user hasn't opted out)
- `false` — skip prompt (tool installed OR user chose "never_prompt" OR "read-docs" onboarding path)

**Preference integration:**

Reads from `.dream-studio/setup-prefs.json`:
```json
{
  "onboarding_path": "wizard" | "as-needed" | "read-docs",
  "first_run_complete": true,
  "tools": {
    "gh": {
      "installed": true,
      "version": "2.40.0",
      "path": "/usr/local/bin/gh",
      "never_prompt": false
    },
    "firecrawl": {
      "installed": false,
      "skipped": true,
      "never_prompt": true
    }
  }
}
```

**Logic:**
1. Load preferences via `loadPreference()` (from `skills/setup/skill.ts`)
2. If `onboarding_path === "read-docs"` → never prompt (user wants full control)
3. If `tools[toolName].never_prompt === true` → skip prompt (user dismissed)
4. If `tools[toolName].installed === true` → skip prompt (already installed)
5. Otherwise → prompt if `onboarding_path === "wizard"` or `"as-needed"`

**Implementation pattern:**
```typescript
import { loadPreference } from "../setup/skill.ts";

const prefs = await loadPreference();

// No preferences file → first run, should prompt
if (!prefs) {
  return true;
}

// User chose read-docs path → never prompt
if (prefs.onboarding_path === "read-docs") {
  return false;
}

// Check tool-specific preferences
const toolPrefs = prefs.tools?.[toolName];

// User explicitly opted out
if (toolPrefs?.never_prompt) {
  return false;
}

// Tool already installed
if (toolPrefs?.installed) {
  return false;
}

// Default: prompt for wizard/as-needed paths
return true;
```

**Usage in skills:**
```typescript
const status = await getToolStatus("gh");

if (status === "missing" && await shouldPromptForTool("gh")) {
  console.log("GitHub CLI (gh) is required for this operation.");
  console.log("Install: https://cli.github.com/manual/installation");
  console.log("Or run `dream-studio:setup wizard` for guided installation.");
  // Optionally: offer to mark as never_prompt
}
```

---

## Preference Management

Skills should NEVER directly modify setup-prefs.json. Use the functions from `skills/setup/skill.ts`:

- `loadPreference()` — read current preferences
- `savePreference(prefs)` — write updated preferences

**Example: Update tool status after detection**
```typescript
import { loadPreference, savePreference } from "../setup/skill.ts";

const status = await detectTool("gh");
const prefs = await loadPreference() || {
  onboarding_path: "as-needed",
  first_run_complete: false,
  tools: {}
};

prefs.tools.gh = {
  installed: status.installed,
  version: status.version,
  path: status.path
};

await savePreference(prefs);
```

---

## Tool Registry

All tool metadata lives in `skills/setup/tool-registry.yml`. Skills should read this for:
- Detection commands (per platform)
- Version commands
- Installation commands
- What the tool unlocks (which skills depend on it)

**Structure:**
```yaml
tools:
  gh:
    name: GitHub CLI
    description: "Official GitHub command-line interface"
    detect_command:
      windows: "where gh"
      mac: "which gh"
      linux: "which gh"
    version_command: "gh --version"
    install_command:
      windows: "choco install gh -y"
      mac: "brew install gh"
      linux: "sudo apt-get install gh"
    what_it_unlocks:
      - dream-studio:core (git workflows)
      - dream-studio:domains (client-work)
    docs_url: "https://cli.github.com/manual"
```

---

## Fallback Patterns

When a tool is missing, skills should:
1. Check `shouldPromptForTool(toolName)` → if true, prompt user
2. If false (user opted out), check for fallback:
   - **gh missing** → Use GitHub REST API (requires PAT in env)
   - **firecrawl missing** → Use scraper-mcp MCP server → Use WebSearch tool
   - **playwright missing** → Skip screenshot/browser tests, warn user
3. Document the degraded functionality clearly

**Example: Graceful degradation**
```typescript
const ghStatus = await getToolStatus("gh");

if (ghStatus === "installed") {
  // Use gh CLI (preferred)
  await execAsync("gh pr list");
} else if (process.env.GITHUB_TOKEN) {
  // Fallback to API
  console.log("⚠️  gh CLI not found, using GitHub API (slower)");
  // ... fetch via REST API
} else {
  // Cannot proceed
  if (await shouldPromptForTool("gh")) {
    console.log("GitHub CLI (gh) is required. Install: https://cli.github.com");
  }
  throw new Error("GitHub CLI not available and no GITHUB_TOKEN set");
}
```

---

## Platform Detection

Use Node.js `process.platform` to determine OS:

```typescript
const isWindows = process.platform === "win32";
const isMac = process.platform === "darwin";
const isLinux = process.platform === "linux";

const detectCommand = isWindows ? "where" : "which";
```

---

## Used by

setup (wizard, status, jit modes), build, review, verify, ship, all domain skills (game-dev, saas-build, mcp-build, client-work)
