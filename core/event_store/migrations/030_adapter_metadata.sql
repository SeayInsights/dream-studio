-- Migration 030: Adapter Metadata Tables
-- Created: 2026-05-06
-- Purpose: Support AI adapter layer execution tracking and normalization metadata
-- Part of: Track C (Control Plane) - AI Adapter Layer
-- Depends on: 017_activity_log.sql (activity_log table)

-- ============================================================================
-- ADAPTER EXECUTION TRACKING
-- ============================================================================

-- Table: adapter_executions
-- Stores optional metadata about adapter normalization executions
-- Allows tracking which adapter normalized which event and performance metrics
CREATE TABLE IF NOT EXISTS adapter_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,
    adapter_type TEXT NOT NULL,  -- 'claude', 'gpt', 'default'
    normalized_at TEXT NOT NULL,  -- ISO 8601 timestamp
    execution_time_ms REAL,  -- Normalization duration in milliseconds
    metadata TEXT,  -- JSON blob with adapter-specific data (model version, prompt tokens, etc.)

    -- Foreign key to activity_log (hub table)
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE CASCADE
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Index for queries filtering by adapter type
CREATE INDEX IF NOT EXISTS idx_adapter_executions_type
ON adapter_executions(adapter_type);

-- Index for time-based queries
CREATE INDEX IF NOT EXISTS idx_adapter_executions_time
ON adapter_executions(normalized_at DESC);

-- Index for performance analysis
CREATE INDEX IF NOT EXISTS idx_adapter_executions_perf
ON adapter_executions(adapter_type, execution_time_ms);

-- Index for activity_id lookups (join performance)
CREATE INDEX IF NOT EXISTS idx_adapter_executions_activity
ON adapter_executions(activity_id);
