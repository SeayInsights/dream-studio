-- Migration 079: intelligence_surfaced_at field + FTS sync triggers for memory_entries.
--
-- Chain 7 (Memory Loop) — 18.4.4
--
-- Part A: Dedup field
--   intelligence_surfaced_at stamps when on-context-inject last surfaced an entry
--   in the current session so the same entry is not re-injected.
--
-- Part B: FTS sync triggers
--   memory_fts is a contentless FTS5 table (no content= backing). Without triggers,
--   INSERTs into memory_entries do not appear in FTS queries. These triggers keep
--   memory_fts in sync so the on-context-inject hook's FTS search works correctly
--   after ds memory ingest populates memory_entries.

-- A: dedup column
ALTER TABLE memory_entries
ADD COLUMN intelligence_surfaced_at TEXT;

-- Index for efficient dedup lookup within a session.
CREATE INDEX IF NOT EXISTS idx_memory_intelligence_surfaced
ON memory_entries(intelligence_surfaced_at)
WHERE intelligence_surfaced_at IS NOT NULL;

-- B: FTS sync triggers (contentless FTS5 — must manage index manually)

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

-- Backfill: sync any existing rows into the FTS index (safe no-op if memory_entries is empty).
INSERT INTO memory_fts(memory_id, content, category, tags)
SELECT memory_id, content, category, COALESCE(tags, '')
FROM memory_entries
WHERE memory_id NOT IN (SELECT memory_id FROM memory_fts);
