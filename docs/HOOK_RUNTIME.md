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
  → run.py searches: runtime/hooks/{core,quality,analyze,domains,meta}/
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

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-06-05: Wave 2 career annihilation — career_ops module, 15 career_* tables (migration 100), ds-career skill pack, /career-ops route, career_ops contract+profile, and career expert workflow removed. capability_center/scoped_agents/github_repo_intake unchanged. Removed the deleted `career` subdirectory from the `runtime/hooks/{...}/` dispatcher-search path list; no other career content in this doc. -->

<!-- 2026-06-06: Wave 5b legacy module removal — wave executors + lineage_cleanup/convergence deleted. No hook runtime content affected; no semantic change required. -->

<!-- reviewed: 2026-06-06, WO-C orphan rot sweep. control/execution/workflow/learning.py deleted (zero importers confirmed, historical performance tracker). No hook runtime content affected; no semantic change required. -->

<!-- 2026-06-06: WO-A telemetry write-path honesty fixes. (1) runtime/dispatch/hooks.py now reads tool_name (snake_case, as sent by Claude Code runtime) with fallback to toolName (camelCase) — Skill PostToolUse events now correctly route to on-skill-metrics and on-skill-complete. (2) on-session-end.py: fixed copy-paste bug (output_tokens now checks "completion_tokens" not "prompt_tokens"), adds outcome = payload.get("stop_reason") or "end_turn" passed to end_session(). (3) on-skill-metrics.py: removed insert_token_usage block that was writing hardcoded zero-token rows to raw_token_usage — writes stopped at source (path b retirement). (4) on-context-threshold.py: no longer blocks on compact sentinel; KB fallback subtracts post-compact baseline (session_kb via monitor.kb_baseline) so size-based fallback measures growth since last /compact. on-post-compact.py: now calls record_kb_baseline() to record JSONL size at compact time. No hook registration changes; no dispatchers removed; fail-open classification unchanged. -->

<!-- 2026-06-07: WO-T autonomous WO-execution workflow. No hook changes — execute-work-orders.yaml is a workflow template, not a hook. core/preflight/capability_probe.py added (reads gh CLI auth + github_repo config; no hook surface). Hook runtime content unaffected; no semantic change required. -->

<!-- Last reviewed 2026-06-07 — WO-O (feat/wo-o-two-tier-gates): pre-push.yaml updated to v2 with advisory tier field. Gate runner and test file updated. No change to hook runtime behavior or workflow execution model — only gate classification metadata added. -->

<!-- Last reviewed 2026-06-07 — WO-HS (feat/wo-hs-handoff-spawner): on-stop-dispatch.py _dispatch_handoff_continuation() de-silenced. Replaced bare `except: pass` (spawn failure) and silent `if _spawn_new_session is None: return` with _log_spawner_warning() — prints to stderr and appends to ~/.dream-studio/diagnostics/handoff-spawn-errors.log. Stale/missing handoff file paths remain silent (normal operation). core/health/doctor.py gains _check_handoff_spawner() check visible via `ds doctor`. No change to hook registration, dispatcher wiring, or fail-open policy — all failures still non-blocking. -->

<!-- 2026-06-07: WO-T2 (feat/wo-t2-autonomous-loop-hardening): No hook changes. execute-work-orders.yaml updated with independent-review node (see WORKFLOW_RUNTIME.md). core/work_orders/close.py gained independent_review_passed gate predicate. tests/evals/test_gate_evals.py gained 3 new gate tests. Hook registration, dispatcher wiring, handler set, and fail-open policy unchanged. -->
<!-- Last reviewed 2026-06-08 — WO-HS2 handoff-to-authority wiring: on-context-threshold.py now separates 'handoff' and 'compact' bands — 'handoff' calls monitor.handle_handoff() (was calling handle_compact_warning). handle_handoff() in monitor.py calls _write_handoff_packet_to_db() which inserts into raw_handoffs via insert_handoff() and writes a thin pending-handoff.json pointer (handoff_id + triggered_at, no content). on-stop-dispatch.py _dispatch_handoff_continuation() now reads pending-handoff.json pointer, queries DB for handoff_id, and spawns claude "resume:" — no handoff content in argv. on-prompt-validate.py _check_pending_handoff() instruction updated to retire the handoff-latest.json write instruction; tells Claude to notify user a continuation session is being prepared. resume_from_handoff.py find_latest_handoff_db() calls mark_handoff_consumed() after loading so the spawner does not re-spawn the same handoff. -->
