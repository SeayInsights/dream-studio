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

## Migration 011 Gap

`core/event_store/migrations/011_*.sql` does not exist. This is an intentional numbering gap.

The root `migrations/011_delete_prd_tables.sql` performed destructive PRD table cleanup during an earlier phase. When the canonical migration directory was established in `core/event_store/migrations/`, migration 011 was deliberately skipped to avoid collision with the root migration numbering. The PRD schema was subsequently rebuilt as `012_prd_schema.sql`.

**Do not fill this gap** with a dummy migration. The migration runner handles non-sequential numbers correctly.

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