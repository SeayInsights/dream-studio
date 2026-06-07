# Database Guide

Dream Studio uses SQLite as the local structured authority for operational intelligence. The public repo contains schema migrations, bootstrap code, read models, tests, and docs. The operator's live database is private runtime state.

## Paths

| Path | Meaning | Git policy |
| --- | --- | --- |
| `core/event_store/migrations/` | Repo-backed schema migrations | Tracked |
| `core/config/sqlite_bootstrap.py` | Bootstrap and migration application | Tracked |
| `core/config/database.py` | Canonical DB path resolver and environment override behavior | Tracked |
| `~/.dream-studio/state/studio.db` | Operator-local live DB | Ignored/private |
| `*.db`, `*.sqlite*`, `*.db-wal`, `*.db-shm` | Runtime DB files | Ignored/private |

## Authority Areas

Dream Studio's SQLite authority covers:

- project, session, milestone, task, and Work Order state;
- route decisions and approval state;
- hook, tool, skill, token, validation, security, workflow, research, decision, and outcome telemetry;
- dashboard attention items and read-model inputs;
- shared intelligence records including adapters, context packets, normalized results, model/provider metadata, learning events, hardening candidates, and evaluation records;
- secure production readiness assessments, control applicability, findings, remediation Work Order links, project health/readiness scorecards, release readiness records, and compliance/legal review flags;
- release/cutover evidence summaries where safe.

Current Capability Center, scoped-agent, and GitHub repo intake
authority lives in migration 044:

- `agent_registry_records` and `agent_context_scope_policies` for scoped worker
  declarations; dashboard summaries also read current invocation and hardening
  records. (Wave 6 / migration 101 dropped the 0-row `capability_center_records`,
  `workflow_agent_skill_mappings`, and `agent_result_records` tables 044 created;
  Capability Center now reports an empty state and normalized agent results route
  to `agent_invocations`/`decision_records`/`validation_results`/`artifact_records`.)
- `github_repo_*` tables for evidence-backed repository evaluations, license,
  security, dependency, integration, pattern, adoption, and attribution records.

Career data is private by default and excluded from public exports unless
explicitly redacted and approved. GitHub repo intake records do not authorize
copying code, adding dependencies, forking, vendoring, or mutating external
projects.

Current AI usage accounting authority lives in:

- `token_usage_records` for token telemetry with billing, token visibility,
  cost visibility, usage source, cost source, and confidence metadata;
- `ai_adapter_accounting_profiles` for operator-declared adapter billing modes
  such as Claude Code subscription, Claude API token-metered, Codex ChatGPT
  plan, Codex token-metered/flexible, local model, and unknown/custom;
- `ai_usage_operational_records` for operational value telemetry such as run
  count, project/milestone/task/Work Order context, files touched, commands
  run, validation outcome, PR/result outcome, rework, duration, and evidence.
- `task_attribution_records` for execution-unit attribution: which adapter,
  model/provider where known, skills/workflows, tools/hooks, files, commands,
  validations, outcome, rework state, commit/PR/result refs, and
  security/readiness impact belong to a meaningful task or Work Order.

Migration `081_cost_columns_numeric.sql` corrects the declared type of two
financial columns from `REAL` (IEEE 754 float) to `NUMERIC(20,8)` (exact
decimal): `token_usage_records.estimated_cost` and
`ai_usage_operational_records.cost_amount`. The correction uses the standard
table-reconstruction pattern; see `docs/architecture/aspirational-schema-debt.md`
for a note on the `legacy_alter_table` PRAGMA choice and the pre-existing
`vw_activity_timeline`/`canonical_events` debt surfaced during this migration.

Tokens are usage telemetry. They are not dollars unless the adapter billing
mode and source metadata explicitly make cost reportable. Plan/subscription
usage preserves observed tokens where available and shows cost as unknown
unless an explicit allocation profile exists. Reconciled legacy token rows must
carry `source_refs_json` and `evidence_refs_json` so token analytics can use
current authority without restoring legacy `canonical_events` as an active
source.

Task attribution links usage, adapter results, validation, security/readiness,
and Work Order facts without becoming token/cost authority. Unknown
model/provider values remain `unknown`; unavailable file or command data remains
`unavailable`; imported or untracked work must be classified instead of
overclaimed.

Dashboard launch commands must use the resolved SQLite path through
`DREAM_STUDIO_DB_PATH` and `DREAM_STUDIO_HOME` instead of assuming the caller's
current directory or default home. Serving or checking the dashboard must not
bootstrap, migrate, backfill, clean, or destructively mutate the live database.

