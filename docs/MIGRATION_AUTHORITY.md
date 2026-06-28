# Migration Authority

## Dev vs Live Migration Workflow

**Problem:** Migrations auto-apply on every `_connect()` call. Without a guard, adding a migration file on a feature branch would silently mutate the live authority DB (`~/.dream-studio/state/studio.db`) the next time any `ds` command runs — before the PR is reviewed or merged.

**Guard mechanism (WO-MS):**

1. **Released version sentinel** — `core/event_store/migrations/.released_version` contains the highest migration number that has landed on `main`. Any migration with a higher number is considered unreleased.

2. **Auto-skip on live DB** — The migration runner (`sqlite_bootstrap.run_migrations()`) compares each pending migration's version against the released version. If the migration is unreleased AND the DB is the live authority AND `DREAM_STUDIO_APPLY_UNRELEASED` is not set, the migration is skipped with a `RuntimeWarning`.

3. **Auto-backup before first live apply** — When any migration is about to apply to the live authority DB, a timestamped snapshot is written to `~/.dream-studio/state/backups/studio-pre-N-TIMESTAMP.db` first. This is a no-op cost for released-only migrations; it is the safety net for the rare `DREAM_STUDIO_APPLY_UNRELEASED=1` path.

**Live authority = `~/.dream-studio/state/studio.db` (and any path under `~/.dream-studio/`). Temp DBs, test DBs, and CI DBs in other paths are never gated.**

### Developer workflow

```text
# Normal dev: create migration file, add code, run tests
# Migrations apply normally to your temp/test DBs (no guard)
py -m pytest tests/ -k migration

# The gate fires only if your ds command runs against the live DB:
py -m interfaces.cli.ds project state
# → [migration-safety] Migration 106 is unreleased (released_version=105). Skipping live authority apply.

# To test against a scratch DB (recommended for in-dev migration work):
DREAM_STUDIO_HOME=/tmp/scratch-ds py -m interfaces.cli.ds project state

# To explicitly apply an unreleased migration to the live DB (with backup):
DREAM_STUDIO_APPLY_UNRELEASED=1 py -m interfaces.cli.ds project state
```

### When a migration PR merges to main

Update `.released_version` to the new max migration number as part of the same PR:

```
echo "106" > core/event_store/migrations/.released_version
```

This file is tracked by git and reviewed as part of the migration PR. After merge, `main` carries the updated sentinel and the guard gate advances.

### Migration-risk gate integration

The `migration-risk` pre-push gate fires when `core/event_store/migrations/` changes. Its printed reminder includes the matrix-watch requirement. The dev-vs-live guard is complementary: the gate prevents premature pushes; the guard prevents premature live-DB applies during branch development.

---

## Canonical Migration Directory

**`core/event_store/migrations/`** is the single source of truth for database schema migrations.

All new migrations MUST be added here. The migration runner in `core/event_store/studio_db.py` reads from this directory exclusively.

## Schema Version Authority

The `_schema_version` table tracks which migrations have been applied. It is managed by `studio_db._run_migrations()` and must not be modified manually or by external tools.

## Notable Drop Migrations

| Migration | Tables dropped | Reason |
|---|---|---|
| 130 | `artifact_records`, `authority_projection_records`, `blocker_resolution_records`, `hook_findings`, `canonical_events_legacy_backup` | Aspirational telemetry tables (0 rows, no production writers). Backup table data already migrated to dual-canonical in migration 102. |
| 129 | `hook_executions`, `validation_failures` | Repointed to DuckDB views; SQLite tables no longer needed. |

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

### Canonical connection functions (SQLite authority):
- `get_connection(read_only=False)` — primary connection function
- `DatabaseContext(read_only=False)` — context manager with auto-commit/rollback
- `transaction(immediate=False)` — transaction context manager

### DuckDB analytics store connections (never-authority):
- `core/analytics/duckdb_store.connect_analytics(read_only=True)` — read-only analytics access for API routes
- `core/analytics/duckdb_store.connect_analytics(read_only=False)` — write access restricted to `core/projections/runner.py` only
- DuckDB schema is managed by `ensure_analytics_schema()` in `core/analytics/duckdb_store.py`, not by the SQLite migration runner

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

Migration `081_cost_columns_numeric.sql` is a type-correction migration (not
additive). It converts `token_usage_records.estimated_cost` and
`ai_usage_operational_records.cost_amount` from `REAL` to `NUMERIC(20,8)` to
close `db-005` findings from the 18.4.2 database audit. SQLite does not support
`ALTER COLUMN TYPE`; the migration uses the table-reconstruction pattern with
`PRAGMA legacy_alter_table = ON` to sidestep SQLite 3.26+ view-validation
during RENAME (explained in the migration file comment; `legacy_alter_table` is
scoped ON/OFF within the migration, not persisted). The `db-005-suppress`
comments in migrations 037, 042, and 043 mark the original REAL declarations
that this migration supersedes. See `docs/architecture/aspirational-schema-debt.md`
for architectural debt in `vw_activity_timeline`/`canonical_events` surfaced during
pre-push diligence; remediation is deferred to 18.4.6.

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

Migration `116_task_acceptance_criteria.sql` is additive. It adds a nullable
`acceptance_criteria TEXT` column to `business_tasks` with no default value.
Existing task rows are unaffected. New tasks registered after migration 116 may
include a structured acceptance criteria string that the independent verifier
checks specifically rather than interpreting the freeform description. The
column is written by `create_task()` via the standard event-spool path; the
`TaskProjection` materializes it. No authority boundary change; `business_tasks`
remains under the SDLC write-path policy (interfaces/cli/ and core/work_orders/
only).

Migration `044_career_capability_agent_github_authority.sql` is additive. It
created Capability Center records, scoped
agent registry/context/result tables, and GitHub repo intake evaluation tables.
It does not publish private data, inspect external
repositories, copy code, add dependencies, fork/vendor repositories, or
authorize agent execution. The 15 opt-in `career_*` tables it originally created
were never activated and were dropped by migration 100 (Wave 2 career
annihilation); the capability_center, scoped_agents, and github_repo_intake
tables it created are not touched, and 044 itself remains immutable history.

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

