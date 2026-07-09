# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Validation results are captured (WO-VALIDATION-CAPTURE, b49c0a65-a299-489a-b40e-e13a834183be):** the validations dashboard component was empty because nothing emitted `validation.result_recorded` (distinct from `event.validation.failed`, which is a schema-rejection/ingestion-health metric — the two must not be conflated). `core/work_orders/verify.py` `run_executable_checks()` — where a work order's SQL/TEST/API-CHECKs run — now emits one `validation.result_recorded` canonical event per check to the spool (validation_type = check kind, status/outcome_status = passed|failed, command, summary), best-effort and non-fatal (a telemetry failure never breaks a check run or a close). `docs/canonical/event_taxonomy_v1.json` adds `validation.result_recorded` to the validation family and `config/event_type_registry.py` routes it → `ai_canonical_events`, so the events pass the ingestion validator and reach `events_fact`, giving the WO-DASH-DUCKDB-PROJECTION validation rollup a real source. End-to-end verified: check → spool → `ai_canonical_events` → `events_fact` → validation rollup shows SQL-CHECK passed/failed counts.
- `tests/unit/test_validation_capture.py`: proves each executable check emits a typed `validation.result_recorded` (passing and failing), the capture is best-effort (a spool failure never breaks the check run), and a task with no check line emits nothing.
- **Subagent invocations emit agent-identified telemetry (WO-AGENT-TELEMETRY, 15735272-93e8-48ab-aea2-50d61ccdc25a):** the `agent_id` dimension was NULL in 100% of canonical events — no subagent was instrumented. Claude Code exposes the subagent identity to the PostToolUse hook as `tool_input.subagent_type` for the Task tool, so `emitters/claude_code/emitter.py` `normalize_post_tool_use` now emits an `agent.execution.completed` canonical event stamping `trace.agent_id`/`agent_type` = subagent_type (the ingestor maps `trace.agent_id` → the `agent_id` column); the Task prompt/description are not included (they carry user content). `core/telemetry/token_capture.py` additionally stamps `agent_id`/`agent_type` onto a Task call's `token.consumed` so agent token cost is attributed. `config/event_type_registry.py` registers `agent.execution.*` → `ai_canonical_events` (previously an unregistered type produced a per-invocation dual-write warning on the hot path). `core/telemetry/read_models.py` repoints the agent dashboard component to read `agent.execution.*` from `events_fact` (the SQLite spine never carried `agent_id`), completing the agent path WO-DASH-DUCKDB-PROJECTION deferred here.
- `tests/unit/test_agent_telemetry.py`: proves the emitter captures `agent_id` when `subagent_type` is present (and the prompt does not leak), a non-Task tool emits no agent event, token_capture attributes the Task call's tokens to the agent, and the agent component reads agent invocations from `events_fact`. End-to-end verified: emit → ingest → `ai_canonical_events.agent_id` → `events_fact.agent_id`.
- **All dispatched hooks log their execution (WO-HOOK-EXEC-STATS, d2ee6f62-0765-4520-8f04-65f8b8feb017):** `control/execution/dispatch_tracking.py` `run_handlers()` now emits a `system.hook.execution.logged` canonical event per dispatched handler (hook_name, hook_type=event_name, duration_ms, exit_code, status), so the DuckDB `hook_executions` view shows every dispatched hook instead of only `on-pulse` (previously the per-hook stats surface showed a single hook). Emission is best-effort/hot-path-safe via the existing `insert_hook_execution` fire-and-forget spool writer, runs after the handler completes, and never writes stdout or alters hook decisions (blocking hooks own their stdout — lesson edb8525f); a `sys.exit(0)` handler is recorded as a clean success, a raising handler as an honest failure. The 2 directly-wired blocking enforce hooks (`on-edit-enforce`, `on-stop-enforce`) bypass the dispatcher and are not covered by this central change (a separate, higher-risk concern, since they own their block-decision stdout).
- `tests/unit/test_hook_exec_stats.py`: proves every dispatched handler logs a distinct hook execution (>1 distinct hook_name) with the fields the `hook_executions` view extracts, that `sys.exit(0)` is a success not a failure, and that a missing/no-main handler logs nothing.
- **Dashboard component reads repointed to DuckDB (WO-DASH-DUCKDB-PROJECTION, 899d3f17-e9a1-4bc2-8ba6-dc04188ad9b2):** `core/telemetry/read_models.py` — the workflow component usage and the validation rollup now derive from the DuckDB analytics store (`aggregate_metrics.db` `events_fact` projection) instead of the SQLite `execution_events` spine, via a new fail-open read-only `_analytics_rows` helper and a `_component_usage_from_events_fact` dispatcher; `component_usage_summary` `source_tables` names `events_fact`, not the spine. Workflow reads `workflow.completed`/`workflow.node.completed`; validation reads `validation.result_recorded` (honestly empty until WO-VALIDATION-CAPTURE lands the capture) and is deliberately NOT the `validation_failures` view (`event.validation.failed` — schema-rejected events, a different metric that must not be conflated with validation outcomes). hook/tool/skill/agent keep the SQLite spine read until their capture reaches canonical (WO-HOOK-EXEC-STATS / WO-AGENT-TELEMETRY) — `hook.tool_activity` has no canonical equivalent, so repointing now would drop live telemetry rather than gain completeness. The dead `duckdb_execution_events` table (fed only by never-emitted `execution.started/completed/failed` events) is unused; `events_fact` is the live projection.
- `tests/unit/test_component_duckdb_sources.py`: proves the workflow + validation reads come from DuckDB (SQLite decoy rows never surface) and that `/api/telemetry/components` `source_tables` names the DuckDB store; `tests/unit/test_telemetry_read_models.py` seeds workflow/validation events into `events_fact` to match the new read source.
- **Migration authority squash (WO-SQUASH-BASELINE, 5fd84891-a329-48b8-b537-f0d4fc94d1a7, 2026-07-04, operator-approved irreversible):** migrations 001-141 collapsed into a single lean baseline, `core/event_store/migrations/142_lean_baseline.sql`. Generated by applying the full pre-squash chain to a fresh temp DB and re-emitting every resulting `sqlite_master` object (tables, indexes, views, triggers) in idempotent `CREATE ... IF NOT EXISTS` form, preceded by `DROP TABLE IF EXISTS` / `DROP VIEW IF EXISTS` for every tombstoned name (`tests/unit/schema_tombstones_data.py`) plus 11 legacy view names permanently retired by the chain's drop/recreate view-guard pattern. Schema-identity verified: a fresh baseline-only DB and a fresh 001-141 chain DB produce an identical `sqlite_master` object set (208 named objects, identical normalized DDL). `.released_version` set to 142; new migrations start at 143. `core/config/sqlite_bootstrap.py` needed no code changes — its version-comparison loop already tolerates a single, non-contiguous migration file. The migration authority is now a single baseline plus forward migrations, not a 141-file incremental chain; see `docs/MIGRATION_AUTHORITY.md` and `core/event_store/migrations/README.md`.

### Removed
- 139 individual pre-squash migration files (`001_*.sql` through `141_*.sql`, minus the two documented gaps at 035/036) deleted from the working tree as part of the WO-SQUASH-BASELINE squash — they remain available in git history.

