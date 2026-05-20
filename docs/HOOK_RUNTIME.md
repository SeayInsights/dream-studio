# Hook Runtime Authority

Phase 5.4A — Hook Runtime Reliability audit and classification.

## Hook Authority Model

### Canonical (active, authoritative)

| File | Role |
|------|------|
| `hooks/hooks.json` | Claude Code hook registration config |
| `hooks/run.py` | Cross-platform hook launcher used by hook registration |
| `hooks/run.sh` | Bash hook launcher (macOS/Linux/Git Bash) |
| `hooks/run.cmd` | Windows cmd hook launcher |
| `runtime/hooks/{pack}/` | Canonical handler directory |
| `control/execution/dispatch_tracking.py` | Dispatcher execution engine |
| `control/execution/dispatch_helpers.py` | Dispatcher helper functions |

### Orphaned / Phase 6C Candidates

| File | Status |
|------|--------|
| `runtime/hooks/on-startup-health.py` | Root-level, not in any pack — not reachable via dispatchers |
| `runtime/hooks/on-periodic-health.py` | Root-level, not in any pack — not reachable via dispatchers |
| `runtime/hooks/meta/on-skill-gate.py` | Orphaned — not wired through dispatch |

### Removed in Phase 6B/6C

| Item | Phase |
|------|-------|
| `hooks/handlers/on-session-resume.py` | 6B Wave 4 — dead import |
| `hooks/lib/__init__.py`, `hooks/lib/paths.py` | 6C Wave 1 — compat shims removed |
| `runtime/hooks/*/_legacy.py` (28 files) | 6B Wave 4 — fallback handlers |
| `hooks/on-startup.py` | 6B Wave 4 — dead handler |

## Hook Execution Flow

```
Claude Code event (e.g., UserPromptSubmit)
  → hooks/hooks.json registers command
  → hooks/run.py <dispatcher-name>
  → run.py searches: runtime/hooks/{core,quality,career,analyze,domains,meta}/
  → finds dispatcher (e.g., on-prompt-dispatch.py)
  → dispatcher imports sub-handlers via dispatch_tracking.run_handlers()
  → each sub-handler's main() called sequentially with shared stdin payload
```

`hooks/hooks.json` must not depend on bare shell expansion of
`${CLAUDE_PLUGIN_ROOT}`. Registered commands resolve `hooks/run.py` from
`CLAUDE_PLUGIN_ROOT`, the current repo root, or a repo descendant. This keeps a
fresh `UserPromptSubmit` from failing before Dream Studio's own launcher can
resolve the plugin root.

On Windows, `hooks/run.cmd` must capture its own script directory before
shifting arguments. Codex app and other adapter surfaces may invoke
`UserPromptSubmit` from a workspace outside the Dream Studio repo; the launcher
must resolve `runtime\hooks\...` from the launcher path, not from the adapter
current working directory.

## Registered Hooks (from hooks.json)

| Event | Handler | Pack Location |
|-------|---------|--------------|
| UserPromptSubmit | `on-prompt-dispatch` | meta (dispatcher) |
| Stop | `on-stop-dispatch` | meta (dispatcher) |
| PostCompact | `on-post-compact` | meta (direct) |
| PostToolUse (Skill) | `on-skill-metrics` | meta (direct) |
| PostToolUse (Skill) | `on-skill-complete` | meta (direct) |
| PostToolUse (Edit\|Write) | `on-edit-dispatch` | meta (dispatcher) |
| PostToolUse (Read) | `on-skill-load` | meta (direct) |
| PostToolUse (default) | `on-tool-activity` | meta (direct) |

Production readiness is not an implicit hook execution path. Hook telemetry may
be evidence for readiness, and future approved hooks may emit readiness-related
facts, but readiness control execution and SQLite persistence remain owned by
the `production-readiness` workflow and explicit runtime authorization.

## Dispatcher Sub-Handler Mapping

### on-prompt-dispatch (UserPromptSubmit)
1. `on-prompt-validate` — runtime/hooks/meta
2. `on-session-start` — runtime/hooks/meta
3. `on-first-run` — runtime/hooks/meta
4. `on-memory-retrieve` — runtime/hooks/meta
5. `on-milestone-start` — runtime/hooks/core
6. `on-context-threshold` — runtime/hooks/meta
7. `on-pulse` — runtime/hooks/meta