<!-- Last reviewed 2026-06-07 — WO-M dual-canonical authority cutover: migration 102 (`102_drop_canonical_events.sql`) retires the legacy `canonical_events` table. It uses the rename-then-view pattern: `ALTER TABLE canonical_events RENAME TO canonical_events_legacy_backup` preserves all historical rows; `CREATE VIEW canonical_events AS UNION(business_canonical_events, ai_canonical_events)` restores SELECT access for the 42 production readers without code changes. The migration is guarded: IF NOT EXISTS / IF EXISTS where applicable. `business_canonical_events` and `ai_canonical_events` (created by migration 067) are now the authoritative event substrates. No data-loss path: the legacy rows are preserved in `canonical_events_legacy_backup`. Raw-only events (routes=[]) remain in `raw_claude_code_events` per Commitment 9. Migration 083 (`083_canonical_events_migration_authority.sql`) is the origin of the physical `canonical_events` table on fresh DBs; it continues to exist unchanged (102 renames what 083 created). -->

Migration `102_drop_canonical_events.sql` is a structural migration (rename + view). It renames the legacy `canonical_events` event store to `canonical_events_legacy_backup` and creates a compat `canonical_events` VIEW as a UNION of `business_canonical_events` and `ai_canonical_events`. All prior writes to `canonical_events` are retired; `spool/ingestor.py` and `core/event_store/event_store.py` now write exclusively to the dual-canonical authority tables. Migration 083 created the physical `canonical_events` table on fresh DBs; migration 102 is its terminal transformation. The SQLite PRAGMA `legacy_alter_table` is NOT needed here (no views reference `canonical_events` at rename time; the migration is safe without it).

<!-- Last reviewed 2026-05-28 — migration 079 bugfix: added CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts to migration 079. memory_fts was originally a runtime-created table (core/memory/store.py); migration 079's backfill INSERT assumed it existed. On fresh DBs built from migrations (test fixtures), this caused 14 failures. Fix adds the CREATE VIRTUAL TABLE before triggers and backfill, making 079 safe in all environments. Policy unchanged: memory_entries is private local state. -->

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

<!-- Last reviewed 2026-05-29 (rev3) — migration 082 (082_memory_fts_triggers_repair.sql): defensive trigger repair. Uses CREATE TRIGGER IF NOT EXISTS to restore memory_entries_fts_{insert,update,delete}. Idempotent no-op on any DB where triggers already exist. No schema content change needed in this document — trigger restoration is not an authority or policy change. -->

<!-- Last reviewed 2026-05-29 (rev2) — migration 081 extended fix: full drop-all-13-views pattern replaces single DROP VIEW; 12 views recreated using migration 062 DDL; vw_activity_timeline permanently retired. sqlite_bootstrap.py exception handler updated to tolerate partial fixtures for token_usage_records/ai_usage_operational_records. No policy or content change to migration 081 section. -->

<!-- Last reviewed 2026-05-29 — migration 081 fix: DROP VIEW IF EXISTS vw_activity_timeline replaces PRAGMA legacy_alter_table = ON to ensure RENAME succeeds on all SQLite versions. The view is not recreated (it references Python-owned canonical_events; debt tracked in docs/architecture/aspirational-schema-debt.md). No policy or content change to migration 081 section in this doc — already present from PR #97. -->

<!-- Phase 18.2.3 (2026-05-27) adds migrations 072 and 073. Migration 072 (072_task_projection_event_tracking.sql) is additive DDL: ALTER TABLE business_tasks ADD COLUMN source_event_id TEXT; ALTER TABLE business_tasks ADD COLUMN last_event_id TEXT. Migration 073 (073_milestone_projection_event_tracking.sql) is additive DDL: ALTER TABLE business_milestones ADD COLUMN source_event_id TEXT; ALTER TABLE business_milestones ADD COLUMN last_event_id TEXT. Both columns are nullable; existing rows retain NULL values until the respective projection (TaskProjection, MilestoneProjection) processes their source events. These columns are the projection idempotency mechanism: last_event_id prevents double-application of the same event; source_event_id provides creation traceability. Schema version: 73 migrations applied. No existing columns modified. No policy or authorization boundary change. -->

<!-- Phase 18.2.4 (2026-05-27) adds migrations 074 and 075. Migration 074 (074_design_brief_projection_event_tracking.sql) is additive DDL: ALTER TABLE business_design_briefs ADD COLUMN source_event_id TEXT; ALTER TABLE business_design_briefs ADD COLUMN last_event_id TEXT. Same projection idempotency mechanism as migrations 072/073. Migration 075 (075_design_brief_backfill_events.sql) is a 3-step data-only backfill: (1) inserts synthetic design_brief.created events into business_canonical_events for all brief rows with source_event_id IS NULL using deterministic event IDs (backfill-brief-created-<brief_id>) and INSERT OR IGNORE for idempotency; (2) inserts synthetic design_brief.locked events for locked briefs with source_event_id IS NULL using deterministic IDs (backfill-brief-locked-<brief_id>); (3) directly updates source_event_id and last_event_id on the brief rows so DesignBriefProjection is already converged without requiring a rebuild. attribution_status = 'backfill' marks synthetic events as pre-event-sourcing data. DesignBriefProjection registered in runner.py and projection_cli.py. Direct UPDATE writes for lock and field-update mutations removed from mutations.py; direct INSERT in create_design_brief retained (needed for existence-check guard in website:discover). Schema version: 75 migrations applied. No policy or authorization boundary change. -->

<!-- Phase 18.2.5 (2026-05-27) adds migrations 076 and 077. Migration 076 (076_project_projection_event_tracking.sql) is additive DDL: ALTER TABLE business_projects ADD COLUMN source_event_id TEXT; ALTER TABLE business_projects ADD COLUMN last_event_id TEXT. Same nullable projection idempotency columns as migrations 072–075. Migration 077 (077_project_backfill_events.sql) is a 3-step data-only backfill: (1) INSERT OR IGNORE synthetic project.created events into business_canonical_events for all project rows with source_event_id IS NULL, using deterministic IDs (backfill-project-created-<project_id>); (2) INSERT OR IGNORE synthetic project.deactivated events for paused projects with source_event_id IS NULL, using deterministic IDs (backfill-project-deactivated-<project_id>); (3) UPDATE business_projects SET source_event_id and last_event_id (CASE: paused rows get last_event_id = deactivated event; others get created event) WHERE source_event_id IS NULL. ProjectProjection handles project.created, project.activated, project.deactivated, project.deleted (soft delete: status='deleted', row retained). Soft-delete replaces hard DELETE FROM in cascade delete path; rows queryable via --include-deleted flag. Schema version: 77 migrations applied. No policy or authorization boundary change. -->

