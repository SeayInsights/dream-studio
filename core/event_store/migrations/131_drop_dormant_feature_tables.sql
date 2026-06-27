-- Migration 131: Drop dormant feature tables (Wave 2 substrate realignment)
--
-- Target architecture: studio.db = canonical EVENTS + non-event-sourced AUTHORITY + pipeline ONLY.
-- Everything derived (projections, telemetry, read-models, analytics) moves to DuckDB.
--
-- Tables DROPPED (0 rows, no live writers, dormant features never reached production):
--
-- adapter_result_records       — dead writer record_adapter_result(); no caller outside tests
-- alert_history                — dead writer trigger_alert(); AlertEvaluator never instantiated in production
-- artifact_authority_records   — dead writer record_artifact_authority(); test-only callers
-- connector_ingestion_runs     — dead writer ingest_connector_payload(); test-only callers
-- cor_skill_corrections        — dead writer skill_correct(); only reachable via unregistered __main__
-- execution_dependencies       — dead writer add_dependency(); dream_exec.py unregistered from ds CLI
-- execution_event_links        — dead writer link_event_to_node(); dream_exec.py unregistered from ds CLI
-- execution_nodes              — dead writer create_node(); dream_exec.py unregistered from ds CLI
-- execution_outputs            — dead writer add_output(); dream_exec.py unregistered from ds CLI
-- github_repo_adoption_decisions — dead writer record_github_repo_evaluation(); never called from production
-- github_repo_evaluations      — dead writer record_github_repo_evaluation(); never called from production
-- hardening_candidate_records  — dead writer record_hardening_candidate(); test-only callers
-- learning_event_records       — dead writer record_learning_event(); test-only callers
-- model_provider_profiles      — dead writer record_model_provider_profile(); test-only callers
-- pending_audits               — dead writer defer_project_audit(); never called from any production path
-- process_runs                 — dead writer record_process_run(); test-only callers
-- raw_research                 — dead writers insert_research()/_store_research(); test-only callers
-- route_decision_records       — dead writer emit_route_decision() via handoff.py; no live callers
-- shared_context_packets       — writer record_shared_context_packet() exists but all callers use persist=False
-- skill_evaluation_runs        — dead writer record_skill_evaluation(); test-only callers
-- task_attribution_records     — dead writer record_task_attribution(); test-only callers
-- tool_embeddings_cache        — dead writer build_embedding_index(); never called from live path
-- tool_registry                — no production INSERT exists; only test fixtures
--
-- Table reviewed and KEPT (NOT dropped — has a LIVE writer):
-- ai_usage_operational_records — written by core/analytics_ingestion.py::ingest_analytics_payload(),
--   reachable from the registered CLI `ds system analytics-ingest`. The Wave 2 writer-trace
--   originally flagged it dormant by only inspecting usage_accounting.record_ai_usage_operational_record
--   (which is itself unused), but missed the live table-driven INSERT in analytics_ingestion.py.
--   Its indexes idx_ai_usage_operational_process/_scope are managed by migrations 081/117.
--
-- VIEWS repaired/dropped (they referenced retired tables):
--   effective_skill_runs   — RECREATED without the dropped cor_skill_corrections LEFT JOIN. The
--     correction join was always a no-op (cor_skill_corrections had no live writer, always 0 rows;
--     COALESCE(c.corrected_success, t.success) always fell through to t.success and signal_source
--     was always 'heuristic'). The view is LIVE: read by studio_db.rebuild_summaries /
--     get_skill_summaries and interfaces/cli/ds_analytics (skill velocity).
--   v_active_execution / v_blocked_nodes / v_completion_rate — DROPPED. They read the retired
--     execution_nodes/execution_dependencies tables and have no live Python reader.
--
-- Result: 100 - 23 = 77 tables.
-- Note: sqlite_autoindex_* indexes are dropped automatically with their tables.
--
-- Reviewed: 2026-06-27 (Wave 2 substrate realignment)

-- adapter_result_records — 0 rows, dead writer record_adapter_result()
DROP INDEX IF EXISTS idx_adapter_results_scope;
DROP TABLE IF EXISTS adapter_result_records;

-- alert_history — 0 rows, dead writer trigger_alert(); AlertEvaluator never instantiated
DROP INDEX IF EXISTS idx_alert_history_rule;
DROP INDEX IF EXISTS idx_alert_history_triggered;
DROP TABLE IF EXISTS alert_history;

-- artifact_authority_records — 0 rows, dead writer record_artifact_authority()
DROP INDEX IF EXISTS idx_artifact_authority_scope;
DROP TABLE IF EXISTS artifact_authority_records;

-- connector_ingestion_runs — 0 rows, dead writer ingest_connector_payload()
DROP INDEX IF EXISTS idx_connector_ingestion_runs_source;
DROP TABLE IF EXISTS connector_ingestion_runs;

-- Repair effective_skill_runs view BEFORE dropping cor_skill_corrections so a partial-fixture
-- replay never leaves a view bound to a table about to be dropped. The recreated view drops the
-- correction LEFT JOIN (cor_skill_corrections retired) and reads raw_skill_telemetry directly.
DROP VIEW IF EXISTS effective_skill_runs;
CREATE VIEW IF NOT EXISTS effective_skill_runs AS
SELECT
    t.id,
    t.skill_name,
    t.invoked_at,
    t.success AS success,
    'heuristic' AS signal_source,
    t.input_tokens,
    t.output_tokens,
    t.execution_time_s
