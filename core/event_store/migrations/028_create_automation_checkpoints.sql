-- Migration 023: Create automation_checkpoints table
-- Fixes: Migration 021 references this table but it was never created in migrations
-- Date: 2026-05-06
-- Track: A (Data Plane)

CREATE TABLE IF NOT EXISTS automation_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,           -- e.g., "cp-run-001-100", UUID
    run_id TEXT NOT NULL,                     -- FK to automation_log
    checkpoint_name TEXT NOT NULL,            -- e.g., "processed_100_items", "stage_2_complete"
    checkpoint_data TEXT,                     -- JSON state snapshot (last item ID, batch cursor, etc.)
    created_at TEXT NOT NULL,                 -- ISO timestamp
    FOREIGN KEY (run_id) REFERENCES automation_log(run_id) ON DELETE CASCADE
);

-- Indexes for automation_checkpoints
CREATE INDEX IF NOT EXISTS idx_checkpoint_run ON automation_checkpoints(run_id);
CREATE INDEX IF NOT EXISTS idx_checkpoint_created ON automation_checkpoints(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_checkpoint_run_created ON automation_checkpoints(run_id, created_at DESC);
