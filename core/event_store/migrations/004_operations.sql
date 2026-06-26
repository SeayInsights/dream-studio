-- Migration 004: Operational tables, indexes, FTS5, column additions

-- ── New tables ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS reg_projects (
    project_id TEXT PRIMARY KEY,
    project_path TEXT NOT NULL,
    project_name TEXT,
    project_type TEXT,
    git_remote TEXT,
    last_session_at TEXT,
    total_sessions INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_sessions (
    session_id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES reg_projects(project_id),
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

CREATE TABLE IF NOT EXISTS raw_handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES raw_sessions(session_id),
    project_id TEXT REFERENCES reg_projects(project_id),
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

-- raw_specs and raw_tasks removed in migration 128
-- (dead tables: migrate_to_db pipeline removed; no live consumer)

CREATE TABLE IF NOT EXISTS raw_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    confidence TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'draft',
    title TEXT NOT NULL,
    what_happened TEXT,
    lesson TEXT,
    evidence TEXT,
    promoted_to TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS raw_sentinels (
    sentinel_key TEXT PRIMARY KEY,
    sentinel_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS raw_token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    project_id TEXT,
    skill_name TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    model TEXT,
    recorded_at TEXT NOT NULL
);

-- ── Indexes on existing tables ──────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_approaches_skill ON raw_approaches(skill_id, outcome);
CREATE INDEX IF NOT EXISTS idx_approaches_captured ON raw_approaches(captured_at);
CREATE INDEX IF NOT EXISTS idx_telemetry_skill ON raw_skill_telemetry(skill_name, invoked_at);
CREATE INDEX IF NOT EXISTS idx_corrections_telemetry ON cor_skill_corrections(telemetry_id);
CREATE INDEX IF NOT EXISTS idx_wfnodes_runkey ON raw_workflow_nodes(run_key);
CREATE INDEX IF NOT EXISTS idx_wfruns_workflow ON raw_workflow_runs(workflow, finished_at);
CREATE INDEX IF NOT EXISTS idx_gotchas_skill ON reg_gotchas(skill_id);
CREATE INDEX IF NOT EXISTS idx_gotchas_discovered ON reg_gotchas(discovered);
-- idx_skills_pack, idx_workflows_category removed in migration 128 (dead tables)
CREATE INDEX IF NOT EXISTS idx_opsnapshots_project ON raw_operational_snapshots(project_slug, snapshot_date);
-- idx_pulse_date, idx_specs_path removed in migration 128 (dead tables)

-- ── Indexes on new tables ───────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_projects_last_session ON reg_projects(last_session_at);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON raw_sessions(project_id, started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON raw_sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_handoffs_session ON raw_handoffs(session_id);
CREATE INDEX IF NOT EXISTS idx_handoffs_project ON raw_handoffs(project_id, created_at);
-- idx_specs_project, idx_tasks_spec, idx_tasks_project removed in migration 128 (dead tables)
CREATE INDEX IF NOT EXISTS idx_lessons_status ON raw_lessons(status);
CREATE INDEX IF NOT EXISTS idx_lessons_source ON raw_lessons(source);
CREATE INDEX IF NOT EXISTS idx_sentinels_type ON raw_sentinels(sentinel_type);
CREATE INDEX IF NOT EXISTS idx_tokens_session ON raw_token_usage(session_id);
CREATE INDEX IF NOT EXISTS idx_tokens_project_date ON raw_token_usage(project_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_tokens_skill ON raw_token_usage(skill_name, recorded_at);

-- ── ALTER TABLE: add project_id/session_id to existing tables ───────────────
-- May fail with "duplicate column name" on re-run; handled gracefully by runner.

ALTER TABLE raw_approaches ADD COLUMN project_id TEXT;
ALTER TABLE raw_approaches ADD COLUMN session_id TEXT;
ALTER TABLE raw_skill_telemetry ADD COLUMN project_id TEXT;
ALTER TABLE raw_skill_telemetry ADD COLUMN session_id TEXT;

CREATE INDEX IF NOT EXISTS idx_approaches_project ON raw_approaches(project_id);
CREATE INDEX IF NOT EXISTS idx_approaches_session ON raw_approaches(session_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_project ON raw_skill_telemetry(project_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_session ON raw_skill_telemetry(session_id);

-- ── FTS5 full-text search on gotchas ────────────────────────────────────────
-- Requires FTS5 extension; skipped gracefully if unavailable.

CREATE VIRTUAL TABLE IF NOT EXISTS fts_gotchas USING fts5(
    gotcha_id, title, context, fix, keywords,
    content=reg_gotchas, content_rowid=rowid
);

CREATE TRIGGER IF NOT EXISTS trg_gotchas_ai AFTER INSERT ON reg_gotchas BEGIN
    INSERT INTO fts_gotchas(rowid, gotcha_id, title, context, fix, keywords)
    VALUES (new.rowid, new.gotcha_id, new.title, new.context, new.fix, new.keywords);
END;

CREATE TRIGGER IF NOT EXISTS trg_gotchas_ad AFTER DELETE ON reg_gotchas BEGIN
    INSERT INTO fts_gotchas(fts_gotchas, rowid, gotcha_id, title, context, fix, keywords)
    VALUES ('delete', old.rowid, old.gotcha_id, old.title, old.context, old.fix, old.keywords);
END;

CREATE TRIGGER IF NOT EXISTS trg_gotchas_au AFTER UPDATE ON reg_gotchas BEGIN
    INSERT INTO fts_gotchas(fts_gotchas, rowid, gotcha_id, title, context, fix, keywords)
    VALUES ('delete', old.rowid, old.gotcha_id, old.title, old.context, old.fix, old.keywords);
    INSERT INTO fts_gotchas(rowid, gotcha_id, title, context, fix, keywords)
    VALUES (new.rowid, new.gotcha_id, new.title, new.context, new.fix, new.keywords);
END;
