-- Migration 007: Document system and analyzed repos registry
--
-- ds_documents cluster: created here, dropped by migration 127
--   (moved to files.db as part of three-store architecture).
--   DDL is retained as historical reference so migration replays work;
--   migration 127 drops the cluster afterwards.
--
-- reg_analyzed_repos, reg_repo_extractions, reg_repo_research_links:
--   DDL removed from this migration (see migration 128).
--   These tables are dead (no live consumer); migration 128 drops any
--   existing instances on upgrade. Fresh installs never create them.

-- ── Document storage table ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ds_documents (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type TEXT NOT NULL,
    parent_doc_id INTEGER,
    project_id TEXT REFERENCES reg_projects(project_id),
    skill_id TEXT REFERENCES reg_skills(skill_id),
    session_id TEXT REFERENCES raw_sessions(session_id),
    title TEXT NOT NULL,
    content TEXT,
    format TEXT DEFAULT 'markdown',
    metadata TEXT,
    tags TEXT,
    keywords TEXT,
    version INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    created_by TEXT,
    updated_at TEXT,
    access_count INTEGER DEFAULT 0,
    last_accessed TEXT,
    ttl_days INTEGER,
    expires_at TEXT,
    FOREIGN KEY (parent_doc_id) REFERENCES ds_documents(doc_id)
);

-- ── FTS5 full-text search on documents ──────────────────────────────────────

CREATE VIRTUAL TABLE IF NOT EXISTS ds_documents_fts USING fts5(
    title, content, keywords, tags,
    content=ds_documents, content_rowid=doc_id
);

CREATE TRIGGER IF NOT EXISTS trg_documents_fts_ai AFTER INSERT ON ds_documents BEGIN
    INSERT INTO ds_documents_fts(rowid, title, content, keywords, tags)
    VALUES (new.doc_id, new.title, new.content, new.keywords, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS trg_documents_fts_ad AFTER DELETE ON ds_documents BEGIN
    INSERT INTO ds_documents_fts(ds_documents_fts, rowid, title, content, keywords, tags)
    VALUES ('delete', old.doc_id, old.title, old.content, old.keywords, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS trg_documents_fts_au AFTER UPDATE ON ds_documents BEGIN
    INSERT INTO ds_documents_fts(ds_documents_fts, rowid, title, content, keywords, tags)
    VALUES ('delete', old.doc_id, old.title, old.content, old.keywords, old.tags);
    INSERT INTO ds_documents_fts(rowid, title, content, keywords, tags)
    VALUES (new.doc_id, new.title, new.content, new.keywords, new.tags);
END;

-- ── Document access tracking trigger ────────────────────────────────────────

CREATE TRIGGER IF NOT EXISTS trg_documents_access_tracking AFTER UPDATE OF access_count ON ds_documents
WHEN new.access_count > old.access_count
BEGIN
    UPDATE ds_documents SET last_accessed = datetime('now') WHERE doc_id = new.doc_id;
END;

-- ── Document auto-archive trigger ───────────────────────────────────────────
-- Note: This trigger fires on UPDATE only when expires_at is checked.
-- Actual archival requires periodic background job.

CREATE TRIGGER IF NOT EXISTS trg_documents_auto_archive AFTER UPDATE OF expires_at ON ds_documents
WHEN new.expires_at IS NOT NULL AND datetime(new.expires_at) <= datetime('now')
BEGIN
    UPDATE ds_documents SET status = 'archived' WHERE doc_id = new.doc_id AND status != 'archived';
END;

-- ── Indexes on ds_documents ──────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_ds_documents_type ON ds_documents(doc_type, status);
CREATE INDEX IF NOT EXISTS idx_ds_documents_project ON ds_documents(project_id, doc_type);
CREATE INDEX IF NOT EXISTS idx_ds_documents_skill ON ds_documents(skill_id, doc_type);
CREATE INDEX IF NOT EXISTS idx_ds_documents_session ON ds_documents(session_id);
CREATE INDEX IF NOT EXISTS idx_ds_documents_created ON ds_documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ds_documents_expires ON ds_documents(expires_at);
CREATE INDEX IF NOT EXISTS idx_ds_documents_parent ON ds_documents(parent_doc_id);
