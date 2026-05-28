# Migration Authority

## Canonical Migration Directory

**`core/event_store/migrations/`** is the single source of truth for database schema migrations.

All new migrations MUST be added here. The migration runner in `core/event_store/studio_db.py` reads from this directory exclusively.

## Schema Version Authority

The `_schema_version` table tracks which migrations have been applied. It is managed by `studio_db._run_migrations()` and must not be modified manually or by external tools.

## Root `migrations/` Directory — Legacy

The root `migrations/` directory contains legacy migration files from an earlier execution-graph and security-linking phase. These files are **not managed by the canonical migration runner** and exist only as historical reference.

**Status:** Legacy / unmanaged. Do not add new files here.
**Disposition:** Archive to `.archive/migrations/` in Phase 6 after confirming no content is unique or unreplaced.

### Root migration inventory (as of 2026-05-09):

| File | Content | Status |
|---|---|---|
| 003_execution_graph.sql | Execution graph tables | Superseded by core migrations |
| 007_production_security_system.sql | Security tables | Superseded by 020_security_findings.sql |
| 008_fix_security_linking.sql | Security FK fixes | Applied; superseded |
| 008_fix_security_linking_v2.sql | Security FK fixes v2 | Applied; superseded |
| 009_add_missing_execution_tables.sql | Execution table gaps | Superseded |
| 010_drop_prd_tables.sql | PRD table cleanup | Applied; superseded by 012_prd_schema.sql |
| 011_delete_prd_tables.sql | PRD table deletion | Applied; see migration 011 gap below |
| 011_delete_prd_tables_simple.sql | PRD table deletion (simplified) | Applied |
| 012_security_governance_schema.sql | Security governance | Superseded by core migrations |
| 013_create_security_views.sql | Security views | Superseded by 029_analytics_views.sql |
| 014_migrate_events_and_delete_tables.sql | Event migration | Applied; destructive |
| 015_final_table_reduction.sql | Table cleanup | Applied; destructive |

## Migration 011

`core/event_store/migrations/011_memory_entries.sql` — this migration exists and is valid.

**History:** The 011 slot was originally left as an intentional numbering gap to avoid collision with the legacy root `migrations/011_delete_prd_tables.sql`. The gap was intentionally closed in phase 18.1.13 by adding `011_memory_entries.sql`, which creates the `memory_entries` table previously bootstrapped at application startup. The `IF NOT EXISTS` guard in the migration safely handles existing databases.

## Database Connection Authority

**`core/config/database.py`** is the single source of truth for database connections.

### Canonical connection functions:
- `get_connection(read_only=False)` — primary connection function
- `DatabaseContext(read_only=False)` — context manager with auto-commit/rollback
- `transaction(immediate=False)` — transaction context manager

### Allowed direct sqlite3.connect:
- `core/config/database.py` — the canonical module itself
- `core/event_store/studio_db.py` — migration runner (needs raw connection before schema exists)
- Test files using explicit temp DBs or `:memory:`
- Archived utility scripts in `scripts/_archived/`

### Disallowed:
- Production runtime modules connecting to `~/.dream-studio/state/studio.db` directly
- Projection/API routes bypassing canonical connection setup
- Security/governance modules with hardcoded DB paths

## Runtime Mutation Policy

Schema mutations (CREATE TABLE, ALTER TABLE, DROP TABLE) must only occur inside numbered migration files in `core/event_store/migrations/`. Runtime code must not create or alter tables outside the migration system.

Exception: `CREATE TABLE IF NOT EXISTS _schema_version` in the migration runner bootstrap is allowed as a transitional necessity.

Migration `040_production_readiness_authority.sql` is additive. It introduces
production readiness assessment, control result, finding, remediation,
scorecard, release-readiness, compliance flag, and skill/control mapping tables.
It does not authorize live migration execution by itself; live updates still
require the normal backup, verification, approval, and rollback boundary.

Migration `042_token_usage_source_refs.sql` is additive. It adds source and
evidence reference columns to `token_usage_records` so legacy token events can
be reconciled into current telemetry authority without recreating
`canonical_events`. The migration is repair-safe for partial historical
fixtures by ensuring the target table exists before applying column additions.

