-- Migration 033: FTS5 retrieval index for memory_entries
--
-- Standalone FTS5 table (no content= sync). Managed by FTS5MemoryRetriever.
-- This is a PROJECTION (rebuildable) index, not authoritative data.

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    memory_id UNINDEXED,
    content,
    category,
    tags
);
