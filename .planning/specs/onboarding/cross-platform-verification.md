# Cross-Platform Verification Checklist — Onboarding (T023)

**Date:** 2026-04-30
**Task:** T023 — Cross-platform testing verification
**Status:** Windows verified (direct); Mac/Linux requires manual testing

---

## Summary

Three onboarding flows tested: first-run detection, tool detection, and wizard install commands.
Windows was directly verified. Mac and Linux entries are verified by code inspection of
`skills/setup/skill.ts` and `skills/setup/tool-registry.yml`.

---

## 1. First-Run Detection

### Mechanism
`isFirstRun()` in `skills/setup/skill.ts` checks for `.dream-studio/setup-prefs.json`
using `fs.access()`. Returns `true` if file is absent, `false` if present.

### Windows (direct test — verified)
- File path: `<cwd>/.dream-studio/setup-prefs.json`
- `fs.access()` raises `ENOENT` when directory or file is missing → returns `true` (first run)
- `fs.mkdir({ recursive: true })` creates `.dream-studio/` on first save — cross-platform safe
- `path.join()` used throughout — no hardcoded separators

### Mac / Linux (code-inspection verified)
- Same `fs.access()` / `path.join()` logic applies unchanged
- No Windows-specific code paths in `isFirstRun()` or `savePreference()`
- `{ recursive: true }` on `fs.mkdir` handles pre-existing directories on all platforms

### Edge cases
- **Symlinks:** `fs.access()` follows symlinks; a symlinked prefs file would suppress first-run on all platforms (acceptable)
- **Read-only filesystem:** `savePreference()` would throw; not currently caught — manual test recommended on restricted-permission Linux environments

---

## 2. Tool Detection

### Mechanism
`whichCommand(bin)` in `skills/setup/skill.ts` returns `where <bin>` on Windows and
`which <bin>` on Mac/Linux. Used by `detectBinary()` for all six tools.

```typescript
function whichCommand(bin: string): string {
  return process.platform === "win32" ? `where ${bin}` : `which ${bin}`;
}
```

### Platform-specific `detect_command` entries in `tool-registry.yml`
All 6 tools have explicit Windows/Mac/Linux entries:

| Tool       | Windows          | Mac              | Linux            |
|------------|------------------|------------------|------------------|
| gh         | `where gh`       | `which gh`       | `which gh`       |
| firecrawl  | `where firecrawl`| `which firecrawl`| `which firecrawl`|
| playwright | `where playwright`| `which playwright`| `which playwright`|
| npm        | `where npm`      | `which npm`      | `which npm`      |
| python     | `where py`       | `which python3`  | `which python3`  |
| node       | `where node`     | `which node`     | `which node`     |

### Python detection — critical platform difference
`detectPython()` tries `python3` first, then falls back to `python`.

- **Windows:** Python Launcher (`py`) is the standard entry point installed by the official
  Python installer. However, `detectPython()` calls `python3` then `python` — NOT `py`.
  The `tool-registry.yml` detect_command correctly uses `where py` for Windows, but the
  TypeScript `detectBinary` call does not use `py` on Windows.
  **ACTION NEEDED:** `detectPython()` should try `py` on Windows before `python3`/`python`.

- **Mac:** `python3` is pre-installed on modern macOS (via Xcode CLT). Falls through correctly.
- **Linux:** `python3` is standard. Falls through correctly.

### Windows (direct test — verified)
- `where gh` returns `C:\Program Files\GitHub CLI\gh.exe` or exits non-zero if absent
- `where` may return multiple paths (multiple installs); `skill.ts` takes first line — correct
- `where npm` / `where node` verified present when Node.js installed via nvm-windows or official installer
- `where python` works when Python added to PATH via installer (not guaranteed without `py` fallback)

### Mac (code-inspection verified — manual test recommended)
- `which gh` works if installed via Homebrew or direct download
- `which python3` works on macOS 12+ (system Python 3.x present)
- `which playwright` works if installed globally via `npm install -g playwright`
- Homebrew prefix varies: `/usr/local/bin` (Intel) vs `/opt/homebrew/bin` (Apple Silicon)
  — `which` resolves both; no code change needed

### Linux (code-inspection verified — manual test recommended)
- `which gh` requires GitHub CLI apt repo configured (`apt-get install gh`)
- `which python3` standard on Ubuntu 20.04+, Debian 11+
- `which firecrawl` — `firecrawl` CLI binary is uncommon on Linux; `detectFirecrawl()` falls back
  to `require.resolve('@mendable/firecrawl-js/package.json')` which works regardless of platform
- `which playwright` works after `npm install -g playwright`

---

## 3. Wizard Install Commands

### Mechanism
`tool-registry.yml` specifies `install_command` per platform. The wizard reads these
and presents them to the user.

### Install commands per platform

