-- Migration 001: Initial schema (workflow runs, telemetry, analytics)

CREATE TABLE IF NOT EXISTS raw_workflow_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key TEXT NOT NULL UNIQUE,
    workflow TEXT NOT NULL,
    yaml_path TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    node_count INTEGER,
    nodes_done INTEGER
);

CREATE TABLE IF NOT EXISTS raw_workflow_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key TEXT NOT NULL REFERENCES raw_workflow_runs(run_key),
    node_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    duration_s REAL,
    output TEXT
);

CREATE TABLE IF NOT EXISTS raw_skill_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT NOT NULL,
    invoked_at TEXT NOT NULL,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    success INTEGER NOT NULL,
    execution_time_s REAL
);

CREATE TABLE IF NOT EXISTS cor_skill_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telemetry_id INTEGER NOT NULL REFERENCES raw_skill_telemetry(id),
    corrected_success INTEGER NOT NULL,
    reason TEXT,
    corrected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sum_skill_summary (
    skill_name TEXT PRIMARY KEY,
    times_used INTEGER,
    success_rate REAL,
    avg_input_tokens REAL,
    avg_output_tokens REAL,
    avg_exec_time_s REAL,
    last_success TEXT,
    last_failure TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS log_batch_imports (
    batch_id TEXT PRIMARY KEY,
    imported_at TEXT NOT NULL,
    row_count INTEGER NOT NULL
);

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

CREATE TABLE IF NOT EXISTS raw_pulse_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL UNIQUE,
    health_score INTEGER NOT NULL,
    health_status TEXT NOT NULL,
    ci_status TEXT,
    open_prs INTEGER,
    stale_branches INTEGER,
    pending_drafts INTEGER,
    open_escalations INTEGER,
    raw_content TEXT
);

CREATE TABLE IF NOT EXISTS raw_planning_specs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_path TEXT NOT NULL UNIQUE,
    title TEXT,
    created_date TEXT,
    task_count INTEGER,
    has_build_commit INTEGER DEFAULT 0,
    last_checked TEXT
);

CREATE TABLE IF NOT EXISTS sum_analytics_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    pulse_rows INTEGER,
    spec_rows INTEGER,
    skill_rows INTEGER,
    output_path TEXT
);

CREATE TABLE IF NOT EXISTS raw_operational_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    project_slug TEXT NOT NULL,
    ci_status TEXT,
    open_prs INTEGER,
    stale_branches INTEGER,
    pending_drafts INTEGER,
    open_escalations INTEGER,
    captured_at TEXT NOT NULL,
    UNIQUE(snapshot_date, project_slug)
);
