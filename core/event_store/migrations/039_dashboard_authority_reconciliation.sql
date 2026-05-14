-- Migration 039: Dashboard Authority Reconciliation
-- Created: 2026-05-14
-- Purpose:
--   Repair dashboard authority objects that may be missing from older operator
--   databases even when their historical migration versions are recorded.
--   This migration is additive except for replacing the placeholder-shaped
--   vw_security_summary view with a current dashboard-compatible view.

-- raw_sessions compatibility repair for installed databases that only have
-- session_id/created_at. Duplicate-column errors are intentionally handled by
-- the migration runner for already-compatible databases.
CREATE TABLE IF NOT EXISTS raw_sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT
);
ALTER TABLE raw_sessions ADD COLUMN project_id TEXT;
ALTER TABLE raw_sessions ADD COLUMN topic TEXT;
ALTER TABLE raw_sessions ADD COLUMN started_at TEXT;
ALTER TABLE raw_sessions ADD COLUMN ended_at TEXT;
ALTER TABLE raw_sessions ADD COLUMN duration_s REAL;
ALTER TABLE raw_sessions ADD COLUMN input_tokens INTEGER;
ALTER TABLE raw_sessions ADD COLUMN output_tokens INTEGER;
ALTER TABLE raw_sessions ADD COLUMN tasks_completed INTEGER DEFAULT 0;
ALTER TABLE raw_sessions ADD COLUMN pipeline_phase TEXT;
ALTER TABLE raw_sessions ADD COLUMN handoff_consumed INTEGER DEFAULT 0;
ALTER TABLE raw_sessions ADD COLUMN outcome TEXT;

CREATE INDEX IF NOT EXISTS idx_sessions_project ON raw_sessions(project_id, started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON raw_sessions(started_at);

-- Alert authority objects. Empty tables are a real current empty state; missing
-- tables are not.
CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id TEXT PRIMARY KEY,
    rule_name TEXT NOT NULL,
    metric_path TEXT NOT NULL,
    condition TEXT NOT NULL,
    threshold REAL,
    severity TEXT,
    enabled BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS alert_history (
    alert_id TEXT PRIMARY KEY,
    rule_id TEXT,
    triggered_at TEXT NOT NULL,
    metric_value REAL,
    severity TEXT,
    resolved_at TEXT,
    FOREIGN KEY (rule_id) REFERENCES alert_rules(rule_id)
);

ALTER TABLE alert_rules ADD COLUMN rule_name TEXT;
ALTER TABLE alert_rules ADD COLUMN metric_path TEXT;
ALTER TABLE alert_rules ADD COLUMN condition TEXT;
ALTER TABLE alert_rules ADD COLUMN threshold REAL;
ALTER TABLE alert_rules ADD COLUMN severity TEXT;
ALTER TABLE alert_rules ADD COLUMN enabled BOOLEAN DEFAULT 1;

ALTER TABLE alert_history ADD COLUMN rule_id TEXT;
ALTER TABLE alert_history ADD COLUMN triggered_at TEXT;
ALTER TABLE alert_history ADD COLUMN metric_value REAL;
ALTER TABLE alert_history ADD COLUMN severity TEXT;
ALTER TABLE alert_history ADD COLUMN resolved_at TEXT;

CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled, severity);
CREATE INDEX IF NOT EXISTS idx_alert_history_triggered ON alert_history(triggered_at, resolved_at);
CREATE INDEX IF NOT EXISTS idx_alert_history_rule ON alert_history(rule_id, triggered_at);

-- Structured ledger for live/dashboard authority reconciliation actions. This
-- lets the DB carry the current-state truth when old objects were repaired,
-- retired, or quarantined.
CREATE TABLE IF NOT EXISTS dashboard_authority_reconciliation_records (
    record_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    target_table TEXT NOT NULL,
    target_id TEXT,
    classification TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dashboard_authority_reconciliation_scope
ON dashboard_authority_reconciliation_records(scope, created_at);

-- Compatible current security table for installed databases where migration 037
-- was recorded but the table is absent. Existing richer schemas are preserved.
CREATE TABLE IF NOT EXISTS security_findings (
    finding_id TEXT PRIMARY KEY,
    scan_id TEXT,
    category TEXT,
    severity TEXT NOT NULL,
    file_path TEXT,
    start_line INTEGER,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Compatible SARIF table for installed databases where migration 020 was
-- recorded but the table is absent. Existing richer schemas are preserved.
CREATE TABLE IF NOT EXISTS sec_sarif_findings (
    sarif_finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_tool TEXT NOT NULL,
    rule_id TEXT,
    rule_name TEXT,
    severity TEXT,
    file_path TEXT NOT NULL,
    line_number INTEGER,
    message TEXT NOT NULL,
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT (datetime('now'))
);

-- Current security dashboard view. The previous placeholder shape looked like
-- SELECT 1 AS placeholder in some installed states, which made the dashboard
-- rely on fallback code instead of a real read model.
DROP VIEW IF EXISTS vw_security_summary;
CREATE VIEW vw_security_summary AS
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
