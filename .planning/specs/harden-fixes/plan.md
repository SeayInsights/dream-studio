# Harden Fixes — Implementation Plan

**Date:** 2026-04-30
**Source:** review-harden-findings.md
**Scope:** 4 High + 4 Medium quick-win fixes. Low findings deferred to a separate PR.
**Constraint:** PR must stay under ~120 lines of changes.

---

## Branch

```
chore/harden-fixes
```

---

## Tasks

### H1 — Remove `.planning/` from `.gitignore`

**Severity:** High
**File:** `.gitignore`

**What to do:**
Remove the `.planning/` entry from `.gitignore`. The planning directory contains `CONSTITUTION.md` and `GOTCHAS.md` — the project constitution pattern requires these to be version-controlled and survive a fresh clone. These are authored/maintained files, not generated artifacts.

**Exact change:**
Delete the line `.planning/` from `.gitignore`. Then `git add .planning/` and include `CONSTITUTION.md`, `GOTCHAS.md`, and any other maintained files under `.planning/` in the commit.

**Acceptance criteria:**
- `git ls-files .planning/CONSTITUTION.md` returns the file (it is tracked).
- `git ls-files .planning/GOTCHAS.md` returns the file (it is tracked).
- `.gitignore` no longer contains a `.planning/` entry.
- `git status` shows `.planning/` files as tracked, not ignored.

---

### H2 — Create stub `packs/career/hooks/` and `packs/analyze/hooks/` directories

**Severity:** High
**Files:** `packs/career/hooks/.gitkeep`, `packs/analyze/hooks/.gitkeep`

**What to do:**
`career` and `analyze` are declared in `packs.yaml` and are searched by `run.sh`/`run.cmd` on every hook invocation, but neither has a `packs/<pack>/hooks/` directory. This causes dead search steps on every invocation and will silently fail if a hook handler is ever added. Create the directories with a `.gitkeep` placeholder so the expected filesystem structure matches the declared pack layout.

**Exact change:**
```
packs/career/hooks/.gitkeep   (new empty file)
packs/analyze/hooks/.gitkeep  (new empty file)
```

**Acceptance criteria:**
- `ls packs/career/hooks/` and `ls packs/analyze/hooks/` succeed.
- Both directories are tracked in git.
- `run.sh` search steps for career and analyze resolve to an existing path (no "directory not found" error on hook dispatch).

---

### H3 — Rename the shadowed `packs/meta/hooks/on-quality-score.py`

**Severity:** High
**File:** `packs/meta/hooks/on-quality-score.py` → `packs/meta/hooks/on-skill-telemetry.py`

**What to do:**
Both `packs/quality/hooks/on-quality-score.py` (233 lines, git-diff scoring) and `packs/meta/hooks/on-quality-score.py` (89 lines, skill telemetry) share the same filename. `run.sh` searches `quality` before `meta`, so the meta version is permanently shadowed and never executes. The two files implement distinct behaviors. Rename the meta version to `on-skill-telemetry.py` to eliminate the collision and make both handlers executable.

**Exact change:**
```
git mv packs/meta/hooks/on-quality-score.py packs/meta/hooks/on-skill-telemetry.py
```

Then update any references to `on-quality-score` inside `hooks/hooks.json` or any dispatch config that targets the meta pack's handler — update those entries to reference `on-skill-telemetry`.

**Acceptance criteria:**
- `packs/meta/hooks/on-quality-score.py` no longer exists.
- `packs/meta/hooks/on-skill-telemetry.py` exists with the original 89-line skill telemetry content.
- No two hook handler files share the same filename within the search path.
- Any dispatch config referencing the renamed file is updated to match.

---

### H4 — Sync `marketplace.json` version to match `plugin.json`

**Severity:** High
**File:** `.claude-plugin/marketplace.json`

**What to do:**
`marketplace.json` declares version `0.6.1` but `plugin.json` declares `0.11.0`. Update `marketplace.json` to `0.11.0`.

**Exact change:**
In `.claude-plugin/marketplace.json`, update:
```json
"version": "0.6.1"
```
→
```json
"version": "0.11.0"
```

**Acceptance criteria:**
- `grep '"version"' .claude-plugin/marketplace.json` returns `0.11.0`.
- Both files declare the same version.

---

### M1 — Remove unused imports in `on-game-validate.py`

**Severity:** Medium (quick win — 2-line change)
**File:** `packs/domains/hooks/on-game-validate.py`

**What to do:**
`ProjectContext` and `ValidationResult` are imported from `domain_lib/game_validate` (lines 37–38) but never used in the module body. Remove both unused import names. If the import block becomes empty, remove the entire import statement.