<!-- Phase 18.3.0 CI repair (2026-05-28) adds migration 078 (078_memory_entries.sql). Renamed from 011 to avoid UNIQUE constraint conflict with the closed gap at slot 011 (Phase 18.1.13). Creates memory_entries table: (memory_id TEXT PK, key TEXT UNIQUE NOT NULL, value TEXT, type TEXT, metadata TEXT, created_at TEXT, updated_at TEXT). Stores Claude Code memory entries from ~/.claude/projects/ session harvesting. Schema version: 78 migrations applied. No policy or authorization boundary change. -->

<!-- Phase 18.3.1 CI repair (2026-05-28) restores migration 011 (011_memory_entries.sql). This migration was incorrectly renamed to 078 during batch2 CI repair. The restoration fixes test_memory_entries_exists_after_011 (which verifies the table is created by migration 011, as required by migration 032_semantic_memory.sql). Migration 078 is now a retained no-op guard (CREATE TABLE IF NOT EXISTS is a no-op since 011 runs first). The memory_entries table creation chain: 011 creates base schema, 032 adds semantic columns (source_type, source_id, lifecycle_state, confidence, provenance, lineage, relationships, updated_at), 033 creates FTS5 index. Schema version: 78 migrations applied. No policy or authorization boundary change. -->

<!-- Phase 18.4.6-followup-1 (2026-05-29) adds migration 083 (083_canonical_events_migration_authority.sql). This migration closes aspirational-schema debt surfaced by the 18.4.6 schema_coherence audit: canonical_events was referenced by 5 migrations (052, 060, 061, 062, 064) but created by Python code, not migrations. Migration 083 declares the authoritative 14-column canonical_events schema from spool/ingestor.py. The 3 extra columns that caused high-severity column_absent_from_python_ddl findings (raw_prompt_retained, raw_tool_output_retained, schema_version) are now canonical in the migration. canonical_events removed from the schema_coherence audit's _PYTHON_OWNED_TABLES registry; swallow entry reclassified from stale to legitimate. Audit verification: schema_coherence findings drop from 9 (5 medium + 3 high + 1 stale-swallow) to 0. Schema version: 83. No policy or authorization boundary change. -->

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

<!-- 2026-06-03: migration 092 ds_eval_baselines — behavioral eval harness baseline storage -->

<!-- 2026-06-03: migration 093 ds_workflow_pattern_signals (always_paired/post_completion/pre_close pattern signals) -->

<!-- 2026-06-03: migration 094 ds_eval_baselines label column — pre_phase_19 named baseline snapshot -->

<!-- 2026-06-03: migration 095 ds_user_extensions + ds_friction_signals (Phase 19.1 unified extensions schema) -->

<!-- 2026-06-03: migration 096 ds_friction_signals + findings.dismissed_at (Phase 19.2 Friction Signal Harvester) — passive session-end capture; idempotent via bucket_key UNIQUE -->
<!-- 2026-06-03: migration 097 classification columns on ds_friction_signals (Phase 19.3) — ALTER TABLE only, no new table -->
<!-- 2026-06-03: migration 098 validation_detail column on ds_user_extensions (Phase 19.5) — ALTER TABLE only -->
<!-- 2026-06-05: phase-18-2 gap closure + popup refactor — no schema change, no migration; _repo_stack_evidence() removed from /details critical path; session_collector NULL project_id fix -->
<!-- Last reviewed 2026-06-05 — Phase 18.6.2 (migration 099): DROP TABLE/VIEW-only migration. 8 tables and 1 view dropped (all 0 rows, no FK deps). This migration breaks the CREATE TABLE migrations 040 and 047 forward — those migrations remain immutable. The drop is reversible only by re-applying 040 and 047 on a new DB; existing data would not be recovered (none to lose). IF EXISTS clauses on all DROPs prevent errors on already-clean databases. Drop order: view first (vw_project_readiness_latest depends on project_readiness_scorecards), then tables in arbitrary order. No additive DDL in this migration. -->

<!-- 2026-06-05: Wave 2 career annihilation — migration 100 (100_drop_career_family.sql) is a DROP TABLE-only migration. 15 career_* tables dropped (all 0 rows on live-DB verification, no views reference them, no incoming FK deps): career_application_events, career_application_field_mappings, career_applications, career_browser_automation_runs, career_case_studies, career_cover_letter_versions, career_evidence_refs, career_interview_story_bank, career_job_opportunities, career_portfolio_artifacts, career_profile_fields, career_profiles, career_resume_versions, career_role_targets, career_scorecards. IF EXISTS clauses on all DROPs prevent errors on already-clean databases. No inter-table FKs among career_* tables, so drop order is arbitrary. This migration breaks the CREATE TABLE migration 044 forward — 044 remains immutable history; the capability_center, scoped_agents, and github_repo_intake tables 044 created are NOT touched. No additive DDL. Body edit in this doc: the migration-044 paragraph now records that its career_* tables were dropped by 100 (044 description otherwise unchanged) and drops the live-feature "Career Ops" framing. -->

<!-- 2026-06-05: Wave 2 career annihilation — career_ops module, 15 career_* tables (migration 100), ds-career skill pack, /career-ops route, career_ops contract+profile, and career expert workflow removed. capability_center/scoped_agents/github_repo_intake unchanged. See the migration-100 review note above for drop-only details; the migration-044 body paragraph was updated to reflect the drop. -->

<!-- 2026-06-06: Wave 4+5 ghost-surface removal reviewed — realtime websocket layer (stream/metrics, connection_manager, broadcast feeder, 2 project_intelligence ghost websockets), export/report/schedule routes + projections/exporters + scheduler/reports backends, and deprecated production_dashboard.py removed (-18,865 lines, no schema change). This doc did not describe the removed surfaces; no semantic change required. -->

<!-- 2026-06-06: Wave 6 verified-dead table drops — migration 101 (101_drop_verified_dead_tables.sql) is a DROP TABLE-only migration. 13 tables dropped (all 0 rows on per-table verification, no live code readers/writers, no view deps): automation_checkpoints, automation_log, risk_mitigations, risk_register, telemetry_entity_registry, telemetry_module_registry, reg_repo_research_links, agent_result_records, capability_center_records, dashboard_authority_reconciliation_records, guardrail_rules_audit, sec_hook_checks, workflow_agent_skill_mappings. IF EXISTS clauses on all DROPs prevent errors on already-clean databases. Drop order is FK-safe (child tables before parent tables). This migration breaks the CREATE TABLE migrations 005/007/020/021/027/028/037/039/044 forward — those remain immutable history; the drop is reversible only by re-applying them on a new DB (no data to recover, all 0 rows). The audit's ~38-candidate list was reduced to 13 after per-table verification found live code paths on 18 candidates; the 7 prd_* cluster tables were deferred because they stay entangled in a view/FK web with kept tables. No career_* re-drops needed — migration 100 covers that family. No additive DDL. -->

