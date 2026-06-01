-- Migration 089: Rename security_scan_runs and security_findings to reflect their
-- actual scope (all-skill data, not security-only).
--
-- Background: security_scan_runs was created in migration 085 for the brownfield
-- security scan pipeline. Migration 087 added skill_id to generalize it to all
-- quality skills (code-quality, testing, types-deps, database). The table now holds
-- scans across all five quality skills keyed by skill_id.
-- security_findings similarly holds findings from all skills via rule_id prefix.
--
-- This rename is cosmetic correctness: the table names should reflect their actual scope.
--
-- Following the migration 088 pattern: views are dropped before renames and recreated
-- afterward to avoid "error in view X: no such table: Y" during ALTER TABLE validation
-- on partial-fixture test DBs where some tables from earlier migrations may not exist.
-- vw_security_summary is updated to reference the new `findings` table name.

PRAGMA foreign_keys = OFF;

-- ── Drop views that may trigger schema-validation errors during renames ───────
-- Same list as migration 088 plus vw_security_summary which references security_findings.
DROP VIEW IF EXISTS effective_skill_runs;
DROP VIEW IF EXISTS v_active_execution;
DROP VIEW IF EXISTS v_blocked_nodes;
DROP VIEW IF EXISTS v_completion_rate;
DROP VIEW IF EXISTS vw_approach_patterns;
DROP VIEW IF EXISTS vw_guardrail_decisions;
DROP VIEW IF EXISTS vw_hook_performance;
DROP VIEW IF EXISTS vw_prd_progress;
DROP VIEW IF EXISTS vw_project_readiness_latest;
DROP VIEW IF EXISTS vw_risk_hotspots;
DROP VIEW IF EXISTS vw_security_summary;
DROP VIEW IF EXISTS vw_task_details;

-- ── 1. Rename primary tables ──────────────────────────────────────────────────
ALTER TABLE security_scan_runs RENAME TO scan_runs;
ALTER TABLE security_findings RENAME TO findings;

-- ── 2. Rename dependent tables that reference these names ─────────────────────
-- security_scan_deltas references security_findings; rename it too
ALTER TABLE security_scan_deltas RENAME TO scan_deltas;

-- ── 3. Re-create indexes with new names (SQLite does not auto-rename indexes) ──
-- Drop old indexes (they still point to the old table names in SQLite's schema)
DROP INDEX IF EXISTS idx_security_findings_project;
DROP INDEX IF EXISTS idx_security_findings_rule;
DROP INDEX IF EXISTS idx_security_findings_hash;
DROP INDEX IF EXISTS idx_security_findings_scan;
DROP INDEX IF EXISTS idx_security_scan_runs_project;
DROP INDEX IF EXISTS idx_security_scan_runs_skill;
DROP INDEX IF EXISTS idx_scan_deltas_scan;

-- Re-create with new table names
CREATE INDEX IF NOT EXISTS idx_findings_project ON findings(project_id, severity, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_findings_rule ON findings(project_id, rule_id, status);
CREATE INDEX IF NOT EXISTS idx_findings_hash ON findings(finding_hash) WHERE finding_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_findings_scan ON findings(scan_id, severity);
CREATE INDEX IF NOT EXISTS idx_scan_runs_project ON scan_runs(project_id, skill_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_runs_skill ON scan_runs(project_id, skill_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_deltas_scan ON scan_deltas(scan_id);

-- ── Recreate views dropped above ─────────────────────────────────────────────
-- Exact DDL from migration 081/088 (idempotent via IF NOT EXISTS).
-- vw_security_summary updated to reference the renamed `findings` table.
-- vw_activity_timeline is permanently omitted — references canonical_events (Python-owned).

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

-- vw_security_summary: updated to reference `findings` (renamed from security_findings in this migration)
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
FROM findings
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