Migration `043_ai_usage_accounting.sql` is additive. It extends
`token_usage_records` with adapter accounting visibility fields and creates
`ai_adapter_accounting_profiles` plus `ai_usage_operational_records`. It does
not inspect provider billing credentials and does not convert subscription-plan
tokens into API-dollar costs. Cost is reportable only when visibility/source
metadata says it is exact, provider-reported, explicitly estimated, or an
operator-configured subscription allocation.

Dashboard launch command changes are runtime-surface changes, not migration
authority changes. `ds dashboard --serve`, `--open`, and `--check` must use the
existing resolved SQLite path and must not create schema, run migrations,
backfill records, or treat dashboard output as authority.

Migration `044_career_capability_agent_github_authority.sql` is additive. It
creates private opt-in Career Ops tables, Capability Center records, scoped
agent registry/context/result tables, and GitHub repo intake evaluation tables.
It does not enable Career Ops by default, publish career data, inspect external
repositories, copy code, add dependencies, fork/vendor repositories, submit job
applications, or authorize agent execution.

Migration `045_task_attribution_authority.sql` is additive. It creates
`task_attribution_records` so meaningful AI/adapter execution units can be
linked to project/milestone/task/Work Order/process-run context, skills,
workflows, tools, files touched, commands, validation, outcome, rework,
commit/PR/result refs, and security/readiness impact. It does not create a
second telemetry system, infer model/provider precision, infer token or cost
values, authorize adapter execution, or mutate live SQLite outside the normal
approved migration boundary.

Legacy install migration is a rehydration flow, not a schema-authority change.
`ds migrate-legacy` applies the current repo-backed migrations to a fresh active
database and then copies only compatible rows into current tables. It must not
recreate old legacy tables as active authority, bulk-copy `canonical_events`,
copy file-sprawl into active state, or run destructive migrations. Unknown or
non-mappable legacy data remains in the backup/manual-review retention set.

Migration `046_platform_hardening_authority.sql` is additive. It creates
records for skill/workflow evaluations, policy decisions, connector ingestion
runs, privacy/redaction exports, local watch declarations, sanitized team
rollups, installer/distribution checks, and demo/case-study packets. It does
not authorize cleanup, external mutation, Docker execution, live SQLite writes,
push/deploy actions, secret access, or public publication.

Migration `047_prd_lifecycle_authority.sql` is additive. It creates project
intake, intake question, assumption, PRD version, milestone, Work Order
authority, change-order, amendment, and route-reconciliation tables. It does
not delete or rewrite legacy `prd_documents`; that table remains a
compatibility list surface while `prd_version_records` and related lifecycle
tables carry current continuation authority. It does not authorize writing PRD
files into external repositories, overwriting PRDs without version lineage,
skipping change orders for material scope changes, or mutating live SQLite
outside the normal approved migration boundary.

<!-- Last reviewed 2026-05-20 — repo-wide `py -m black .` formatting applied; no behavior or policy change required here. -->

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

<!-- Last reviewed 2026-05-21 — Platform profile is NOT migration-backed: `core.config.platform` writes `platform.json` as a flat JSON file, not as a SQLite table. No new migration is required. No changes to `core/event_store/migrations/`. -->

<!-- Last reviewed 2026-05-21 — TA0 adds migration 061 (`061_backfill_sdlc_creation_events.sql`). It is a data-only (no DDL) backfill migration: inserts synthetic `project.created`, `milestone.created`, and `work_order.created` events into canonical_events for all rows in ds_projects, ds_milestones, and ds_work_orders that predate event emission. Deterministic event IDs (`backfill-<type>-<entity_id>`) and `INSERT OR IGNORE` guarantee idempotency. attribution_status = 'backfill' in trace distinguishes synthetic from forward-emitted events. task.created backfill is deferred to TA1. No authorization for live DB writes beyond the normal migration approval boundary. -->

<!-- Last reviewed 2026-05-21 — TA0b adds migrations 058–060 to `core/event_store/migrations/`. Migration 058 (`058_ta0b_domain_field_validation.sql`) is documentation-only — SQL comments only, no schema DDL; registers the domain field validation requirement in the migration log. Migration 059 (`059_ta0b_execution_events_projection_link.sql`) is additive: adds `_built_from_event_id TEXT` column and a partial index to `execution_events` so each projected row carries a traceable link to its source canonical_events row; idempotent (ALTER TABLE ... ADD COLUMN is no-op if column exists; CREATE INDEX IF NOT EXISTS). Migration 060 (`060_ta0b_backfill_execution_events_from_canonical.sql`) is a one-time backfill: updates `trace` JSON in canonical_events to set `$.domain` for rows missing it, then inserts missing execution_events rows from canonical_events for execution.started / execution.completed / execution.failed event types. All three are additive and do not drop, rename, or alter existing columns. -->

