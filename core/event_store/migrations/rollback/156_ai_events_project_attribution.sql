-- Rollback 156: remove AI-event project attribution (reverse of
-- 156_ai_events_project_attribution.sql). A reverse migration legitimately drops
-- what its forward created; it is exempt from the forward-migration DROP-safety
-- gate. Order: indexes, then the column.
--
-- This discards whatever attribution the backfill established. That is
-- recoverable — core/telemetry/project_backfill.py re-derives it from session
-- evidence, which is not itself destroyed here.

DROP INDEX IF EXISTS idx_ace_project_event_type;
DROP INDEX IF EXISTS idx_ace_project_id;
ALTER TABLE ai_canonical_events DROP COLUMN project_id;
