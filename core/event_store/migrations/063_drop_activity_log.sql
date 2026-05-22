-- Migration 063: Drop activity_log table.
--
-- Prerequisite: migration 062 must have run, which:
--   - Made activity_id nullable in all 7 child tables
--   - Replaced vw_activity_timeline and vw_guardrail_decisions
--   - Backfilled 159 activity_log rows into canonical_events
--
-- After this migration, the activity_log table and all its indexes
-- are permanently removed. canonical_events is the sole event store.

DROP INDEX IF EXISTS idx_activity_type_time;

DROP INDEX IF EXISTS idx_activity_stream;

DROP INDEX IF EXISTS idx_activity_status_severity;

DROP INDEX IF EXISTS idx_activity_anomaly;

DROP TABLE IF EXISTS activity_log;
