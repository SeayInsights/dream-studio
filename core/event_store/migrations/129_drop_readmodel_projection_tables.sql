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
--   hook_executions      — DuckDB: hook_executions VIEW over system.hook.execution.logged.
--                          Writer removed: studio_db.py insert_hook_execution() now only emits
--                          the HOOK_EXECUTION_LOGGED canonical event (no SQLite projection row).
--                          Reads repointed: hooks.py /hooks/executions, /hooks/executions/{exec_id}
--                          (now keyed on event_id UUID), /hooks/performance; intelligence.py.
--                          /hooks/findings route removed (hook_findings carried 0 rows; the
--                          empty JOIN returned nothing). vw_hook_performance SQL view dropped
--                          (dead analytics view over hook_executions; no production readers).
--
-- Tables NOT DROPPED (live read-WRITE authority or data DuckDB cannot serve):
--   token_usage_records  — KEPT: NOT a droppable read-model. The DuckDB token_usage_records view
--                          derives from canonical token events whose payloads carry NO model_id
--                          (0 of 1792 rows) and NO cost — so estimated_cost cannot be computed
--                          (compute_cost() needs a model to select a rate) and cost_visibility
--                          is absent. Per usage_accounting.py governance ("Plan usage ... must not
--                          [be converted] into API dollars") and the dashboard_truth gate's
--                          priceable_cost_present invariant (reads token_usage_records in SQLite,
--                          wired into work_orders/close.py), fabricating cost is forbidden.
--                          SQLite holds the only model_id (32 rows) + cost_visibility data.
--   raw_sessions         — KEPT: NOT a read-model — it is read-WRITE session-lifecycle authority.
--                          end_session() UPDATEs ended_at/duration_s/outcome; record_session()
--                          INSERTs; mark_handoff_consumed() UPDATEs handoff_consumed, a mutable
--                          flag with NO canonical-event source (DuckDB view hardcodes it NULL).
--                          resume_from_handoff.py reads handoff_consumed to prevent handoff
--                          re-spawn. Dropping would silently break handoff-resume dedup.
--                          (The DuckDB raw_sessions read VIEW was fixed in this WO to populate
--                          ended_at/duration_s via a payload-keyed dedup join, for dashboards.)
--   hook_findings        — KEPT: 0 rows, no readers (JOIN removed), writer uncalled. Left in
--                          place (empty/harmless); flagged as a follow-up dead-table cleanup.
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

-- Drop hook_executions (now served by DuckDB view over system.hook.execution.logged).
-- Drop the dependent analytics view first, then its indexes, then the table.
DROP VIEW IF EXISTS vw_hook_performance;
DROP INDEX IF EXISTS idx_hook_exec_activity;
DROP INDEX IF EXISTS idx_hook_exec_name_status;
DROP INDEX IF EXISTS idx_hook_exec_duration;
DROP INDEX IF EXISTS idx_hook_exec_started;
DROP TABLE IF EXISTS hook_executions;
