-- Migration 129: Drop SQLite read-model projection tables (WO-READMODELS-DUCKDB)
--
-- These tables are replaced by DuckDB views in aggregate_metrics.db derived from
-- events_fact (which sources from ai_canonical_events + business_canonical_events).
-- API routes have been repointed to read from DuckDB. Writers have been removed.
--
-- Tables DROPPED (no live readers; reads repointed to DuckDB):
--   validation_failures  — DuckDB: validation_failures VIEW over event.validation.failed
--                          Writer removed: event_store.py _log_validation_failure() no-op'd
--                          Reads repointed: hooks.py /hooks/validation-failures
--
-- Tables NOT DROPPED (live readers that DuckDB cannot serve):
--   token_usage_records  — KEPT: token_usage_sql() in authority_sources.py reads SQLite;
--                          estimated_cost / cost_visibility columns not derivable from events_fact;
--                          execution_spine.py still writes; dropping would break cost accounting.
--   hook_executions      — KEPT: /hooks/executions/{exec_id} requires integer PK lookup and
--                          hook_findings JOIN; DuckDB hook_exec_id is TEXT UUID (event_id),
--                          hook_findings not present in DuckDB.
--   raw_sessions         — KEPT: end_session() in studio_db.py UPDATEs raw_sessions (ended_at,
--                          duration_s, outcome); get_session() reads it; dropping would break
--                          the session-end runtime hook.
--
-- Projection tables DROPPED (no live readers; DuckDB events_fact is the source of truth):
--   proj_workflow_runs   — consumer in consumers.py removed; no live reads found
--   proj_skill_stats     — consumer in consumers.py removed; no live reads found
--   proj_sessions        — consumer in consumers.py removed; no live reads found
--   proj_decision_patterns — consumer in consumers.py removed; no live reads found
--   proj_security_summary  — consumer in consumers.py removed; no live reads found
--
-- Reviewed: 2026-06-26 (WO-READMODELS-DUCKDB)

-- Drop proj_* indexes before tables
DROP INDEX IF EXISTS idx_proj_wf_status;
DROP INDEX IF EXISTS idx_proj_wf_name;

-- Drop proj_* projection tables (created by Python consumers, not migrations)
DROP TABLE IF EXISTS proj_workflow_runs;
DROP TABLE IF EXISTS proj_skill_stats;
DROP TABLE IF EXISTS proj_sessions;
DROP TABLE IF EXISTS proj_decision_patterns;
DROP TABLE IF EXISTS proj_security_summary;

-- Drop validation_failures (now served by DuckDB view)
DROP INDEX IF EXISTS idx_validation_failures_event_type;
DROP TABLE IF EXISTS validation_failures;