### on-stop-dispatch (Stop)
1. `on-session-end` — runtime/hooks/meta
2. `on-stop-handoff` — runtime/hooks/core
3. `on-quality-score` — runtime/hooks/quality
4. `on-skill-telemetry` — runtime/hooks/meta
5. `on-milestone-end` — runtime/hooks/core
6. `on-token-log` — runtime/hooks/meta
7. `on-meta-review` — runtime/hooks/meta
8. `on-workflow-progress` — runtime/hooks/core
9. `on-changelog-nudge` — runtime/hooks/core

### on-edit-dispatch (PostToolUse Edit|Write)
1. `on-agent-correction` — runtime/hooks/quality
2. `on-game-validate` — runtime/hooks/domains
3. `on-security-scan` — runtime/hooks/quality
4. `on-structure-check` — runtime/hooks/quality

## Handlers NOT Invoked by hooks.json or Dispatchers

These exist in runtime/hooks/ but are not reachable via any registered hook:

| Handler | Pack | Risk |
|---------|------|------|
| `on-skill-gate` | meta | Low — HK-6, defined but never invoked |
| `on-startup-health` | (root) | Low — root-level, not in pack search path |
| `on-periodic-health` | (root) | Low — root-level, not in pack search path |

## Silent Failure Classification

| Category | Handlers | Risk |
|----------|----------|------|
| Safe telemetry (silent ok) | on-skill-metrics, on-token-log, on-tool-activity | Low |
| Safe advisory (silent ok) | on-skill-complete, on-skill-load, on-skill-gate | Low |
| Risky operational (should log) | on-session-start, on-session-end, on-stop-handoff | Medium |
| Should warn | on-context-threshold, on-pulse | Medium |
| Unchanged for now | All — dispatcher-level try/except/pass is Phase 6 scope | — |

## Timeout Risk Classification

| Risk | Handlers | Reason |
|------|----------|--------|
| May block (subprocess) | on-changelog-nudge, on-quality-score | Calls subprocess (git) |
| May block (DB) | on-session-start, on-session-end, on-stop-handoff, on-pulse | SQLite writes |
| Safe (no IO) | All advisory/nudge handlers | Pure stdout output |
| Recommendation | Timeout enforcement belongs in dispatcher wrapper or run.sh, not individual handlers | Phase 6 scope |

## External Service / Local-First Classification

| Handler | External? | Classification |
|---------|-----------|---------------|
| on-pulse_legacy | References Playwright | Legacy only, opt-in, not default |
| All other handlers | No external calls | Local-only |
| Entire active hook set | No network calls | Local-first compliant |

## Phase 5.4A Changes

1. Fixed dispatcher paths: `packs/*/hooks/` → `runtime/hooks/*/` in three dispatchers
2. Added hook runtime tests (test_hook_runtime_reliability.py)
3. Created this documentation

## Phase 6 Recommendations

1. Remove all `*_legacy.py` files (20 files)
2. Remove dead `hooks/handlers/on-session-resume.py`
3. Remove dead root-level `on-startup-health.py` and `on-periodic-health.py` (or move into a pack)
4. Evaluate whether `on-skill-gate` should be wired into hooks.json
5. Add structured logging to replace silent `except: pass` in dispatchers
6. Evaluate timeout enforcement in `run_handlers()`
7. ~~Remove `hooks/lib/` compat shims~~ (done in Phase 6C Wave 1)

<!-- Last reviewed 2026-05-20 — repo-wide `py -m black .` formatting applied; no behavior or policy change required here. -->

<!-- Last reviewed 2026-05-20 — A3: `control/execution/workflow/runner.py:_invoke_skill` no longer self-shells via `subprocess.run(['ds','skill','invoke', specifier])`; instead it calls `core.skills.invocation.load_skill_content` + `record_skill_invocation` directly in-process. ~40x faster per node, tracebacks intact, mockable. dry_run path unchanged. No policy or contract change here. -->