-- Migration 017: Central Activity Log (Hub Table)
-- Created: 2026-05-06
-- Purpose: Foundational hub table for dream-studio's hub-and-spoke architecture
-- Links: All specialized tables (hooks, security, risks, audits) will link here via foreign keys
-- Replaces: Siloed activity tracking with unified central log

-- ============================================================================
-- CENTRAL ACTIVITY LOG
-- ============================================================================

-- Central activity log (hub table for all system events)
CREATE TABLE IF NOT EXISTS activity_log (
    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_type TEXT NOT NULL,  -- 'hook_execution', 'security_finding', 'workflow_node', 'research_completed', 'lesson_captured', 'audit_run'
    stream_id TEXT,  -- The ID of the primary entity (task_id, prd_id, workflow_run_key, etc.)
    stream_type TEXT,  -- 'task', 'prd', 'workflow', 'skill', 'session'
    event_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_data TEXT,  -- JSON blob for flexible event-specific data

    -- Foreign keys (all nullable - activities can exist independently)
    prd_id TEXT,
    task_id TEXT,
    session_id TEXT,
    workflow_run_key TEXT,
    skill_id TEXT,

    -- Status tracking
    status TEXT CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'cancelled')),
    severity TEXT CHECK(severity IN ('info', 'warning', 'error', 'critical')),
    duration_ms INTEGER,

    -- Anomaly detection
    is_anomaly BOOLEAN DEFAULT 0,
    anomaly_score REAL DEFAULT 0.0,

    -- Foreign key constraints
    FOREIGN KEY (prd_id) REFERENCES prd_documents(prd_id) ON DELETE SET NULL,
    FOREIGN KEY (task_id) REFERENCES prd_tasks(task_id) ON DELETE SET NULL,
    FOREIGN KEY (session_id) REFERENCES prd_sessions(session_id) ON DELETE SET NULL,
    FOREIGN KEY (workflow_run_key) REFERENCES raw_workflow_runs(run_key) ON DELETE SET NULL,
    FOREIGN KEY (skill_id) REFERENCES reg_skills(skill_id) ON DELETE SET NULL
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Index for queries filtering by activity type and time
CREATE INDEX IF NOT EXISTS idx_activity_type_time
ON activity_log(activity_type, event_timestamp DESC);

-- Index for stream-based queries (e.g., "show all events for task T001")
CREATE INDEX IF NOT EXISTS idx_activity_stream
ON activity_log(stream_type, stream_id, event_timestamp DESC);

-- Index for status and severity filtering
CREATE INDEX IF NOT EXISTS idx_activity_status_severity
ON activity_log(status, severity);

-- Partial index for anomaly detection queries (only indexes anomalous events)
CREATE INDEX IF NOT EXISTS idx_activity_anomaly
ON activity_log(anomaly_score DESC)
WHERE is_anomaly = 1;