<!-- Last reviewed 2026-05-28 — 18.4.3-cleanup: studio_db.py modified (black reformatting + inline cq-006-suppress comments). No migrations added. No schema changes. -->

<!-- Last reviewed 2026-05-28 — 18.4.4: migrations 079 and 080. Migration 079 adds intelligence_surfaced_at TEXT to memory_entries and FTS sync triggers (INSERT/UPDATE/DELETE on memory_entries → memory_fts). Migration 080 extends memory_entries with source_type, source_id, lifecycle_state, confidence, updated_at, provenance, lineage, relationships — columns expected by MemoryStore.upsert_by_provenance() but missing from migration 011. Both are additive (nullable columns, IF NOT EXISTS). No destructive DDL. No new primary authority table. -->

<!-- Last reviewed 2026-05-22 — TA0c adds migrations 062 and 063. Migration 062 (`062_nullify_activity_id_backfill_and_replace_views.sql`) is structural and destructive: drops all 15 views before any table recreation (SQLite recompiles all views during ALTER TABLE RENAME; dropping all prevents broken-view aborts); recreates 7 child tables with `activity_id` nullable (NOT NULL constraint removed, FK to activity_log removed) via the SQLite table-recreation pattern; permanently retires `vw_graph_edges` and `vw_component_stats` (not recreated — broken since initial commit 790965e); recreates 13 valid views with `vw_activity_timeline` rewritten to query `canonical_events` and `vw_guardrail_decisions` rewritten to query `guardrail_decisions`; backfills 159 `activity_log` rows into `canonical_events` with `INSERT OR IGNORE` and `trace.attribution_status = 'backfill'`. Migration 063 (`063_drop_activity_log.sql`) drops `activity_log` and its 4 indexes. These are the first destructive (DROP TABLE) migrations in this directory since the initial build. The `_ta0c_cleanup_dirty_state.py` tool in `tools/` handles recovery from partial migration 062 runs caused by Python 3.12 sqlite3 auto-commit behavior on the first DDL statement. -->

<!-- Last reviewed 2026-05-22 — TA1 adds migration 064 (`064_backfill_task_creation_events.sql`). Data-only (no DDL). Inserts synthetic `task.created` events into canonical_events for all pre-TA1 ds_tasks rows; full SDLC trace resolved via ds_tasks JOIN ds_work_orders. Deterministic event IDs and INSERT OR IGNORE for idempotency. attribution_status = 'backfill'. No schema change. No authorization boundary change. -->

<!-- Last reviewed: TA2 (2026-05-22) — no structural change required for this workstream -->


<!-- Last reviewed 2026-05-22 — TA3 reviewed; no changes required for this doc. -->

<!-- Last reviewed 2026-05-22 — Phase 18.0 C3: migration 065 ( 65_remove_test_fixture_contamination.sql) added. Cleans 23 test fixture rows from ds_projects written directly to production studio.db by tests that bypassed the guard_real_homedir autouse fixture via the DatabaseRuntime singleton retaining a stale real-DB path. guard_real_homedir now calls DatabaseRuntime.reset_instance() before yield and after yield. Three tests in test_ta3_token_capture.py fixed to pass dream_studio_home=db_home / DREAM_STUDIO_HOME env var. -->

<!-- Last reviewed 2026-05-22 -- Phase 18.1.1 adds migration 066 (066_raw_claude_code_events.sql). Additive DDL: creates raw_claude_code_events table (event_id PK, received_at, event_type, event_timestamp, schema_version, source_payload, session_id, project_id, workflow_id, skill_id, agent_id, hook_id, tool_id, model_id, adapter_id, correlation_id) plus 14 indexes per Commitment 8 (mandatory indexing). This is the L1 raw layer: adapter-specific, immutable, indexed for analytical drill-down. The spool ingestor creates the table inline (CREATE TABLE IF NOT EXISTS) so the table is queryable before the migration runner applies 066. Raw write failure during spool ingest returns the spool file to inbox for retry. No existing tables modified. The backfill exception: scripts/backfill_raw_claude_code_events.py uses INSERT OR IGNORE and does not run as a migration; it is a one-time operator tool. -->

