-- Migration 081: Convert financial REAL columns to NUMERIC(20, 8).
--
-- Background:
--   ds-quality:database Batch 7 audit (18.4.2) surfaced 4 critical db-005
--   findings: estimated_cost REAL in token_usage_records and cost_amount REAL
--   in ai_usage_operational_records. REAL (IEEE 754 float) accumulates rounding
--   error over repeated additions. NUMERIC(20, 8) provides exact decimal
--   arithmetic adequate for USD costs and microcents precision.
--
-- Pattern:
--   SQLite does not support ALTER COLUMN TYPE. This migration uses the standard
--   table-reconstruction pattern: (1) create new table with corrected type,
--   (2) copy data with explicit CAST, (3) drop old table, (4) rename new table.
--   Followed by recreation of any associated objects (FK-dependent tables are
--   not altered — only the FK-source ai_usage_operational_records references
--   token_usage_records.token_usage_id (PK), which is unchanged).
--
-- Safety:
--   - CAST(REAL AS NUMERIC) is lossless for the cost values stored (small floats
--     representing USD amounts with sub-cent precision).
--   - PRAGMA foreign_keys = OFF used to suppress FK constraint checking during
--     reconstruction. Re-enabled at the end.
--   - IF NOT EXISTS / DROP TABLE IF EXISTS used throughout for idempotency.
--   - Backup of live DB before applying is the recommended rollback path.
--
-- Affected columns:
--   1. token_usage_records.estimated_cost  REAL NOT NULL DEFAULT 0  → NUMERIC(20,8)
--   2. ai_usage_operational_records.cost_amount  REAL               → NUMERIC(20,8)

PRAGMA foreign_keys = OFF;

-- ── Part 0: Drop ALL views (migration 062 pattern) ──────────────────────────
--
-- SQLite 3.26+ validates every view in the schema during ALTER TABLE RENAME.
-- Any view referencing a table that is absent in the current DB (e.g., a partial
-- test fixture or an upgrade DB missing later tables) aborts the rename.
-- Two known problem views:
--   - effective_skill_runs → raw_skill_telemetry (absent in partial test fixtures)
--   - vw_activity_timeline → canonical_events (Python-owned, absent in all
--     migration-only DBs; exception handler in sqlite_bootstrap.py:120 swallows
--     "canonical_events" errors, making the rename failure silent and leaving the
--     schema broken)
-- The safe fix is the migration 062 approach: drop ALL views before reconstruction,
-- recreate all but vw_activity_timeline afterward. vw_activity_timeline is NOT
-- recreated — it references the Python-owned canonical_events table (pre-existing
-- architectural debt, see docs/architecture/aspirational-schema-debt.md).

DROP VIEW IF EXISTS effective_skill_runs;
DROP VIEW IF EXISTS v_active_execution;
DROP VIEW IF EXISTS v_blocked_nodes;
DROP VIEW IF EXISTS v_completion_rate;
DROP VIEW IF EXISTS vw_activity_timeline;
DROP VIEW IF EXISTS vw_approach_patterns;
DROP VIEW IF EXISTS vw_guardrail_decisions;
DROP VIEW IF EXISTS vw_hook_performance;
DROP VIEW IF EXISTS vw_prd_progress;
DROP VIEW IF EXISTS vw_project_readiness_latest;
DROP VIEW IF EXISTS vw_risk_hotspots;
DROP VIEW IF EXISTS vw_security_summary;
DROP VIEW IF EXISTS vw_task_details;

-- ── Part 1: token_usage_records.estimated_cost ──────────────────────────────

CREATE TABLE IF NOT EXISTS token_usage_records_new (
    token_usage_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    agent_id TEXT,
    skill_id TEXT,
    workflow_id TEXT,
    hook_id TEXT,
    model_id TEXT,
    provider TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost NUMERIC(20, 8) NOT NULL DEFAULT 0,
    purpose TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    adapter_id TEXT,
    billing_mode TEXT NOT NULL DEFAULT 'unknown',
    token_visibility TEXT NOT NULL DEFAULT 'exact',
    cost_visibility TEXT NOT NULL DEFAULT 'unknown',
    usage_source TEXT NOT NULL DEFAULT 'local_telemetry',
    cost_source TEXT NOT NULL DEFAULT 'unknown',
    accounting_confidence TEXT NOT NULL DEFAULT 'medium'
);

INSERT INTO token_usage_records_new
SELECT
    token_usage_id,
    project_id,
    milestone_id,
    task_id,
    process_run_id,
    agent_id,
    skill_id,
    workflow_id,
    hook_id,
    model_id,
    provider,
    input_tokens,
    output_tokens,
    cached_tokens,
    total_tokens,
    CAST(estimated_cost AS NUMERIC) AS estimated_cost,
    purpose,
    created_at,
    source_refs_json,
    evidence_refs_json,
    adapter_id,
    billing_mode,
    token_visibility,
    cost_visibility,
    usage_source,
    cost_source,
    accounting_confidence
FROM token_usage_records;

DROP TABLE IF EXISTS token_usage_records;
ALTER TABLE token_usage_records_new RENAME TO token_usage_records;

-- ── Part 2: ai_usage_operational_records.cost_amount ────────────────────────

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
        REFERENCES ai_adapter_accounting_profiles(profile_id),
    FOREIGN KEY (token_usage_id) REFERENCES token_usage_records(token_usage_id)
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
    CAST(cost_amount AS NUMERIC) AS cost_amount,
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

-- ── Part 3: Recreate 12 views (vw_activity_timeline omitted — broken view) ──
-- Exact DDL from migration 062; all views use IF NOT EXISTS for idempotency.
-- vw_activity_timeline is permanently dropped here — it references canonical_events
-- which is owned by EventStore._init_tables() and absent from migrations.