<!-- Last reviewed 2026-06-07 — WO-F prd_* cluster drop (migration 103): migration 103 drops the entire prd_* cluster (prd_documents, prd_plans, prd_tasks, prd_sessions, prd_handoffs, session_tasks, prd_version_records, prd_amendment_records, prd_route_reconciliation_records) and the views vw_prd_progress and vw_task_details. AD-10 decision: business_projects IS what PRD was. All prd_* callers removed from studio_db.py, prd_authority.py (deleted), routes/prd.py (deleted), analytics_ingestion.py, module_contracts.py, dashboard_freshness.py, contract_atlas.py, contract_registry.py, project_intelligence.py, shared_intelligence.py, resume_from_handoff.py, and migrate_prd_schema.py (deleted). -->

<!-- Last reviewed 2026-06-07 — WO-I swallow-handler narrowing (P5.5): sqlite_bootstrap.py's swallow block for fts_gotchas/ds_documents/canonical_events narrowed from broad substring-match to statement-type-aware. CREATE INDEX and CREATE TRIGGER on absent tables now propagate (M2-class casualty prevention); INSERT, UPDATE, ALTER TABLE, DROP on absent tables remain swallowed (graceful degradation). No migration file added or removed. No schema change. No swallow removed for memory_entries or token_usage_records handlers — only the fts_gotchas/ds_documents/canonical_events block changed. Migration authority for existing migrations is unchanged. -->

<!-- Last reviewed 2026-06-07 — WO-N behavioral eval harness (18.8.3): migration 104 adds ds_eval_runs table for per-run evidence storage. Columns: run_id, eval_id, eval_version, started_at, completed_at, model_tested, skill_versions_snapshot, event_score, behavior_score, total_score, passed, failure_reasons, token_cost_usd, baseline_run_id. Three indexes: idx_eval_runs_eval_id, idx_eval_runs_started_at, idx_eval_runs_passed. Table complementary to ds_eval_baselines (migration 092). -->

<!-- Last reviewed 2026-06-07 — WO-J cache_read_tokens column (migration 105): migration 105 is a simple ALTER TABLE ADD COLUMN — not a table-rebuild, no data migration required. Default 0 is safe for all existing rows. Column is optional in read path (authority_sources.py uses _column_or_literal fallback). Migration authority: additive-only, no existing column renamed or dropped. -->

<!-- Last reviewed 2026-06-07 — WO-R AI spine consolidation (migration 106): migration 106 is DROP TABLE IF EXISTS for 5 per-type invocation tables. All rows were verified 100% covered by execution_events before DROP. No data loss. Drop order is FK-safe (no FK relationships between the 5 tables). IF EXISTS on all DROPs — safe on clean installs or DBs that skipped the original CREATE via the swallow handler. .released_version updated to 106. emitters.py no longer dual-writes to these tables so re-applying the original CREATE TABLE migrations on a fresh DB will not recreate data pathways. -->

<!-- Last reviewed 2026-06-07 — WO-S preflight findings layer (migration 107): migration 107 creates two new tables (preflight_events, business_work_order_preflights) — no existing table modified, renamed, or dropped. DDL uses CREATE TABLE IF NOT EXISTS — safe on re-apply and clean installs. Indexes use CREATE INDEX IF NOT EXISTS. The preflight_events.status column is written by the emitter (default 'open' on created events, the new_status on status_changed events) — it is metadata on the event row, not a mutable field. The read-model (business_work_order_preflights) is rebuilt by PreflightProjection.fold_spine(). .released_version updated to 107. -->

<!-- Last reviewed 2026-06-07 — WO-ORD explicit work-order ordering (migrations 108+109): migration 108 uses ALTER TABLE ADD COLUMN (not a table rebuild) — the sequence_order column is nullable with no DEFAULT, safe for all existing rows. work_order_dependencies uses CREATE TABLE IF NOT EXISTS with FK references to business_work_orders; FK enforcement depends on PRAGMA foreign_keys=ON (not enabled by default in SQLite; the table structure is correct and will enforce on pragma-enabled connections). Migration 109 uses UPDATE...WHERE and INSERT OR IGNORE — both are idempotent safe on re-apply (UPDATE already-set rows is a no-op; INSERT OR IGNORE skips duplicates). Dependency edge seeds use LIKE 'uuid-prefix%' cross-join pattern — produces zero rows when either endpoint is absent, produces exactly one row per matching UUID pair. .released_version remains at 107 (no sentinel update in this migration pair — sentinel updates require a separate explicit approval). -->

<!-- Last reviewed 2026-06-07 — WO-ORD task 6 milestone referential integrity (migration 110): migration 110 safety analysis. Step 1 INSERT: randomblob() UUID generation is safe SQLite 3.9+ behavior; INSERT OR IGNORE not used (no UNIQUE conflict possible since we only insert when no milestones exist for the project). Safe on clean installs and on DBs where all projects already have milestones (the WHERE NOT EXISTS guard produces zero rows). Step 2 UPDATE NULL: UPDATE...WHERE milestone_id IS NULL is a data-only migration, no DDL, idempotent (already-assigned rows stay assigned). Step 3 UPDATE dangling: same pattern — NOT EXISTS subquery targets only rows whose milestone_id references a non-existent milestone; zero rows affected on a clean DB. App-level guard in create_work_order() added before the spool event emit — guard returns ok=False immediately without touching the DB if milestone_id is None or not found. This is a fail-hard (not fail-open) guard because a work order without a milestone is permanently invisible to the scheduler. .released_version remains at 107. -->

<!-- Last reviewed 2026-06-08 — .released_version sentinel bump 107→110: sentinel change only — no new migration file, no DDL. The three migration files (108, 109, 110) were already reviewed and merged in PR #211. This commit activates them by raising the release gate. Migration runner will back up the live authority DB (timestamped .bak) before applying the first unreleased migration, per the WO-MS backup protocol in sqlite_bootstrap.py. -->

