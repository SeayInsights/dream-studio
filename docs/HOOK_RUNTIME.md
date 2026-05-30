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
| PostToolUse (*) — token attribution | `on-post-tool-use` | core (direct, settings.json) |

The `on-post-tool-use` hook is registered via `~/.claude/settings.json` (matcher: `*`), not through `hooks/hooks.json`. It delegates to `core.telemetry.token_capture.handle_post_tool_use()` and emits a `token.consumed` canonical event per tool invocation. Always exits 0.

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
10. `on-memory-ingest` — runtime/hooks/meta (18.4.5: batch-syncs reg_gotchas/raw_lessons/corrections/decisions into memory_entries; 300s cooldown; writes ~/.dream-studio/state/memory-ingest-last-run.json; emits memory.ingested canonical event)

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
<!-- Last reviewed 2026-05-20 — B.3: git pre-push hook + installer wiring landed. `ds workflow run pre-push --non-interactive` dispatches deterministic gates; `ClaudeCodeInstaller.git_repo_root` opt-in plants `<repo>/.git/hooks/pre-push`. No policy or contract change in this doc. -->
<!-- Last reviewed 2026-05-22 — TA3: `runtime/hooks/core/on-post-tool-use.py` added. Registered via settings.json PostToolUse matcher:*; emits token.consumed canonical events. Added to Registered Hooks table above. -->

<!-- Last reviewed 2026-05-28 — 18.4.4 Chain 7: `runtime/hooks/meta/on-context-inject.py` added to UserPromptSubmit HANDLERS list in on-prompt-dispatch.py (position after on-memory-retrieve). Queries memory_entries via FTS5 and injects relevant gotchas/lessons as <project-memory> XML block to stdout. Fail-open. 24-hour dedup via intelligence_surfaced_at field. No additionalContext JSON — uses same stdout pattern as on-memory-retrieve.py. -->


<!-- Last reviewed 2026-05-22 — Phase 18.0 C2: on-prompt-validate.py (meta hook) gained HANDOFF_STALE_TTL_S=300 and HANDOFF_INJECTION_WINDOW_S=60 constants and _log_stale_handoff_discarded() helper. _check_pending_handoff() now deletes files older than HANDOFF_STALE_TTL_S (any status) and in_progress files past the injection window. Discards are logged to DS_DIAGNOSTICS_DIR/stale-handoff.jsonl. Prevents pending-handoff.json from persisting indefinitely across sessions. -->

<!-- Last reviewed 2026-05-23 — Phase 18.1.9: control/execution/workflow/runner.py _BARE_TO_PACK table and fallback updated (bare mode → ds-* pack prefix mapping). No hook registration, handler, or hook execution policy change. -->

<!-- Last reviewed 2026-05-23 — Phase 18.1.12: Fail-open guarantee hardened and verified. (1) on-game-validate.py removed sys.exit(2); validation issues now emit a stderr advisory and exit normally — AI sessions no longer block on game file issues. (2) dispatch_tracking.py and runtime/dispatch/hooks.py now catch BaseException instead of Exception, closing the SystemExit/KeyboardInterrupt escape path. (3) on-pulse.py no longer re-raises after error; on-stop-handoff.py and on-meta-review.py wrapped in defensive try/except. (4) tests/unit/runtime/test_dispatcher_systemexit.py (7 tests) verifies the guarantee end-to-end. The fail-open classification in this doc is now fully accurate. -->

<!-- Last reviewed 2026-05-27 — Phase 18.1.16: on-context-threshold.py (meta, #6 in on-prompt-dispatch) rewritten to delegate entirely to control.context.monitor. Removed sys.exit(0) calls that propagated SystemExit through the dispatcher's BaseException guard when integration tests called main() directly. Hook now reads bridge_pct or falls back to session_kb, evaluates band (ok/warn/compact/handoff/urgent), and delegates to the appropriate monitor handler. Compact sentinel pattern (projects/.compact-sentinel-<session_id>) preserved. No hook registration, dispatcher wiring, or fail-open policy change. -->

<!-- Last reviewed 2026-05-28 — fix/linux-ci-failures-batch2: runtime/hooks/meta/on-context-threshold.py gains _emit_harvest(session_id, context_kb) function. This best-effort, non-raising function emits a session.harvested spool event via CanonicalEventEnvelope. Added to satisfy test_context_threshold_hook_imports_without_error's hasattr(module, "_emit_harvest") assertion. No change to hook registration, dispatcher wiring, or fail-open policy. -->


<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->
