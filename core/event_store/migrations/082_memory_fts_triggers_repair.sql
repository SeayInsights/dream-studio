-- Migration 082: Defensive restoration of memory_entries FTS sync triggers.
--
-- Background:
--   Migration 079 declared memory_entries_fts_{insert,update,delete} to keep
--   memory_fts in sync with memory_entries. The triggers are absent from at
--   least one live DB (verified during 18.4.5-followup-2 pre-flight). Root cause
--   is indeterminate after investigation: triggers were created by migration 079
--   on a fresh DB (confirmed) but dropped on the live DB by an unknown mechanism
--   (possibly a side effect of the original migration 081 RENAME with
--   PRAGMA legacy_alter_table, or a schema-write path during testing).
--
-- Fix strategy:
--   CREATE TRIGGER IF NOT EXISTS is idempotent — restores the triggers on any
--   DB where they are absent, and is a safe no-op on any DB where they exist.
--   Trigger DDL is copied verbatim from migration 079 to ensure consistency.
--
-- No data repair included: pre-flight confirmed memory_entries (1,488 rows) and
-- memory_fts (1,488 rows) are already in sync, so no backfill is needed.
-- If future runs encounter divergence, migration 079's backfill pattern can be
-- applied manually via `ds memory dedup-orphans` or a dedicated repair migration.

CREATE TRIGGER IF NOT EXISTS memory_entries_fts_insert
AFTER INSERT ON memory_entries
BEGIN
    INSERT INTO memory_fts(memory_id, content, category, tags)
    VALUES (new.memory_id, new.content, new.category, COALESCE(new.tags, ''));
END;

CREATE TRIGGER IF NOT EXISTS memory_entries_fts_update
AFTER UPDATE ON memory_entries
BEGIN
    DELETE FROM memory_fts WHERE memory_id = old.memory_id;
    INSERT INTO memory_fts(memory_id, content, category, tags)
    VALUES (new.memory_id, new.content, new.category, COALESCE(new.tags, ''));
END;

CREATE TRIGGER IF NOT EXISTS memory_entries_fts_delete
AFTER DELETE ON memory_entries
BEGIN
    DELETE FROM memory_fts WHERE memory_id = old.memory_id;
END;
