-- Migration 059: TA0b — Add projection link column to execution_events
-- Adds _built_from_event_id to trace each execution_events row back to the
-- canonical_events record that produced it. NULL = direct-written (historical baseline).
-- Rows projected by execution_events_projection.py carry the source canonical event_id.

ALTER TABLE execution_events ADD COLUMN _built_from_event_id TEXT;
CREATE INDEX IF NOT EXISTS idx_execution_events_canonical_link
    ON execution_events(_built_from_event_id)
    WHERE _built_from_event_id IS NOT NULL;
