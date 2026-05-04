-- Migration 007: Document system and analyzed repos registry

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

-- ── Analyzed repositories registry ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS reg_analyzed_repos (
    repo_id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_url TEXT UNIQUE NOT NULL,
    repo_name TEXT NOT NULL,
    description TEXT,
    first_analyzed TEXT,
    last_analyzed TEXT,
    last_commit_sha TEXT,
    analysis_count INTEGER DEFAULT 0,
    stars INTEGER,
    language TEXT,
    framework TEXT,
    trust_score REAL DEFAULT 0.8,
    patterns_extracted INTEGER DEFAULT 0,
    building_blocks_extracted INTEGER DEFAULT 0,
    research_queries_count INTEGER DEFAULT 0,
    validation_success_rate REAL,
    check_for_updates INTEGER DEFAULT 1,
    last_update_check TEXT,
    status TEXT DEFAULT 'active'
);

-- ── Repository extractions (patterns, building blocks, techniques) ──────────

CREATE TABLE IF NOT EXISTS reg_repo_extractions (
    extraction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL REFERENCES reg_analyzed_repos(repo_id),
    extraction_type TEXT NOT NULL,
    title TEXT,
    file_path TEXT,
    commit_sha TEXT,
    code_sample TEXT,
    description TEXT,
    document_id INTEGER REFERENCES ds_documents(doc_id),
    times_used INTEGER DEFAULT 0,
    effectiveness_score REAL,
    extracted_at TEXT
);

-- ── Repository to research links (future-proofing for Wave 1) ───────────────

CREATE TABLE IF NOT EXISTS reg_repo_research_links (
    link_id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL REFERENCES reg_analyzed_repos(repo_id),
    research_id INTEGER NOT NULL,
    relevance_score REAL,
    findings_from_repo TEXT,
    created_at TEXT
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

-- ── Indexes on reg_analyzed_repos ────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_repos_framework ON reg_analyzed_repos(framework, status);
CREATE INDEX IF NOT EXISTS idx_repos_trust ON reg_analyzed_repos(trust_score DESC);
CREATE INDEX IF NOT EXISTS idx_repos_language ON reg_analyzed_repos(language, status);
CREATE INDEX IF NOT EXISTS idx_repos_last_analyzed ON reg_analyzed_repos(last_analyzed);

-- ── Indexes on reg_repo_extractions ──────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_repo_extractions_repo ON reg_repo_extractions(repo_id);
CREATE INDEX IF NOT EXISTS idx_repo_extractions_type ON reg_repo_extractions(extraction_type);
CREATE INDEX IF NOT EXISTS idx_repo_extractions_document ON reg_repo_extractions(document_id);
CREATE INDEX IF NOT EXISTS idx_repo_extractions_effectiveness ON reg_repo_extractions(effectiveness_score DESC);

-- ── Indexes on reg_repo_research_links ───────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_repo_research_repo ON reg_repo_research_links(repo_id);
CREATE INDEX IF NOT EXISTS idx_repo_research_research ON reg_repo_research_links(research_id);
CREATE INDEX IF NOT EXISTS idx_repo_research_relevance ON reg_repo_research_links(relevance_score DESC);
