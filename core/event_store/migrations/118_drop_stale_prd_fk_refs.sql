-- Migration 118: Drop stale prd_tasks / prd_documents FK references
--
-- Migration 103 dropped prd_tasks and prd_documents, but three tables
-- still carry REFERENCES clauses pointing at them:
--   raw_workflow_runs  → prd_documents(prd_id), prd_tasks(task_id)
--   research_cache     → prd_documents(prd_id), prd_tasks(task_id), activity_log(activity_id)
--   raw_research       → prd_documents(prd_id), prd_tasks(task_id), activity_log(activity_id)
--
-- With PRAGMA foreign_keys = ON, even NULL inserts fail with
-- "no such table: main.prd_tasks", breaking archive_workflow() and
-- research insertion. Recreate each table without the stale FKs.

PRAGMA foreign_keys = OFF;

-- Drop stale view left behind by migration 112 (which dropped sec_sarif_findings
-- but not this view). SQLite validates view references during ALTER TABLE RENAME,
-- so the rename fails if this view exists while its underlying table is missing.
DROP VIEW IF EXISTS vw_risk_hotspots;

-- ── raw_workflow_runs ────────────────────────────────────────────────────────
CREATE TABLE raw_workflow_runs_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key TEXT NOT NULL UNIQUE,
    workflow TEXT NOT NULL,
    yaml_path TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    node_count INTEGER,
    nodes_done INTEGER,
    activity_id INTEGER,
    prd_id TEXT,
    task_id TEXT
);

INSERT INTO raw_workflow_runs_new
    SELECT id, run_key, workflow, yaml_path, status, started_at,
           finished_at, node_count, nodes_done, activity_id, prd_id, task_id
    FROM raw_workflow_runs;

DROP TABLE raw_workflow_runs;
ALTER TABLE raw_workflow_runs_new RENAME TO raw_workflow_runs;

CREATE INDEX idx_wfruns_workflow ON raw_workflow_runs(workflow, finished_at);
CREATE INDEX idx_workflow_runs_prd ON raw_workflow_runs(prd_id);
CREATE INDEX idx_workflow_runs_task ON raw_workflow_runs(task_id);
CREATE INDEX idx_workflow_runs_activity ON raw_workflow_runs(activity_id);

-- ── research_cache ───────────────────────────────────────────────────────────
CREATE TABLE research_cache_new (
    cache_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    focus_areas TEXT,
    sources TEXT,
    findings TEXT,
    confidence_score REAL,
    triangulation_score REAL,
    activity_id INTEGER,
    prd_id TEXT,
    task_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT
);

INSERT INTO research_cache_new
    SELECT cache_id, topic, focus_areas, sources, findings,
           confidence_score, triangulation_score, activity_id, prd_id, task_id,
           created_at, expires_at
    FROM research_cache;

DROP TABLE research_cache;
ALTER TABLE research_cache_new RENAME TO research_cache;

CREATE INDEX idx_research_cache_prd ON research_cache(prd_id);
CREATE INDEX idx_research_cache_task ON research_cache(task_id);
CREATE INDEX idx_research_cache_activity ON research_cache(activity_id);

-- ── raw_research ─────────────────────────────────────────────────────────────
CREATE TABLE raw_research_new (
    research_id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT,
    findings TEXT NOT NULL,
    confidence_score REAL DEFAULT 0.5,
    trust_score REAL DEFAULT 0.5,
    validation_status TEXT DEFAULT 'pending',
    validated_by TEXT,
    validated_at TEXT,
    times_referenced INTEGER DEFAULT 0,
    success_rate REAL DEFAULT 0.5,
    activity_id INTEGER,
    prd_id TEXT,
    task_id TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    ttl_days INTEGER DEFAULT 30,
    expires_at TEXT,
    CONSTRAINT chk_confidence_range CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    CONSTRAINT chk_trust_range CHECK (trust_score >= 0.0 AND trust_score <= 1.0),
    CONSTRAINT chk_success_rate_range CHECK (success_rate >= 0.0 AND success_rate <= 1.0),
    CONSTRAINT chk_validation_status CHECK (validation_status IN ('pending', 'validated', 'rejected')),
    CONSTRAINT chk_source_type CHECK (source_type IN ('stack', 'security', 'docs', 'pattern', 'general'))
);

INSERT INTO raw_research_new
    SELECT research_id, query, query_hash, source_type, source_url, findings,
           confidence_score, trust_score, validation_status, validated_by, validated_at,
           times_referenced, success_rate, activity_id, prd_id, task_id,
           created_at, ttl_days, expires_at
    FROM raw_research;

DROP TABLE raw_research;
ALTER TABLE raw_research_new RENAME TO raw_research;

CREATE INDEX idx_raw_research_prd ON raw_research(prd_id);
CREATE INDEX idx_raw_research_task ON raw_research(task_id);
CREATE INDEX idx_raw_research_activity ON raw_research(activity_id);

PRAGMA foreign_keys = ON;