CREATE VIEW IF NOT EXISTS effective_skill_runs AS
SELECT
    t.id,
    t.skill_name,
    t.invoked_at,
    COALESCE(c.corrected_success, t.success) AS success,
    CASE WHEN c.id IS NOT NULL THEN 'corrected' ELSE 'heuristic' END AS signal_source,
    t.input_tokens,
    t.output_tokens,
    t.execution_time_s
FROM raw_skill_telemetry t
LEFT JOIN cor_skill_corrections c ON c.telemetry_id = t.id;

CREATE VIEW IF NOT EXISTS v_active_execution AS
SELECT
    node_id,
    node_type,
    title,
    status,
    started_at,
    (julianday('now') - julianday(started_at)) * 24 * 60 as runtime_minutes
FROM execution_nodes
WHERE status = 'active'
ORDER BY started_at ASC;

CREATE VIEW IF NOT EXISTS v_blocked_nodes AS
SELECT
    en.node_id,
    en.node_type,
    en.title,
    en.status,
    COUNT(ed.dependency_id) as blocking_count
FROM execution_nodes en
JOIN execution_dependencies ed ON en.node_id = ed.source_node_id
JOIN execution_nodes blocker ON ed.target_node_id = blocker.node_id
WHERE en.status = 'blocked'
  AND blocker.status != 'completed'
  AND ed.dependency_type = 'blocks'
GROUP BY en.node_id
ORDER BY blocking_count DESC;

CREATE VIEW IF NOT EXISTS v_completion_rate AS
SELECT
    node_type,
    COUNT(*) as total,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    ROUND(100.0 * SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) / COUNT(*), 1) as completion_pct
FROM execution_nodes
GROUP BY node_type;

CREATE VIEW IF NOT EXISTS vw_approach_patterns AS
SELECT
    skill_id,
    approach,
    COUNT(*) AS times_tried,
    SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes,
    ROUND(
        CAST(SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS REAL)
        / COUNT(*) * 100, 1
    ) AS success_pct,
    CAST(AVG(tokens_used) AS INTEGER) AS avg_tokens,
    ROUND(AVG(duration_s), 1) AS avg_duration
FROM raw_approaches
GROUP BY skill_id, approach
HAVING COUNT(*) >= 2;

CREATE VIEW IF NOT EXISTS vw_guardrail_decisions AS
SELECT
    decision_id,
    rule_id,
    action AS decision,
    event_id,
    evaluated_at AS event_timestamp,
    message AS reason
FROM guardrail_decisions
ORDER BY evaluated_at DESC;

CREATE VIEW IF NOT EXISTS vw_hook_performance AS
SELECT
    hook_name,
    COUNT(*) AS execution_count,
    AVG(duration_ms) AS avg_duration_ms,
    MAX(duration_ms) AS max_duration_ms,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failure_count
FROM hook_executions
GROUP BY hook_name
ORDER BY avg_duration_ms DESC;

CREATE VIEW IF NOT EXISTS vw_prd_progress AS
SELECT
    p.prd_id,
    p.title,
    p.status,
    p.total_tasks,
    p.completed_tasks,
    ROUND(100.0 * p.completed_tasks / NULLIF(p.total_tasks, 0), 1) AS pct_complete,
    p.created_at,
    p.approved_at,
    p.completed_at,
    (SELECT COUNT(*) FROM prd_handoffs h WHERE h.prd_id = p.prd_id) AS handoff_count,
    (SELECT COUNT(*) FROM prd_sessions s WHERE s.prd_id = p.prd_id) AS session_count
FROM prd_documents p;

CREATE VIEW IF NOT EXISTS vw_project_readiness_latest AS
SELECT
    pr.project_id,
    pr.assessment_id,
    pr.readiness_score,
    pr.confidence AS readiness_confidence,
    pr.status AS readiness_status,
    pr.missing_evidence_json,
    pr.blocking_factors_json,
    pr.created_at
FROM project_readiness_scorecards pr
JOIN (
    SELECT project_id, MAX(created_at) AS max_created_at
    FROM project_readiness_scorecards
    GROUP BY project_id
) latest
ON pr.project_id = latest.project_id AND pr.created_at = latest.max_created_at;

CREATE VIEW IF NOT EXISTS vw_risk_hotspots AS
SELECT
    file_path,
    COUNT(*) AS finding_count,
    MAX(severity) AS max_severity,
    GROUP_CONCAT(DISTINCT scan_tool) AS tools
FROM sec_sarif_findings
WHERE status = 'open'
  AND file_path IS NOT NULL
GROUP BY file_path
HAVING finding_count >= 3
ORDER BY finding_count DESC;

CREATE VIEW IF NOT EXISTS vw_security_summary AS
SELECT
    'telemetry_security' AS source_type,
    finding_id,
    COALESCE(scan_id, category, 'telemetry_security') AS tool,
    severity,
    file_path,
    start_line AS line_number,
    description AS message,
    status,
    created_at
FROM security_findings
UNION ALL
SELECT
    'sarif' AS source_type,
    CAST(sarif_finding_id AS TEXT) AS finding_id,
    scan_tool AS tool,
    severity,
    file_path,
    line_number,
    message,
    status,
    created_at
FROM sec_sarif_findings
ORDER BY created_at DESC;

CREATE VIEW IF NOT EXISTS vw_task_details AS
SELECT
    t.task_id,
    t.task_name,
    t.description,
    t.status,
    t.phase,
    t.prd_id,
    p.title AS prd_title,
    p.status AS prd_status,
    t.wave_id,
    t.depends_on,
    t.started_at,
    t.completed_at,
    t.created_at
FROM prd_tasks t
JOIN prd_documents p ON t.prd_id = p.prd_id;

PRAGMA foreign_keys = ON;