Platform hardening authority lives in migration
`046_platform_hardening_authority.sql` and covers:

- `skill_evaluation_runs`
- `policy_decision_records`
- `connector_ingestion_runs`
- `privacy_redaction_export_records`
- `local_watch_schedule_records`
- `team_rollup_records`
- `installer_distribution_checks`
- `demo_case_study_packets`

These records make skill evaluation, permission decisions, connector imports,
privacy/export checks, opt-in watchers, sanitized team rollups,
installer/distribution checks, and demo/case-study packets queryable without
promoting local files to authority.

PRD lifecycle authority lives in migration
`047_prd_lifecycle_authority.sql` and covers:

- `project_intake_records` and `project_intake_questions` for adaptive
  new-project and import-existing-project intake;
- `project_assumption_records` for explicit assumptions and operator
  confirmation state;
- `prd_version_records` for PRD lifecycle state, confidence, version lineage,
  source refs, evidence refs, known unknowns, and current-version selection;
- `project_milestone_records` for ordered milestone authority, stage gates,
  validation expectations, security/readiness checks, evidence requirements,
  and adapter context requirements;
- `project_work_order_authority_records` for Work Order purpose, scope,
  approved surfaces, stop gates, verdict taxonomy, route expectations, and
  rollback strategy;
- `project_change_order_records` and `prd_amendment_records` for material and
  lightweight PRD changes without silently overwriting current authority;
- `prd_route_reconciliation_records` for planned-vs-actual milestone, release,
  or project closeout reconciliation.

`prd_documents` remains a compatibility/list surface. It is not sufficient as
the only PRD authority for in-flight continuation because it lacks change-order
lineage, milestone impact, route reconciliation, and adapter context-scoping
fields. PRD files, when generated, are exports and must not become a competing
source of truth.

Legacy install upgrades do not add legacy tables to the current schema. The
upgrade flow creates a fresh current SQLite database through the normal
migration runner, then imports only compatible rows into tables that already
exist in the current schema. Legacy-only tables, FTS/shadow tables,
`canonical_events`, backup/import-map tables, and old file-sprawl remain in the
backup/manual-review set unless a future additive migration gives them current
authority semantics.
installer/distribution checks, and demo/case-study packets measurable without
replacing validation, Work Order, security, analytics, or adapter authority.

## Runtime Rules

- Normal runtime uses the canonical path resolver.
- Tests that write must use temp or injected DB paths.
- Live DB migration requires explicit approval, fresh backup, backup verification, and rollback instructions.
- Destructive migration, DB record deletion, retention cleanup, compaction, and archive execution are separate approval boundaries.
- Public docs may describe schema concepts but must not include private rows, raw logs, operator decisions, local evidence contents, or DB backups.

## Read Models

Telemetry read models aggregate structured state into dashboard-consumable views. They are derived views and must expose or imply:

- `derived_view: true`
- `primary_authority: false`
- `routing_authority: false`
- source tables and freshness metadata
- module availability and empty-state behavior

## Publication Boundary

Never commit live DB files, backups, WAL/SHM files, dumps, raw telemetry, cutover evidence, cleanup manifests, or local audit trails. Use sanitized fixtures and synthetic examples for public tests and demos.

<!-- Last reviewed 2026-05-20 — repo-wide `py -m black .` formatting applied; no behavior or policy change required here. -->

<!-- Last reviewed 2026-05-28 — migration 079 fix: added CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts to migration 079 Part B. memory_fts was previously only created at application-startup time; fresh DBs built from migrations (test fixtures starting at schema v0) failed with "no such table: memory_fts". Fix is additive and safe on live DBs via IF NOT EXISTS. -->

<!-- Last reviewed 2026-05-28 — 18.4.3-cleanup: studio_db.py modified (black reformatting only; no schema changes). Added inline cq-006-suppress comments to 3 JSON payload parsing sites. No primary authority table changes. No migration. -->

<!-- Last reviewed 2026-05-28 — 18.4.4 Chain 7: migrations 079 + 080 extend memory_entries. 079 adds intelligence_surfaced_at (dedup field) + FTS sync triggers. 080 adds source_type/source_id/lifecycle_state and other columns required by MemoryStore.upsert_by_provenance (pre-existing schema gap). Both migrations use IF NOT EXISTS / nullable additions — safe on existing DBs. memory_entries authority unchanged (private local state). -->

<!-- Last reviewed 2026-05-20 — pipeline optimization landed (migration 057 extends ds_work_order_types with workflow_template, precondition_skill, task_generator, resolution_instructions; CLI gains `ds project state` single-query, auto-advance, gotcha injection, brief mode); doc policy unchanged here. -->