## Phase 18.1.2 Review (2026-05-22)

Migration 067 (067_dual_canonical.sql): Adds business_canonical_events and ai_canonical_events. Idempotent (CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS). Does not alter canonical_events. New tables are at v2 data layer L2a and L2b respectively. Routes determined by config/event_type_registry.py. Source column='ingestor' for live writes, 'backfill' for historical backfill from scripts/backfill_dual_canonical.py.

<!-- Last reviewed 2026-05-22 — Phase 18.1.5 adds migrations 068 and 069. Migration 068 (068_projection_framework_tables.sql) is additive DDL: creates projection_state (PK: projection_name; cursor columns: last_processed_business_event_id, last_processed_ai_event_id, last_run_at, events_processed_total, events_failed_total), projection_dead_letter (quarantine for permanently-failing events: event_id, event_source CHECK IN ('business','ai'), projection_name, error_message, error_traceback, failed_at, retry_count, last_retry_at, status CHECK IN ('active','resolved','ignored')), and projection_retry_queue (backoff retry: event_id, event_source, projection_name, next_retry_at, retry_count). Migration 069 (069_business_work_orders.sql) is additive DDL: creates business_work_orders L3 hub table (work_order_id PK, project_id, milestone_id, title, status DEFAULT 'created', created_at, started_at, closed_at, blocked_at, unblocked_at, block_reason, source_event_id, last_event_id, last_updated_at) with 6 indexes including compound (project_id, status). No existing tables modified. -->

<!-- Phase 18.1.7 (2026-05-23) adds migration 070 (070_ds_to_business_renames.sql). Structural DDL: RENAME TABLE operations renaming all ds_* operational tables to business_* per Approach A of the Phase 18.1.6 reconciliation. Renames: ds_projects → business_projects, ds_milestones → business_milestones, ds_work_orders → business_work_orders, ds_tasks → business_tasks, ds_design_briefs → business_design_briefs, ds_work_order_types → business_work_order_types. Foreign keys updated via CASCADE on all renames. All 2 rows in ds_projects and 15 rows in ds_work_orders + 5 milestones + 9 tasks + 1 brief + 10 type rows preserved. Project_* tables NOT renamed (out of scope; they drop in Phase 18.6 after Phase 18.4 builds business_* projection equivalents). -->

<!-- Phase 18.1.9 (2026-05-23) adds migration 071 (071_drop_activity_log_fk_from_workflow_tables.sql). Structural DDL: removes stale FOREIGN KEY (activity_id) REFERENCES activity_log from raw_workflow_runs and raw_workflow_nodes. Uses the backup-table pattern (CREATE TABLE bak AS SELECT * → DROP original → CREATE new table without the FK → INSERT from bak → DROP bak) to avoid the SQLite broken-view abort that RENAME TABLE triggers when any view references a non-existent table (vw_activity_timeline references canonical_events which may not exist during migration). activity_log was dropped in migration 063; the stale FK caused every INSERT into raw_workflow_runs and raw_workflow_nodes to fail with "no such table: main.activity_log" once PRAGMA foreign_keys = ON was enforced. Migration is idempotent via IF NOT EXISTS / DROP IF EXISTS guards. Schema version: 71 migrations applied. -->


<!-- Last reviewed 2026-05-24 — Phase 18.1.13: ds validate and ds doctor --help text updated to explicitly identify each command's health-check plane. ds validate description now reads: DB authority plane (schema version, migrations, module profiles). ds doctor description now reads: Claude Code integration plane (skills, agents, hooks, routing, version). Each help text cross-references the other command. README.md health-checks section expanded; docs/operations/fresh-install-validation.md updated to require both commands. No runtime behavior change. No new CLI surface. No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-26 — Phase 18.1.15b: no new migrations; schema remains at 71. No policy or contract change in this doc. -->