<!-- Last reviewed 2026-06-08 — WO-Y findings event-spine (migrations 111+112): migration 111 uses CREATE TABLE IF NOT EXISTS for all three tables (security_events, readiness_events, findings_current_status) — safe on re-apply and clean installs. All indexes use CREATE INDEX IF NOT EXISTS. No existing table modified, renamed, or dropped. Migration 112 safety: the INSERT OR IGNORE from findings uses a column-level mapping (finding_id→event_id, process_run_id→correlation_id, category→vuln_class, description→title) — idempotent via OR IGNORE on event_id PK. The INSERT from resolved_finding_links maps link_id→event_id, prev_finding_id→parent_event_id, verdict→body, adjudicated_at→created_at — idempotent via OR IGNORE. The INSERT OR REPLACE into findings_current_status seeds status from the migrated finding.resolved events. All DROP TABLE statements use IF EXISTS — safe on clean installs and DBs that already had these tables dropped. DROP order is FK-safe: child tables (resolved_finding_links, production_readiness_remediation_work_orders, production_readiness_findings, production_readiness_control_results, production_readiness_skill_control_mappings) are dropped before parent tables (findings). DROP VIEW IF EXISTS before CREATE VIEW to handle idempotent re-apply. The production_readiness cluster was all 0 rows (verified before DROP). .released_version pending bump to 112 after merge. -->

<!-- Last reviewed 2026-06-08 — WO-LEARN gap loop wiring: no migrations added or modified. WorkflowPatternAnalyzer wired into end_session() uses ds_workflow_pattern_signals (migration 093, already released). Deprecation comments added to shared intelligence functions — no schema impact. -->

<!-- Last reviewed 2026-06-08 — WO-MA migrate activate: added activate_pending_migrations() to sqlite_bootstrap.py — operator-invoked only via ds migrate activate. Function calls run_migrations(conn, apply_unreleased=True) then bumps .released_version to latest_migration_version(). apply_unreleased parameter added to run_migrations() (None→reads env var, True→bypasses gate). No new migrations. .released_version will be bumped 110→112 by the operator running ds migrate activate --confirm after merge. -->

<!-- Last reviewed 2026-06-09 — migration-release-112: .released_version bumped 110→112. Migrations 111 (security_events/readiness_events/findings_current_status CREATE) and 112 (sec_sarif_findings/sec_cve_matches/sec_manual_reviews DROP + data migration) are now released. No schema additions beyond what was already reviewed for WO-Y. -->

<!-- Last reviewed 2026-06-09 — WO-W migration 113 (brownfield_onboarding): additive migration — vision_statement column on business_projects + pending_audits scheduling table. No DROP, no data migration, no existing schema changes. -->

<!-- Last reviewed 2026-06-09 — migration-release-113: .released_version bumped 112→113. Migration 113 (ALTER TABLE business_projects + CREATE TABLE pending_audits) is now released. Additive-only migration; no DROP or data migration. -->

<!-- Last reviewed 2026-06-09 — WO-TS3 DuckDB analytics store: no new SQLite migrations. DuckDB schema for the analytics read model is managed by core/analytics/duckdb_store.py:ensure_analytics_schema() and is outside the canonical migration runner scope. The DuckDB connection authority boundary is enforced by the authority-boundary pre-push gate: connect_analytics(read_only=False) is permitted only in core/projections/runner.py. All API read paths use connect_analytics(read_only=True) via core/analytics/duckdb_read.py helpers with fail-open fallback to SQLite. No SQLite schema changes in WO-TS3 Task 6. -->

<!-- Last reviewed 2026-06-09 — WO-TS4 correction: removing wrong-scope DuckDB-first read paths from project_intelligence.py and discovery_internal.py. Business entity reads (project existence checks, project row for authority) now go directly to SQLite business_projects (Store 3 authority). No new SQLite migrations. The authority-boundary gate is unaffected: connect_analytics(read_only=False) remains restricted to core/projections/runner.py. -->
<!-- Last reviewed 2026-06-10 — WO-REVIEW-GATE (feat/wo-review-gate-independent-verify): Migration 114 (independent_review_gate.sql) sets post_build_gate='independent_review' on cleanup and infrastructure work order types. This is an UPDATE to existing business_work_order_types rows — no new tables or columns. The independent_review gate checks .planning/work-orders/<id>/review-verdict.json for passed=true (written by core/work_orders/verify.py). The migration runner picks it up via the standard *.sql glob. No released_version bump needed — this migration applies on next bootstrap. -->

<!-- Last reviewed 2026-06-10 — WO-DEBT-B (fix/wo-debt-b-broken-surfaces): No migrations added. Released version bumped to 114 (migration 114 was part of WO-REVIEW-GATE, already reviewed above). Code changes in this WO reference security_events and findings_current_status (both migration 111) and correct stale references to the dropped findings table (migration 112). No new schema objects introduced. -->

<!-- Last reviewed 2026-06-10 — WO-DEBT-F migration 115 (vestigial table sweep): Drop-only migration. Drops 11 tables (7 prd_* no-ops + pi_wave_tasks + pi_waves + agent_context_scope_policies + agent_registry_records). All drops use DROP TABLE IF EXISTS — idempotent. No FK violations: pi_wave_tasks dropped before pi_waves. No new tables or columns. No PRAGMA foreign_key constraint changes persist beyond the migration transaction. research_evidence_records: data cleared via DELETE, schema intact. Confirmed safe: prd_* never existed; pi_wave* had no SQL consumers (docstring-only); agent_context_scope_policies had no SQL consumers (metadata lists only); agent_registry_records guarded by _table_exists() with [] fallback. .released_version not bumped in this commit — will activate on next ds migrate activate after merge. -->

<!-- Last reviewed 2026-06-11 — WO-DEBT-I swallow-handler narrowing (fix/wo-debt-i-swallow-narrowing): sqlite_bootstrap.py run_migrations() error handler narrowed for the token_usage_records/ai_usage_operational_records clause (migration 081 tolerance) and the ds_* project-spine clause (migration 070 tolerance) — both now statement-type-aware: CREATE INDEX / CREATE UNIQUE INDEX / CREATE TRIGGER on absent covered tables propagate; INSERT/UPDATE/ALTER TABLE/DROP remain swallowed (graceful degradation). No migration file added or removed; no schema change; migration authority for existing migrations unchanged. This completes the narrowing series begun by O7 (memory_entries) and WO-I (fts_gotchas/ds_documents/canonical_events) — no broad substring-only 'no such table' swallow remains. Related: issue #264 (migration 081 omitted usage-table index recreation, pre-existing). -->