FROM raw_skill_telemetry t;

-- cor_skill_corrections — 0 rows, only reachable via unregistered __main__
DROP INDEX IF EXISTS idx_corrections_telemetry;
DROP TABLE IF EXISTS cor_skill_corrections;

-- Drop the execution-graph views before their backing tables (no live Python reader).
DROP VIEW IF EXISTS v_active_execution;
DROP VIEW IF EXISTS v_blocked_nodes;
DROP VIEW IF EXISTS v_completion_rate;

-- execution_dependencies — 0 rows, dream_exec.py unregistered from ds CLI
DROP INDEX IF EXISTS idx_execution_deps_source;
DROP INDEX IF EXISTS idx_execution_deps_target;
DROP INDEX IF EXISTS idx_execution_deps_type;
DROP TABLE IF EXISTS execution_dependencies;

-- execution_event_links — 0 rows, dream_exec.py unregistered from ds CLI
DROP INDEX IF EXISTS idx_execution_event_links_event;
DROP INDEX IF EXISTS idx_execution_event_links_node;
DROP TABLE IF EXISTS execution_event_links;

-- execution_nodes — 0 rows, dream_exec.py unregistered from ds CLI
DROP INDEX IF EXISTS idx_execution_nodes_created;
DROP INDEX IF EXISTS idx_execution_nodes_parent;
DROP INDEX IF EXISTS idx_execution_nodes_project;
DROP INDEX IF EXISTS idx_execution_nodes_status;
DROP INDEX IF EXISTS idx_execution_nodes_type;
DROP TABLE IF EXISTS execution_nodes;

-- execution_outputs — 0 rows, dream_exec.py unregistered from ds CLI
DROP INDEX IF EXISTS idx_execution_outputs_created;
DROP INDEX IF EXISTS idx_execution_outputs_node;
DROP INDEX IF EXISTS idx_execution_outputs_type;
DROP TABLE IF EXISTS execution_outputs;

-- github_repo_adoption_decisions — 0 rows, dead writer record_github_repo_evaluation()
DROP TABLE IF EXISTS github_repo_adoption_decisions;

-- github_repo_evaluations — 0 rows, dead writer record_github_repo_evaluation()
DROP INDEX IF EXISTS idx_github_repo_evaluations_repo;
DROP TABLE IF EXISTS github_repo_evaluations;

-- hardening_candidate_records — 0 rows, dead writer record_hardening_candidate()
DROP INDEX IF EXISTS idx_hardening_component;
DROP TABLE IF EXISTS hardening_candidate_records;

-- learning_event_records — 0 rows, dead writer record_learning_event()
DROP INDEX IF EXISTS idx_learning_events_component;
DROP INDEX IF EXISTS idx_learning_events_scope;
DROP TABLE IF EXISTS learning_event_records;

-- model_provider_profiles — 0 rows, dead writer record_model_provider_profile()
DROP TABLE IF EXISTS model_provider_profiles;

-- pending_audits — 0 rows, dead writer defer_project_audit()
DROP INDEX IF EXISTS idx_pending_audits_project_status;
DROP TABLE IF EXISTS pending_audits;

-- process_runs — 0 rows, dead writer record_process_run()
DROP INDEX IF EXISTS idx_process_runs_scope;
DROP TABLE IF EXISTS process_runs;

-- raw_research — 0 rows, dead writers insert_research()/_store_research()
DROP INDEX IF EXISTS idx_raw_research_activity;
DROP INDEX IF EXISTS idx_raw_research_prd;
DROP INDEX IF EXISTS idx_raw_research_task;
DROP TABLE IF EXISTS raw_research;

-- route_decision_records — 0 rows, dead writer emit_route_decision() via handoff.py
DROP INDEX IF EXISTS idx_route_records_scope;
DROP TABLE IF EXISTS route_decision_records;

-- shared_context_packets — 0 rows, writer exists but all callers use persist=False
DROP INDEX IF EXISTS idx_context_packets_adapter;
DROP TABLE IF EXISTS shared_context_packets;

-- skill_evaluation_runs — 0 rows, dead writer record_skill_evaluation()
DROP INDEX IF EXISTS idx_skill_evaluation_runs_target;
DROP TABLE IF EXISTS skill_evaluation_runs;

-- task_attribution_records — 0 rows, dead writer record_task_attribution()
DROP INDEX IF EXISTS idx_task_attribution_adapter;
DROP INDEX IF EXISTS idx_task_attribution_outcome;
DROP INDEX IF EXISTS idx_task_attribution_process;
DROP INDEX IF EXISTS idx_task_attribution_project;
DROP INDEX IF EXISTS idx_task_attribution_work_order;
DROP TABLE IF EXISTS task_attribution_records;

-- tool_embeddings_cache — 0 rows, dead writer build_embedding_index()
DROP INDEX IF EXISTS idx_embeddings_model;
DROP TABLE IF EXISTS tool_embeddings_cache;

-- tool_registry — 0 rows, no production INSERT exists; only test fixtures
DROP INDEX IF EXISTS idx_tool_category;
DROP INDEX IF EXISTS idx_tool_tags;
DROP TABLE IF EXISTS tool_registry;
