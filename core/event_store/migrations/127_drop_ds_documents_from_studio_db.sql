-- Migration 127: Drop ds_documents cluster from studio.db
--
-- Three-store architecture fix: ds_documents (and its FTS shadow tables and
-- triggers) were created in studio.db by migration 007.  They belong in
-- files.db (the document/artifact store), not in studio.db (the canonical
-- event authority).
--
-- Pre-condition: the data migration in
--   interfaces/cli/migrate_docstore_to_files_db.py
-- must be run BEFORE this migration is applied.  That script copies all
-- ds_documents rows from studio.db into files.db and rebuilds the FTS index.
--
-- Migration class: migration-class (DROP TABLE on a non-empty table).
-- Gate: matrix-watch required before merge.
--
-- Drop order: triggers → FTS virtual table (auto-drops shadow tables) →
--   main table.  The FTS virtual table must be dropped BEFORE any attempt to
--   drop its shadow tables individually; dropping shadow tables first causes
--   SQLite's vtable constructor to fail when it tries to re-open the
--   now-incomplete FTS state.

-- ── Triggers ─────────────────────────────────────────────────────────────────
DROP TRIGGER IF EXISTS trg_documents_fts_ai;
DROP TRIGGER IF EXISTS trg_documents_fts_ad;
DROP TRIGGER IF EXISTS trg_documents_fts_au;
DROP TRIGGER IF EXISTS trg_documents_access_tracking;
DROP TRIGGER IF EXISTS trg_documents_auto_archive;

-- ── FTS5 virtual table (dropping this auto-removes all shadow tables) ─────────
DROP TABLE IF EXISTS ds_documents_fts;

-- ── Indexes on ds_documents ──────────────────────────────────────────────────
DROP INDEX IF EXISTS idx_ds_documents_type;
DROP INDEX IF EXISTS idx_ds_documents_project;
DROP INDEX IF EXISTS idx_ds_documents_skill;
DROP INDEX IF EXISTS idx_ds_documents_session;
DROP INDEX IF EXISTS idx_ds_documents_created;
DROP INDEX IF EXISTS idx_ds_documents_expires;
DROP INDEX IF EXISTS idx_ds_documents_parent;
DROP INDEX IF EXISTS idx_ds_documents_source_path;

-- ── Main table ───────────────────────────────────────────────────────────────
-- reg_repo_extractions.document_id FK is a soft reference (no DEFERRABLE
-- constraint enforced at the DB level as of migration 007); dropping
-- ds_documents does not cascade any FK violation.
DROP TABLE IF EXISTS ds_documents;