**Exact change:**
Remove `ProjectContext` and `ValidationResult` from the import at lines 37–38. Verify no other usage exists with a quick grep before deleting.

**Acceptance criteria:**
- `grep "ProjectContext\|ValidationResult" packs/domains/hooks/on-game-validate.py` returns no results.
- File passes `python -m py_compile` without errors.
- No `F401` flake8 warning for those names.

---

### M2 — Remove dead pydantic import in `on-stop-handoff.py`

**Severity:** Medium (quick win — 1-line change)
**File:** `packs/core/hooks/on-stop-handoff.py`

**What to do:**
`from pydantic import ValidationError` is imported inside a try block (line 68) but `ValidationError` is never referenced in any except clause or elsewhere. The import is dead. Remove it. The surrounding try block catches via bare `except Exception` — the `StopPayload(**payload)` call is the only thing that needs the try block, and that should continue to work without the named import.

**Exact change:**
Remove line 68: `from pydantic import ValidationError`

Keep the try/except structure intact — only delete the unused import line.

**Acceptance criteria:**
- `grep "from pydantic" packs/core/hooks/on-stop-handoff.py` returns no results.
- File passes `python -m py_compile` without errors.
- Hook behavior is unchanged (StopPayload validation still has a try/except fallback).

---

### M3 — Delete stale `coverage.json` artifact from working tree

**Severity:** Medium (quick win — 1-file deletion)
**File:** `coverage.json` (repo root)

**What to do:**
`coverage.json` references `hooks/lib/skill_metrics.py` which no longer exists on disk. The file is listed in `.gitignore` but is present in the working tree as a stale untracked artifact. Delete it from disk so it no longer pollutes coverage metrics or confuses CI.

**Exact change:**
```
rm coverage.json
```

Do not add it to git — it is already gitignored. Just remove it from the working tree.

**Acceptance criteria:**
- `coverage.json` does not exist in the repo root.
- `git status` does not show `coverage.json` as untracked.

---

### M4 — Resolve `CONTEXT.md` untracked status

**Severity:** Medium (quick win — classify and act)
**File:** `CONTEXT.md` (repo root)

**What to do:**
`CONTEXT.md` is untracked and not in `.gitignore`. It is a generated/session-authored domain glossary. Determine which applies:
- If it is a maintained reference doc → `git add CONTEXT.md` and commit it.
- If it is a generated/ephemeral artifact → add `CONTEXT.md` to `.gitignore`.

**Decision guidance:** Check its content. If it has structured, manually maintained content that aids development, commit it. If it looks auto-generated or session-specific, gitignore it.

**Acceptance criteria:**
- `git status` does not show `CONTEXT.md` as untracked.
- Either `git ls-files CONTEXT.md` returns the file (tracked), OR `.gitignore` contains `CONTEXT.md` (explicitly excluded).

---

## Deferred (out of scope for this PR)

The following findings are deferred to a separate PR to keep this one under the 120-line limit:

| Finding | Reason for deferral |
|---------|---------------------|
| M3 (scripts/ test coverage) | Requires writing new test files — large scope |
| M3 (scripts/ error handling) | Requires editing multiple scripts with try/except |
| M3 (pyproject.toml coverage omit) | Config change, but root cause is missing tests |
| L1–L5 (all Low findings) | Intentionally deferred per scope constraint |

---

## Estimated diff size

| Task | Est. lines changed |
|------|--------------------|
| H1 — .gitignore | 1 line removed |
| H2 — stub dirs | 2 files (empty .gitkeep) |
| H3 — rename + update dispatch | ~5 lines (rename + any dispatch config) |
| H4 — marketplace.json version | 1 line |
| M1 — remove unused imports | 2 lines |
| M2 — remove dead import | 1 line |
| M3 — delete coverage.json | 0 lines (deletion) |
| M4 — CONTEXT.md classify | 1 line (.gitignore) or 0 (just git add) |
| **Total** | **~13 lines** well under 120-line limit |

---

## Execution order

Run in this order to minimize churn:
1. H4 (1-line version bump — easiest, isolated)
2. H1 (remove .gitignore entry, then `git add .planning/`)
3. H2 (create stub directories)
4. H3 (rename file, update dispatch config)
5. M1 (remove unused imports)
6. M2 (remove dead import)
7. M3 (delete coverage.json)
8. M4 (classify CONTEXT.md)

Commit all as one logical commit: `chore: fix 4 High + 4 Medium harden findings`
