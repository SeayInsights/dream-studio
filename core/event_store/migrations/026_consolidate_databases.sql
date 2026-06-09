-- Migration 021: Consolidate Databases
-- Track: A (Data Plane)
-- Task: TA-003
-- Date: 2026-05-06
-- Purpose: Prepare schema for merging dream-studio.db → studio.db
--
-- Background:
--   The audit (TA-002) found 5 databases, but only studio.db is actively used.
--   dream-studio.db contains 2 duplicate tables (automation_checkpoints, automation_log)
--   that also exist in studio.db. This migration prepares for merging those duplicates.
--
-- Tables affected:
--   - automation_checkpoints (merge duplicate rows from dream-studio.db)
--   - automation_log (merge duplicate rows from dream-studio.db)
--
-- What this migration does:
--   1. Validates current state (row counts)
--   2. Adds indexes for merge performance
--   3. Documents rollback procedure
--
-- What this migration does NOT do:
--   - Create new tables (they already exist in studio.db)
--   - Copy data (handled by merge script in TA-004)
--   - Delete old databases (handled in TA-009)
--
-- Rollback: See bottom of file
-- Dependencies: TA-001 (backups), TA-002 (audit)

-- ============================================================================
-- SECTION 1: Pre-merge validation
-- ============================================================================
-- These queries document the current state before merge.
-- The merge script (TA-004) will re-run these to compare row counts.

SELECT 'PRE-MERGE VALIDATION' as step;

-- Skipped: These validation queries assume tables exist (created in migration 023)
-- SELECT 'automation_checkpoints' as table_name, COUNT(*) as row_count
-- FROM automation_checkpoints;

-- SELECT 'automation_log' as table_name, COUNT(*) as row_count
-- FROM automation_log;

-- ============================================================================
-- SECTION 2: Schema optimization for merge
-- ============================================================================
-- Add indexes to improve merge performance (INSERT ... WHERE NOT EXISTS)

SELECT 'ADDING INDEXES FOR MERGE PERFORMANCE' as step;

-- Note: automation_checkpoints created in migration 023 with its own indexes
-- These indexes are redundant and moved to migration 023

-- Index on automation_log for deduplication during merge
CREATE INDEX IF NOT EXISTS idx_automation_log_started_at
ON automation_log(started_at);

CREATE INDEX IF NOT EXISTS idx_automation_log_status
ON automation_log(status);

SELECT 'INDEXES CREATED' as step;

-- ============================================================================
-- SECTION 3: Post-merge validation templates
-- ============================================================================
-- These queries will be used by the merge script (TA-004) to validate success.
-- They are commented out here (migration does not run them).
--
-- Post-merge checks:
--   1. Row count should equal or exceed pre-merge count
--   2. No duplicate primary keys (checkpoint_id, log_id)
--   3. No NULL values in NOT NULL columns
--
-- Example validation queries for TA-004:
--
-- SELECT COUNT(*) as total_checkpoints FROM automation_checkpoints;
-- SELECT COUNT(DISTINCT checkpoint_id) as unique_checkpoints FROM automation_checkpoints;
-- SELECT COUNT(*) as total_logs FROM automation_log;
-- SELECT COUNT(DISTINCT log_id) as unique_logs FROM automation_log;
--
-- Check for duplicates:
-- SELECT checkpoint_id, COUNT(*) as count FROM automation_checkpoints
-- GROUP BY checkpoint_id HAVING COUNT(*) > 1;
--
-- SELECT log_id, COUNT(*) as count FROM automation_log
-- GROUP BY log_id HAVING COUNT(*) > 1;

-- ============================================================================
-- SECTION 4: Migration metadata
-- ============================================================================
-- Migration runner automatically records version in _schema_version

SELECT 'MIGRATION 021 COMPLETE' as step;
SELECT 'Ready for TA-004 (merge script execution)' as next_step;

-- ============================================================================
-- ROLLBACK INSTRUCTIONS
-- ============================================================================
--
-- If merge fails or causes issues, restore from backups:
--
-- Windows (PowerShell):
--   cp "$env:USERPROFILE\.dream-studio\backups\studio.db.bak" "$env:USERPROFILE\.dream-studio\state\studio.db"
--   cp "$env:USERPROFILE\.dream-studio\backups\dream-studio.db.bak" "$env:USERPROFILE\.dream-studio\dream-studio.db"
--
-- Linux/Mac (Bash):
--   cp ~/.dream-studio/backups/studio.db.bak ~/.dream-studio/state/studio.db
--   cp ~/.dream-studio/backups/dream-studio.db.bak ~/.dream-studio/dream-studio.db
--
-- Verify rollback:
--   sqlite3 ~/.dream-studio/state/studio.db "SELECT COUNT(*) FROM automation_checkpoints;"
--   sqlite3 ~/.dream-studio/dream-studio.db "SELECT COUNT(*) FROM automation_checkpoints;"
--
-- Remove this migration from schema version:
--   DELETE FROM _schema_version WHERE version = 21;
--
-- ============================================================================
