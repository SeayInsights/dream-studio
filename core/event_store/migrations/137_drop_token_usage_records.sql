-- Migration 137: Drop the retired token_usage_records SQLite read-model (WO-DBA-DROP)
--
-- Target architecture: studio.db = canonical EVENTS + non-event-sourced AUTHORITY
-- + pipeline ONLY. token_usage_records was a private direct-write projection table
-- for a signal that is really an event: the canonical token.consumed events in
-- ai_canonical_events/business_canonical_events are the complete, authoritative
-- source (operator-confirmed 2026-07-03).
--
-- Evidence this table is safely droppable (WO-DBA-DROP investigation, superseding
-- the migration-136-era schema_keeplist_data.py "KEEP" rationale):
--   * All 113 live rows in the operator's authority have billing_mode='unknown',
--     cost_visibility='unknown', estimated_cost=0.0 — the accounting columns this
--     table existed to hold are uniformly degenerate. They carry no information
--     the canonical event stream doesn't already carry.
--   * PR #450/#451 widened the DuckDB aggregate_metrics.db token_usage_records VIEW
--     (core/analytics/duckdb_store.py) to derive model_id (COALESCE of
--     events_fact.model_id and payload $.model), cached_tokens
--     ($.cache_creation_input_tokens), cache_read_tokens
--     ($.cache_read_input_tokens), and estimated_cost (LEFT JOIN
--     token_model_pricing, the same arithmetic as
--     core/pricing/claude_models.compute_cost) — the exact gap that made this
--     table "KEEP" at migration 136 time no longer exists. The DuckDB view is now
--     strictly more informative than the SQLite table it used to mirror.
--
-- Writers removed:
--   core/telemetry/execution_spine.py::record_token_usage — deleted (the function
--     had no remaining purpose once its sole INSERT target was dropped).
--   core/telemetry/emitters.py::emit_token_usage_record — no longer calls
--     record_token_usage; still emits the execution_events "token.usage_recorded"
--     row unchanged (that dual-write is independent telemetry, not token
--     accounting).
--   core/projections/token_projection.py::TokenConsumptionProjection — deleted
--     (materialized token.consumed events into this table from
--     ai_canonical_events; the DuckDB events_fact pipeline now does this job for
--     the dashboard read side). Registration removed from
--     core/projections/runner.py (sync_tick + main()).
--
-- Readers repointed to the DuckDB aggregate_metrics.db token_usage_records VIEW
-- (core/analytics/duckdb_store.py), all via connect_analytics(read_only=True)
-- with graceful empty-state on any exception (missing store, missing view):
--   projections/core/collectors/authority_sources.py::token_usage_sql() — when the
--     passed SQLite connection has no token_usage_records table (the production
--     post-migration-137 case), materializes the current DuckDB rows into a
--     connection-scoped SQLite TEMP TABLE and returns a SELECT over it, so every
--     existing caller (token_collector.py, model_collector.py,
--     projections/api/routes/metrics.py, projections/api/routes/intelligence.py)
--     keeps working via the same "embed as subquery" pattern unchanged. The
--     historical "connection has the real table" branch is left intact for any
--     not-yet-migrated authority — dead in production, harmless.
--   projections/core/cost_analysis.py::api_equivalent_cost() — same pattern:
--     legacy-table branch first (kept for direct callers/tests), DuckDB view
--     second, empty result third. Never raises.
--   projections/api/routes/analytics.py::get_trends() — token/cost trend rows
--     read directly from the DuckDB connection already open for session trends.
--   projections/api/routes/insights.py::get_attribution_breakouts() — token
--     attribution breakouts read from the DuckDB view; business_projects.name
--     enrichment stays on SQLite (two-connection pattern already used in
--     analytics.py).
--   core/telemetry/read_models.py::_token_rollup / _token_cost_intelligence /
--     process_run_timeline / workflow_execution_graph — token_usage_records
--     removed from the FACT_TABLES required-table gate (it is no longer a SQLite
--     table in a fresh install); token rollups repoint to the DuckDB view with
--     the same conn-first/DuckDB-fallback/empty pattern.
--   core/shared_intelligence/usage_accounting.py::_token_accounting_rows —
--     repointed to the DuckDB view.
--   core/gates/dashboard_truth.py — the three token invariants
--     (token_model_null_fraction, token_skill_attributed, priceable_cost_present)
--     now run against the DuckDB view via connect_analytics(read_only=True); a
--     missing analytics store/view is a pass-with-note, never a gate failure —
--     work-order close must not be blocked by an absent (rebuildable,
--     NEVER-AUTHORITY) analytics store.
--   core/telemetry/dashboard_freshness.py — token_usage_records classification
--     now reflects the DuckDB-backed source instead of reporting the dropped
--     SQLite table as schema drift.
--
-- decision_records, eval_registry, ds_eval_baselines, raw_sessions, and
-- raw_token_usage are NOT touched by this migration — separate authority/registry
-- tables and the session-lifecycle read-write authority (handoff_consumed has no
-- event source) outside this change set.
--
-- Dangling FK note: ai_usage_operational_records.token_usage_id had
-- FOREIGN KEY (token_usage_id) REFERENCES token_usage_records(token_usage_id)
-- (migrations 043/081). Dropping token_usage_records while that FK exists would
-- break every future INSERT into ai_usage_operational_records — a live table
-- (analytics_ingestion.ingest_analytics_payload() is a live writer) — with
-- "no such table: token_usage_records" once PRAGMA foreign_keys=ON validates
-- the constraint's parent table. This migration rebuilds
-- ai_usage_operational_records via the same table-reconstruction pattern
-- migration 081 used (CREATE _new + INSERT...SELECT + DROP + RENAME), dropping
-- only that one FK clause; every column, CHECK constraint, and the other two
-- FKs (adapter_id, accounting_profile_id) are unchanged. token_usage_id stays
-- as a plain (unenforced) TEXT column — a not-yet-migrated authority's
-- operational records keep whatever token_usage_id they were written with;
-- new rows may simply leave it NULL. The two indexes migration 117 recreated
-- (idx_ai_usage_operational_scope, idx_ai_usage_operational_process) are
-- recreated again since DROP TABLE removes them.
--
-- Idempotent: DROP TABLE IF EXISTS / CREATE TABLE IF NOT EXISTS / CREATE INDEX
-- IF NOT EXISTS throughout.
--
-- Result: 76 - 1 = 75 tables.
-- Reviewed: 2026-07-03 (WO-DBA-DROP, authority e0b90310-bf30-4146-b9df-58707a2e5d86)

PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS ai_usage_operational_records_new (
    usage_record_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    work_order_id TEXT,
    process_run_id TEXT,
    adapter_id TEXT NOT NULL,
    provider TEXT,
    model_id TEXT,
    accounting_profile_id TEXT,
    token_usage_id TEXT,
    billing_mode TEXT NOT NULL DEFAULT 'unknown',
    token_visibility TEXT NOT NULL DEFAULT 'unavailable',
    cost_visibility TEXT NOT NULL DEFAULT 'unknown',
    usage_source TEXT NOT NULL DEFAULT 'local_telemetry',
    cost_source TEXT NOT NULL DEFAULT 'unknown',
    confidence TEXT NOT NULL DEFAULT 'unknown',
    input_tokens INTEGER,
    output_tokens INTEGER,
    cached_tokens INTEGER,
    total_tokens INTEGER,
    cost_amount NUMERIC(20, 8),
    cost_currency TEXT,
    run_count INTEGER NOT NULL DEFAULT 1,
    files_touched_json TEXT NOT NULL DEFAULT '[]',
    commands_run_json TEXT NOT NULL DEFAULT '[]',
    validation_result TEXT,
    pr_result_outcome TEXT,
    success INTEGER,
    failure_reason TEXT,
    rework_needed INTEGER,
    security_findings_json TEXT NOT NULL DEFAULT '[]',
    readiness_findings_json TEXT NOT NULL DEFAULT '[]',
    duration_ms INTEGER,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (billing_mode IN (
        'subscription_plan', 'plan_allowance', 'token_metered', 'api_metered',
        'credit_metered', 'enterprise_contract', 'unknown', 'unavailable'
    )),
    CHECK (token_visibility IN ('exact', 'partial', 'estimated', 'unavailable')),
    CHECK (cost_visibility IN (
        'exact', 'provider_reported', 'estimated', 'allocated_subscription_cost',
        'unavailable', 'unknown'
    )),
    CHECK (usage_source IN (
        'provider_metadata', 'provider_usage_export', 'local_telemetry',
        'plan_usage_panel', 'manual_config', 'unavailable'
    )),
    CHECK (cost_source IN (
        'provider_metadata', 'provider_usage_export', 'billing_api',
        'plan_allocation_config', 'local_estimate', 'unavailable', 'unknown'
    )),
    CHECK (confidence IN ('high', 'medium', 'low', 'unknown')),
    CHECK (success IN (0, 1) OR success IS NULL),
    CHECK (rework_needed IN (0, 1) OR rework_needed IS NULL),
    FOREIGN KEY (adapter_id) REFERENCES adapter_authority_profiles(adapter_id),
    FOREIGN KEY (accounting_profile_id)
        REFERENCES ai_adapter_accounting_profiles(profile_id)
    -- FK to token_usage_records(token_usage_id) removed — the table is dropped below.
);

INSERT INTO ai_usage_operational_records_new
SELECT
    usage_record_id,
    project_id,
    milestone_id,
    task_id,
    work_order_id,
    process_run_id,
    adapter_id,
    provider,
    model_id,
    accounting_profile_id,
    token_usage_id,
    billing_mode,
    token_visibility,
    cost_visibility,
    usage_source,
    cost_source,
    confidence,
    input_tokens,
    output_tokens,
    cached_tokens,
    total_tokens,
    cost_amount,
    cost_currency,
    run_count,
    files_touched_json,
    commands_run_json,
    validation_result,
    pr_result_outcome,
    success,
    failure_reason,
    rework_needed,
    security_findings_json,
    readiness_findings_json,
    duration_ms,
    source_refs_json,
    evidence_refs_json,
    created_at
FROM ai_usage_operational_records;

DROP TABLE IF EXISTS ai_usage_operational_records;
ALTER TABLE ai_usage_operational_records_new RENAME TO ai_usage_operational_records;

CREATE INDEX IF NOT EXISTS idx_ai_usage_operational_scope
ON ai_usage_operational_records(project_id, milestone_id, task_id, work_order_id, adapter_id);

CREATE INDEX IF NOT EXISTS idx_ai_usage_operational_process
ON ai_usage_operational_records(process_run_id, adapter_id, model_id);

DROP TABLE IF EXISTS token_usage_records;

PRAGMA foreign_keys = ON;
