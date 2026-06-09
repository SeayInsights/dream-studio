-- Slice 5d: add source_path to ds_documents for idempotent memory ingest.
-- run_migrations silently skips "duplicate column name" and "no such table: ds_documents" errors,
-- so this is safe to replay and safe on partial test DBs that predate migration 007.
ALTER TABLE ds_documents ADD COLUMN source_path TEXT;
CREATE INDEX IF NOT EXISTS idx_ds_documents_source_path ON ds_documents(source_path);