<!-- Last reviewed 2026-05-20 — A1 extraction: 22 CLI handlers refactored into importable functions under core/projects, core/work_orders, core/design_briefs, core/milestones, core/skills, core/health. ds.py wrappers are now thin (call function, print result, return exit code). No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-20 — A2.1: `_work_order_start` decomposed into `read_work_order_brief`, `write_work_order_context`, `start_work_order` under `core/work_orders/start.py`. Stdin y/N prompt removed from the pure path; CLI wrapper preserves the legacy stderr warning + non-TTY auto-accept for operator terminals. No policy or contract change here. -->

<!-- Last reviewed 2026-05-20 — A2.2: `_work_order_close` decomposed into `run_gate_check`, `check_close_gates`, `close_work_order` under `core/work_orders/close.py`. `_run_gate_check` lifted out of `interfaces/cli/ds.py`; `core/projects/queries.py` now imports the predicate directly. CLI wrapper re-emits `[gate.bypassed] WARNING:` to stderr from the returned `bypassed_gates` list for operator-terminal parity. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.3: `_project_start` decomposed into the `start_project` composer under `core/projects/start.py`, which orchestrates `set_active_project` (mutations) + `get_next_work_order` (queries) + `start_work_order` (work_orders/start). CLI wrapper converts the compound result dict into the legacy operator-facing summary; no policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.4: `_skill_invoke` (heaviest CLI handler) decomposed into `load_skill_content` + `record_skill_invocation` + `seed_gate_artifact_files` under `core/skills/invocation.py`. Duplicate `_load_packs` / `_SKILL_SPECIFIER_RE` / `_SKILL_FM_RE` removed from `interfaces/cli/ds.py`; the canonical `_load_packs` lives in `core/skills/queries.py`. Phase A3 workflow runner can now compose these three functions directly. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.5: `_design_brief_create` lifted to `create_design_brief` in `core/design_briefs/mutations.py` (returns dict with brief_id, project_id, status, next_step). CLI wrapper preserves the legacy `Draft brief created:` stdout line. A2.4's lazy `from interfaces.cli.ds import _design_brief_create` in `core/skills/invocation.py` is now a direct `core.design_briefs.mutations` import. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.6: `_design_brief_lock` lifted to `lock_design_brief` in `core/design_briefs/mutations.py` (returns dict with brief_id, status='locked', locked_at; ok=False/error for missing brief). CLI wrapper preserves the legacy `Brief <id> locked.` stdout line and exit-1 JSON path. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.7: `_milestone_close` lifted to `close_milestone` in `core/milestones/close.py`. Pure function returns one canonical result dict across every path (missing milestone / open WOs / gate failures / forced bypass / success); CLI wrapper preserves the legacy mixed-format operator output (JSON for failures, plain-text on success, `[gate.bypassed] WARNING:` stderr on force). No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.8: `_update_command` no longer self-shells via `subprocess.run(['ds','integrate','install','claude_code','--execute'])`; instead it calls `ClaudeCodeInstaller.install('execute')` directly in-process, mirroring the `ds integrate install` code path. Skips interpreter respawn, keeps tracebacks intact, and lets callers patch the installer with `unittest.mock`. Final A2 handler. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A6.3: `_project_delete` lifted to `delete_project` in `core/projects/mutations.py` (returns dict; CLI wrapper preserves the `--confirm` operator-facing text). New `ds-project:manage` mode under `canonical/skills/ds-project/modes/manage/` wraps `get_project_list` + `set_active_project` + `deactivate_project` + `delete_project` per the AI-presents-from-database discipline. Final A6 PR. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — B.3: git pre-push hook + installer wiring landed. `ds workflow run pre-push --non-interactive` dispatches deterministic gates; `ClaudeCodeInstaller.git_repo_root` opt-in plants `<repo>/.git/hooks/pre-push`. No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-21 — Platform profile clarification: `~/.dream-studio/state/platform.json` is NOT a SQLite table and is NOT managed by the migration runner. It is a flat JSON file written by `core.config.platform.ensure_platform_recorded()` during install and `ds doctor`. It lives alongside `studio.db` in the `state/` directory but is outside SQLite authority. Override via `DS_PLATFORM_PROFILE_PATH`. No migration required. -->