<!-- Last reviewed 2026-06-11 — WO-IDX-RECREATE (migration 117): additive index-only migration recreating idx_token_usage_scope (037) and idx_ai_usage_operational_scope/process (043) lost to migration 081's DROP+RENAME reconstruction. IF NOT EXISTS for idempotency; safe on all upgrade paths including pre-081 DBs. .released_version bumped to 117. Migrations 037/043/081 remain immutable history — 117 is the corrective forward migration. No FK, no data movement, no reversibility concerns (DROP INDEX reverses it). -->

<!-- Last reviewed 2026-06-11 — WO-RETRY-TEST (migration 118): corrective migration dropping stale FK references orphaned by migration 103 (prd_tasks/prd_documents dropped) and 112 (sec_sarif_findings/activity_log dropped). Three tables recreated via the standard SQLite rename pattern (PRAGMA foreign_keys = OFF; CREATE new; INSERT SELECT; DROP old; RENAME; PRAGMA foreign_keys = ON): raw_workflow_runs, research_cache, raw_research. Stale REFERENCES removed from each; all existing column definitions and CHECK constraints preserved verbatim; indexes recreated verbatim after rename. vw_risk_hotspots dropped (referenced sec_sarif_findings, absent since migration 112; SQLite validates view references during ALTER TABLE RENAME, blocking the migration without this drop). No new tables, columns, or constraints added. Data preserved: no rows affected beyond the structural recreation. Migration is safe on live DBs: all rows survive; FK checks that were already silently failing (due to foreign_keys OFF on the live DB before each operation) are removed, not tightened. .released_version bumped 117 → 118. -->

<!-- Last reviewed 2026-06-11 — WO-EVAL-QUEUE (migration 122): migration 122 (122_eval_registry_pending_rerun.sql) is a single ALTER TABLE ADD COLUMN on eval_registry. Adds pending_rerun INTEGER NOT NULL DEFAULT 0. SQLite NOT NULL + DEFAULT is safe at SQL layer — no row back-fill, no lock escalation. No new tables, no FK changes, no indexes, no views. .released_version bumped 121 → 122. Migration-risk gate acknowledged (MIGRATION_RISK_ACKNOWLEDGED=1). -->

<!-- Last reviewed 2026-06-11 — WO-EVAL-LOOP-THRESHOLD (migration 121): migration 121 (121_eval_registry_friction_threshold.sql) is two ALTER TABLE ADD COLUMN statements on eval_registry. Adds friction_signal_count INTEGER NOT NULL DEFAULT 0 and friction_threshold INTEGER NOT NULL DEFAULT 3. SQLite evaluates NOT NULL + DEFAULT as safe at the SQL layer — no row back-fill, no lock escalation. No new tables, no FK changes, no indexes, no views. .released_version bumped 120 → 121. Migration-risk gate acknowledged (MIGRATION_RISK_ACKNOWLEDGED=1). -->

<!-- Last reviewed 2026-06-11 — WO-EVAL-LIVE (migration 120): migration 120 (120_eval_runs_run_mode.sql) is a single ALTER TABLE ADD COLUMN statement on ds_eval_runs (run_mode TEXT NOT NULL DEFAULT 'fixture'). SQLite evaluates NOT NULL + DEFAULT as safe at the SQL layer — no row back-fill, no lock escalation. Three allowed values: 'fixture' (default), 'live', 'verify'. No new tables, no FK changes, no indexes, no views. .released_version bumped 119 → 120. Migration-risk gate acknowledged in the pre-push gate (MIGRATION_RISK_ACKNOWLEDGED=1). -->

<!-- Last reviewed 2026-06-11 — WO-EVAL-REGISTRY (migration 119): migration 119 (119_eval_registry_hook_eval_runs.sql) is additive DDL. Creates eval_registry (one row per evaluated target: eval_id TEXT PK = target_id||'::'||target_type, target_type CHECK IN('skill','hook','workflow','agent'), target_id, rubric_score INTEGER, last_run_at, last_run_id, baseline_run_id, friction_flag DEFAULT 0, created_at, updated_at) and hook_eval_runs (per-evaluation hook guardrail pass/fail: run_id TEXT PK, hook_id, eval_type DEFAULT 'guardrail', passed INTEGER CHECK IN(0,1), score REAL, failure_reasons TEXT, created_at). All DDL uses CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS — safe on re-apply and clean installs. No existing table modified, renamed, or dropped. Backfill: eval_registry seeded from skill_evaluation_runs (ROW_NUMBER OVER PARTITION BY target_type, target_id ORDER BY created_at DESC to pick most-recent per target) and from hook_executions (GROUP BY hook_name, MAX(started_at)) — both use INSERT OR IGNORE for idempotency. hook_invocations was dropped in migration 106; hook_executions (migration 018, persists) is the correct backfill source. guardrails/evaluator.py write path unchanged in policy semantics — adds optional hook_id parameter that triggers one hook_eval_runs INSERT per guardrail evaluation. New CLI surface: ds eval registry list/show. .released_version bumped 118 → 119. No FK deps on other tables; no data migration beyond the backfill INSERTs. -->

<!-- Last reviewed 2026-06-12 — WO-VIEW-GHOSTS (fix/wo-view-ghosts-migration-replay): migrations 102 and 118 patched to follow the established DROP VIEW before RENAME → recreate after pattern (migrations 062/088/089 precedent). Root cause: SQLite 3.26+ recompiles ALL views during ALTER TABLE RENAME; vw_approach_patterns, vw_guardrail_decisions, vw_prd_progress, vw_task_details referenced tables absent from the minimal v38 test fixture, causing OperationalError during migration 102 replay. Fix: DROP VIEW IF EXISTS for all 4 before the RENAME; recreate vw_approach_patterns and vw_guardrail_decisions (live base tables) after. Migration 118 gets the same treatment for its 3 RENAME operations. sqlite_bootstrap.py partial-fixture exception handler generalised to swallow no-such-table for pure data statements. Migration-risk gate acknowledged (MIGRATION_RISK_ACKNOWLEDGED=1). -->

