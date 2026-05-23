-- Migration 071: Remove stale activity_log FK from workflow tables
--
-- Background: activity_log was retired in TA0c and dropped in migration 063.
-- Migration 022 added FOREIGN KEY (activity_id) REFERENCES activity_log(...)
-- to raw_workflow_runs and raw_workflow_nodes. These FKs were not removed in
-- migration 062 (which only nullified the column, not the constraint). With
-- PRAGMA foreign_keys = ON now enforced after migrations, any INSERT into
-- these tables fails with "no such table: main.activity_log" even for NULL
-- values (SQLite validates referenced-table existence at enforcement time).
--
-- SQLite limitation: ALTER TABLE RENAME recompiles all views; broken views
-- (e.g. vw_activity_timeline that references canonical_events) abort the
-- rename. Workaround: use backup table + DROP + CREATE + INSERT + DROP backup,
-- avoiding RENAME entirely.
--
-- prd_documents and prd_tasks still exist; their FKs are preserved.

PRAGMA foreign_keys = OFF;

-- ── raw_workflow_runs ────────────────────────────────────────────────────────

CREATE TABLE raw_workflow_runs_bak071 AS SELECT * FROM raw_workflow_runs;

DROP TABLE raw_workflow_runs;

CREATE TABLE raw_workflow_runs (
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
    prd_id TEXT REFERENCES prd_documents(prd_id) ON DELETE SET NULL,
    task_id TEXT REFERENCES prd_tasks(task_id) ON DELETE SET NULL
);

INSERT INTO raw_workflow_runs SELECT * FROM raw_workflow_runs_bak071;

DROP TABLE raw_workflow_runs_bak071;

CREATE INDEX IF NOT EXISTS idx_wfruns_workflow ON raw_workflow_runs(workflow, finished_at);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_prd ON raw_workflow_runs(prd_id);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_task ON raw_workflow_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_activity ON raw_workflow_runs(activity_id);

-- ── raw_workflow_nodes ───────────────────────────────────────────────────────

CREATE TABLE raw_workflow_nodes_bak071 AS SELECT * FROM raw_workflow_nodes;

DROP TABLE raw_workflow_nodes;

CREATE TABLE raw_workflow_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key TEXT NOT NULL REFERENCES raw_workflow_runs(run_key),
    node_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    duration_s REAL,
    output TEXT,
    activity_id INTEGER
);

INSERT INTO raw_workflow_nodes SELECT * FROM raw_workflow_nodes_bak071;

DROP TABLE raw_workflow_nodes_bak071;

CREATE INDEX IF NOT EXISTS idx_wfnodes_runkey ON raw_workflow_nodes(run_key);
CREATE INDEX IF NOT EXISTS idx_workflow_nodes_activity ON raw_workflow_nodes(activity_id);

PRAGMA foreign_keys = ON;