<!-- Last reviewed 2026-05-21 — TA0 SDLC entity creation events: migration 061 added. Migration 061 (`061_backfill_sdlc_creation_events.sql`) backfills synthetic `project.created`, `milestone.created`, and `work_order.created` events into canonical_events for rows that predate event emission. Uses deterministic `backfill-<type>-<id>` event_ids and `INSERT OR IGNORE` for idempotency. attribution_status = 'backfill' marks them as synthetic. Forward emission added to `register_project`, `create_milestone`, and `create_work_order`. No schema DDL change (data-only migration). No policy change here. -->

<!-- Last reviewed 2026-05-21 — TA0b dual event store reconciliation: three new migrations applied. Migration 058 is documentation-only (registers domain field validation requirement; no schema change). Migration 059 adds `_built_from_event_id TEXT` column and `idx_execution_events_canonical_link` index to `execution_events`, establishing the projection link from execution_events rows back to their source canonical_events row. Migration 060 backfills `trace.domain` on existing canonical_events rows ('telemetry' for session/prompt/tool/token/execution event types; 'sdlc' for work_order/task/milestone/project/skill event types) and backfills `_built_from_event_id` on existing execution_events rows that can be matched by event_type. The `execution_events` table is now a projection of `canonical_events`; direct writes to execution_events outside the projection path are deprecated. `canonical_events` is the authoritative event store. -->

<!-- Last reviewed 2026-05-22 — TA0c activity_log retirement: migrations 062 and 063 applied. Migration 062 is destructive/structural: relaxes `activity_id` from NOT NULL to nullable in 7 child tables (hook_executions, hook_findings, sec_sarif_findings, sec_manual_reviews, sec_cve_matches, sec_hook_checks, adapter_executions) via table-recreation pattern; permanently retires `vw_graph_edges` and `vw_component_stats` (both broken since initial commit 790965e — wrong column names and non-existent table refs); rewrites `vw_activity_timeline` to query `canonical_events` and `vw_guardrail_decisions` to query `guardrail_decisions` directly; backfills 159 historical `activity_log` rows into `canonical_events` via `INSERT OR IGNORE` with deterministic `backfill-activity-log-<id>` event_ids and `trace.attribution_status = 'backfill'`. Migration 063 drops the `activity_log` table and its 4 indexes. `canonical_events` is now the sole event store. All read/write sites in production code have been migrated off `activity_log`. -->

<!-- Last reviewed 2026-06-07 — WO-M dual-canonical authority cutover: migration 102 (`102_drop_canonical_events.sql`) renames `canonical_events` to `canonical_events_legacy_backup` and creates a `canonical_events` compat VIEW as a UNION of `business_canonical_events` and `ai_canonical_events` with legacy column mappings. All 42 production readers that SELECT from `canonical_events` continue to work via the compat VIEW. Direct writes to `canonical_events` are retired: `spool/ingestor.py` promotes `_write_to_dual_canonical` to primary (removing the legacy `_write_to_sqlite` path), and `core/event_store/event_store.py` calls `_write_to_dual_canonical` directly. `scripts/backfill_dual_canonical.py` was extended to handle the post-migration state where the source table is `canonical_events_legacy_backup`. Backfill result: 8433 historical rows processed, 0 write failures, parity confirmed in both authority tables. `business_canonical_events` and `ai_canonical_events` are now the canonical event substrates. -->

<!-- Last reviewed 2026-05-23 — Phase 18.1.7 project-spine rename: migration 070 (`070_business_renames.sql`) renames all `ds_*` project-spine tables to `business_*` to align naming with v2 dual-canonical architecture. Renamed pairs: `ds_projects`→`business_projects`, `ds_milestones`→`business_milestones`, `ds_work_orders`→`business_work_orders`, `ds_tasks`→`business_tasks`, `ds_design_briefs`→`business_design_briefs`, `ds_work_order_types`→`business_work_order_types`. Migration copies data from `ds_*` into the renamed tables and drops `ds_*` originals; idempotent on fresh installs where `ds_*` never existed. All production code, queries, mutations, CLI handlers, and emitters updated. `sqlite_bootstrap.py` error handler extended to skip migration 070 gracefully on test DBs that never had `ds_*` source tables. Authority, schema shape, and column definitions unchanged — naming clarified only. -->