| Tool       | Windows                          | Mac                          | Linux                              |
|------------|----------------------------------|------------------------------|------------------------------------|
| gh         | `choco install gh -y`            | `brew install gh`            | `sudo apt-get install gh`          |
| firecrawl  | `pip install firecrawl-py`       | `pip install firecrawl-py`   | `pip install firecrawl-py`         |
| playwright | `pip install playwright && playwright install` | same | same              |
| npm        | `choco install nodejs -y`        | `brew install node`          | `sudo apt-get install nodejs npm`  |
| python     | `choco install python -y`        | `brew install python@3.12`   | `sudo apt-get install python3.12 python3.12-venv` |
| node       | `choco install nodejs -y`        | `brew install node`          | `sudo apt-get install nodejs`      |

### Windows (direct test — verified)
- Chocolatey (`choco`) must be pre-installed; wizard does not install Chocolatey itself
  — wizard should detect `choco` and warn if absent before presenting choco commands
- `pip install` works when Python is in PATH

### Mac (code-inspection verified — manual test recommended)
- Homebrew must be pre-installed; `brew` assumed present
- `brew install python@3.12` installs a versioned Python; `python3` may still point to
  system Python. Users may need to update PATH or use `python3.12` explicitly.

### Linux (code-inspection verified — manual test recommended)
- `sudo apt-get install gh` requires the GitHub CLI apt repository to be configured first.
  Without it, `apt-get` will fail with "Unable to locate package gh". The wizard should
  include the apt-key + source-list setup step before the install command.
- `sudo apt-get install python3.12` is only available on Ubuntu 22.04+; Ubuntu 20.04 users
  need the `deadsnakes` PPA. Consider using `python3` (unversioned) as fallback.

---

## 4. `status` Command Verification

### Expected output on all platforms
After wizard completion, `dream-studio setup status` should display:
```
Tools:
  gh         ✓ installed (2.47.0)
  node       ✓ installed (20.11.0)
  npm        ✓ installed (10.5.0)
  python     ✓ installed (3.12.x)
  firecrawl  ✗ not installed
  playwright ✗ not installed

Onboarding: wizard (complete)
```

### Windows (direct test — verified)
- `ToolStatus.path` returns Windows-style path (e.g., `C:\Program Files\...`) — display only, no functional impact
- Version parsing handles `\r\n` line endings — `stdout.split(/\r?\n/)` in `detectBinary()` handles this correctly

### Mac / Linux (code-inspection verified)
- `ToolStatus.path` returns Unix-style path — no issues expected
- No `\r` in stdout — regex `/\r?\n/` degrades safely to `/\n/`

---

## 5. Issues Found During Verification

| # | Severity | Platform | Description | File |
|---|----------|----------|-------------|------|
| 1 | Medium | Windows | `detectPython()` does not try `py` (Windows Python Launcher) before `python3`/`python`. On systems where only the Microsoft Store stub `python` is present, detection will fail or return wrong version. | `skills/setup/skill.ts` line 257 |
| 2 | Low | Linux | `sudo apt-get install gh` install command missing apt-key/source-list prerequisite step | `skills/setup/tool-registry.yml` |
| 3 | Low | Mac | `brew install python@3.12` may not update `python3` symlink; users may be confused about which Python is active | `skills/setup/tool-registry.yml` |
| 4 | Low | Windows | Wizard assumes Chocolatey is installed; no pre-check or fallback if `choco` is absent | wizard mode implementation |

---

## 6. Manual Testing Checklist (Mac / Linux)

Tasks to run on a Mac or Linux machine before marking cross-platform support complete:

- [ ] Delete `.dream-studio/setup-prefs.json` and run `dream-studio setup` — confirm first-run prompt appears
- [ ] Choose `wizard` path and step through all 6 tools — confirm detection works for installed tools
- [ ] Choose `as-needed` path — confirm no wizard prompt, but JIT prompt fires when a skill needs a missing tool
- [ ] Choose `read-docs` path — confirm no prompts at all
- [ ] Run `dream-studio setup status` — confirm all detected tools show correct version and path
- [ ] On Mac Apple Silicon: confirm `which gh` and `which python3` resolve under `/opt/homebrew/bin`
- [ ] On Ubuntu 20.04: confirm `apt-get install gh` fails gracefully with a message about the apt repo
- [ ] Verify `detectPython()` returns correct result when only `python3` is installed (no `python` alias)
- [ ] Verify `detectPython()` returns correct result when `python3` is absent but `python` (Python 3) is present

---

## 7. Code Locations

| Component | File |
|-----------|------|
| Platform detection (`whichCommand`) | `skills/setup/skill.ts` line 26-28 |
| `isFirstRun()` | `skills/setup/skill.ts` line 88-97 |
| `detectBinary()` | `skills/setup/skill.ts` line 36-62 |
| `detectPython()` | `skills/setup/skill.ts` line 251-261 |
| Tool install/detect commands | `skills/setup/tool-registry.yml` |
| Platform differences documentation | `skills/core/setup.md` |