<!-- Phase 18.2.3 (2026-05-27) adds migrations 072 and 073. Migration 072 (072_task_projection_event_tracking.sql) is additive DDL: ALTER TABLE business_tasks ADD COLUMN source_event_id TEXT; ALTER TABLE business_tasks ADD COLUMN last_event_id TEXT. Migration 073 (073_milestone_projection_event_tracking.sql) is additive DDL: ALTER TABLE business_milestones ADD COLUMN source_event_id TEXT; ALTER TABLE business_milestones ADD COLUMN last_event_id TEXT. Both columns are nullable; existing rows retain NULL values until the respective projection (TaskProjection, MilestoneProjection) processes their source events. These columns are the projection idempotency mechanism: last_event_id prevents double-application of the same event; source_event_id provides creation traceability. Schema version: 73 migrations applied. No existing columns modified. No policy or authorization boundary change. -->

<!-- Phase 18.2.4 (2026-05-27) adds migrations 074 and 075. Migration 074 (074_design_brief_projection_event_tracking.sql) is additive DDL: ALTER TABLE business_design_briefs ADD COLUMN source_event_id TEXT; ALTER TABLE business_design_briefs ADD COLUMN last_event_id TEXT. Same projection idempotency mechanism as migrations 072/073. Migration 075 (075_design_brief_backfill_events.sql) is a 3-step data-only backfill: (1) inserts synthetic design_brief.created events into business_canonical_events for all brief rows with source_event_id IS NULL using deterministic event IDs (backfill-brief-created-<brief_id>) and INSERT OR IGNORE for idempotency; (2) inserts synthetic design_brief.locked events for locked briefs with source_event_id IS NULL using deterministic IDs (backfill-brief-locked-<brief_id>); (3) directly updates source_event_id and last_event_id on the brief rows so DesignBriefProjection is already converged without requiring a rebuild. attribution_status = 'backfill' marks synthetic events as pre-event-sourcing data. DesignBriefProjection registered in runner.py and projection_cli.py. Direct UPDATE writes for lock and field-update mutations removed from mutations.py; direct INSERT in create_design_brief retained (needed for existence-check guard in website:discover). Schema version: 75 migrations applied. No policy or authorization boundary change. -->

<!-- Phase 18.2.5 (2026-05-27) adds migrations 076 and 077. Migration 076 (076_project_projection_event_tracking.sql) is additive DDL: ALTER TABLE business_projects ADD COLUMN source_event_id TEXT; ALTER TABLE business_projects ADD COLUMN last_event_id TEXT. Same nullable projection idempotency columns as migrations 072–075. Migration 077 (077_project_backfill_events.sql) is a 3-step data-only backfill: (1) INSERT OR IGNORE synthetic project.created events into business_canonical_events for all project rows with source_event_id IS NULL, using deterministic IDs (backfill-project-created-<project_id>); (2) INSERT OR IGNORE synthetic project.deactivated events for paused projects with source_event_id IS NULL, using deterministic IDs (backfill-project-deactivated-<project_id>); (3) UPDATE business_projects SET source_event_id and last_event_id (CASE: paused rows get last_event_id = deactivated event; others get created event) WHERE source_event_id IS NULL. ProjectProjection handles project.created, project.activated, project.deactivated, project.deleted (soft delete: status='deleted', row retained). Soft-delete replaces hard DELETE FROM in cascade delete path; rows queryable via --include-deleted flag. Schema version: 77 migrations applied. No policy or authorization boundary change. -->

<!-- Phase 18.3.0 CI repair (2026-05-28) adds migration 078 (078_memory_entries.sql). Renamed from 011 to avoid UNIQUE constraint conflict with the closed gap at slot 011 (Phase 18.1.13). Creates memory_entries table: (memory_id TEXT PK, key TEXT UNIQUE NOT NULL, value TEXT, type TEXT, metadata TEXT, created_at TEXT, updated_at TEXT). Stores Claude Code memory entries from ~/.claude/projects/ session harvesting. Schema version: 78 migrations applied. No policy or authorization boundary change. -->

<!-- Phase 18.3.1 CI repair (2026-05-28) restores migration 011 (011_memory_entries.sql). This migration was incorrectly renamed to 078 during batch2 CI repair. The restoration fixes test_memory_entries_exists_after_011 (which verifies the table is created by migration 011, as required by migration 032_semantic_memory.sql). Migration 078 is now a retained no-op guard (CREATE TABLE IF NOT EXISTS is a no-op since 011 runs first). The memory_entries table creation chain: 011 creates base schema, 032 adds semantic columns (source_type, source_id, lifecycle_state, confidence, provenance, lineage, relationships, updated_at), 033 creates FTS5 index. Schema version: 78 migrations applied. No policy or authorization boundary change. -->
