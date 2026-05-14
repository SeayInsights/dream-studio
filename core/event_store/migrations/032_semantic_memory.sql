-- Migration 032: Semantic memory convergence — Phase 3B schema extension
--
-- Adds columns to memory_entries for provenance tracking, lifecycle state,
-- and idempotent ingestion from multiple source systems.
-- The "source" column continues to hold memory_type (lesson|gotcha|correction|etc).

ALTER TABLE memory_entries ADD COLUMN source_type TEXT DEFAULT 'unknown';
ALTER TABLE memory_entries ADD COLUMN source_id TEXT;
ALTER TABLE memory_entries ADD COLUMN lifecycle_state TEXT DEFAULT 'ACTIVE';
ALTER TABLE memory_entries ADD COLUMN confidence REAL;
ALTER TABLE memory_entries ADD COLUMN provenance JSON;
ALTER TABLE memory_entries ADD COLUMN lineage JSON;
ALTER TABLE memory_entries ADD COLUMN relationships JSON;
ALTER TABLE memory_entries ADD COLUMN updated_at TEXT;

-- Idempotent ingestion: (source_type, source_id) uniquely identifies a memory
CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_provenance
ON memory_entries(source_type, source_id) WHERE source_id IS NOT NULL;

-- Lifecycle filtering for retrieval
CREATE INDEX IF NOT EXISTS idx_memory_lifecycle
ON memory_entries(lifecycle_state);
