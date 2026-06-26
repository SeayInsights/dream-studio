-- Migration 062: Nullify activity_id FKs, backfill activity_log → canonical_events,
-- and replace views that referenced activity_log.
--
-- Background: activity_log is being retired (TA0c). Before it can be dropped
-- (migration 063), all child tables that use activity_id as a NOT NULL FK must
-- have that column relaxed to nullable, and all views that query activity_log
-- must be rewritten or retired.
--
-- SQLite limitation: ALTER COLUMN is not supported. Table recreation is the
-- canonical pattern. SQLite 3.26+ recompiles ALL views during ALTER TABLE RENAME;
-- any broken view aborts the rename. The solution is to drop ALL views before
-- the first table recreation and recreate the valid ones afterward.
--
-- Parts:
--   0 — Idempotency: drop leftover _new tables from prior partial runs
--   1 — Drop ALL views (15 DROP VIEW IF EXISTS — covers live + previously-absent)
--   2 — Recreate 7 tables with activity_id nullable (PRAGMA foreign_keys OFF/ON)
--   3 — Recreate 13 valid views (vw_graph_edges and vw_component_stats retired)
--   4 — INSERT OR IGNORE backfill: 159 activity_log rows → canonical_events

-- ============================================================================
-- Part 0: Idempotency — drop leftover _new tables from prior partial runs
-- ============================================================================

DROP TABLE IF EXISTS hook_executions_new;

DROP TABLE IF EXISTS hook_findings_new;

DROP TABLE IF EXISTS sec_sarif_findings_new;

DROP TABLE IF EXISTS sec_manual_reviews_new;

DROP TABLE IF EXISTS sec_cve_matches_new;

DROP TABLE IF EXISTS sec_hook_checks_new;

-- adapter_executions_new: removed (adapter_executions dropped in migration 128)

-- ============================================================================
-- Part 1: Drop ALL views before any table recreation.
-- SQLite recompiles every view during ALTER TABLE RENAME; a single broken view
-- aborts the rename. Dropping all views here makes all 7 recreations safe.
-- vw_graph_edges and vw_component_stats are permanently retired (broken since
-- initial publication commit 790965e, no production readers).
-- ============================================================================

DROP VIEW IF EXISTS effective_skill_runs;

DROP VIEW IF EXISTS v_active_execution;

DROP VIEW IF EXISTS v_blocked_nodes;

DROP VIEW IF EXISTS v_completion_rate;

DROP VIEW IF EXISTS vw_activity_timeline;

DROP VIEW IF EXISTS vw_approach_patterns;

DROP VIEW IF EXISTS vw_component_stats;

DROP VIEW IF EXISTS vw_graph_edges;

DROP VIEW IF EXISTS vw_guardrail_decisions;

DROP VIEW IF EXISTS vw_hook_performance;

DROP VIEW IF EXISTS vw_prd_progress;

DROP VIEW IF EXISTS vw_project_readiness_latest;

DROP VIEW IF EXISTS vw_risk_hotspots;

DROP VIEW IF EXISTS vw_security_summary;

DROP VIEW IF EXISTS vw_task_details;

-- ============================================================================
-- Part 2: Recreate 7 tables with activity_id nullable.
-- Removes NOT NULL constraint and FK to activity_log (which is dropped in 063).
-- ============================================================================

PRAGMA foreign_keys = OFF;

-- 2a: hook_executions
CREATE TABLE hook_executions_new (
    hook_exec_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER,
    hook_name TEXT NOT NULL,
    hook_type TEXT,
    trigger_context TEXT,
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    duration_ms INTEGER,
    exit_code INTEGER,
    status TEXT CHECK(status IN ('pending', 'running', 'success', 'failed', 'timeout')),
    output TEXT,
    error_message TEXT,
    cpu_time_ms INTEGER,
    memory_mb REAL
);

INSERT INTO hook_executions_new SELECT * FROM hook_executions;

DROP TABLE hook_executions;

ALTER TABLE hook_executions_new RENAME TO hook_executions;

CREATE INDEX idx_hook_exec_activity ON hook_executions(activity_id);

CREATE INDEX idx_hook_exec_name_status ON hook_executions(hook_name, status);

CREATE INDEX idx_hook_exec_duration ON hook_executions(duration_ms DESC);