<!-- Last reviewed 2026-05-22 — TA1 task lifecycle events: migration 064 added. Migration 064 (`064_backfill_task_creation_events.sql`) is a data-only backfill: inserts synthetic `task.created` events into canonical_events for all pre-TA1 task rows by joining ds_tasks → ds_work_orders to resolve the full SDLC trace (project_id, milestone_id, work_order_id, task_id). Deterministic event IDs (`backfill-task-created-<task_id>`) and `INSERT OR IGNORE` guarantee idempotency. attribution_status = 'backfill' marks them as synthetic. Forward emission added to `create_task()` and `add_tasks_from_file()` (task.created) and to `delete_project()` cascade (task.deleted per task). `task.completed` trace enriched with milestone_id + project_id (resolved via JOIN). task.started has no call site — tasks have no in_progress state; type registered for TA2 wiring only. No DDL change (data-only migration). No policy change here. -->

<!-- Last reviewed: TA2 (2026-05-22) — no structural change required for this workstream -->


<!-- Last reviewed 2026-05-22 — TA3 reviewed; no changes required for this doc. -->

<!-- Last reviewed 2026-05-22 — Phase 18.0 C3: migration 065 added ( 65_remove_test_fixture_contamination.sql). Data-only (no DDL): deletes 23 test fixture rows from ds_projects that were written to the production DB by pytest tests bypassing guard_real_homedir (names: 'My Project', 'Programmatic Project', 'API Project', 'TA0 Verification Test', 'TA0 E2E Verify'). Idempotent DELETE WHERE. No schema change. No authorization boundary change. -->

<!-- Last reviewed 2026-05-22 -- Phase 18.1.1 adds migration 066 (066_raw_claude_code_events.sql), establishing the L1 raw layer of the v2 data architecture. The new raw_claude_code_events table preserves the full native event shape (source_payload TEXT) for every Claude Code event, with 14 indexes covering individual correlation ID components (session_id, project_id, workflow_id, skill_id, agent_id, hook_id, tool_id), the composed correlation_id, event_type, received_at, event_timestamp, and compound pairs (project x time, type x time, session x type). The spool ingestor dual-writes to raw_claude_code_events FIRST (raw write failure leaves the spool file in inbox for retry), then proceeds to canonical_events. A backfill script (scripts/backfill_raw_claude_code_events.py) reconstructed 1,909 existing canonical_events rows into raw using INSERT OR IGNORE; backfilled rows carry _backfill=True in source_payload to distinguish them from forward-written events. raw_claude_code_events is the first adapter-specific raw table; future adapters will get separate tables (raw_cursor_events, raw_codex_events, etc.). -->

## Phase 18.1.2 Review (2026-05-22)

Migration 067 adds business_canonical_events and ai_canonical_events (L2a/L2b dual canonical tables). Both tables include event_id PK, received_at, event_type, event_timestamp, schema_version, trace JSON, payload JSON, correlation_id (indexed), severity, and source columns. business_canonical_events adds project_id, milestone_id, work_order_id, task_id denormalized columns. ai_canonical_events adds session_id, skill_id, workflow_id, agent_id, hook_id, model_id denormalized columns. 25 explicit indexes plus 2 implicit PK indexes. canonical_events is NOT touched -- preserved for legacy readers during Phase 18.1.x transition.

<!-- Last reviewed 2026-05-22 — Phase 18.1.5 projection framework: migrations 068 (projection_framework_tables) and 069 (business_work_orders) added. Migration 068 creates projection_state (cursor tracking per projection: last_processed_business_event_id, last_processed_ai_event_id, last_run_at, events_processed_total, events_failed_total), projection_dead_letter (transient failure quarantine: event_id, event_source, projection_name, error_message, error_traceback, failed_at, retry_count, last_retry_at, status CHECK IN ('active','resolved','ignored')), and projection_retry_queue (exponential backoff retry: event_id, event_source, projection_name, next_retry_at, retry_count). Migration 069 creates business_work_orders L3 hub-and-spoke table projected from business_canonical_events by WorkOrderProjection. No existing tables modified. Schema version: 69 migrations applied. -->

<!-- Last reviewed 2026-05-23 — Phase 18.1.9 test infrastructure cleanup: migration 071 (071_drop_activity_log_fk_from_workflow_tables.sql) added. Structural DDL: removes stale FOREIGN KEY (activity_id) REFERENCES activity_log from raw_workflow_runs and raw_workflow_nodes using the backup-table pattern (CREATE AS SELECT → DROP → CREATE new schema → INSERT → DROP bak). activity_log was dropped in migration 063; with PRAGMA foreign_keys = ON active, any INSERT into these tables failed with "no such table: main.activity_log". RENAME pattern avoided due to vw_activity_timeline referencing canonical_events causing a broken-view abort. Additionally, studio_db._connect now explicitly executes PRAGMA foreign_keys = ON after _run_migrations() completes, since migration 062 issues PRAGMA foreign_keys = OFF internally and the terminal ON inside that migration did not reliably restore it in all code paths. Schema version: 71 migrations applied. -->


