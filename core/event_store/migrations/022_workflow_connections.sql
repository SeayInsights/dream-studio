-- Migration 021: Workflow Connections (Phase 3 Cross-Domain Traceability)
-- Created: 2026-05-06
-- Purpose: Add FK columns to link workflows to activity_log, PRDs, and tasks
-- Links: raw_workflow_runs + raw_workflow_nodes → activity_log + prd_documents + prd_tasks
-- Enables: Complete audit trail, cross-domain impact analysis, workflow-to-task traceability

PRAGMA foreign_keys = ON;

-- ============================================================================
-- ALTER raw_workflow_runs: Add FK columns
-- ============================================================================

-- Add activity_id FK to raw_workflow_runs
ALTER TABLE raw_workflow_runs
ADD COLUMN activity_id INTEGER;

-- Add prd_id FK to raw_workflow_runs
ALTER TABLE raw_workflow_runs
ADD COLUMN prd_id TEXT;

-- Add task_id FK to raw_workflow_runs
ALTER TABLE raw_workflow_runs
ADD COLUMN task_id TEXT;

-- ============================================================================
-- ALTER raw_workflow_nodes: Add FK columns
-- ============================================================================

-- Add activity_id FK to raw_workflow_nodes
ALTER TABLE raw_workflow_nodes
ADD COLUMN activity_id INTEGER;

-- ============================================================================
-- FOREIGN KEY CONSTRAINTS
-- ============================================================================

-- Constraints for raw_workflow_runs
CREATE TABLE raw_workflow_runs_temp AS SELECT * FROM raw_workflow_runs;

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
    prd_id TEXT,
    task_id TEXT,

    -- Foreign keys: SET NULL on delete to preserve workflow history
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE SET NULL,
    FOREIGN KEY (prd_id) REFERENCES prd_documents(prd_id) ON DELETE SET NULL,
    FOREIGN KEY (task_id) REFERENCES prd_tasks(task_id) ON DELETE SET NULL
);

INSERT INTO raw_workflow_runs
SELECT * FROM raw_workflow_runs_temp;

DROP TABLE raw_workflow_runs_temp;

-- Constraints for raw_workflow_nodes
CREATE TABLE raw_workflow_nodes_temp AS SELECT * FROM raw_workflow_nodes;

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
    activity_id INTEGER,

    -- Foreign key: SET NULL on delete to preserve node history
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE SET NULL
);

INSERT INTO raw_workflow_nodes
SELECT * FROM raw_workflow_nodes_temp;

DROP TABLE raw_workflow_nodes_temp;

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Index for querying workflow runs by PRD
CREATE INDEX IF NOT EXISTS idx_workflow_runs_prd
ON raw_workflow_runs(prd_id);

-- Index for querying workflow runs by task
CREATE INDEX IF NOT EXISTS idx_workflow_runs_task
ON raw_workflow_runs(task_id);

-- Index for querying workflow runs by activity
CREATE INDEX IF NOT EXISTS idx_workflow_runs_activity
ON raw_workflow_runs(activity_id);

-- Index for querying workflow nodes by activity
CREATE INDEX IF NOT EXISTS idx_workflow_nodes_activity
ON raw_workflow_nodes(activity_id);

-- Recreate original indexes that were lost in table rebuild
CREATE INDEX IF NOT EXISTS idx_wfnodes_runkey
ON raw_workflow_nodes(run_key);

CREATE INDEX IF NOT EXISTS idx_wfruns_workflow
ON raw_workflow_runs(workflow, finished_at);