CREATE INDEX idx_hook_exec_started ON hook_executions(started_at DESC);

-- 2b: hook_findings
CREATE TABLE hook_findings_new (
    finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER,
    hook_exec_id INTEGER NOT NULL,
    finding_type TEXT NOT NULL,
    severity TEXT CHECK(severity IN ('info', 'warning', 'error', 'critical')),
    message TEXT NOT NULL,
    context TEXT,
    recommendation TEXT,
    status TEXT CHECK(status IN ('open', 'acknowledged', 'resolved', 'wont_fix')),
    resolved_at DATETIME,
    resolution_notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hook_exec_id) REFERENCES hook_executions(hook_exec_id) ON DELETE CASCADE
);

INSERT INTO hook_findings_new SELECT * FROM hook_findings;

DROP TABLE hook_findings;

ALTER TABLE hook_findings_new RENAME TO hook_findings;

CREATE INDEX idx_hook_finding_activity ON hook_findings(activity_id);

CREATE INDEX idx_hook_finding_exec ON hook_findings(hook_exec_id);

CREATE INDEX idx_hook_finding_status_severity ON hook_findings(status, severity);

-- 2c: sec_sarif_findings
CREATE TABLE sec_sarif_findings_new (
    sarif_finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER,
    scan_tool TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    rule_name TEXT,
    severity TEXT CHECK(severity IN ('critical', 'high', 'medium', 'low', 'info')),
    file_path TEXT NOT NULL,
    line_number INTEGER,
    message TEXT NOT NULL,
    cwe_ids TEXT,
    cvss_score REAL,
    status TEXT CHECK(status IN ('open', 'mitigated', 'false_positive', 'accepted')) DEFAULT 'open',
    mitigated_at TEXT,
    mitigation_task_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (mitigation_task_id) REFERENCES prd_tasks(task_id) ON DELETE SET NULL
);

INSERT INTO sec_sarif_findings_new SELECT * FROM sec_sarif_findings;

DROP TABLE sec_sarif_findings;

ALTER TABLE sec_sarif_findings_new RENAME TO sec_sarif_findings;

CREATE INDEX idx_sarif_activity ON sec_sarif_findings(activity_id);

CREATE INDEX idx_sarif_status ON sec_sarif_findings(status);

CREATE INDEX idx_sarif_severity ON sec_sarif_findings(severity);

CREATE INDEX idx_sarif_rule_file ON sec_sarif_findings(rule_id, file_path, line_number);

-- 2d: sec_manual_reviews
CREATE TABLE sec_manual_reviews_new (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER,
    reviewer TEXT NOT NULL,
    review_type TEXT CHECK(review_type IN ('code_review', 'architecture_review', 'security_review')),
    findings TEXT,
    risk_level TEXT CHECK(risk_level IN ('critical', 'high', 'medium', 'low')),
    recommendations TEXT,
    status TEXT CHECK(status IN ('draft', 'published', 'closed')) DEFAULT 'draft',
    created_at TEXT DEFAULT (datetime('now'))
);

INSERT INTO sec_manual_reviews_new SELECT * FROM sec_manual_reviews;

DROP TABLE sec_manual_reviews;

ALTER TABLE sec_manual_reviews_new RENAME TO sec_manual_reviews;

CREATE INDEX idx_review_activity ON sec_manual_reviews(activity_id);

CREATE INDEX idx_review_status ON sec_manual_reviews(status);

CREATE INDEX idx_review_risk ON sec_manual_reviews(risk_level);