<!-- Last reviewed 2026-05-24 — Phase 18.1.13: ds validate and ds doctor --help text updated to explicitly identify each command's health-check plane. ds validate description now reads: DB authority plane (schema version, migrations, module profiles). ds doctor description now reads: Claude Code integration plane (skills, agents, hooks, routing, version). Each help text cross-references the other command. README.md health-checks section expanded; docs/operations/fresh-install-validation.md updated to require both commands. No runtime behavior change. No new CLI surface. No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-26 — Phase 18.1.15b: hook install opt-out and contributor docs only; no schema or DB changes. No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-27 — Phase 18.2.3 task and milestone projections: migrations 072 and 073 added. Migration 072 (072_task_projection_event_tracking.sql) is additive DDL: adds source_event_id TEXT and last_event_id TEXT columns to business_tasks. These columns are used by TaskProjection to track which canonical event created the row (source_event_id) and which event was last applied to it (last_event_id), enabling idempotent replays. Migration 073 (073_milestone_projection_event_tracking.sql) is additive DDL: adds the same source_event_id and last_event_id columns to business_milestones for MilestoneProjection. Both migrations are additive and non-destructive. Direct writes to business_tasks and business_milestones from writer functions (create_task, add_tasks_from_file, mark_task_done, create_milestone, close_milestone) have been removed; the projection pipeline is now the sole write path for these tables. No policy or publication boundary change. -->

<!-- Last reviewed 2026-05-29 (rev3) — migration 082: defensive restoration of memory_entries_fts triggers (no schema content change; triggers are non-schema objects restored by migration 082). No new authority section needed. -->

<!-- Last reviewed 2026-05-29 (rev2) — migration 081 extended fix: full drop-all-13-views + recreate-12 pattern; vw_activity_timeline permanently retired. Exception handler updated for partial-fixture tolerance of token_usage_records and ai_usage_operational_records. Test fixtures updated to use latest_migration_version(). No new schema content change needed in this document. -->

<!-- Last reviewed 2026-05-29 — migration 081 fix: PRAGMA legacy_alter_table replaced with DROP VIEW IF EXISTS vw_activity_timeline before table reconstruction, fixing RENAME failure on Linux SQLite. packs.yaml meta handler list updated for on-memory-ingest. No schema content change to this document — migration 081 section already present from PR #97. -->

<!-- Last reviewed 2026-05-27 — Phase 18.2.4 design brief lifecycle events: migrations 074 and 075 added. Migration 074 (074_design_brief_projection_event_tracking.sql) is additive DDL: adds source_event_id TEXT and last_event_id TEXT columns to business_design_briefs, matching the idempotency-tracking pattern from migrations 072/073. Migration 075 (075_design_brief_backfill_events.sql) is a data-only backfill that inserts synthetic design_brief.created and design_brief.locked events into business_canonical_events for pre-event-sourcing brief rows, then directly sets source_event_id/last_event_id on those rows so DesignBriefProjection is converged without a rebuild. Three new event types registered: design_brief.created, design_brief.updated, design_brief.locked (all routed to business_canonical_events). Writers now emit canonical events for lock and field-update operations; direct UPDATE writes removed from those paths. The direct INSERT in create_design_brief is retained for existence-check guard in website:discover. Schema version: 75 migrations applied. No policy or publication boundary change. -->

<!-- Last reviewed 2026-05-27 — Phase 18.2.5 project status writers and cascade events: migrations 076 and 077 added. Migration 076 (076_project_projection_event_tracking.sql) is additive DDL: adds source_event_id TEXT and last_event_id TEXT columns to business_projects, matching the idempotency-tracking pattern from migrations 072–075. Migration 077 (077_project_backfill_events.sql) is a 3-step data-only backfill: (1) inserts synthetic project.created events for all project rows with source_event_id IS NULL using deterministic IDs (backfill-project-created-<id>); (2) inserts synthetic project.deactivated events for paused projects; (3) updates source_event_id/last_event_id on all affected rows so ProjectProjection is already converged. Six new event types registered or formalized: project.activated, project.deactivated (replace direct UPDATEs in set_active_project and deactivate_project), work_order.deleted, design_brief.deleted (cascade emissions from delete_project), plus project.registered and project.updated marked as DEPRECATED (no callers). ProjectProjection (project.created/activated/deactivated/deleted) registered in runner.py and projection_cli.py. Direct UPDATE/DELETE writes removed from set_active_project, deactivate_project, and delete_project — events drive the projection. Direct INSERT in register_project retained (existence-check guard pattern). Soft-delete pattern: status='deleted' rather than hard DELETE FROM — row stays queryable. Schema version: 77 migrations applied. No policy or publication boundary change. -->

