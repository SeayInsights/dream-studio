-- Migration 052: Add invocation_mode column to canonical_events.
-- canonical_events is created lazily by the ingestor (_write_to_sqlite), not by migrations.
-- The ingestor's own CREATE TABLE already includes invocation_mode for new databases.
-- This ALTER TABLE adds the column to existing databases that were created before Slice 6c.
-- run_migrations safe-skips 'no such table: canonical_events' and 'duplicate column name'.

ALTER TABLE canonical_events ADD COLUMN invocation_mode TEXT;
