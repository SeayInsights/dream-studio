"""ds_documents schema (DDL) and connection helpers for the document store.

ds_documents lives in files.db (the three-store document/artifact store),
NOT in studio.db (the canonical event authority). All reads and writes go
through connect_files() / files_db_path() from core.files.store.

WO-GF-CORE-DATA-split: split from core/storage/document_store.py into
document_store_{schema,crud}.py; core/storage/document_store.py is now a
thin facade re-exporting the public API.
"""

from __future__ import annotations
import logging
import sqlite3
from contextlib import contextmanager

from core.files.store import connect_files, ensure_files_schema
from core.ontology.lifecycles import DocumentLifecycle, to_db_value

logger = logging.getLogger("core.storage.document_store")

_ACTIVE = to_db_value(DocumentLifecycle.ACTIVE)
_ARCHIVED = to_db_value(DocumentLifecycle.ARCHIVED)

# ---------------------------------------------------------------------------
# DDL for ds_documents in files.db
# ---------------------------------------------------------------------------

_DOCUMENTS_DDL = """
CREATE TABLE IF NOT EXISTS ds_documents (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type TEXT NOT NULL,
    parent_doc_id INTEGER,
    project_id TEXT,
    skill_id TEXT,
    session_id TEXT,
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
    source_path TEXT,
    FOREIGN KEY (parent_doc_id) REFERENCES ds_documents(doc_id)
);

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

CREATE TRIGGER IF NOT EXISTS trg_documents_access_tracking
    AFTER UPDATE OF access_count ON ds_documents
    WHEN new.access_count > old.access_count
BEGIN
    UPDATE ds_documents SET last_accessed = datetime('now') WHERE doc_id = new.doc_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_documents_auto_archive
    AFTER UPDATE OF expires_at ON ds_documents
    WHEN new.expires_at IS NOT NULL AND datetime(new.expires_at) <= datetime('now')
BEGIN
    UPDATE ds_documents
    SET status = 'archived'
    WHERE doc_id = new.doc_id AND status != 'archived';
END;

CREATE INDEX IF NOT EXISTS idx_ds_documents_type ON ds_documents(doc_type, status);
CREATE INDEX IF NOT EXISTS idx_ds_documents_project ON ds_documents(project_id, doc_type);
CREATE INDEX IF NOT EXISTS idx_ds_documents_skill ON ds_documents(skill_id, doc_type);
CREATE INDEX IF NOT EXISTS idx_ds_documents_session ON ds_documents(session_id);
CREATE INDEX IF NOT EXISTS idx_ds_documents_created ON ds_documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ds_documents_expires ON ds_documents(expires_at);
CREATE INDEX IF NOT EXISTS idx_ds_documents_parent ON ds_documents(parent_doc_id);
CREATE INDEX IF NOT EXISTS idx_ds_documents_source_path ON ds_documents(source_path);
"""


def ensure_documents_schema(conn: sqlite3.Connection) -> None:
    """Idempotently create ds_documents + FTS schema in the given connection.

    Uses executescript() which correctly handles multi-statement DDL including
    triggers with embedded semicolons in their BEGIN...END bodies.
    executescript() issues an implicit COMMIT before running, which is fine for
    DDL-only calls.
    """
    conn.executescript(_DOCUMENTS_DDL)


@contextmanager
def _docs_connection():
    """Open a read connection to files.db with ds_documents schema ensured.

    Always resolves the path via connect_files() → files_db_path(); tests
    isolate by monkeypatching files_db_path (see the _isolate_files_db fixture),
    so no path parameter is threaded through DocumentStore's public API.
    """
    conn = connect_files()
    try:
        ensure_files_schema(conn)
        ensure_documents_schema(conn)
        yield conn
    finally:
        conn.close()


@contextmanager
def _docs_transaction():
    """Open a write transaction on files.db with ds_documents schema ensured.

    Path resolution and test isolation follow the same rule as
    _docs_connection(): connect_files() → files_db_path(), monkeypatched in tests.
    """
    conn = connect_files()
    try:
        ensure_files_schema(conn)
        ensure_documents_schema(conn)
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