<!-- Last reviewed 2026-05-28 — fix/linux-ci-failures-batch2: migration 078 (078_memory_entries.sql) added. This migration was renamed from 011 to 078 to avoid a UNIQUE constraint conflict with the closed gap at slot 011 (Phase 18.1.13). The memory_entries table stores Claude Code memory entries (key, value, type, metadata, created_at, updated_at). Schema version: 78 migrations applied. No existing tables modified. No policy or authorization boundary change. -->

<!-- Last reviewed 2026-05-28 — fix/full-ci-failures-batch3: migration 011 (011_memory_entries.sql) restored — it was incorrectly renamed to 078 in batch2. Migration 078 is now a retained no-op guard (CREATE TABLE IF NOT EXISTS, which is a no-op since 011 creates the table first). The memory_entries table schema is defined at 011 and extended at 032 (semantic memory columns). Schema version: 78 migrations applied. No schema policy or authorization boundary change. -->

<!-- Last reviewed 2026-05-29 — 18.4.6-followup-1: migration 083 (083_canonical_events_migration_authority.sql) added. This migration establishes canonical_events as a migration-owned table using the authoritative 14-column schema from spool/ingestor.py:_write_to_sqlite (event_id, event_type, timestamp, trace, severity, payload, actor, confidence_score, source_type, raw_prompt_retained, raw_tool_output_retained, schema_version, created_at, invocation_mode). canonical_events was previously Python-owned (created lazily by EventStore._init_tables and the ingestor, not by any migration). Migration 083 uses CREATE TABLE IF NOT EXISTS — it is a no-op on any DB where canonical_events already exists (schema 82+ upgrade path). EventStore._init_tables updated to align with the 14-column schema and is now an idempotent fallback. Schema version: 83 migrations applied. The sqlite_bootstrap.py swallow entry for canonical_events reclassified from stale to intentional — migrations 052-064 still run before 083 in sequence and still fail gracefully on fresh installs. -->

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- reviewed: 2026-05-30, migration 086 delta infrastructure + no-marker attribution. No semantic changes required. -->

<!-- reviewed: 2026-05-30, migration 086 delta infrastructure + no-marker attribution. No semantic changes required. -->

<!-- reviewed: 2026-05-30, migration 087 skill_id on scan runs + code-quality fan-out. No semantic changes required. -->

<!-- 2026-05-31: reg_projects deleted (migration 084); business_projects is canonical. pi_* tables dropped; project_intelligence and prd_authority updated to read detected_stack/stack_json from business_projects. -->

<!-- 2026-05-31: migration 088 removes dead FK refs to dropped reg_projects from raw_sessions/handoffs/specs/tasks. upsert_project() writes to business_projects. -->

<!-- 2026-05-31: migration 088 fixed (explicit column names, view drop/recreate). ds_memory, discovery_internal updated. -->

<!-- 2026-06-01: security_scan_runs → scan_runs, security_findings → findings, security_scan_deltas → scan_deltas (migration 089); brownfield intake prompt added; proving-index.md added. -->

<!-- 2026-06-01: guard_events table (migration 090), memory_entries taint tracking (migration 091), memory_taint.py module -->

<!-- 2026-06-01: fix migration 089 view-drop-before-rename (vw_approach_patterns/vw_security_summary); fix v38 test fixture findings→security_findings -->

<!-- 2026-06-03: migration 092 adds ds_eval_baselines table for behavioral eval harness (18.8.3) -->

<!-- 2026-06-03: migration 093 ds_workflow_pattern_signals — workflow pattern detection for Phase 19 -->

<!-- 2026-06-03: migration 094 adds label column to ds_eval_baselines for pre-Phase-19 baseline capture (18.10) -->

<!-- 2026-06-03: migration 095 ds_user_extensions — Phase 19.1 unified extensions schema (adaptive learning foundation) -->