-- 2e: sec_cve_matches
CREATE TABLE sec_cve_matches_new (
    cve_match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER,
    cve_id TEXT NOT NULL,
    package_name TEXT NOT NULL,
    package_version TEXT NOT NULL,
    severity TEXT CHECK(severity IN ('critical', 'high', 'medium', 'low')),
    cvss_score REAL,
    description TEXT,
    fixed_version TEXT,
    status TEXT CHECK(status IN ('vulnerable', 'patched', 'mitigated')) DEFAULT 'vulnerable',
    patched_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

INSERT INTO sec_cve_matches_new SELECT * FROM sec_cve_matches;

DROP TABLE sec_cve_matches;

ALTER TABLE sec_cve_matches_new RENAME TO sec_cve_matches;

CREATE INDEX idx_cve_activity ON sec_cve_matches(activity_id);

CREATE INDEX idx_cve_status ON sec_cve_matches(status);

CREATE INDEX idx_cve_severity ON sec_cve_matches(severity);

CREATE INDEX idx_cve_package ON sec_cve_matches(package_name, package_version);

-- 2f: sec_hook_checks
CREATE TABLE sec_hook_checks_new (
    hook_check_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER,
    hook_exec_id INTEGER NOT NULL,
    check_type TEXT CHECK(check_type IN ('credentials_check', 'permissions_check', 'config_check')),
    check_result TEXT CHECK(check_result IN ('pass', 'fail', 'warning')),
    details TEXT,
    remediation TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (hook_exec_id) REFERENCES hook_executions(hook_exec_id) ON DELETE CASCADE
);

INSERT INTO sec_hook_checks_new SELECT * FROM sec_hook_checks;

DROP TABLE sec_hook_checks;

ALTER TABLE sec_hook_checks_new RENAME TO sec_hook_checks;

CREATE INDEX idx_hook_check_activity ON sec_hook_checks(activity_id);

CREATE INDEX idx_hook_check_exec ON sec_hook_checks(hook_exec_id);

CREATE INDEX idx_hook_check_result ON sec_hook_checks(check_result);

-- 2g: adapter_executions removed (dead table, dropped in migration 128).

PRAGMA foreign_keys = ON;

-- ============================================================================
-- Part 3: Recreate 13 valid views.
-- vw_graph_edges and vw_component_stats are permanently retired (broken since
-- initial publication commit 790965e — wrong column names in pi_dependencies,
-- missing reg_sessions table — no production readers exist).
-- vw_activity_timeline rewritten to read from canonical_events.
-- vw_guardrail_decisions rewritten with correct column names (action, message,
-- evaluated_at) matching the actual guardrail_decisions table schema.
-- All other views use exact canonical DDL from the live DB.
-- ============================================================================

CREATE VIEW effective_skill_runs AS
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

CREATE VIEW v_active_execution AS
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

CREATE VIEW v_blocked_nodes AS
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

CREATE VIEW v_completion_rate AS
SELECT
    node_type,
    COUNT(*) as total,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    ROUND(100.0 * SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) / COUNT(*), 1) as completion_pct
FROM execution_nodes
GROUP BY node_type;

-- vw_activity_timeline rewritten: reads from canonical_events instead of activity_log.
-- Column mapping: event_id→activity_id, event_type→activity_type,
-- timestamp→event_timestamp, trace JSON→stream_type/stream_id,
-- payload JSON→summary.
CREATE VIEW vw_activity_timeline AS
SELECT
    event_id,
    event_type,
    timestamp AS event_timestamp,
    severity,
    json_extract(trace, '$.stream_type') AS stream_type,
    json_extract(trace, '$.stream_id') AS stream_id,
    json_extract(payload, '$.summary') AS summary
FROM canonical_events
ORDER BY timestamp DESC;

CREATE VIEW vw_approach_patterns AS
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

-- vw_guardrail_decisions rewritten: removes JOIN to activity_log; uses correct
-- column names from the actual guardrail_decisions schema (action, message,
-- evaluated_at — the original DDL wrongly used decision, reason, event_timestamp).
CREATE VIEW vw_guardrail_decisions AS
SELECT
    decision_id,
    rule_id,
    action AS decision,
    event_id,
    evaluated_at AS event_timestamp,
    message AS reason
FROM guardrail_decisions
ORDER BY evaluated_at DESC;

CREATE VIEW vw_hook_performance AS
SELECT
    hook_name,
    COUNT(*) AS execution_count,
    AVG(duration_ms) AS avg_duration_ms,
    MAX(duration_ms) AS max_duration_ms,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failure_count
FROM hook_executions
GROUP BY hook_name
ORDER BY avg_duration_ms DESC;

CREATE VIEW vw_prd_progress AS
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

CREATE VIEW vw_project_readiness_latest AS
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

CREATE VIEW vw_risk_hotspots AS
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

CREATE VIEW vw_task_details AS
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