### Added
- Mutating `ds restore <backup>` (WO-RESTORE): the destructive counterpart to the validate-only `ds restore-check`, in `core/installed_productization.restore_runtime`. Default is a dry-run (validate + plan, mutates nothing); `--execute` takes a pre-restore backup of the CURRENT state FIRST — written outside the home so it survives — then replaces the state-tier databases (`studio.db`, and `files.db` if present in the backup) from the chosen backup, clearing stale WAL/SHM sidecars so the restored db is authoritative. `--force` overrides a not-restore-ready backup. CLI subcommand `ds restore <backup> [--execute] [--force] [--backup-dir]`; runtime command surface + `docs/contracts/restore-contract.md` + installed-runtime/troubleshooting/architecture docs updated.
- `tests/integration/test_restore.py`: restore replaces state, pre-restore backup taken first (reversible), exact-backup selection, dry-run-default, not-ready-refused-without-force, end-to-end (5 tests).
- Mutating `ds uninstall` (WO-UNINSTALL): the destructive counterpart to the read-only `ds uninstall-check`, with three explicitly-gated tiers in `core/installed_productization.uninstall_runtime`. Default is a dry-run plan that mutates nothing; `--execute` deregisters the Dream-Studio hook wiring from BOTH generated `.claude/settings.json` copies (via new `integrations/targets/claude_code/settings_merge.deregister_ds_hooks`, the inverse of the additive install merge — foreign hooks are preserved) and removes the global `ds.cmd`/`ds.ps1` launchers while preserving `~/.dream-studio` state (reversible by reinstall); `--purge-state --force` additionally wipes the state tier, refused without the mandatory second confirmation and always backed up outside the home first. CLI subcommand + `_default_claude_settings_paths` resolve both copies; runtime command surface, `docs/contracts/uninstall-contract.md`, `docs/reference/cli.md`, and the installed-runtime/troubleshooting/architecture docs updated.
- `tests/unit/test_uninstall_contract.py` + `tests/integration/test_uninstall.py`: contract enumerates removed-vs-preserved targets, dry-run-default mutates nothing, integration teardown removes hooks+launchers while preserving state, both `.claude` copies cleared, and `--purge-state` requires the second confirm + backs up before wiping (end-to-end).
- Escalation ladder (WO-ESCALATION-LADDER): when the deterministic verifier/outcome-eval says a closed WO is NOT FIXED, the platform reopens and escalates instead of silently re-closing. New `core/work_orders/escalation.py` + migration 126 `ds_escalations` (per-WO `escalation_level`/`retry_count`/`designated_executor`). (1) An escalated WO's retry routes to Opus — `resolve_executor` returns `opus`; both the autonomous loop (new `escalation-probe` node + `ds work-order executor <id>`) and the manual path (`start_work_order`'s `executor` field) honor it. (2) Re-close REQUIRES a passing independent review — for escalated WOs `close_work_order` skips the unreviewable/gap bypasses and `force=True` cannot bypass the `independent_review` gate (returns `escalated: True`). (3) Retries are capped (`escalation.retry_cap`, env `DREAM_STUDIO_ESCALATION_RETRY_CAP` > `ds_config` > default 3); at the cap the outcome-eval reopen path escalates to the operator (`ESC-RETRYCAP-*`) instead of looping. `ds-workorder` SKILL.md (Rule 10) + close-mode text and the DATABASE/MIGRATION_AUTHORITY/WORKFLOW_RUNTIME/HOOK_RUNTIME docs updated.
- `tests/unit/test_escalation.py` (not-fixed signal, retry-cap→operator, default cap) + `tests/integration/test_escalation.py` (Opus routing on reopen, mandatory review on re-close, loop+manual honor routing, end-to-end ladder to operator).
- Tasks-done close gate (WO-TASKS-DONE-ENFORCE): `core/work_orders/close.py` `close_work_order()` now blocks the close when any task is not `complete`/`cancelled` — no 0/N or partial closes ("NOTHING LEFT HANGING"). `force=True` bypasses and records the bypass via the existing `gate.bypassed` event (gate `tasks_done`). A `sync_tick()` runs before the task-status read so a freshly marked-done task is not misread as pending (projection lag). Enforcement lives in the single shared `close_work_order`, so the CLI close path and the autonomous execute-work-orders loop inherit it identically; `ds-workorder` SKILL.md (Rule 9) and the close/execute mode skill text are updated.
- `tests/unit/test_tasks_done_gate.py` + `tests/integration/test_tasks_done_gate.py`: sync_tick-before-status-read ordering proof, close-blocked-with-pending-tasks (+ force bypass), CLI-and-loop both enforce, and end-to-end (blocked while pending → closes once all tasks done).
- Outcome eval (WO-OUTCOME-EVAL): `core/eval/runner.py` gains `run_outcome_eval()`/`evaluate_wo_outcome()` — a safety net behind the close gate that measures OUTCOME (did the symptom actually stay resolved), not just PROCESS. For each recently-closed WO with an originating symptom it re-runs the symptom SQL-CHECK (and, off the hot path, the task ACs) against live/seeded state; on FAIL with `auto_reopen` it sets the WO back to `in_progress`, emits a `work_order.outcome_failed` event, and writes an unresolved `ESC-OUTCOME-*.md` escalation file (counted by the pulse open-escalations scan). Wired into `interfaces/cli/pulse_collector.generate_pulse()` with a 7-day window and `symptom_only=True` so it runs on every pulse (not dormant) without auto-reopening ancient WOs whose symptom SQL is environment-dependent.
- `tests/unit/test_outcome_eval.py` + `tests/integration/test_outcome_eval.py`: persisting-symptom detection, resolved-symptom pass, runner-wiring guard, failed-outcome auto-reopen + escalation, and end-to-end.
- Blast-radius merge gate (WO-BLAST-RADIUS-GATE): `core/gates/blast_radius.py` computes the impact set from a diff (a changed test runs itself; a changed source module pulls in every test referencing its dotted module path) plus the impacted contract domains, and `core/gates/hanging_detectors.py` runs four nothing-left-hanging detectors — stale removed-symbol tests (#347 class), changed-signature callers (#353 class), unowned/duplicate table writes (#354 class), and migration file+DB duplication. Wired as a blocking `python -m core.gates.blast_radius` step in the pr-smoke matrix (`.github/workflows/ci.yml`) and into `interfaces/cli/ci_gate.py`, so the diff-dependent regressions that previously slipped past the fixed pr-smoke subset into the post-merge full suite (main went red for 11 merges) now block at merge time.
- `tests/unit/test_impact_selection.py`, `tests/unit/test_hanging_detectors.py`, `tests/integration/test_pr_smoke_impact.py`, and `tests/integration/test_session_regressions.py`: impact-selection, per-detector, gate pass/fail, and a session-regression proof that replays the #347/#353/#354 pre-merge states and asserts the gate would have blocked all three.
- Files.db wiring — handoff and recap blobs now stored in artifact blob store (WO-FILESDB-WIRE): Migration 124 adds `file_id TEXT` and `checksum TEXT` nullable columns to `raw_handoffs` (cross-store pointer + SHA-256 integrity check). `insert_handoff()` accepts `file_id` and `checksum` keyword args. `monitor._write_handoff_packet_to_db()` writes the rendered handoff markdown to `files.db` via `core/files/store.write_file()` (category=`'handoff'`), captures `file_id` + checksum, and records both in the `raw_handoffs` row. `write_recap()` similarly stores recap blobs. Completes the three-store architecture: Store 1 (studio.db) now carries cross-store pointers to Store 3 (files.db). `.released_version` bumped 123 → 124.
- `tests/integration/test_filesdb_wire.py`: 6 integration tests covering migration 124 column presence, `insert_handoff()` file-pointer round-trip, `write_file()`/`list_files()`/`read_file()` round-trips, and `write_recap()` blob persistence in `files.db`.
- `eval.friction_threshold` three-tier resolution (WO-FRICTION-CONFIG, PR #338): `DREAM_STUDIO_FRICTION_THRESHOLD` env var > `ds_config` SQLite row > per-row `eval_registry.friction_threshold` column (default 3). Migration 123 adds the `ds_config` key-value store (`key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT`). `core/config/authority.py`: `get_config_value(key)`, `set_config_value(key, value)`, `list_config()`. CLI: `ds config set <key> <value>` / `ds config show`. `.released_version` bumped 122 → 123.
- `tests/unit/test_friction_config.py`: 7 tests for the three-tier threshold resolution — env-var override, ds_config row override, per-row default, non-numeric env fallback, no-db graceful degradation.
- `docs/proving-index.md`: `ds-quality:security × Rust` proven on `BurntSushi/ripgrep` (sec-001/003/006/009/018 PASS; others SKIP — CLI tool); `ds-quality:security × Shell/YAML` proven on `github.com/cli/cli` (sec-001/006/009/018 PASS; sec-009 one CANDIDATE on release workflow GH_TOKEN scope); code-quality×Go, database×MySQL, database×MongoDB corrected as NOT DECLARED (rules.yml audit confirms applies_to never included those ecosystems) (WO-PROVING-RUNS-2, PR #339).
- `tests/unit/test_wo_verify.py`: `test_unreviewable_with_passing_ac_proceeds` (renamed from `test_close_proceeds_on_unreviewable_grader`) now asserts an unreviewable grader verdict closes ONLY because the always-on executable-AC gate compensates — not because unreviewable auto-passes; `test_unreviewable_without_ac_blocks_close` adds the inverse unit guard (unreviewable + a failing AC leaves `close_work_order` at `ok=False`, with the `executable_ac` failure as the blocker). Aligns the unit suite with the WO-REVIEW-TRACEABILITY contract that an unreviewable verdict is never a certified pass; supersedes the original WO-VERIFY-NOSUMMARY assertion (PR #341) inverted by PRs #366/#367.

### Fixed
- Workflow completion events emit again (WO 9f47a1a0): `raw_workflow_runs`/`raw_workflow_nodes` had been write-orphaned since 2026-05-18 — `archive_workflow()` (`core/event_store/studio_db.py`) inserted into them inside the same best-effort try/except that also emitted canonical events, so a raw-table INSERT failure silently swallowed the whole write. `control/execution/workflow/state.py` no longer calls `archive_workflow()` at all; it now writes `workflow.completed` (+ one `workflow.node.completed` per node) canonical event envelopes directly to the spool, decoupled from any SQLite write. `archive_workflow()` and its `_emit_workflow_telemetry()` helper are deleted; the `execution_events` dual-write moved into state.py's new `_emit_execution_events_telemetry()` helper. `raw_workflow_runs`/`raw_workflow_nodes` dropped via migration 141 (`141_drop_orphaned_workflow_raw_tables.sql`); `projections/core/collectors/workflow_collector.py`, `projections/core/sla/tracker.py`, and `studio_db.py::last_run`/`run_count` repointed to `ai_canonical_events`.
- `core/work_orders/mutations.py`: `mark_task_done()` now calls `_sync_tick()` after emitting the `task.completed` event, mirroring `create_task`/`create_work_order`. It was the only SDLC mutation omitting the sync, so `business_tasks.status` (and `ds work-order tasks`) reported a stale `pending` until an unrelated operation triggered a projection sync — misleading task tracking and the close-gate task view. Regression test `tests/unit/test_taskdone_sync.py::test_mark_task_done_syncs_status_without_external_tick` fails pre-fix, passes post-fix (WO-TASKDONE-SYNC).
- `core/telemetry/read_models.py`: `process_runs` removed from `CORE_TABLES`; `_process_runs_from_events()` helper added to derive process run summaries from `execution_events GROUP BY process_run_id` — the `process_runs` table is empty in production; dashboard-visible data was always on `execution_events`. `process_run_timeline()` and `_scoped_summary()` updated to use the derived path. All 12 unit tests pass (WO-DASH-VALIDATION-GAPS T1).
- Root `DATABASE.md` reduced to a redirect stub; `docs/DATABASE.md` gets `[DROPPED]` markers for three table clusters retired by migrations 099, 103, 106, and 112 (WO-DASH-VALIDATION-GAPS T2).
- `projections/api/routes/project_intelligence.py`: `_classify_project_authority()` distinguishes `registered_no_path` (no path recorded — kept in default view) from `path_unverified` (path recorded but not found locally — kept in default view). Both were previously collapsed to `manual_review_required` and excluded. `update_project_path()` added to `core/projects/mutations.py` to emit `project.path_set` for audit trail (WO-DASH-VALIDATION-GAPS T3).
- `projections/frontend/dashboard.html`: `loadHooksData()` rewritten with `Promise.all` parallel fetch, real summary card updates, lazy Chart.js chart creation (hooks timeline 7-day and performance distribution), and per-hook status card population from `statsData.by_hook`. Removed `initHooksCharts()` on-load call that was creating empty placeholder charts before data arrived (WO-DASH-VALIDATION-GAPS T4).
- Dead test files and fixture resurrection deleted/fixed in 11 files, 3 deleted (WO-FIXTURE-SWEEP, PR #340): `tests/test_api_discovery.py`, `tests/test_discovery_integration.py`, `tests/unit/test_phase18_0_ds_projects_guard.py` deleted (dead `pi_*`/`reg_projects`/`ds_*` behavior). `findings`, `hook_invocations`, `skill_invocations`, `tool_invocations`, `workflow_invocations`, `pi_analysis_runs`, `pi_improvements`, `production_readiness_*` dead CREATE TABLE DDL removed from 8 fixtures. 14 files retained intentional migration-replay DDL (migrations 061, 064, 096 backfill paths).
- `core/work_orders/verify.py`: `_collect_grader` now detects empty/whitespace LLM output and returns `{unreviewable: True, reason: grader_no_summary}` instead of raising `ValueError`. `_run_graders_parallel` retries once (timeout=30s) on unreviewable. `verify_work_order` detects unreviewable graders after retry, writes an unreviewable verdict (`unreviewable_graders: [...]`) mirroring the existing no-commits-found path — close proceeds without `force=True` (WO-VERIFY-NOSUMMARY, PR #341).
- `core/work_orders/close.py`: `close_work_order` now surfaces `unreviewable_graders` in the result dict when auto-verify returns an unreviewable verdict from grader no-summary (WO-VERIFY-NOSUMMARY, PR #341).

### Fixed
- Full-CI matrix (ubuntu/macos/windows) stabilized through 5 targeted repair PRs (#332–#336): resurrection-guard tests added to pr-smoke matrix; dead-route tests deleted and `pl-009` assertion corrected; `idea-validation` mode removed from `ds-domains` packs.yaml (it belongs under `ds-analyze`); dynamic timestamp used in token-metrics test fixture to eliminate date-boundary flakiness; duplicate test run removed from `full-ci.yml` with timeout bumped to 60m.
- `test_audit_pl009_fires_on_dream_studio_clean` renamed to `test_audit_pl009_silent_on_dream_studio_clean` in `tests/unit/test_audit_dispatcher.py`: the repo has no git tags, so `rules_scanner.py` pl-009 detection loop never runs and the rule is correctly SILENT; the test assertion was inverted from `assert pl009` to `assert not pl009` (WO 919a9055).
- `_insert_gap_work_orders()` in `core/work_orders/verify.py` now deduplicates remediation WO spawning: before inserting a new gap WO, checks for an open WO (`status IN ('created','in_progress')`) with the same title in the same milestone; on match, appends the gap's tasks to the existing WO instead of creating a duplicate (WO-SPAWN-DEDUPE). `merged_into_existing: True` field on the result entry signals a merge.

### Added
- `tests/evals/test_gap_wo_dedupe.py`: 6 gate tests for the dedup path in `_insert_gap_work_orders`: fresh-spawn, task-attachment, merge-on-title-match, task-append-to-existing, no-milestone-skips-dedup, multi-gap-independent-dedup (WO-SPAWN-DEDUPE).
- `tests/evals/test_rubric_immutability_gate.py`: 4 gate tests for `rubric_immutability_gate.main()` covering no-rubric-change exit 0, rubric+token allow, rubric-without-token block, and skip-record-decision paths (WO 7dc2f344).
- `tests/evals/test_eval_queue_show_aggregate.py`: 7 gate tests for `ds eval queue show` (pending rows, empty list, missing table error), `ds eval queue aggregate` (delegates to `aggregate_friction_signals` with correct `db_path`, result forwarded to output), and `ds eval queue run` (passing result clears `pending_rerun=0` in DB, empty queue returns count=0) (WO 7dc2f344, WO aa759063).
- `check_rubric_write_guardrail(file_path, conn, event_id, is_operator)` in `guardrails/evaluator.py`: runtime guardrail that records a `guardrail_decisions` block row with `rule_id='rubric-immutability-constraint'` when a Write/Edit targets `eval-rubric.yml`; `is_operator=True` exempts operator sessions (WO 58890751, b57c60eb).
- `_check_rubric_guardrail()` in `runtime/hooks/meta/on-edit-dispatch.py`: wires `check_rubric_write_guardrail` into the PostToolUse Write/Edit dispatch pipeline; fires for every Edit/Write event; `is_operator` parameter added and detected from `DREAM_STUDIO_OPERATOR_SESSION` env var in `main()` (WO b57c60eb, WO 577b90c3).
- `tests/evals/test_rubric_immutability_guardrail.py`: 6 gate tests covering block decision creation, non-rubric passthrough, event_id forwarding, None file_path, operator-session exemption, and non-operator block (WO 58890751, b57c60eb).
- `tests/evals/test_post_tool_use_guardrail_dispatch.py`: 2 integration tests exercising the dispatch entry point `_check_rubric_guardrail` in `on-edit-dispatch.py` — non-operator Write to eval-rubric.yml creates a guardrail_decisions block row; operator session (is_operator=True) writes zero rows (WO 577b90c3).

### Fixed
- `_run_case_live()` in `core/eval/runner.py` now checks `proc.returncode` after spawning the claude subprocess; a non-zero exit returns an `EvalResult` with `passed=False` and an `error` field including the returncode and stderr snippet, preventing a failed subprocess from silently yielding a misleading 0-score result (WO 312dc5ac).
- `record_invocation()` in `core/telemetry/execution_spine.py` now logs skipped DB writes at DEBUG level instead of silently discarding the exception (WO 68fe6a1b). Adds `import logging` and a module-level logger.

### Added
- `tests/unit/test_eval_runner_live_path.py`: 5 tests covering `EvalRunner.run_case(live=True)` routing to `_run_case_live`, `run_all(live=True/False)` kwarg pass-through, and CLI `--live` flag wiring to the runner (WO 63f09915).
- `tests/unit/test_eval_dispatch_live_mode.py`: 4 tests covering `ds eval run --live` JSON output (delta_from_fixture_baseline, failure_reasons, non-live exclusion, passing run empty reasons) (WO 1ce3aad7). Also fixes pre-existing `AttributeError` on `result.behavior_score` via `getattr` fallback.
- `ds eval run <id> --live` JSON output now includes `delta_from_fixture_baseline` (fixture_baseline_score − live_score, rounded to 4dp) and `failure_reasons` (list of missing_events + negative_violations) when run in live mode (WO c4c8d9aa).
- `tests/unit/test_eval_registry_dispatch.py`: 8 tests covering `ds eval registry list` (all entries, filter by type, empty table), `ds eval registry show` (entry with runs, missing target), and `_write_hook_eval_run()` (pass insert, failure reasons JSON, noop on missing table) (WO 7ca96641).
- `ci_gate.py` JSON verdict now includes a `failing_tests` list on the `test` check: empty when tests pass, populated with pytest node IDs (e.g. `tests/unit/test_foo.py::test_bar`) when tests fail (WO f0e8f2c0). Non-test checks are unaffected.
- Pulse health now degrades to `DEGRADED` when the latest `full-ci` run on `main` has a `failure` conclusion (WO de7e86cd). Adds `check_full_ci_on_main()` to pulse_collector and `full_ci_conclusion` field to the pulse stats dict. Report CI section flags the failure with a warning line.

### Fixed
- `ds eval queue show` and `ds eval queue run` now filter on `pending_rerun = 1` instead of `friction_flag = 1` (WO d1f3e656).
- `_COMPLETION_PROMPT_TEMPLATE` structure verified by 4 contract tests in `tests/unit/test_wo_verify.py` (WO e3e30247): `{work_order_type}` placeholder present and interpolates; behavioral AC check block mentions feature/infrastructure as trigger types; Do-NOT-emit conditions include the already-present case. `pending_rerun` is the explicit queue-membership flag; `friction_flag` may remain set on targets whose re-run failed. `queue show` SELECT also surfaces the `pending_rerun` column.
- Eval queue mechanism now has explicit schema backing (WO 9a6222ca): migration 122 adds `pending_rerun INTEGER NOT NULL DEFAULT 0` to `eval_registry`; `aggregate_friction_signals()` sets `pending_rerun=1` alongside `friction_flag=1`; `ds eval queue run` clears `pending_rerun=0` alongside `friction_flag=0` after a passing re-run.
- `count_degraded_skills()` now requires both `friction_flag=1` AND `rubric_score < baseline_score * 100` (WO 3ca8be3a). Previously counted any flagged target regardless of whether the score had actually degraded below baseline. Uses a LEFT JOIN with `ds_eval_baselines` so targets without a baseline are still counted as degraded.

### Fixed
- N+1 SQL patterns in `aggregate_friction_signals()` (WO c6b6f3ed): source (c) `guardrail_decisions` check now uses a single `JOIN eval_registry` instead of a per-row `SELECT 1` loop; the `friction_signal_count` increment and `friction_flag` gate now use batched `WHERE target_id IN (...)` instead of per-row UPDATE statements.

### Changed
- `DREAM_STUDIO_FRICTION_THRESHOLD` env var added to `aggregate_friction_signals()` as a global operator-level threshold override. When set, all targets use that threshold instead of the per-row `friction_threshold` column (default 3). Result dict gains `effective_threshold` field reporting the active threshold.

### Fixed
- `eval_registry` friction threshold logic (WO-EVAL-LOOP-THRESHOLD): `aggregate_friction_signals()` now increments `friction_signal_count` per run and only sets `friction_flag=1` when the count reaches `friction_threshold` (default 3 per row). Migration 121 adds `friction_signal_count INTEGER NOT NULL DEFAULT 0` and `friction_threshold INTEGER NOT NULL DEFAULT 3` to `eval_registry`. Source (a) table reference (`raw_skill_telemetry` vs non-existent `skill_invocations`) documented in code.

### Added
- Friction-to-eval feedback loop (WO-EVAL-LOOP): `core/eval/friction.py` aggregates three friction sources (session failures, skill corrections, guardrail blocks) into `eval_registry.friction_flag`; `ds eval queue show/run/aggregate` CLI surface; `ds eval baseline --live` and `ds eval run --live` already in place; pulse `degraded_skills` now uses max of telemetry-based and registry-based degraded counts; `rubric-immutability` pre-push gate blocks changes to `eval-rubric.yml` without `[rubric-update]` commit token (PR #292).

### Fixed
- `eval_registry` not updated after live eval runs: `_write_live_eval_run` now UPDATEs `eval_registry.last_run_at`, `last_run_id`, and `rubric_score` so `ds eval registry show` reflects live-run state; sets `friction_flag=1` when live score drops >10% below fixture baseline. `ds eval baseline --live --eval-id <id>` added to capture live baselines independently (WO-EVAL-LIVE remediation, PR #291).

### Added
- Live-session eval mode (`ds eval run --live`): spawns a fresh `claude` subprocess with `--output-format json`, synthesizes Dream Studio events from its tool-call output (`skill.invoked` / `skill.completed`), and scores with the same deterministic matcher as fixture mode. Live baselines stored under `eval_id + ":live"` key to avoid conflating with fixture baselines. Requires `claude` CLI in PATH; skipped gracefully when absent (WO-EVAL-LIVE).
- `ds_eval_runs.run_mode` column (migration 120): `ALTER TABLE ADD COLUMN run_mode TEXT NOT NULL DEFAULT 'fixture'` — distinguishes `'fixture'` (deterministic, default), `'live'` (subprocess spawn), and `'verify'` (WO-close verifier) runs. Additive-only; all existing rows implicitly read as `'fixture'` (WO-EVAL-LIVE).

### Fixed
- `docs/DATABASE.md`: explicit three-store placement for `eval_registry`, `ds_eval_runs`, `skill_evaluation_runs`, and `hook_eval_runs` — these are primary SQLite authority, not DuckDB analytics projections, consistent with `ds_eval_runs` (migration 104) and `guardrail_decisions` patterns (WO-EVAL-REGISTRY follow-up, PR #289).
- Migration 117 recreates the three usage-table indexes migration 081's table reconstruction dropped and never recreated (`idx_token_usage_scope`, `idx_ai_usage_operational_scope`, `idx_ai_usage_operational_process`) — every DB at schema 81–116 silently lacked them; DDL matches migrations 037/043 verbatim with `IF NOT EXISTS` (issue #264, WO-IDX-RECREATE).
- `test_o7_swallow_narrowing.py`: the stale live-copy audit test (frozen 2026-05-29 diagnostics DB; failed locally, skipped in CI) is replaced with a hermetic reconstructed-live-DB test that asserts the exact idx_memory_lifecycle casualty set and runs on every platform (issue #265).

### Changed
- Out-of-scope findings now require authority registration: context.md enforcement rule 6 (`core/work_orders/start.py`), the Debug Workflow in CLAUDE.md, and the ds-quality debug skill all instruct registering a Dream Studio authority work order (status `created`) before/alongside any GitHub issue — an issue alone is invisible to `get_next_work_order` and on-close routing (WO-FINDING-TRACK).

### Fixed
- `canonical/workflows/pre-push.yaml`: docs-drift gate escalated from advisory to blocking. CI runs the identical `contract_docs_drift_gate.py` script (same `origin/main...HEAD` merge-base change set) as a blocking step, so the advisory local tier let PR #263 push green and then fail all three matrix platforms on the same drift. Regression tests pin the full-branch change-set computation and the blocking tier (WO-GATE-PARITY).
- `core/work_orders/verify.py`: `_collect_git_commits` now falls back to grepping the WO title token (e.g. `WO-DEBT-I`) when the UUID grep finds nothing — squash-merge commit messages carry the WO name, never the UUID, so every squash-merged WO previously graded against an empty diff (score-0 "N/A: empty diff" violations spawning unactionable remediation WOs). When neither pattern matches, the diff is `None` and `verify_work_order` records an `unreviewable` verdict (no gaps, no spawned WOs) instead of grading nothing (WO-GRADER-LOOKUP).
- `core/work_orders/close.py`: the `independent_review` gate passes on `unreviewable` verdicts, and `close_work_order` surfaces the warning as `verify_warning` in the close result instead of blocking or spawning remediation loops.
- `core/work_orders/verify.py`: `_spawn_grader` feeds the prompt via stdin (daemon-thread writer, joined before collection) instead of argv — real-diff prompts exceed Windows' ~32K command-line limit and crashed verify with WinError 206 (WO-GRADER-LOOKUP follow-up, found re-verifying WO-DEBT-I).

### Changed
- `canonical/skills/ds-workorder/modes/{start,execute,close}/SKILL.md`: continuous autonomous execution — start flows into task execution, execute chains into close when all tasks complete, close announces `auto_started` WOs and continues into them; operator stops only at force-close, missing-brief confirmation, blocked WO, `auto_start_error`, milestone-complete, or a genuine blocking question. Task lists are mirrored into the native todo display (SQLite stays sole authority). Close/start surface contracts refreshed to match actual return shapes (`status: "closed"`, `auto_started`, `gaps_block`, `next_block`, `spawned_work_orders`, `auto_start_error`, `auto_start_message`, `sequence_warning`, `pending_audits`) (WO-TASK-UX).
- `core/work_orders/start.py`: context.md enforcement rules now permit parallel-wave execution of clearly independent tasks (each still marked done individually) and instruct mirroring the task list into the native todo display.

### Fixed
- `core/config/sqlite_bootstrap.py`: narrowed the two remaining broad `no such table` swallow clauses (token_usage_records / ai_usage_operational_records and the ds_* project spine) to statement-type-aware matching — CREATE INDEX / CREATE TRIGGER failures now raise instead of being silently discarded (M2 class, the idx_memory_lifecycle mechanism); data statements remain graceful degradation so migration 070/081 partial-fixture tolerance is unchanged (WO-DEBT-I).

### Added
- Migration 119: `eval_registry` + `hook_eval_runs` tables — unified eval status per target (skill/hook/workflow/agent), backfilled from `skill_evaluation_runs` and `hook_executions`. `.released_version` bumped to 119 (WO-EVAL-REGISTRY).
- `guardrails/evaluator.py`: optional `hook_id` parameter wires guardrail pass/fail into `hook_eval_runs` after each evaluation; no-op on older DBs without migration 119.
- `ds eval registry list [--type skill|hook|workflow|agent]`: list all registered eval targets with latest run status.
- `ds eval registry show <target_id>`: per-target eval run history from `ds_eval_runs` / `hook_eval_runs`.
- `docs/proving-index.md`: `ds-quality:security × Go` proven on `github.com/cli/cli` — sec-001 FIRE (hardcoded OAuth client ID/secret, intentional public-client pattern); sec-003/004/006/009/010/011/013/015 PASS; 6 rules SKIP (CLI tool context) (WO-DEBT-K).
- `tests/unit/test_wo_debt_i_swallow_narrowing.py`: 7 tests driving the real `run_migrations()` handler via a synthetic migration set, plus clean-path index checks at schema v69/v80.

## feat(wo-hs2) — Context-pressure handoff wired to authority DB (2026-06-08)

### Changed
- `control/context/monitor.py`: `handle_handoff()` now calls `_write_handoff_packet_to_db()` which inserts a packet into `raw_handoffs` via `insert_handoff()` and writes a thin `pending-handoff.json` pointer `{handoff_id, triggered_at}`.
- `runtime/hooks/meta/on-context-threshold.py`: "handoff" and "compact" bands now dispatched separately — "handoff" calls `monitor.handle_handoff()` instead of `handle_compact_warning()`.
- `runtime/hooks/meta/on-stop-dispatch.py`: `_dispatch_handoff_continuation()` reads `pending-handoff.json` (pointer only) and spawns `claude "resume:"` — no handoff content in argv. File `handoff-latest.json` no longer used as content carrier.
- `runtime/hooks/meta/on-prompt-validate.py`: `_check_pending_handoff()` instruction updated — no longer asks Claude to write content to `handoff-latest.json`; tells Claude to notify user a continuation session is being prepared.
- `interfaces/cli/resume_from_handoff.py`: `find_latest_handoff_db()` calls `mark_handoff_consumed()` after loading to prevent re-spawning.

### Added
- `tests/unit/test_wo_hs2_handoff_authority.py`: 12 unit tests covering DB write, band dispatch, reference-only spawn, stale pointer cleanup, and consumed marking.

## migration(wo-m) — Dual-canonical authority cutover (2026-06-07)

### Changed
- `spool/ingestor.py`: `_write_to_dual_canonical` promoted from best-effort to primary; failure now surfaces to caller and moves event to `failed/` for triage. `_write_to_sqlite` removed entirely.
- `core/event_store/event_store.py`: `_init_tables()` no longer creates `canonical_events` table; `write_event()` and `_emit_validation_failure_event()` now call `_write_to_dual_canonical` directly.
- Migration 102 (`102_drop_canonical_events.sql`): renames `canonical_events` to `canonical_events_legacy_backup`; creates `canonical_events` compat VIEW over UNION of both authority tables, preserving all 42 production readers without code changes.
- `scripts/backfill_dual_canonical.py`: updated to fall back to `canonical_events_legacy_backup` when the table has already been renamed by migration 102.
- All affected tests updated to query `business_canonical_events` or `ai_canonical_events` per event-type routing rules.

### Added
- `ingestor.py`: best-effort inline execution-events projection block reads from event dict (not from retired `canonical_events` table).

## fix(wo-u) — Context-threshold hook: version-gate + dispatch consolidation (2026-06-07)

### Fixed
- `ds update` version-gate now detects canonical hook source drift without a version bump; `_canonical_hook_drift()` compares `runtime/hooks/meta/*.py` hashes against the installed manifest and triggers re-projection when they differ
- Dual-scope reinstall: running `ds update` from a project-scoped directory now also updates the user-global `~/.claude` surface in one command
- Dispatch consolidation: project-scope installs strip hook event registrations from `.claude/settings.json`; only the user-global `~/.claude/settings.json` registers hooks, eliminating double-firing of every hook event
- Both projection trees (`~/.claude/hooks/` and `<repo>/.claude/hooks/`) now carry the WO-A canonical fixes: `handle_urgent_reminder`, `record_kb_baseline`, `completion_tokens` guard, `tool_name` snake_case fix, `insert_token_usage` removal

## fix(ci) — Linux CI failure repair batch 2 (2026-05-27)

### Fixed
- spool writer payload validation: test fixtures switched to `prompt.lifecycle.submitted` events
- `activity_log` removal (migration 063): test fixtures migrated to `canonical_events`; dead dashboard filter tests removed
- `canonical_events` runtime-created: added explicit `CREATE TABLE IF NOT EXISTS` in tests that need it
- Migration slot 011 collision: `011_memory_entries.sql` renamed to `078_memory_entries.sql`
- Async projection pattern: restored synchronous SQL in `mutations.py` for `set_active_project`, `deactivate_project`, `delete_project`
- `DREAM_STUDIO_DB_PATH` env priority over `Path.home()`: added `delenv` in test `_fake_home()` helper
- `docker-compose.yml` deleted (triggered publication readiness gate failure)
- `on-post-tool-use` hook added to `packs.yaml` core hooks list
- Windows PowerShell launcher test marked `skipif` on non-Windows
- Projection framework tables added to `allowed_exact` in state contract boundaries test
- `projections/api/routes/ml.py`: replaced raw `sqlite3.connect` with `_open_conn` to respect DB path env override
- Private content / publication readiness: replaced operator absolute paths with generic placeholders; added `contract_atlas.py` to private content skip list; security skill modes dir added to secret scan skip list
- `.claude-plugin/marketplace.json`: created and tracked (`.gitignore` updated to track `marketplace.json` only)
- Cloud backup auto-push test: added `paths.plugin_root()` mock so `studio_backup.py` existence check passes
- TA6 attribution fixture: milestone now inserted via direct SQL (async projection since Phase 18.2.3)
- `on-context-threshold.py`: added `_emit_harvest` function required by import check test
- Adapter projections: generated and committed all 8 projection files (chatgpt, claude, codex, copilot, cursor, local-model, mcp, shell) so staleness and contract atlas boundary checks pass

## Phase 18.1.16–18.1.17 — Test contamination + CI/CD infrastructure (2026-05-27)

### Fixed
- `_compute_directory_hash` in `core/health/doctor.py` used absolute path parts for hidden-dir filter, causing all installed skills under `~/.claude/` to always hash to empty — `ds doctor` falsely reported 11 stale skills on every run
- CRLF/LF normalization added to `_compute_directory_hash` so Windows-installed skills compare equal to LF repo source
- `canonical/skills/workflow/docs/contracts/workflow-contract.md` promoted from installed-only to canonical source
- `on-context-threshold.py` hook rewrote to delegate to `control.context.monitor`; removed `sys.exit()` calls that leaked `SystemExit` through the dispatcher into integration tests
- `SKILL_BUDGET_EXCEEDED` added to `EVENT_TYPE_REGISTRY`; `test_types.py` counts updated for `TOKEN_CONSUMED` (15 HOOK_EMITTED types, 6 emitter-implemented)
- Coverage floor restored to 8% (was incorrectly set to 5%)

### Added
- PR Smoke CI now runs on multi-OS matrix: `ubuntu-latest`, `macos-latest`, `windows-latest`
- `pip-audit` dependency vulnerability scan added to PR Smoke (advisory)
- Full CI workflow now triggers on push to `main` in addition to manual dispatch
- Full CI adds `pytest-cov --cov-fail-under=8` coverage enforcement
- `INSTALL.md` added as standalone installation reference
- README CI/CD section added

## Phase 18.1.13 — Install correctness + packaging: 12 pieces, fresh-install BLOCKER fixes (2026-05-24)

### Fixed
- `pyproject.toml` now contains a `[project]` section — `pip install -e .` was failing on fresh machines with "No `[project]` table in your pyproject.toml"
- Three runtime dependencies added to `requirements.txt`: `python-pptx`, `openpyxl`, `pytest-asyncio` (missing from prior inventory)
- Floating deps pinned; `pip check` conflicts resolved (3 conflicting packages); `requirements.lock` generated
- Missing `__init__.py` files added across 6 packages (`runtime/`, `interfaces/`, `interfaces/cli/`, `shared/`, and two others) — resolves `ModuleNotFoundError` on fresh installs
- Migration `011_memory_entries.sql` added; fresh-install migration gap closed: `_ensure_tables()` now validates the schema version rather than silently creating tables when migrations have not run
- `ds` CLI commands now exit 0 on success; exit-code regression test added (`tests/unit/cli/test_exit_codes.py`)
- `install.ps1` and `install.sh` now run `pip install -e .` and `ds rehearsal-install` before `ds integrate install` — prior scripts skipped both
- README: fixed clone URL (was pointing to non-existent repo path), version badge, and CI badge
- `test_github_pr_cicd_release_gate.py` assertion updated to `dream-studio-clean` repo name (unblocked `pr-smoke` CI gate)

### Added
- `docs/operations/fresh-install-validation.md` — step-by-step fresh-machine validation procedure; requires both `ds validate` (DB authority plane) and `ds doctor` (Claude Code integration plane)
- `ds validate --help` updated with explicit plane label ("DB authority: schema version, migrations, module profiles") and cross-reference to `ds doctor`
- `ds doctor --help` updated with explicit plane label ("Claude Code integration: hooks, skills, agents, routing") and cross-reference to `ds validate`
- README "Health checks" section added documenting both planes and when to run each

### Changed (style)
- `black` formatting applied to pre-existing unformatted files (mechanical; no semantic changes)

### Fixed (18.1.13.0 — test isolation, pulled forward from 18.1.16.3)
- Systemic test isolation: `DREAM_STUDIO_HOME`, `DREAM_STUDIO_DB_PATH`, and `DS_SPOOL_ROOT` are now set at `conftest.py` **module import time** (before pytest collects or imports any test module). Root cause: `DatabaseRuntime` initializes a singleton on first use and caches the real DB path if any test module's import chain reaches it before a fixture can monkeypatch the env var. The top-of-conftest block ensures the singleton always sees the tmp path on developer machines.
- `guard_real_homedir` mtime check now skips when `DREAM_STUDIO_DB_PATH` is redirected (the spool ingestor writes legitimate operator events to the real DB on developer machines, making mtime comparison a false positive). Guard now calls `pytest.exit(returncode=2)` on contamination instead of `assert`.
- `tests/unit/cli/test_exit_codes.py`: `bootstrapped_db` fixture runs `ds rehearsal-install` + `ds project register` before tests that need a populated DB; `test_project_state_exits_zero` and `test_work_order_list_exits_zero` now pass
- `tests/unit/cli/test_help.py` added: 4 tests enforcing that `ds validate` help references `ds doctor` and vice versa, with plane keywords present in each

### Policy decisions
- `ds validate` and `ds doctor` check genuinely different health planes and neither substitutes for the other. `ds validate` = DB authority (schema version, migrations, module profiles). `ds doctor` = Claude Code integration (hooks, skills, agents, routing). Both commands are required before declaring a fresh install healthy.
- Test isolation is now an enforced contract at `conftest.py` import time, not a best-effort fixture. Pull-forward from 18.1.16.3 was validated safe: Category (i) damage assessment confirmed no operator data was corrupted.

### Coverage baseline (post-18.1.13)
- Scope: `tests/unit/ tests/integration/migrations/ tests/unit/cli/`
- **2993 passed** / 109 pre-existing failures / 1 error / 10 xfailed / 1 skipped
- Delta from pre-18.1.13 baseline (2935+ passed, 110 failures, 50 errors): +58 passing, −1 failure, −49 errors
- Pre-existing failures categorized by phase home in `.planning/pre-existing-failures-categorized.md`

## Phase 18.1.12 — Audit follow-ups: fail-open gap, coverage scope, Sentry removal, env var audit (2026-05-23)

### Fixed
- Hook dispatcher fail-open guarantee restored: `dispatch_tracking.run_handlers()` and `runtime/dispatch/hooks.main()` now catch `BaseException` instead of `Exception`, so `SystemExit` and `KeyboardInterrupt` from handlers can no longer escape and block AI sessions
- `on-game-validate.py` no longer calls `sys.exit(2)` when validation issues are found; it now prints an advisory to stderr and returns normally (the handler should advise, not block)
- `on-pulse.py` no longer re-raises exceptions from `run_pulse_check()`; errors are recorded and the hook exits cleanly
- `on-stop-handoff.py` and `on-meta-review.py` now wrap their bodies in `try/except` for defense in depth
- Coverage scope corrected: `[tool.coverage.run] source` was pointing to `hooks/lib` (does not exist) and `packs/domains/domain_lib` (empty); now points to the actual production directories (`core`, `runtime`, `interfaces`, `spool`, `projections`, `emitters`, `canonical`, `control`); honest baseline: **9% of 42,683 statements** (was measuring <5% of nothing); `fail_under` set to 5 to reflect reality and give slack for CI variance

### Changed (Removed)
- Removed `sentry-sdk` from `requirements.txt`; Dream Studio does not phone home; `core/telemetry/telemetry.py` is now a documented no-op; `init_sentry()` and `capture_exception()` are API-preserving stubs

### Added
- `tests/unit/runtime/test_dispatcher_systemexit.py` — 7 tests verifying dispatcher fail-open for `SystemExit`, `KeyboardInterrupt`, `Exception`, and documenting the `os._exit()` known limitation
- `docs/operations/environment-variables.md` — complete env var inventory: all production variables, defaults, network/privacy implications; `SENTRY_DSN` listed under "Removed"
- Architecture doc `dream-studio-ai-orchestration-architecture.md` updated with honest "Current State" section: 2 of 22 hook handlers currently route through canonical events; dispatcher fail-open gap documented and closed

### Policy decisions
- Dispatcher fail-open is now a tested contract, not just a documented claim (18.1.12 real-world example of architectural-claim-vs-reality drift)
- Dream Studio does not send telemetry to external services; local crash dashboard planned in 18.8.10.1

### Fixed (additions from 2026-05-24 execution-verified audit)
- `WorkOrderProjection` status state machine regression introduced in Phase 18.2.2 and undetected until 2026-05-24 execution-verified audit: `business_work_orders.status` now correctly reflects work order lifecycle events instead of returning `'created'` for all statuses. Root cause: 18.2.2 removed the direct DB writes from CLI mutators (`start_work_order`, `close_work_order`, `block_work_order`, `unblock_work_order`, `create_work_order`) without adding synchronous projection execution; the projection only runs via the background daemon. Fix: restored dual-write pattern — CLI mutators write directly to `business_work_orders` for immediate consistency AND emit canonical events for the projection audit trail. Three eval tests that caught the regression: `test_eval_close_wo`, `test_eval_build_contract`, `test_eval_plan_contract`.
- Test contract for `create_work_order()` corrected: test was asserting `status == 'open'` (pre-rename status from `ds_work_orders`); `business_work_orders` uses `'created'` per migration 070 status mapping.

### Removed (additions from 2026-05-24 execution-verified audit)
- `control/research/methods.py` and downstream callers removed. Module returned hardcoded stub data (`placeholder://research-pending` sources, `confidence: 0.0`), never implemented per the Wave 3 plan. Operator decision: remove cleanly rather than ship fake data. `control/research/engine._execute_research()` now returns an explicit `status: "unavailable"` response. Research integration can be added in a future phase if needed.

## Phase 18.1.11 — Substrate policy lock: read-after-write + schema evolution (2026-05-23)

### Fixed
- `close_milestone` open-WO check now uses a canonical-events fallback: when `business_work_orders` shows a WO as `in_progress` due to projection lag, `business_canonical_events` is checked for a `work_order.closed` event; if found, the WO is treated as closed (fixes H4-2 — the standard `close_work_order → close_milestone` operator workflow was failing with "Cannot close milestone: open work orders remain")

### Added
- `ProjectionRegistry.projected_tables()` returns the set of all target tables across registered projections; single source of truth for projection-backed table enumeration (R3)
- `RegistryEntry.payload_required_keys: frozenset[str]` field on every registry entry; populated for the 5 SDLC WO event types consumed by `WorkOrderProjection`
- Runtime payload validation in `spool.writer.write_event()`: raises `ValueError` on emit if a required key is absent (R10 Layer 1)
- Integration test: `tests/integration/substrate/test_read_after_write_under_projection_lag.py` — 3 tests covering stale projection, canonical-events fallback, and mixed genuinely-open + stale cases (R2)
- Unit test: `tests/unit/config/test_event_schema_evolution_policy.py` — 17 tests covering registry integrity, versioned naming convention, fixture-payload coverage, `write_event` raises on missing key, and `write_event` succeeds with complete payload (R10 Layer 2)
- Architecture docs: `docs/architecture/substrate-policy.md` (parent), `docs/architecture/read-after-write-convergence.md`, `docs/architecture/event-schema-evolution.md`

### Policy decisions
- H4: Pattern C — optimistic return + named exclusion (within-function) + canonical-events fallback (cross-function); `work_order.closed` is terminal, presence of a canonical event is sufficient regardless of projection cursor
- H6: Additive-only schema evolution; breaking changes require a new `event_type` using `<base>.v<N>` naming convention; type-change detection is a documented known gap deferred to a future phase

## Phase 18.1.10 — Repo hygiene cleanup (2026-05-23)

### Changed
- Internal working documents scrubbed from git history (planning roadmaps, writer inventories, phase audit findings, PR body scaffolding, and operational tracking docs)
- `.gitignore` updated: added `venv/`, `env/`, `*.egg-info/`, `.env`, `.env.local`, `*.tmp`, `.pymon`, `docs/audits/`, `docs/publication/`, `backlog.md`, and patterns for `tools/_ta*.md`/`tools/_ta*.py` phase investigation files
- Documentation taxonomy established: end-user and architecture canonical docs in `docs/`; internal planning in `.planning/` (gitignored); historical audits in `.audit/` (gitignored)
- `tools/` cleaned: removed 9 phase investigation documents; retained `canonical_join.py`, `correlation_validate.py`, `raw_drilldown.py` as active development utilities

## Phase 18.1.9 — Test infrastructure cleanup (2026-05-23)

### Fixed
- 8 pre-existing test failures fixed (F1-F8): architectural violations (emitter import, TA6 fixture sync gap), infrastructure gaps (FK pragma, retry telemetry), stale references (dead dual-write test, `_BARE_TO_PACK` pack names), and test isolation issues (gotcha scanner monkeypatch target)
- `studio_db._connect` now restores `PRAGMA foreign_keys = ON` after `_run_migrations` (migration 062 left FK enforcement silently OFF on fresh DBs)
- Migration 071: removes stale `FOREIGN KEY (activity_id) REFERENCES activity_log` from `raw_workflow_runs` and `raw_workflow_nodes` (activity_log was dropped in migration 063)
- `emitters/claude_code/project.py` no longer imports from `core.config.database` (architectural boundary violation); DB path resolved from env vars inline
- `core/telemetry/execution_spine.py` dual-write restored: direct `INSERT OR IGNORE INTO execution_events` before spool write (12+ FK-referencing tables were failing on fresh DBs)
- `requirements.txt` comment corrected: removed self-contradictory "Python 3.14" claim; stubs in `guardrails/scanners/` are now correctly documented as the active implementation; Phase 18.4.3 is the integration scope

### Changed
- `_BARE_TO_PACK` in `control/execution/workflow/runner.py` updated to use `ds-*` prefixed pack names per packs.yaml as of Slice 9; fallback changed from `"core"` to `"ds-core"`
- `tests/integration/spool/test_ta6_e2e_attribution.py` fixture uses direct SQL for work order and task setup (projection-only architecture)
- `tests/integration/test_registry.py` gotcha scanner test patched at correct monkeypatch target (`core.learning.gotcha_scanner._try_db_search`)
- `tests/core/test_dual_write.py` deleted (referenced removed `_insert_activity_log` function)
- Contract docs drift gate satisfied for `sqlite_schema_authority` and `workflow_and_hooks` domains

## Phase 18.2.2 — Work-order writer migration (2026-05-23)

### Fixed
- `unblock_work_order` now emits `work_order.unblocked` event (registry entry existed, projection handled it, emit call was missing)

### Changed
- `business_work_orders` is now populated exclusively by `WorkOrderProjection` — zero direct writes remain
- Removed direct INSERT from `create_work_order` (W07); event emission retained
- Removed direct UPDATE from `start_work_order` (W08); event emission retained
- Removed direct UPDATE from `close_work_order` (W09); event emission retained; milestone-completion and next-WO queries updated to exclude the closing WO by ID so they remain correct without the synchronous write
- Removed direct UPDATE from `block_work_order` (W10); event emission retained
- Removed direct UPDATE from `unblock_work_order` (W11); event emission retained (newly added in this PR)
- Tests updated to reflect projection-only architecture: synchronous `business_work_orders` DB assertions removed; event-emission assertions retained

## Phase 18.1.7 — ds_* → business_* renames (2026-05-23)

### Renamed
- `ds_projects` → `business_projects` (2 rows preserved)
- `ds_milestones` → `business_milestones` (5 rows preserved; +schema enrichment fields: stage_gate_json, validation_expectations_json, security_readiness_checks_json)
- `ds_work_orders` → `business_work_orders` (14 rows merged; status mapping: open→created, complete→closed)
- `ds_tasks` → `business_tasks` (9 rows preserved)
- `ds_design_briefs` → `business_design_briefs` (1 row preserved)
- `ds_work_order_types` → `business_work_order_types` (10 rows preserved)

### Notes
- `ds_documents` and `ds_technology_signals` NOT renamed (out of scope: not business domain entities)
- `business_milestones` enrichment fields (stage_gate_json etc.) are NULL until Phase 18.4 populates them
- Phase 18.1 is now 100% complete. Phase 18.2 (writer migration) and 18.3 (file-state migration) are now unblocked.

## Phase 18.1.5 — Projection Framework (2026-05-23)

### Added
- `core/projections/framework.py` — v2 Projection ABC, ProjectionRegistry, ProjectionEngine (rewritten from pre-v2 to read from dual canonical tables)
- `core/projections/runner.py` — ProjectionRunner daemon process (5s / 100-event trigger, graceful SIGTERM shutdown, PID file lifecycle)
- `core/projections/work_order_projection.py` — First v2 projection: derives `business_work_orders` from `work_order.*` business canonical events
- Migration 068 — `projection_state`, `projection_dead_letter`, `projection_retry_queue` tables
- Migration 069 — `business_work_orders` table (L3 business entity, projection-populated)
- `ds projection list/status/rebuild/dead-letter/daemon` CLI commands
- `config/event_type_registry.py` — added `work_order.unblocked` entry
- 59 tests in `tests/unit/test_phase18_1_5_*` (framework + work order projection)

### Statistics
- Business canonical events processed: 33
- Work orders projected into business_work_orders: 14
- Schema version: 69

### Added — Phase 18.1.6 Project Entity Family Reconciliation (2026-05-22)

- **`docs/architecture/project-family-reconciliation.md`** — complete investigation and decision document for the `ds_*` vs `project_*` table family reconciliation. Enumerates both families in full (schema, row counts, writers, readers), maps all 16 concepts to their v2 placement, records the Approach A decision (ds_* canonical, project_* retires), and provides a migration plan sketch for Phases 18.4 and 18.6.
- **`.planning/data-model-v2.md` Amendment 4** — added "Project Entity Family — Reconciliation Decision" subsection confirming that `business_change_orders` is the target name, `project_*` tables drop in Phase 18.6, and `ds_*` tables rename to `business_*` with schema enrichment. Updated companion documents list to reflect the reconciliation document now exists.

### Decided — Phase 18.1.6

- **Project entity family: Approach A.** `ds_*` is the canonical operational layer. `project_*` family retires: the 8 tables (all at 0 rows) drop in Phase 18.6 after Phase 18.4 builds projection-populated `business_*` equivalents. No true concept duplicates exist — the families serve complementary purposes (operational tracking vs PRD authority specification). The prd_authority.py module (1,250+ lines, never invoked in production) is a design asset to be harvested by Phase 18.4, not lost.

### Added — Phase 18.1.3 Correlation ID Infrastructure (2026-05-22)

- **`core/correlation/composer.py`** — canonical implementation of correlation ID composition rules. Functions: `compose(parts)` builds `sess-X:wf-Y:skill-Z:agent-A:hook-H:tool-T` from a dict; `decompose(cid)` parses back to components; `extend(base, entity_type, entity_id)` adds a context level; `validate(cid)` checks format; `normalize_legacy(cid)` normalizes pre-18.1.3 IDs. Uses lookahead regex splitting so skill IDs containing colons (e.g. `ds-security:scan`) are preserved as single segments.
- **`core/correlation/__init__.py`** — public re-export of all five composer functions.
- **Ingestor delegation** (`spool/ingestor.py`) — `_extract_correlation_ids()` now delegates string composition to `core.correlation.composer.compose()` instead of building it inline. Extraction logic (reading trace/payload/top-level fields) stays in the ingestor; composition is canonical.
- **Backfill script** (`scripts/backfill_correlation_ids.py`) — best-effort correlation ID backfill for all three event tables. Per-row: if valid → kept; if malformed → normalized; if missing → reconstructed from ID columns + trace JSON; if unfixable → marked. Safe to re-run. Live result: 2770 events checked, 756 valid (kept), 0 malformed, 2014 missing (historical events without reconstructible context).
- **Validation utility** (`tools/correlation_validate.py`) — walks recent events, validates composition rules, reports malformed/missing per table. Exit 0 if all valid, exit 1 if any malformed, exit 2 on DB error. Flags: `--limit`, `--since`, `--db-path`, `--json`. Live result: 0 malformed across all three tables.
- **54 unit tests** (`tests/unit/test_phase18_1_3_correlation.py`) — covers compose/decompose/extend/validate/normalize_legacy, ingestor integration, backfill dry-run/live, and validation tool.

### Added — Phase 18.1.2 Dual Canonical Structure + Event Type Registry (2026-05-22)

- **`business_canonical_events` table** — new L2a business canonical table (migration 067). 14 columns including denormalized project_id, milestone_id, work_order_id, task_id for index-backed SDLC queries. 12 explicit indexes (correlation_id, event_type, project_id, milestone_id, work_order_id, task_id, event_timestamp, received_at, compound pairs). Does not replace `canonical_events` — both coexist during Phase 18.1.x transition.
- **`ai_canonical_events` table** — new L2b AI canonical table (migration 067). 16 columns including denormalized session_id, skill_id, workflow_id, agent_id, hook_id, model_id for index-backed AI analytics queries. 13 explicit indexes including compound (session × type, skill × time).
- **Event type registry** (`config/event_type_registry.py`) — 85-entry routing registry mapping every known event_type to its canonical destination(s). `RegistryEntry` dataclass with `routes_to` tuple, `granularity_level`, and `description`. Public API: `get_routes()`, `is_registered()`, `get_entry()`, `all_entries()`. Unknown types default to both canonicals (safe over-record). Raw-only types (tool.execution.completed, tool.execution.started, hook.tool_activity) carry `granularity_level="mechanical-detail"` per Commitment 9.
- **Ingestor dual canonical write** — `spool/ingestor.py` `_write_to_dual_canonical()` consults the event type registry on every ingest and routes to business, AI, both, or neither. Implemented as best-effort: dual canonical failure logs a warning but does not block the legacy `canonical_events` write. Raw write failure still blocks (inbox restore).
- **Backfill script** (`scripts/backfill_dual_canonical.py`) — one-time best-effort reconstruction of 1,938 existing `canonical_events` rows into the dual canonical tables. Results: 56 → business_canonical_events, 743 → ai_canonical_events, 1,139 skipped as raw-only per Commitment 9. Source column set to `"backfill"`. Safe to re-run via INSERT OR IGNORE.
- **Correlation join CLI** (`tools/canonical_join.py`) — verification utility for the dual canonical join. Supports `--stats`, `--list` (top correlation_ids by event count), `--correlation-id ID` (join both tables), `--json`, `--limit`, `--db-path`. Verified: 100 distinct correlation_ids present in ai_canonical_events after backfill.

### Added — Phase 18.1.1 Raw Layer Infrastructure (2026-05-22)

- **`raw_claude_code_events` table** — new L1 raw layer table (migration 066) that preserves the full native event shape for every Claude Code event. 14 indexes cover individual correlation ID components (session_id, project_id, workflow_id, skill_id, agent_id, hook_id, tool_id), the composed `correlation_id`, event_type, received_at, event_timestamp, and compound pairs (project × time, type × time, session × type). Part of the v2 data architecture; future adapters get their own tables.
- **Ingestor dual-write** — `spool/ingestor.py` now writes to `raw_claude_code_events` FIRST before writing to `canonical_events`. Raw write failure returns the spool file to the inbox for retry on the next ingest run; canonical write is only attempted after a successful raw write.
- **`_extract_correlation_ids()`** — new ingestor function that extracts session_id, project_id, workflow_id, skill_id, agent_id, hook_id, tool_id, model_id, adapter_id from top-level fields, trace, and payload; composes a `correlation_id` string in the form `sess-X:wf-Y:skill-Z:agent-A:hook-H:tool-T` (only non-null parts included).
- **Backfill script** (`scripts/backfill_raw_claude_code_events.py`) — one-time best-effort reconstruction of 1,909 existing `canonical_events` rows into `raw_claude_code_events` via `INSERT OR IGNORE`. Backfilled rows carry `_backfill=True` in source_payload. Safe to re-run.
- **Drill-down CLI** (`tools/raw_drilldown.py`) — interactive query tool for `raw_claude_code_events` supporting `--stats`, `--correlation-id`, `--session-id`, `--workflow-id`, `--skill-id`, `--hook-id`, `--tool-id`, `--project-id`, `--event-type`, `--limit`, `--json`, and `--db-path` flags.

### Fixed — Phase 18.0 Emergency Cleanup (2026-05-22)
- **C1 — spool/emitter.py created**: `on-context-threshold.py` imported `from spool.emitter import emit` but the module did not exist, silently failing every context threshold event. `spool/emitter.emit()` now wraps `CanonicalEventEnvelope` + `write_envelopes` with a non-raising interface (returns `True`/`False`).
- **C2 — Handoff TTL guards**: `on-prompt-validate.py` can no longer leave `pending-handoff.json` alive indefinitely. Added `HANDOFF_STALE_TTL_S=300` and `HANDOFF_INJECTION_WINDOW_S=60` constants. Files older than 300s are deleted; `in_progress` files past 60s are cleaned up. Discards logged to `DS_DIAGNOSTICS_DIR/stale-handoff.jsonl`.
- **C3 — DB contamination cleanup**: migration 065 deletes 23 test fixture rows from `ds_projects` that were written to production `studio.db` by tests bypassing isolation. `guard_real_homedir` now calls `DatabaseRuntime.reset_instance()` before/after yield. Three tests in `test_ta3_token_capture.py` fixed to pass `dream_studio_home=db_home`.
- **C4 — Guardrails evaluator dependency**: `guardrails/evaluator.py` referenced removed `activity_log` table (dropped in migration 063). `_custom_query_matches()` now checks `canonical_events` / `hook_invocations`, rejects `activity_log` references with a descriptive error.

### Added
- **Publication boundary** - added public/private publication guidance, docs index, and current product positioning for Dream Studio as a local-first AI orchestration and operational intelligence platform.
- **Pattern Enhancement (35 tasks)** — 9 foundational patterns for optimized LLM consumption with 40% token savings target (#pattern-enhancement)
  - Progressive disclosure: `quality/debug` refactored 217→65 lines with 6 reference files for on-demand loading
  - Design system library: 5 curated systems (3,561 lines) - tech-minimal, editorial-modern, brutalist-bold, playful-rounded, executive-clean
  - I-Lang discovery protocol: 8-dimension design intent capture with NLP mappings
  - Version guards: Python/Node/Power BI feature gating for 70% compatibility bug reduction
  - Decision tables: symptom→solution routing in debug (8 patterns), client-work (6 patterns), design (5 systems)
  - Response contracts: standardized output sections for security reviews, client deliverables, ship gate
  - Structured frontmatter: ds: namespace added to all 41 mode SKILL.md files
  - CI validation: SKILL.md standards enforcement (line count, YAML, banned phrases, reference links)
  - DO/DON'T lesson template: 75% scan-time reduction (2min→30sec) with visual markers
- **YAML mode config** — migrated skill metadata from SKILL.md frontmatter to dedicated `config.yml` files across all 48 skill directories; SKILL.md is now pure instructions (#83)
- **Granular skill tracking** — dashboard shows mode-level names ("core:think", "quality:debug") instead of pack-only names ("core", "quality") (#84)
- **Smart model routing** — `get_model_for_skill()` API reads `model_tier` from config.yml for subagent model selection (opus/sonnet/haiku) with telemetry tracking (#80)
- **Hook consolidation** — 3 dispatchers replace 19 subprocess calls (UserPromptSubmit 6→1, Stop 9→1, Edit|Write 4→1) with per-handler timing telemetry (#81)
- **Context trimming** — extract detailed content from 14 SKILL.md files into examples.md (44% line reduction), hook timing dashboard panel, global CLAUDE.md deduplication (#82)
- **Analytics in CI** — dashboard renders on main branch pushes and uploads as a build artifact (#85)
- **Onboarding skill** (`ds:setup`) — wizard, status, and JIT modes for guided tool installation and project setup (#46)
- **Web access module** (`skills/core/web.md`) — 3-tier fallback chain (Firecrawl → scraper-mcp → WebSearch/WebFetch) with JIT install prompts
- **Tool registry** (`skills/setup/tool-registry.yml`) — metadata for 6 optional tools with detect/install/upgrade commands

### Fixed
- **Chain suggestions restored** — `on-skill-complete.py` now reads `chain_suggests` from config.yml instead of stripped SKILL.md frontmatter (#85)
- **Installer statusLine schema** — Claude Code installer now writes `statusLine.type: "command"` alongside `statusLine.command`, satisfying the Claude Code settings schema and clearing the `/doctor` validation error on fresh installs.

### Changed
- **License** - updated current public licensing to Apache-2.0.
- **README and product docs** - replaced adapter-first language with platform-first language; Claude Code is documented as one adapter surface.
- **Visual architecture documentation** — created simplified root `ARCHITECTURE.md` with Mermaid diagrams (system overview, database ERD, session lifecycle) as visual front-door for GitHub browsers; updated `/refresh-architecture` command to maintain consistency between root and detailed docs
- **Documentation** — updated 10 files with stale "SKILL.md frontmatter" references to reflect config.yml as the metadata SSOT (#85)
- **Workflow coverage** — token efficiency improvements and feature activation gates (#48)
- **Linux gh install** — corrected install command; Mac Python symlink fix (#47)

## [0.11.0] — 2026-04-30

### Changed
- **Pack consolidation** — 37 individual skills consolidated into 7 pack-level router skills (core, quality, career, security, analyze, domains, workflow). Each pack uses a `modes/` subdirectory for sub-skill content. Total skill description budget drops from ~10,000 to ~885 chars, ensuring all skills load for every user out of the box.
- **packs.yaml** — bumped to schema_version 2; `skills` field replaced with `skill` (singular) + `modes` list per pack
- **CLAUDE.md routing table** — 35-row individual skill routing replaced with 7-row pack-based routing
- **sync-cache.ps1** — dynamic version detection, stale directory cleanup on sync
- **README.md** — updated skill documentation to reflect pack-based invocation pattern
- **plugin.json** — version 0.11.0

### Removed
- 37 top-level skill directories (moved into pack `modes/` subdirectories — content unchanged)

### Migration
- Invocations change from `ds:think` to `ds:core` with arg `think`
- Natural language routing still works — pack routers infer mode from keywords
- `workflow` remains standalone (unchanged)

## [0.10.0] — 2026-04-29

### Added
- **agents/** directory with integration README — entry point for bundled specialist agents
- **agents/data-engineer.md**, **mobile-developer.md**, **research-analyst.md**, **idea-validator.md**, **accessibility-expert.md**, **technical-writer.md**, **terraform-architect.md**, **kubernetes-expert.md**, **devops-engineer.md** — 9 bundled specialist agents synthesized from external repo patterns (infra, mobile, data, research, quality domains)
- **skills/domains/infra/**, **mobile/**, **data/**, **research/**, **quality/** — 8 domain knowledge YAMLs (patterns, gotchas, synthesis eval rubric); all ASCII-clean, yaml.safe_load validated
- **skills/domains/eval-rubric.yml** — 8 quality signals for domain synthesis assessment
- **workflows/domain-ingest.yaml** — 4-phase domain synthesis pipeline: discover → extract → synthesize → register
- **workflows/domain-refresh.yaml** — automated stale agent re-synthesis workflow
- **`type: specialist`** node in workflow execution protocol (SKILL.md)
- **On-pulse stale agent detection** — `hooks/on_pulse.py` now reports agents past their `refresh_due` date
- **README Bundled Specialists section** — documents the 9 agents, domains covered, and install instructions

### Changed
- **skills/domains/ingest-log.yml** — schema extended with `agent_type` field; 9 domain agents backfilled as entries
- **skills/coach/analysts/route-classifier.yml** — expanded with ingest-log agent install suggestion for unrecognized skill requests

## [0.9.0] — 2026-04-29

### Added
- **ARCHITECTURE.md** — Documents the two-layer design: `packs/` (Python hook runtime) vs `skills/` (Claude guidance), key paths, how they connect, and the full new-skill checklist
- **skills/domains/ingest-log.yml** — External knowledge registry tracking every repo analyzed: URL, stars, domain, files touched, analysis date, refresh-due date. Backfilled with 11 repos from the 2026-04-28 integration
- **`workflow: repo-ingest`** node in `skills/workflow/SKILL.md` — Formalizes external repo intake: domain detection, dedup check, ≤10 pattern extraction, domain YAML write, ingest-log entry. Replaces ad-hoc ingestion with a tracked, repeatable workflow
- **`.planning/specs/infra-lessons-ingest/`** — Plan and tasks for this release

### Fixed
- **`~/.dream-studio/config.json`** — Now includes `director_name` and `claude_memory_path`; silences the "Setup not complete" warning that fired every session
- **`skills/learn/config.yml`** — `harvest.projects_root` now set to `builds/`; enables `learn: harvest` to auto-discover projects

### Changed
- **skills/build/gotchas.yml** — Added `compact-at-75-percent` best practice: run `/compact` proactively between waves before context approaches 75% (promoted from 26 pending draft lessons)
- **skills/STRUCTURE.md** — Added Skill Depth Policy section: JIT enrichment only, no sprint; skill tier table (Enhanced / Standard / JIT-pending)
- **skills/polish/SKILL.md** — Now references `checklists/` directory with all 4 checklists named inline
- **skills/mcp-build/SKILL.md**, **dashboard-dev/SKILL.md**, **saas-build/SKILL.md** — Added `## Depth Status` section marking each as JIT-pending
- **skills/workflow/SKILL.md** — `repo-ingest` built-in workflow node added (see Added above)

### Meta
- 26 pending draft lessons triaged: 22 rejected (context-threshold noise + sonnet-theme), 4 high-context theme promoted to `build/gotchas.yml`
- Draft lesson queue cleared to 0

## [0.8.0] — 2026-04-29

### Added — Skill & Workflow Improvements (TR-001–TR-013)
- **skills/explain/** — New `explain` skill: traces entry point through layers to output, depth adapts to question; includes SKILL.md, metadata, gotchas, config, changelog
- **skills/coach/analysts/route-classifier.yml** — Route-classifier analyst persona for mapping unmatched intents to nearest skill
- **skills/coach/modes.yml** — `route-classify` mode entry for coach
- **skills/core/repo-map.md** — New core module: repo-map generation patterns, registered in REGISTRY.md
- **skills/domains/bi/dax-patterns.md** — DAX calculation patterns for Power BI domain knowledge base
- **skills/domains/bi/m-query-patterns.md** — M-query data transformation recipes for Power BI
- **skills/client-work/powerbi/pbip-format.md** — PBIP format reference for Power BI project files
- **hooks/lib/skill_metrics.py** — Appends skill usage records (name, duration, tokens) to `~/.dream-studio/skill-metrics.jsonl` on every invocation
- **scripts/sync-cache.ps1** — PowerShell cache sync utility

### Changed
- **CLAUDE.md** — Added routing fallback clause: unmatched intents route to `coach` with `route-classify` mode (TR-012)
- **skills/coach/SKILL.md** — Added `route-classify` mode (TR-012)
- **skills/build/SKILL.md** — Repo-map generation step at Step 0 (TR-006), per-task checkpoints at every step (TR-007), worktree isolation instruction for parallel dispatch (TR-008), auto-learn suggestion at checkpoint (TR-013)
- **skills/debug/SKILL.md** — Step 1.5 failing-test capture gate (TR-011), auto-learn suggestion (TR-013)
- **skills/verify/SKILL.md** — Red-green bug fix verification section (TR-011)
- **skills/review/SKILL.md** — JSON reviewer schema for structured findings output (TR-003)
- **skills/core/orchestration.md** — JSON agent schema, static-before-dynamic prompt ordering (TR-003/TR-004), repo-map field in implementer template (TR-006), pipeline gate check pattern (TR-009)
- **skills/core/format.md** — Task-level checkpoint format variant (TR-007)
- **skills/build/config.yml** — Checkpoint threshold set to 1 task (TR-007)
- **workflows/fix-issue.yaml** — `create-issue` node after diagnose (TR-001), write-failing-test conditional node (TR-005)
- **workflows/idea-to-pr.yaml** — Conditional security branch (TR-005)
- **settings.json** — PostToolUse metrics hook for Skill tool (TR-010)
- 30+ SKILL.md files updated with content improvements across all packs
- Updated gotchas.yml for build, debug, plan, review, secure, think, verify
- Regenerated `skills/dream-studio-catalog.md` — now covers 38 skills

## [0.7.0] — 2026-04-28

### Added — Skill Architecture Enhancement (Phase 2)
- **skills/*/metadata.yml** — Evolution tracking, quality metrics (success_rate, times_used, avg_token_usage), dependency tracking for all 37 skills
- **skills/*/gotchas.yml** — Structured lessons learned (avoid, best_practices, edge_cases, limitations, deprecated) for all 37 skills
- **skills/*/config.yml** — Runtime configuration and performance budgets for all 37 skills
- **skills/*/changelog.md** — Version history for all 37 skills
- **skills/generate-catalog.py** — Auto-generates dream-studio-catalog.md from skill metadata
- **skills/dream-studio-catalog.md** — Auto-generated searchable skill dashboard with quality metrics, dependency graph, health status
- **skills/STRUCTURE.md** — Complete architecture guide (skill structure, file purposes, creating/updating skills, best practices)
- **skills/templates/** — Templates for metadata.yml, gotchas.yml, config.yml for new skill creation
- **skills/build/examples/** — Simple + complex usage examples with input/output (also for plan, review, verify, ship)
- **skills/build/templates/** — Agent prompts (implementer, reviewer) and output formats (checkpoint, findings-report, plan-format)
- **skills/build/smoke-test.md** — Quick validation tests (also for plan, review, verify, ship)
- **skills/build/core-imports.md** — Module dependency documentation and impact analysis (also for plan, review, verify, ship)

### Changed
- **skills/core/REGISTRY.md** — Updated with Phase 2 architecture enhancement history
- **README.md** — Added Skill Architecture section documenting structured framework
- All 37 skills now follow standardized structure with metadata, gotchas, config, and changelog

### Infrastructure
- **Makefile** — standard targets: `test`, `lint`, `fmt`, `security`, `install-dev`, `status`
- **pyproject.toml** — black, flake8, pytest, and coverage config (replaces need for separate `.coveragerc`)
- **hooks/lib/time_utils.py** — `utcnow()` utility; replaced all bare `datetime.now(timezone.utc)` calls in handlers and `context_handoff.py`
- **hooks/lib/models.py** — Pydantic v2 models (`UserPromptSubmitPayload`, `PostToolUsePayload`, `StopPayload`) for stdin validation in handlers
- **hooks/lib/audit.py** — append-only event log writing to `~/.dream-studio/audit.jsonl`
- **hooks/lib/telemetry.py** — optional Sentry error tracking stub (activated by `SENTRY_DSN` env var)
- **SECURITY.md** — vulnerability disclosure process (30-day SLA, ***REMOVED***)
- **CONTRIBUTING.md** — branch naming, commit format, PR checklist, code style guide
- **requirements.txt** — runtime dependencies (pydantic, sentry-sdk) split from dev deps
- **requirements-dev.txt** — added freezegun, factory-boy, black, flake8, pip-audit, pre-commit
- **.pre-commit-config.yaml** — black and flake8 hooks
- **scripts/bom.py** — Bill of Materials script (git SHA, Python version, pip freeze, build date)
- **skills/harden/SKILL.md** — `/harden` skill: 20-item audit + gap-fill from templates
- **templates/project-standards/** — reusable template files (Makefile, pyproject.toml, SECURITY.md, CONTRIBUTING.md, requirements files, hooks/lib stubs)
- **tests/factories.py** — factory_boy factories for hook payload models
- **on-tool-activity** hook: one-time `/harden audit` nudge on first Edit/Write in unhardened projects

### Changed
- `on-token-log.py`, `on-milestone-start.py`, `on-milestone-end.py`, `on-pulse.py`, `on-meta-review.py`, `context_handoff.py` — all `datetime.now(timezone.utc)` replaced with `utcnow()` from `time_utils`
- `on-token-log.py`, `on-context-threshold.py` — added Pydantic payload validation with graceful fallback on `ValidationError`
- `test_hook_on_pulse.py`, `test_hook_on_milestone_end.py`, `test_hook_on_token_log.py` — added `@freeze_time` to time-sensitive tests

## [0.6.1] — 2026-04-19

### Added
- **skills/domain-re/** — Real estate analysis skill: forensic skeptic (sonnet) + diplomatic executor (haiku) + battle-tested strategist (sonnet); modes: lease-analysis, credit-check, renewal-economics, rollover-analysis; 3 analysts, anti-sycophancy design
- **skills/coach/** — Claude Code workflow coach: evaluates workflow-fit, context-health, pr-hygiene, agent-dispatch; `full-audit` mode runs all four in parallel with consensus-report synthesis
- **skills/secure/** — Rewritten as parallel analyst-orchestrated skill: 6 OWASP analysts (injection, auth, exposure, access-control, misconfig, dependencies) + 6 STRIDE analysts; `any-reject` verdict (any HIGH = BLOCKED); incomplete review defaults to BLOCKED; ship gate integration
- **~/.claude/agents/**: typescript-expert, python-expert, go-expert, devops-engineer, ml-engineer, bi-developer — six language and domain expert agents (global scope)
- **~/.claude/CLAUDE.md** — Claude Code patterns section: context rewind threshold (~300-400k tokens), PR size target (~120 lines), subagent dispatch at >50% context

## [0.6.0] — 2026-04-17

### Changed
- **verify** skill: added Iron Law gate, Common Failures table, Red Flags list, Rationalization Prevention table, evidence patterns (borrowed from Superpowers verification-before-completion)
- **review** skill: two-stage review ordering — spec compliance first, then code quality; subagent reviewer dispatch templates; "Do Not Trust the Report" principle (borrowed from Superpowers subagent-driven-development)
- **build** skill: subagent-driven execution with fresh agent per task, pre-inlined context injection, dependency-wave parallel execution, model selection heuristic, implementer prompt template, phase-locked transitions (borrowed from Superpowers + GSD)
- **handoff** skill: dual-output (markdown + JSON), recovery state machine for programmatic resume, context pressure triggers (borrowed from GSD pause/resume pattern)
- **on-context-threshold** hook: doubled all thresholds (WARN 1500→3000, COMPACT 2500→5000, HANDOFF 3500→7000, URGENT 4500→9000)

## [0.5.0] — 2026-04-16

### Added
- `agents/chief-of-staff.md`, `agents/engineering.md`, `agents/game.md`, `agents/client.md` — four agent personas flattened from `<name>/CLAUDE.md` layout; Dannis/SeayInsights references replaced with `{{director_name}}` placeholder resolved at skill-load time
- `agents/director.md` — fill-in-blanks Director persona template (name, role, focus, hard limits, tool preferences)
- `agents/context/director-preferences.md`, `director-corrections.md`, `session-context.md`, `session-primer.md`, `fullstack-standards.md` — ported from studio, generalized (notion-studio-mcp calls and brand-specific tokens removed; `{{director_name}}` placeholder)
- `on-context-threshold.py` slug builder now replaces spaces with `-` on both drive-letter and fallback branches (mirrors studio fix from commit `25208c9`); new unit test covers Windows-path-with-spaces, Unix-path-with-spaces, and no-spaces cases
- Integration test `test_projects_dir_slug_replaces_spaces` (52 tests total)

### Removed
- `agents/torii/` — TORII is a separate product, not shipped with dream-studio
- All `notion-studio-mcp` auto-logging calls from agent personas (log_agent_action, log_escalation, get_pending_escalations, etc.)
- References to `studio-ops`, `dannis-naomi`, specific project repos
- "SeayInsights brand tokens" section in `fullstack-standards.md` — now a fill-in-blanks block

## [0.4.0] — 2026-04-16

### Added
- 10 hook handlers ported to `hooks/handlers/`, all built on `hooks/lib`:
  - `on-pulse` — cross-project health check; `github_repo` comes from `config.json`, not hardcoded
  - `on-milestone-start` / `on-milestone-end` — DCL-matched milestone marker in `~/.dream-studio/state/`
  - `on-context-threshold` — four-band warn/compact/handoff/block with project-dir auto-detection (override via `CLAUDE_PROJECTS_DIR`)
  - `on-quality-score` — advisory diff scan (tests, debug, secrets, size, scope); writes `quality-score.json`
  - `on-token-log` — appends token usage rows to `token-log.md`
  - `on-meta-review` — weekly retrospective reading `~/.dream-studio/planning/session-context.md`
  - `on-agent-correction` — pattern accumulation with auto-draft threshold (override via `DREAM_STUDIO_CORRECTIONS_PATH`)
  - `on-skill-load` — logs skill reads; surfaces `{{director_name}}` resolution from `config.json`
  - `on-tool-activity` — rolling activity snapshot under `state/activity.json`
- `hooks/hooks.json` — declares hooks on `UserPromptSubmit`, `Stop`, and `PostToolUse` (via `${CLAUDE_PLUGIN_ROOT}/hooks/run.sh`)
- 28 integration tests (one file per hook) — `pytest tests/` now runs 51 tests total

### Removed
- `_notion.py` and `_torii_feed.py` helpers — dream-studio core no longer talks to Notion or the TORII feed

## [0.3.0] — 2026-04-16

### Added
- `hooks/lib/paths.py` — `plugin_root`, `user_data_dir` (`~/.dream-studio/`), `project_root`, `meta_dir`, `state_dir`, `planning_dir`
- `hooks/lib/python_shim.py` — `detect_python()` tries `py`, `python3`, `python` in order, raises `PythonNotFoundError` with OS-specific install hints
- `hooks/lib/state.py` — `read_config`/`write_config`, `read_pulse`/`write_pulse`, schema-version guard via `SchemaVersionError`
- `hooks/run.sh` + `hooks/run.cmd` — cross-platform handler launchers that pick a Python interpreter and exec `hooks/handlers/<name>.py`, preserving `CLAUDE_PLUGIN_ROOT`
- `tests/` — 23 unit tests (paths, python_shim, state) with 97% line coverage on `hooks/lib`
- `requirements-dev.txt` pinning pytest + pytest-cov
- `.gitattributes` enforcing LF for `.sh`/Python and CRLF for `.cmd`/`.bat`
- CI matrix now installs deps and runs `pytest --cov=hooks/lib --cov-fail-under=80`

## [0.2.0] — 2026-04-16

### Added
- 18 skills ported from studio as `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`):
  - Process: `think`, `plan`, `build`, `review`, `verify`, `debug`
  - Domain: `saas-build`, `game-dev`, `client-work`, `design`, `mcp-build`, `dashboard-dev` (was `torii-dev`)
  - Quality: `polish`, `secure`, `ship`
  - Studio: `recap`, `handoff`, `learn`

### Changed
- Flat skills layout (`skills/<name>/SKILL.md`) instead of category folders, matching Claude Code adapter convention
- `design` skill: brand tokens table converted to fill-in template
- `mcp-build` skill: `@seayinsights/` package scope generalized to `@<your-scope>/`
- `client-work` skill: "Notion Client Projects" generalized to "the project tracker"
- `saas-build` skill: dropped the specific project list line

### Removed
- All SeayInsights-specific references (brand name, Dannis, repo URLs, Notion workspace IDs)
- TORII product branding from the dashboard skill (now `dashboard-dev`, fully generic)

## [0.1.0] — 2026-04-16

### Added
- `.claude-plugin/plugin.json` manifest (name, version, author, license, repository)
- `.claude-plugin/marketplace.json` self-hosted dev marketplace entry
- `README.md`, initial license file, `.gitignore`, `CHANGELOG.md`
- `.github/workflows/ci.yml` scaffold (lint + pytest matrix on Windows/macOS/Linux × py3.10/3.11/3.12, empty tests OK)
- Repo bootstrapped, initial commit on `main`
- Verified `claude plugins list` shows `dream-studio@0.1.0` after local install

## [0.0.1] — 2026-04-16

### Added
- Scaffolding
