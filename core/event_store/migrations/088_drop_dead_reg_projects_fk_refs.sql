-- Migration 088: Remove dead FK references to reg_projects
--
-- Migration 084 dropped reg_projects but left raw_sessions, raw_handoffs,
-- raw_specs, and raw_tasks with FK references to it. SQLite raises
-- "no such table: main.reg_projects" on INSERT when foreign_keys=ON,
-- breaking all operational table writes.
--
-- Fix: recreate the four affected tables without the dead FK clause.
-- Data is preserved; project_id columns stay TEXT (just without the REFERENCES).

PRAGMA foreign_keys = OFF;

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
INSERT INTO raw_sessions_new SELECT * FROM raw_sessions;
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
INSERT INTO raw_handoffs_new SELECT * FROM raw_handoffs;
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
INSERT INTO raw_specs_new SELECT * FROM raw_specs;
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
INSERT INTO raw_tasks_new SELECT * FROM raw_tasks;
DROP TABLE raw_tasks;
ALTER TABLE raw_tasks_new RENAME TO raw_tasks;

CREATE INDEX idx_tasks_spec ON raw_tasks(spec_id);
CREATE INDEX idx_tasks_project ON raw_tasks(project_id, status);

PRAGMA foreign_keys = ON;
