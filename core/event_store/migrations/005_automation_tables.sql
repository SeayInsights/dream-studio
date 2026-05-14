-- Migration 005: Create automation tracking tables
-- Date: 2026-05-06
-- Purpose: Create tables for tracking long-running automation scripts
-- Note: These tables were present in production DB but missing from migrations,
--       causing failures when migrations run from scratch (e.g., in tests)

CREATE TABLE IF NOT EXISTS automation_log (
    run_id TEXT PRIMARY KEY,                  -- e.g., "run-2026-05-05-001", UUID
    script_name TEXT NOT NULL,                -- Script identifier (e.g., "security_scan", "data_pipeline")
    started_at TEXT NOT NULL,                 -- ISO timestamp when run started
    completed_at TEXT,                        -- ISO timestamp when run finished
    status TEXT NOT NULL,                     -- "running", "completed", "failed", "cancelled"
    items_processed INTEGER DEFAULT 0,        -- Progress counter
    items_total INTEGER,                      -- Total items to process (if known)
    error_message TEXT,                       -- Error details for failed runs
    retry_count INTEGER DEFAULT 0             -- Number of retry attempts
);

-- Indexes for automation_log (used by migration 021)
CREATE INDEX IF NOT EXISTS idx_automation_log_started_at
ON automation_log(started_at);

CREATE INDEX IF NOT EXISTS idx_automation_log_status
ON automation_log(status);
