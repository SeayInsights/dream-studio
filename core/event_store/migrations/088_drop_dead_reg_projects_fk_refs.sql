-- Migration 088: Remove dead FK references to reg_projects
--
-- Migration 084 dropped reg_projects but left raw_sessions, raw_handoffs,
-- raw_specs, and raw_tasks with FK references to it. SQLite raises
-- "no such table: main.reg_projects" on INSERT when foreign_keys=ON,
-- breaking all operational table writes.
--
-- Fix: recreate the four affected tables without the dead FK clause.
-- Data is preserved; project_id columns stay TEXT (just without the REFERENCES).
--
-- Following the migration 081 pattern: views that reference tables in this
-- migration are dropped before the table operations and recreated afterward.
-- This avoids "error in view X: no such table: Y" errors during ALTER TABLE
-- RENAME operations on partial-fixture test DBs (where some tables from earlier
-- migrations may not exist). On production DBs the DROP IF EXISTS statements
-- are no-ops and the view recreations are idempotent.

PRAGMA foreign_keys = OFF;

-- ── Drop views that may trigger schema-validation errors during renames ───────
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

-- ── raw_sessions ─────────────────────────────────────────────────────────────

CREATE TABLE raw_sessions_new (
    session_id TEXT PRIMARY KEY,
    project_id TEXT,
    topic TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_s REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    tasks_completed INTEGER DEFAULT 0,
    pipeline_phase TEXT,
    handoff_consumed INTEGER DEFAULT 0,
    outcome TEXT
);
INSERT INTO raw_sessions_new (session_id, project_id, topic, started_at, ended_at, duration_s, input_tokens, output_tokens, tasks_completed, pipeline_phase, handoff_consumed, outcome)
SELECT session_id, project_id, topic, started_at, ended_at, duration_s, input_tokens, output_tokens, tasks_completed, pipeline_phase, handoff_consumed, outcome FROM raw_sessions;
DROP TABLE raw_sessions;
ALTER TABLE raw_sessions_new RENAME TO raw_sessions;

CREATE INDEX idx_sessions_project ON raw_sessions(project_id, started_at);
CREATE INDEX idx_sessions_started ON raw_sessions(started_at);

-- ── raw_handoffs ──────────────────────────────────────────────────────────────

CREATE TABLE raw_handoffs_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES raw_sessions(session_id),
    project_id TEXT,
    topic TEXT NOT NULL,
    plan_path TEXT,
    pipeline_phase TEXT,
    current_task_id TEXT,
    current_task_name TEXT,
    tasks_completed INTEGER,
    tasks_total INTEGER,
    branch TEXT,
    last_commit TEXT,
    working TEXT,
    broken TEXT,
    pending_decisions TEXT,
    active_files TEXT,
    next_action TEXT,
    lessons_json TEXT,
    gotchas_hit TEXT,
    approaches_json TEXT,
    created_at TEXT NOT NULL
);
INSERT INTO raw_handoffs_new (id, session_id, project_id, topic, plan_path, pipeline_phase, current_task_id, current_task_name, tasks_completed, tasks_total, branch, last_commit, working, broken, pending_decisions, active_files, next_action, lessons_json, gotchas_hit, approaches_json, created_at)
SELECT id, session_id, project_id, topic, plan_path, pipeline_phase, current_task_id, current_task_name, tasks_completed, tasks_total, branch, last_commit, working, broken, pending_decisions, active_files, next_action, lessons_json, gotchas_hit, approaches_json, created_at FROM raw_handoffs;
DROP TABLE raw_handoffs;
ALTER TABLE raw_handoffs_new RENAME TO raw_handoffs;

CREATE INDEX idx_handoffs_session ON raw_handoffs(session_id);
CREATE INDEX idx_handoffs_project ON raw_handoffs(project_id, created_at);

-- ── raw_specs ─────────────────────────────────────────────────────────────────

CREATE TABLE raw_specs_new (
    spec_id TEXT PRIMARY KEY,
    project_id TEXT,
    title TEXT NOT NULL,
    status TEXT DEFAULT 'draft',
    task_count INTEGER,
    tasks_done INTEGER DEFAULT 0,
    spec_content TEXT,
    plan_content TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    pr_numbers TEXT
);
INSERT INTO raw_specs_new (spec_id, project_id, title, status, task_count, tasks_done, spec_content, plan_content, created_at, completed_at, pr_numbers)
SELECT spec_id, project_id, title, status, task_count, tasks_done, spec_content, plan_content, created_at, completed_at, pr_numbers FROM raw_specs;
DROP TABLE raw_specs;
ALTER TABLE raw_specs_new RENAME TO raw_specs;

CREATE INDEX idx_specs_project ON raw_specs(project_id, status);

-- ── raw_tasks ─────────────────────────────────────────────────────────────────

CREATE TABLE raw_tasks_new (
    task_id TEXT NOT NULL,
    spec_id TEXT NOT NULL,
    project_id TEXT,
    title TEXT NOT NULL,
    status TEXT DEFAULT 'planned',
    depends_on TEXT,
    estimated_hours REAL,
    actual_hours REAL,
    assigned_session TEXT,
    commit_sha TEXT,
    completed_at TEXT,
    PRIMARY KEY (task_id, spec_id)
);
INSERT INTO raw_tasks_new (task_id, spec_id, project_id, title, status, depends_on, estimated_hours, actual_hours, assigned_session, commit_sha, completed_at)
SELECT task_id, spec_id, project_id, title, status, depends_on, estimated_hours, actual_hours, assigned_session, commit_sha, completed_at FROM raw_tasks;
DROP TABLE raw_tasks;
ALTER TABLE raw_tasks_new RENAME TO raw_tasks;

CREATE INDEX idx_tasks_spec ON raw_tasks(spec_id);
CREATE INDEX idx_tasks_project ON raw_tasks(project_id, status);

-- ── Recreate views dropped above ─────────────────────────────────────────────
-- Exact DDL from migration 081 (idempotent via IF NOT EXISTS).
-- vw_activity_timeline is permanently omitted — it references canonical_events
-- which is Python-owned and absent from migrations (see migration 081 comment).

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