<!-- 2026-06-03: migration 096 creates ds_friction_signals (3 signal types: dismissed_finding, partial_completion, pattern_gap) + alters findings table to add dismissed_at/dismissed_reason columns (Phase 19.2 Friction Signal Harvester) -->
<!-- 2026-06-03: migration 097 adds classification_confidence, classification_reason, classification_skipped to ds_friction_signals (Phase 19.3 Gap Classifier) -->
<!-- 2026-06-03: migration 098 adds validation_detail TEXT column to ds_user_extensions (Phase 19.5 Retroactive Validation audit trail) -->
<!-- 2026-06-05: phase-18-2 gap closure + popup refactor — no schema change, no migration; _repo_stack_evidence() removed from /details critical path; session_collector NULL project_id fix -->
<!-- Last reviewed 2026-06-05 — Phase 18.6.2 (migration 099): DROP TABLE for 8 project_* tables and DROP VIEW for vw_project_readiness_latest. All 8 tables had 0 rows and no FK dependencies. Tables dropped: project_readiness_scorecards, project_health_scorecards, project_intake_records, project_intake_questions, project_assumption_records, project_milestone_records, project_work_order_authority_records, project_change_order_records. prd_version_records, prd_amendment_records, prd_route_reconciliation_records, and prd_documents remain. No new tables added. Guards added to 5 code paths (prd_authority.py, analytics_ingestion.py, controls.py, contract_atlas.py, module_contracts.py) before drop. -->
<!-- 2026-06-05: Wave 2 career annihilation — migration 100 DROP TABLE IF EXISTS for 15 career_* tables (all 0 rows, no views, no incoming FK deps): career_application_events, career_application_field_mappings, career_applications, career_browser_automation_runs, career_case_studies, career_cover_letter_versions, career_evidence_refs, career_interview_story_bank, career_job_opportunities, career_portfolio_artifacts, career_profile_fields, career_profiles, career_resume_versions, career_role_targets, career_scorecards. Creating migration 044 remains immutable history; the capability_center, scoped_agents, and github_repo_intake tables it created are NOT touched. No new tables added. -->

<!-- 2026-06-05: Wave 2 career annihilation — career_ops module, 15 career_* tables (migration 100, drop-only, 0 rows, IF EXISTS, no view/FK deps; migration 044 stays immutable), ds-career skill pack, /career-ops route, career_ops contract+profile, and career expert workflow removed. capability_center/scoped_agents/github_repo_intake unchanged. Body edit: removed the `career_profiles`/`career_*` tables bullet and dropped "Career Ops" from the "authority lives in migration 044" lead-in (the other three modules still live there); the "Career data is private by default and excluded from public exports" sentence stays as a privacy-class statement. -->

<!-- 2026-06-06: Wave 4+5 ghost-surface removal reviewed — realtime websocket layer (stream/metrics, connection_manager, broadcast feeder, 2 project_intelligence ghost websockets), export/report/schedule routes + projections/exporters + scheduler/reports backends, and deprecated production_dashboard.py removed (-18,865 lines, no schema change). This doc did not describe the removed surfaces; no semantic change required. -->


<!-- 2026-06-06: Wave 6 verified-dead table drops — migration 101 (101_drop_verified_dead_tables.sql) is a DROP TABLE-only migration. 13 tables dropped, all 0 rows on per-table verification with no live code readers/writers, no view deps, and FK-safe child-before-parent order (IF EXISTS on every DROP): automation_checkpoints, automation_log, risk_mitigations, risk_register, telemetry_entity_registry, telemetry_module_registry, reg_repo_research_links, agent_result_records, capability_center_records, dashboard_authority_reconciliation_records, guardrail_rules_audit, sec_hook_checks, workflow_agent_skill_mappings. The audit's ~38-candidate list was reduced to 13 after per-table verification found live paths on 18; the 7 prd_* cluster tables are deferred (view/FK web with kept tables). Creating migrations (005/007/020/021/027/028/037/039/044) remain immutable history. Body edit: the migration-044 paragraph now records that capability_center_records, workflow_agent_skill_mappings, and agent_result_records were dropped (Capability Center reports empty state; normalized agent results route to agent_invocations/decision_records/validation_results/artifact_records). No additive DDL; no policy or publication boundary change. -->

<!-- Last reviewed 2026-06-07 — WO-F prd_* cluster drop (migration 103): migration 103 drops the entire prd_* cluster (prd_documents, prd_plans, prd_tasks, prd_sessions, prd_handoffs, session_tasks, prd_version_records, prd_amendment_records, prd_route_reconciliation_records) and the views vw_prd_progress and vw_task_details. AD-10 decision: business_projects IS what PRD was. All prd_* callers removed from studio_db.py, prd_authority.py (deleted), routes/prd.py (deleted), analytics_ingestion.py, module_contracts.py, dashboard_freshness.py, contract_atlas.py, contract_registry.py, project_intelligence.py, shared_intelligence.py, resume_from_handoff.py, and migrate_prd_schema.py (deleted). -->
