-- Migration 130: Drop aspirational telemetry + legacy backup tables (Wave 1 substrate realignment)
--
-- Target architecture: studio.db = canonical EVENTS + non-event-sourced AUTHORITY + pipeline ONLY.
-- Everything derived (projections, telemetry, read-models, analytics) moves to DuckDB.
--
-- Tables DROPPED (no live writers; all queries return empty results from 0-row tables):
--
--   canonical_events_legacy_backup (8433 rows)
--     Operator explicit DROP. Legacy backup created when canonical_events was renamed in
--     migration 102 (WO-M). Data already fully migrated to ai_canonical_events +
--     business_canonical_events (dual-canonical). The backfill script was a one-time tool.
--     Backup taken by operator before this migration. No live readers.
--
--   hook_findings (0 rows)
--     No live readers — the /hooks/{id}/findings JOIN was removed in migration 129
--     (WO-READMODELS-DUCKDB) comment, and the /hooks/findings route was removed.
--     Writer (insert_hook_finding in studio_db.py) exists but is never called from
--     production code. Left over from pre-129 hook_executions era. Writer function
--     and dead code removed in this commit.
--
--   authority_projection_records (0 rows)
--     Aspirational telemetry from execution_spine.py (WO-P). Writer function
--     record_authority_projection() defined but never called from production code.
--     Readers in read_models.py return empty results since the table is always empty.
--     Dashboard route /telemetry/summary called _artifact_lineage_lifecycle() which
--     SELECTed from this table — the function is removed in this commit along with
--     the table drop. No data is lost (0 rows). No DuckDB repoint needed (nothing to serve).
--
--   blocker_resolution_records (0 rows)
--     Aspirational telemetry from execution_spine.py (WO-P). Writer function
--     record_blocker_resolution() defined but never called from production code.
--     Readers in read_models.py returned empty results. Dashboard route /telemetry/summary
--     called _research_blocker_resolution() which SELECTed from this table — removed
--     in this commit. No data is lost (0 rows). No DuckDB repoint needed.
--
--   artifact_records (0 rows)
--     Aspirational telemetry. No INSERT statement exists in production code — only in
--     tests. Readers in read_models.py (_artifact_lineage_lifecycle, _artifact_lifecycle_counts)
--     returned empty results. Referenced as "normalization_targets" in platform_hardening.py
--     config dicts (not SQL queries) — references removed in this commit.
--     No data is lost (0 rows). No DuckDB repoint needed.
--
-- Tables reviewed and KEPT (per operator decision rule: non-derivable authority or
-- live readers requiring repoint-first):
--   All other OTHER-set tables retained pending Wave 2 analysis.
--
-- Result: 106 - 5 = 101 tables.
--
-- Reviewed: 2026-06-27 (Wave 1 substrate realignment)

-- canonical_events_legacy_backup — operator explicit DROP, legacy backup
DROP INDEX IF EXISTS idx_canonical_events_legacy_type;
DROP INDEX IF EXISTS idx_canonical_events_legacy_session;
DROP INDEX IF EXISTS idx_canonical_events_legacy_ts;
DROP TABLE IF EXISTS canonical_events_legacy_backup;

-- hook_findings — 0 rows, no live readers, dead writer
DROP INDEX IF EXISTS idx_hook_findings_exec;
DROP INDEX IF EXISTS idx_hook_findings_activity;
DROP INDEX IF EXISTS idx_hook_findings_status;
DROP TABLE IF EXISTS hook_findings;

-- authority_projection_records — 0 rows, no live writer, aspirational telemetry
DROP INDEX IF EXISTS idx_auth_proj_project;
DROP INDEX IF EXISTS idx_auth_proj_milestone;
DROP INDEX IF EXISTS idx_auth_proj_task;
DROP INDEX IF EXISTS idx_auth_proj_domain;
DROP TABLE IF EXISTS authority_projection_records;

-- blocker_resolution_records — 0 rows, no live writer, aspirational telemetry
DROP INDEX IF EXISTS idx_blocker_project;
DROP INDEX IF EXISTS idx_blocker_milestone;
DROP INDEX IF EXISTS idx_blocker_task;
DROP INDEX IF EXISTS idx_blocker_route;
DROP TABLE IF EXISTS blocker_resolution_records;

-- artifact_records — 0 rows, no production writer, aspirational telemetry
DROP INDEX IF EXISTS idx_artifact_project;
DROP INDEX IF EXISTS idx_artifact_milestone;
DROP INDEX IF EXISTS idx_artifact_task;
DROP INDEX IF EXISTS idx_artifact_role;
DROP INDEX IF EXISTS idx_artifact_lifecycle;
DROP TABLE IF EXISTS artifact_records;