-- ============================================================================
-- Part 4: Backfill 159 activity_log rows into canonical_events.
-- INSERT OR IGNORE is idempotent: re-running produces no duplicate rows.
-- Deterministic event_id prefix: 'backfill-activity-log-' || activity_id.
-- Stream context preserved in trace JSON; original event_data becomes payload.
-- ============================================================================

INSERT OR IGNORE INTO canonical_events (
    event_id, event_type, timestamp, trace, severity, payload,
    raw_prompt_retained, raw_tool_output_retained, schema_version
)
SELECT
    'backfill-activity-log-' || activity_id,
    'system.session.recorded',
    event_timestamp,
    json_object(
        'domain', 'system',
        'attribution_status', 'backfill',
        'stream_type', COALESCE(stream_type, ''),
        'stream_id', COALESCE(stream_id, '')
    ),
    COALESCE(severity, 'info'),
    COALESCE(event_data, '{}'),
    0, 0, 1
FROM activity_log WHERE activity_type = 'session_started';

INSERT OR IGNORE INTO canonical_events (
    event_id, event_type, timestamp, trace, severity, payload,
    raw_prompt_retained, raw_tool_output_retained, schema_version
)
SELECT
    'backfill-activity-log-' || activity_id,
    'system.session.closed',
    event_timestamp,
    json_object(
        'domain', 'system',
        'attribution_status', 'backfill',
        'stream_type', COALESCE(stream_type, ''),
        'stream_id', COALESCE(stream_id, '')
    ),
    COALESCE(severity, 'info'),
    COALESCE(event_data, '{}'),
    0, 0, 1
FROM activity_log WHERE activity_type = 'session_ended';

INSERT OR IGNORE INTO canonical_events (
    event_id, event_type, timestamp, trace, severity, payload,
    raw_prompt_retained, raw_tool_output_retained, schema_version
)
SELECT
    'backfill-activity-log-' || activity_id,
    'system.handoff.created',
    event_timestamp,
    json_object(
        'domain', 'system',
        'attribution_status', 'backfill',
        'stream_type', COALESCE(stream_type, ''),
        'stream_id', COALESCE(stream_id, '')
    ),
    COALESCE(severity, 'info'),
    COALESCE(event_data, '{}'),
    0, 0, 1
FROM activity_log WHERE activity_type = 'handoff_created';

INSERT OR IGNORE INTO canonical_events (
    event_id, event_type, timestamp, trace, severity, payload,
    raw_prompt_retained, raw_tool_output_retained, schema_version
)
SELECT
    'backfill-activity-log-' || activity_id,
    'system.hook.execution.logged',
    event_timestamp,
    json_object(
        'domain', 'system',
        'attribution_status', 'backfill',
        'stream_type', COALESCE(stream_type, ''),
        'stream_id', COALESCE(stream_id, '')
    ),
    COALESCE(severity, 'info'),
    COALESCE(event_data, '{}'),
    0, 0, 1
FROM activity_log WHERE activity_type = 'hook_execution';

INSERT OR IGNORE INTO canonical_events (
    event_id, event_type, timestamp, trace, severity, payload,
    raw_prompt_retained, raw_tool_output_retained, schema_version
)
SELECT
    'backfill-activity-log-' || activity_id,
    'workflow.completed',
    event_timestamp,
    json_object(
        'domain', 'system',
        'attribution_status', 'backfill',
        'stream_type', COALESCE(stream_type, ''),
        'stream_id', COALESCE(stream_id, '')
    ),
    COALESCE(severity, 'info'),
    COALESCE(event_data, '{}'),
    0, 0, 1
FROM activity_log WHERE activity_type = 'workflow_run';

INSERT OR IGNORE INTO canonical_events (
    event_id, event_type, timestamp, trace, severity, payload,
    raw_prompt_retained, raw_tool_output_retained, schema_version
)
SELECT
    'backfill-activity-log-' || activity_id,
    'workflow.node.completed',
    event_timestamp,
    json_object(
        'domain', 'system',
        'attribution_status', 'backfill',
        'stream_type', COALESCE(stream_type, ''),
        'stream_id', COALESCE(stream_id, '')
    ),
    COALESCE(severity, 'info'),
    COALESCE(event_data, '{}'),
    0, 0, 1
FROM activity_log WHERE activity_type = 'workflow_node';
