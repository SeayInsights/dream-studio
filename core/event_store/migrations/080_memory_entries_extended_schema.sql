-- Migration 080: Extend memory_entries with columns expected by MemoryStore.
--
-- Chain 7 (Memory Loop) — 18.4.4
-- core/memory/store.py was written for an extended schema that was never
-- materialized in the migrations. These columns are required for
-- run_all_ingestion() (GotchaIngestionConsumer, LessonIngestionConsumer, etc.)
-- to write rows into memory_entries via MemoryStore.upsert_by_provenance().
--
-- All added columns are nullable or have safe defaults so existing rows are
-- unaffected.

ALTER TABLE memory_entries ADD COLUMN source_type TEXT;
ALTER TABLE memory_entries ADD COLUMN source_id TEXT;
ALTER TABLE memory_entries ADD COLUMN lifecycle_state TEXT DEFAULT 'ACTIVE';
ALTER TABLE memory_entries ADD COLUMN confidence REAL;
ALTER TABLE memory_entries ADD COLUMN updated_at TEXT;
ALTER TABLE memory_entries ADD COLUMN provenance JSON;
ALTER TABLE memory_entries ADD COLUMN lineage JSON;
ALTER TABLE memory_entries ADD COLUMN relationships JSON;

-- Index for dedup lookup by provenance (source_type + source_id uniqueness check)
CREATE INDEX IF NOT EXISTS idx_memory_provenance
ON memory_entries(source_type, source_id)
WHERE source_type IS NOT NULL AND source_id IS NOT NULL;