<!-- Last reviewed 2026-06-13 — WO-FRICTION-CONFIG (migration 123): migration 123 (123_ds_config.sql) creates ds_config using CREATE TABLE IF NOT EXISTS — purely additive. Schema: key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT (datetime('now')). No row back-fill, no existing table touched, no FK references, no DROP or ALTER statements. Upsert path (set_config_value()) uses INSERT INTO ... ON CONFLICT(key) DO UPDATE SET — standard SQLite upsert, idempotent on re-apply. get_config_value() and list_config() use read-only sqlite3.connect() connections. .released_version bumped 122 → 123. Safe on all upgrade paths including fresh installs (IF NOT EXISTS). No data migration, no PRAGMA changes, no authority boundary change. -->

<!-- Last reviewed 2026-06-14 — WO-LESSONS-DB-UNIFY (feat/lessons-db-unify): No migration — raw_lessons table already existed (migration history intact). Change: lesson storage callers migrated from writing .md files under meta/draft-lessons/ to calling insert_lesson() in core/event_store/studio_db.py with explicit db_path=paths.state_dir()/"studio.db". Two new API helpers (draft_lesson, reject_lesson) added to studio_db.py but NO schema change (raw_lessons table schema unchanged). studio_db.py is a DDL site under migration-risk monitoring — this change adds only Python API helpers, not DDL. .released_version unchanged. Pre-push migration-risk gate: no acknowledgement needed (no migration file added). -->

<!-- Last reviewed 2026-06-14 — WO-FILESDB-WIRE (feat/filesdb-wire): Migration 124 (124_handoff_file_pointer.sql) adds two nullable columns to raw_handoffs via ALTER TABLE ADD COLUMN: file_id TEXT (cross-store pointer to ds_files.file_id in files.db — cross-store FK, not enforced by SQLite) and checksum TEXT (SHA-256 of the content blob for integrity verification). Both columns default to NULL — existing rows and rows from producers not yet wired retain NULL. insert_handoff() signature extended with file_id and checksum keyword arguments. monitor._write_handoff_packet_to_db() stores the rendered handoff markdown in files.db (category='handoff') via core/files/store.write_file(), captures the returned file_id and SHA-256 checksum, and records both in the raw_handoffs row. write_recap() in control/context/handoff.py similarly stores the recap markdown blob in files.db (category='handoff'). Additive-only ALTER TABLE — no existing column, index, view, or table modified, renamed, or dropped. No PRAGMA foreign_keys change persists beyond the migration. .released_version bumped 123 → 124. No authority boundary change; no PII in the new columns. Migration-risk gate acknowledged (MIGRATION_RISK_ACKNOWLEDGED=1). -->

<!-- Last reviewed 2026-06-14 — WO-DASH-VALIDATION-GAPS (T1): core/telemetry/read_models.py no longer reads from the process_runs table directly. _process_runs_from_events() derives process run summaries from execution_events GROUP BY process_run_id — the table is empty in production; all useful data was always on execution_events. This is a read model change only: no migration added or removed, .released_version unchanged. process_run_timeline() and _scoped_summary() both updated to use the derived aggregation path. No migration authority change. -->

<!-- Last reviewed 2026-06-14 — WO-SYMPTOM-RESOLUTION (feat/symptom-resolution): Migration 125 (125_originating_symptom.sql) adds originating_symptom TEXT (nullable) to business_work_orders via ALTER TABLE ADD COLUMN. This is a purely additive DDL change — no existing column, index, view, or FK is modified, renamed, or dropped. Backfill rows: WO-TOKEN-CAPTURE originating_symptom set to 'SQL-CHECK: SELECT COUNT(*) FROM token_usage_records'; a symptom-check task (stable UUID) inserted into business_tasks for WO-TOKEN-CAPTURE (INSERT OR IGNORE — idempotent on re-apply). close_work_order() in core/work_orders/close.py re-runs the symptom SQL at close time: a zero/falsy result or SQL error blocks close (unless force=True). set_originating_symptom() in mutations.py provides a direct UPDATE path for post-creation backfills. WorkOrderProjection reads originating_symptom from work_order.created event payloads for future WOs. .released_version will be bumped 124 → 125 on merge. No FK, no DROP, no PRAGMA change, no PII. Migration-risk gate acknowledged (MIGRATION_RISK_ACKNOWLEDGED=1). -->

<!-- Last reviewed 2026-06-14 → WO-CI-RED-RECOVERY (fix/ci-red-recovery): Migration 125 (125_originating_symptom.sql) RELEASED. #358 merged the migration but never bumped the .released_version sentinel, so run_migrations() auto-skipped version 125 on every live authority (originating_symptom column absent) and the fresh-bootstrap test failed (schema 124 != latest 125). Released via `ds migrate activate --confirm`: .released_version 124 → 125, the additive ALTER TABLE applied to the authority with a pre-apply backup. The only migration-tree change in this change set is the sentinel bump — no new DDL. Accompanied by test reconciliations for the post-merge red (stale inline work-orders DDL, #347 dashboard markup, #354 token_usage_records ownership, #353 handoff signature, #355 design-brief emit-only). -->

<!-- Last reviewed 2026-06-17 — WO-ESCALATION-LADDER (feat/escalation-ladder): Migration 126 (126_ds_escalations.sql) adds a NEW table ds_escalations via CREATE TABLE IF NOT EXISTS — purely additive, no existing column/index/view/FK modified, renamed, or dropped. .released_version bumped 125 → 126 in the same change set (per the dev-vs-live workflow above) so the table lands on fresh bootstraps once merged. Temp/test DBs apply it immediately (unreleased gate exempts non-live paths). No backfill rows, no FK, no DROP, no PRAGMA change, no PII. Migration-risk gate acknowledged (MIGRATION_RISK_ACKNOWLEDGED=1). -->

<!-- Last reviewed 2026-06-17 — WO-GATE-HARDEN-CLEANUP (fix/gate-harden-cleanup): NO migration or schema change. core/event_store/studio_db.py read helpers were wrapped in try/finally so the sqlite connection always closes even when a query raises (connection-leak hardening). Queries, transaction semantics, and the migration tree are unchanged; no new DDL and no .released_version bump. -->

<!-- Last reviewed 2026-06-20 — WO-SPLIT-PROJECT-INTEL (feat/split-project-intel-routes): project_intelligence.py (2480 lines) split into projections/api/lib/ (security_helpers, stack_helpers, project_helpers) and four route files (project_list, project_detail, project_artifacts, project_security). Pure module reorganization — no SQL queries, schema, migration, business logic, or API contract changed. -->

