-- Migration 018: Hook Execution Tracking (Spoke Tables)
-- Created: 2026-05-06
-- Purpose: Track hook executions and their findings, linked to activity_log hub
-- Links: activity_log (hub) → hook_executions + hook_findings (spokes)
-- Enables: Drill-down into hook performance, failure analysis, and finding resolution

-- ============================================================================
-- HOOK EXECUTIONS
-- ============================================================================

-- Tracks individual hook execution attempts with timing and resource metrics
CREATE TABLE IF NOT EXISTS hook_executions (
    hook_exec_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,  -- FK to activity_log (hub)
    hook_name TEXT NOT NULL,  -- 'on_pulse', 'on_commit', 'on_pr_open', etc.
    hook_type TEXT,  -- 'pre-commit', 'post-commit', 'on-event', etc.
    trigger_context TEXT,  -- JSON blob: what triggered the hook (commit SHA, event data, etc.)

    -- Execution timing
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    duration_ms INTEGER,

    -- Execution results
    exit_code INTEGER,
    status TEXT CHECK(status IN ('pending', 'running', 'success', 'failed', 'timeout')),
    output TEXT,
    error_message TEXT,

    -- Resource usage
    cpu_time_ms INTEGER,
    memory_mb REAL,

    -- Foreign key: cascade delete when activity is removed
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE CASCADE
);

-- ============================================================================
-- HOOK FINDINGS
-- ============================================================================

-- Tracks issues discovered by hooks (lints, test failures, security checks, etc.)
CREATE TABLE IF NOT EXISTS hook_findings (
    finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,  -- FK to activity_log (hub)
    hook_exec_id INTEGER NOT NULL,  -- FK to hook_executions

    finding_type TEXT NOT NULL,  -- 'lint_error', 'test_failure', 'security_check', 'performance_warning', etc.
    severity TEXT CHECK(severity IN ('info', 'warning', 'error', 'critical')),
    message TEXT NOT NULL,
    context TEXT,  -- JSON blob: file path, line number, rule ID, etc.
    recommendation TEXT,

    -- Status tracking
    status TEXT CHECK(status IN ('open', 'acknowledged', 'resolved', 'wont_fix')),
    resolved_at DATETIME,
    resolution_notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys: cascade delete when activity or execution is removed
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE CASCADE,
    FOREIGN KEY (hook_exec_id) REFERENCES hook_executions(hook_exec_id) ON DELETE CASCADE
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Hook Executions Indexes

-- Index for queries filtering by activity (e.g., "show all hooks for task T001")
CREATE INDEX IF NOT EXISTS idx_hook_exec_activity
ON hook_executions(activity_id);

-- Index for queries filtering by hook name and status (e.g., "show failed on_commit hooks")
CREATE INDEX IF NOT EXISTS idx_hook_exec_name_status
ON hook_executions(hook_name, status);

-- Index for finding slow hooks (sorted by duration, descending)
CREATE INDEX IF NOT EXISTS idx_hook_exec_duration
ON hook_executions(duration_ms DESC);

-- Index for time-series queries (most recent executions first)
CREATE INDEX IF NOT EXISTS idx_hook_exec_started
ON hook_executions(started_at DESC);

-- Hook Findings Indexes

-- Index for queries filtering by activity (e.g., "show all findings for task T001")
CREATE INDEX IF NOT EXISTS idx_hook_finding_activity
ON hook_findings(activity_id);

-- Index for queries filtering by execution (e.g., "show findings from this hook run")
CREATE INDEX IF NOT EXISTS idx_hook_finding_exec
ON hook_findings(hook_exec_id);

-- Index for queries filtering by status and severity (e.g., "show open critical findings")
CREATE INDEX IF NOT EXISTS idx_hook_finding_status_severity
ON hook_findings(status, severity);
