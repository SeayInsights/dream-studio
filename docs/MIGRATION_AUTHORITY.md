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

Migration `046_platform_hardening_authority.sql` is additive. It creates
records for skill/workflow evaluations, policy decisions, connector ingestion
runs, privacy/redaction exports, local watch declarations, sanitized team
rollups, installer/distribution checks, and demo/case-study packets. It does
not authorize cleanup, external mutation, Docker execution, live SQLite writes,
push/deploy actions, secret access, or public publication.