<!-- Last reviewed 2026-06-26 — WO-DEAD-TABLES (feat/dead-tables-removal): Migration 128 (128_drop_dead_tables.sql) drops 24 verified-dead tables. Dead table DDL removed from source migrations 001/003/004/007/008/030/041/044/046 so fresh installs never create them. Upgrade path: migration 128 uses DROP TABLE IF EXISTS for all 24. Both paths verified: fresh in-memory run_migrations ends with 0 of the 24 tables present; temp-copy upgrade from v127 ends with same. sqlite_schema_authority domain reviewed; no FK constraint violations on drop order. .released_version bumped 127 → 128. -->

<!-- Last reviewed 2026-06-24 — chore/docstore-move-files-db (three-store architecture fix): Migration 127 (127_drop_ds_documents_from_studio_db.sql) drops the ds_documents cluster from studio.db — DROP TRIGGER (5 triggers), DROP TABLE (FTS virtual table ds_documents_fts, which auto-removes shadow tables ds_documents_fts_config/_docsize/_idx/_data), DROP INDEX (8 indexes), DROP TABLE ds_documents. ds_documents and its FTS are three-store violations (document storage belongs in files.db, not the canonical event authority studio.db). All writes repointed to files.db via core/storage/document_store.py ensure_documents_schema()/connect_files(). Pre-condition: idempotent data migration script interfaces/cli/migrate_docstore_to_files_db.py copies 12 existing rows from studio.db to files.db before the DROP is applied. .released_version bumped 126 → 127. Migration-risk gate triggered (DROP TABLE on non-empty table class); matrix-watch required before merge. No PII; no FK cascade risk (reg_repo_extractions.document_id is a soft reference, not enforced at the DB level). -->

<!-- Last reviewed 2026-06-27 — WO-READMODELS-DUCKDB (worktree-agent-a57e51b228124e525): Migration 129 (129_drop_readmodel_projection_tables.sql) drops SQLite read-model/projection tables now served by DuckDB views in aggregate_metrics.db (derived from ai_canonical_events + business_canonical_events via events_fact). DROPPED: validation_failures (DuckDB VIEW over event.validation.failed; writer event_store._log_validation_failure() no-op'd) and hook_executions (DuckDB VIEW over system.hook.execution.logged; writer studio_db.insert_hook_execution() now emits only the canonical event; vw_hook_performance SQL view + 4 idx_hook_exec_* indexes dropped first; reads repointed: hooks.py /hooks/executions, /hooks/executions/{exec_id} keyed on event_id UUID, /hooks/performance, intelligence.py; /hooks/findings route removed since hook_findings carried 0 rows). Also dropped 5 Python-consumer projection tables (proj_workflow_runs/skill_stats/sessions/decision_patterns/security_summary) — consumers.py retired, no live readers. NOT DROPPED (read-write authority / data DuckDB cannot serve): raw_sessions (end_session UPDATE + mark_handoff_consumed flag has no canonical-event source; DuckDB read VIEW fixed this WO with a payload-keyed dedup join so ended_at/duration_s populate 521/513 of 559); token_usage_records (DuckDB token view has 0/1792 model_id and no cost, so estimated_cost/cost_visibility cannot be derived — usage_accounting forbids converting plan usage to API dollars and the dashboard_truth priceable_cost_present gate reads SQLite); hook_findings (0 rows, orphaned, kept harmless — follow-up cleanup). Both paths verified: fresh in-memory run_migrations ends with the dropped objects absent; temp-copy upgrade of live studio.db (107→105 tables) drops validation_failures + hook_executions + vw_hook_performance, keeps the retained tables. .released_version bumped 128 → 129. Migration-risk gate: DROP-class change on non-empty tables; matrix-watch required before merge (parent reviews + handles push; MIGRATION_RISK_ACKNOWLEDGED not set). -->

<!-- Last reviewed 2026-06-27 — Wave 2 substrate realignment (migration 131, worktree-agent-a910d590fedb5c672): Migration 131 (131_drop_dormant_feature_tables.sql) drops 24 DORMANT feature tables from studio.db — tables whose INSERT/UPSERT writer exists in source but is never called from any live entry point (CLI command, mounted route, registered hook, runner projection, spool ingest). Dropped: adapter_result_records, ai_usage_operational_records, alert_history, artifact_authority_records, connector_ingestion_runs, cor_skill_corrections, execution_dependencies, execution_event_links, execution_nodes, execution_outputs, github_repo_adoption_decisions, github_repo_evaluations, hardening_candidate_records, learning_event_records, model_provider_profiles, pending_audits, process_runs, raw_research, route_decision_records, shared_context_packets, skill_evaluation_runs, task_attribution_records, tool_embeddings_cache, tool_registry (plus their non-autoindex indexes). Dead writer/reader code removed (authority.py, usage_accounting.py, task_attribution.py, platform_hardening.py, execution_spine.py, emitters.py, graph.py, workflow_integration.py, studio_db.py, alert_evaluator.py, github_repo_intake.py, projects/mutations.py, research/engine.py, research/tools.py, hardening_loop.py, memory/ingestion.py CorrectionIngestionConsumer, eval/friction.py source-b, work_orders/start.py pending-audits advisory); dead alert_history API routes + dream_exec.py/exec_graph.py CLI deleted. 17 tables verified ACTIVE (writer on a live path) and kept. studio.db 100 → 76 tables. .released_version bumped 130 → 131. Migration-risk gate: DROP-class change on empty tables; matrix-watch required before merge (parent reviews + handles push; MIGRATION_RISK_ACKNOWLEDGED not set). -->
<!-- Last reviewed 2026-06-28 — Migration 132 (132_drop_ds_technology_signals.sql): idempotent DROP TABLE IF EXISTS ds_technology_signals. Forward-only drop of a dormant derived analytics sink (created in migration 055, never consumed). Safe on existing DBs; fresh installs create-then-drop via the 055->132 chain. .released_version bumped 131 -> 132. -->

<!-- Last reviewed 2026-06-28 — canonical-first migration Batch 1: Migration 133 drops compliance_review_flags (from migration 040, persist=False dead gate), release_readiness_records (migration 040, same dead gate), policy_decision_records (migration 046, test-only writer record_policy_decision()), guard_events (migration 090, all three writers test-only reachable). Both upgrade path (DROP TABLE IF EXISTS) and fresh-install path (CREATE TABLE removed from 040/046/090 baseline migrations) verified. .released_version bumped 132 -> 133. Docs-drift gate stamp: this entry. -->
