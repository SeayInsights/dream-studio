"""Universal CRUD API for the document store (ds_documents table).

ds_documents lives in files.db (the three-store document/artifact store),
NOT in studio.db (the canonical event authority).  All reads and writes go
through connect_files() / files_db_path() from core.files.store.
"""

from __future__ import annotations
import json
import logging
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.files.store import connect_files, ensure_files_schema
from canonical.events.envelope import CanonicalEventEnvelope
from canonical.events.types import EventType as CanonicalEventType
from emitters.shared.spool_writer import write_envelopes
from core.ontology.lifecycles import (
    LIFECYCLE_CATALOG,
    DocumentLifecycle,
    to_db_value,
)

logger = logging.getLogger(__name__)

_ACTIVE = to_db_value(DocumentLifecycle.ACTIVE)
_ARCHIVED = to_db_value(DocumentLifecycle.ARCHIVED)

# Security scanning (Wave 4)
try:
    from guardrails.scanners.giskard_scanner import scan_llm_output

    _SECURITY_ENABLED = True
except ImportError:
    _SECURITY_ENABLED = False

    def scan_llm_output(output: str, context: dict) -> dict:
        """Fallback stub if security module not available."""
        return {"safe": True, "vulnerabilities": [], "risk_score": 0.0}


_NOW = lambda: datetime.now(UTC).isoformat()

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
def _docs_connection(db_path: Path | None = None):
    """Open a read connection to files.db with ds_documents schema ensured."""
    conn = connect_files(db_path)
    try:
        ensure_files_schema(conn)
        ensure_documents_schema(conn)
        yield conn
    finally:
        conn.close()


@contextmanager
def _docs_transaction(db_path: Path | None = None):
    """Open a write transaction on files.db with ds_documents schema ensured."""
    conn = connect_files(db_path)
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


class DocumentStore:
    """Universal CRUD interface for ds_documents table with FTS5 search.

    The table lives in files.db (the three-store document/artifact store),
    not in studio.db.  Canonical events (DOCUMENT_CREATED, DOCUMENT_UPDATED,
    DOCUMENT_ARCHIVED) are still emitted via the spool pipeline so the event
    spine remains intact.
    """

    @staticmethod
    def create(
        doc_type: str,
        title: str,
        content: str,
        *,
        project_id: str | None = None,
        skill_id: str | None = None,
        session_id: str | None = None,
        format: str = "markdown",
        metadata: dict | None = None,
        tags: list | None = None,
        keywords: str | None = None,
        ttl_days: int | None = None,
        db_path: Path | None = None,
    ) -> int:
        """
        Create a new document and return its doc_id.

        Args:
            doc_type: Type of document (e.g., 'spec', 'plan', 'lesson', 'gotcha')
            title: Document title
            content: Document content
            project_id: Optional project reference
            skill_id: Optional skill reference
            session_id: Optional session reference
            format: Content format ('markdown', 'yaml', 'json', 'text')
            metadata: Optional metadata dict (will be JSON-encoded)
            tags: Optional list of tags (will be JSON-encoded)
            keywords: Optional space-separated keywords for FTS5
            ttl_days: Optional time-to-live in days (sets expires_at)
            db_path: Override files.db path (for testing)

        Returns:
            doc_id of the newly created document

        Raises:
            sqlite3.Error: If database operation fails
        """
        created_at = _NOW()
        expires_at = None

        if ttl_days is not None:
            expires_dt = datetime.now(UTC) + timedelta(days=ttl_days)
            expires_at = expires_dt.isoformat()

        # Security scan before storage (Wave 4)
        scan_result = scan_llm_output(content, {"doc_type": doc_type, "title": title})

        # Merge scan results into metadata
        if metadata is None:
            metadata = {}
        metadata["security_scan"] = {
            "scanned_at": created_at,
            "safe": scan_result["safe"],
            "risk_score": scan_result["risk_score"],
            "vulnerability_count": len(scan_result.get("vulnerabilities", [])),
        }

        # Log high-risk documents
        if scan_result["risk_score"] > 0.7:
            print(
                f"⚠️  HIGH RISK document detected: {title} (risk: {scan_result['risk_score']:.2f})"
            )
            for vuln in scan_result.get("vulnerabilities", [])[:3]:
                print(f"   - {vuln.get('type', 'Unknown')}: {vuln.get('description', 'N/A')}")

        metadata_json = json.dumps(metadata) if metadata is not None else None
        tags_json = json.dumps(tags) if tags is not None else None

        with _docs_transaction(db_path) as c:
            cursor = c.execute(
                """INSERT INTO ds_documents
                   (doc_type, title, content, project_id, skill_id, session_id,
                    format, metadata, tags, keywords, version, status,
                    created_at, updated_at, access_count, ttl_days, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, NULL, 0, ?, ?)""",
                (
                    doc_type,
                    title,
                    content,
                    project_id,
                    skill_id,
                    session_id,
                    format,
                    metadata_json,
                    tags_json,
                    keywords,
                    _ACTIVE,
                    created_at,
                    ttl_days,
                    expires_at,
                ),
            )
            doc_id = cursor.lastrowid

        # Emit event AFTER commit (document is durably stored) — via spool (Slice 3)
        _envelope = CanonicalEventEnvelope(
            event_type=CanonicalEventType.DOCUMENT_CREATED.value,
            session_id=None,
            payload={
                "doc_id": doc_id,
                "doc_type": doc_type,
                "title": title,
                "format": format,
                "project_id": project_id,
                "skill_id": skill_id,
            },
            confidence="unavailable",
            project_id=None,
        )
        try:
            write_envelopes([_envelope])
        except Exception:
            # spool write failure means the event will not reach SQLite;
            # the calling operation must abort to preserve audit/consistency invariants.
            raise RuntimeError(
                f"Event emission failed for DOCUMENT_CREATED (doc_id={doc_id}). "
                f"Aborting document creation to prevent audit gap."
            )

        return doc_id

    @staticmethod
    def read(doc_id: int, *, db_path: Path | None = None) -> dict | None:
        """
        Read a document by ID and increment access_count.

        Args:
            doc_id: Document ID to retrieve
            db_path: Override files.db path (for testing)

        Returns:
            Complete document record as dict, or None if not found

        Note:
            Automatically increments access_count and updates last_accessed
        """
        with _docs_transaction(db_path) as c:
            # Increment access count
            c.execute(
                "UPDATE ds_documents SET access_count = access_count + 1 WHERE doc_id = ?",
                (doc_id,),
            )

            # Fetch the document
            row = c.execute("SELECT * FROM ds_documents WHERE doc_id = ?", (doc_id,)).fetchone()

            if not row:
                return None

            # Convert row to dict
            doc = dict(row)

            # Deserialize JSON fields
            if doc.get("metadata"):
                try:
                    doc["metadata"] = json.loads(doc["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass

            if doc.get("tags"):
                try:
                    doc["tags"] = json.loads(doc["tags"])
                except (json.JSONDecodeError, TypeError):
                    pass

            return doc

    @staticmethod
    def search(
        query: str,
        doc_type: str | None = None,
        limit: int = 50,
        *,
        db_path: Path | None = None,
    ) -> list[dict]:
        """
        Search documents using FTS5 full-text search.

        Args:
            query: FTS5 search query (searches title, content, keywords, tags)
            doc_type: Optional filter by document type
            limit: Maximum number of results (default 50)
            db_path: Override files.db path (for testing)

        Returns:
            List of matching document dicts, sorted by relevance

        Note:
            Uses FTS5 MATCH syntax. Simple keywords work, but you can also use
            advanced FTS5 operators like AND, OR, NOT, "phrase", etc.
        """
        with _docs_connection(db_path) as c:
            if doc_type:
                rows = c.execute(
                    """SELECT d.* FROM ds_documents d
                       INNER JOIN ds_documents_fts f ON d.doc_id = f.rowid
                       WHERE ds_documents_fts MATCH ? AND d.doc_type = ?
                       LIMIT ?""",
                    (query, doc_type, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    """SELECT d.* FROM ds_documents d
                       INNER JOIN ds_documents_fts f ON d.doc_id = f.rowid
                       WHERE ds_documents_fts MATCH ?
                       LIMIT ?""",
                    (query, limit),
                ).fetchall()

            results = []
            for row in rows:
                doc = dict(row)

                # Deserialize JSON fields
                if doc.get("metadata"):
                    try:
                        doc["metadata"] = json.loads(doc["metadata"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                if doc.get("tags"):
                    try:
                        doc["tags"] = json.loads(doc["tags"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                results.append(doc)

            return results

    @staticmethod
    def update(doc_id: int, _db_path: Path | None = None, **fields: Any) -> bool:
        """
        Update specified fields of a document.

        Args:
            doc_id: Document ID to update
            _db_path: Override files.db path (for testing)
            **fields: Field names and values to update

        Returns:
            True if successful, False if document not found

        Note:
            Automatically sets updated_at to current timestamp.
            Metadata and tags should be passed as dicts/lists (will be JSON-encoded).

        Example:
            DocumentStore.update(123, title="New Title", status=_ARCHIVED)
            DocumentStore.update(456, metadata={"version": "2.0"}, tags=["updated"])
        """
        if not fields:
            return False

        if "status" in fields:
            new_status = fields["status"]
            if not LIFECYCLE_CATALOG.validate_state("artifact", new_status):
                logger.warning("Unrecognized document status: %s", new_status)

        # JSON-encode metadata and tags if present
        if "metadata" in fields and fields["metadata"] is not None:
            fields["metadata"] = json.dumps(fields["metadata"])

        if "tags" in fields and fields["tags"] is not None:
            fields["tags"] = json.dumps(fields["tags"])

        # Always set updated_at
        fields["updated_at"] = _NOW()

        # Build SET clause
        set_clause = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values())
        values.append(doc_id)

        with _docs_transaction(_db_path) as c:
            cursor = c.execute(
                f"UPDATE ds_documents SET {set_clause} WHERE doc_id = ?",  # noqa: S608
                values,
            )
            success = cursor.rowcount > 0

        # Emit event AFTER commit — via spool (Slice 3)
        if success:
            _envelope = CanonicalEventEnvelope(
                event_type=CanonicalEventType.DOCUMENT_UPDATED.value,
                session_id=None,
                payload={
                    "doc_id": doc_id,
                    "fields_updated": list(fields.keys()),
                },
                confidence="unavailable",
                project_id=None,
            )
            try:
                write_envelopes([_envelope])
            except Exception:
                # spool write failure means the event will not reach SQLite;
                # the calling operation must abort to preserve audit/consistency invariants.
                raise RuntimeError(
                    f"Event emission failed for DOCUMENT_UPDATED (doc_id={doc_id}). "
                    f"Aborting update to prevent audit gap."
                )

        return success

    @staticmethod
    def archive(doc_id: int, *, db_path: Path | None = None) -> bool:
        """
        Archive a document by setting status to 'archived'.

        Args:
            doc_id: Document ID to archive
            db_path: Override files.db path (for testing)

        Returns:
            True if successful, False if document not found
        """
        success = DocumentStore.update(doc_id, db_path, status=_ARCHIVED)

        # Emit event AFTER update (which already emits DOCUMENT_UPDATED)
        # STABILITY: fail if event fails — via spool (Slice 3)
        if success:
            _envelope = CanonicalEventEnvelope(
                event_type=CanonicalEventType.DOCUMENT_ARCHIVED.value,
                session_id=None,
                payload={"doc_id": doc_id},
                confidence="unavailable",
                project_id=None,
            )
            try:
                write_envelopes([_envelope])
            except Exception:
                # spool write failure means the event will not reach SQLite;
                # the calling operation must abort to preserve audit/consistency invariants.
                raise RuntimeError(
                    f"Event emission failed for DOCUMENT_ARCHIVED (doc_id={doc_id}). "
                    f"Document was updated but archive event failed."
                )

        return success

    @staticmethod
    def get_by_type(
        doc_type: str, status: str = _ACTIVE, *, db_path: Path | None = None
    ) -> list[dict]:
        """
        Get all documents of a given type with a given status.

        Args:
            doc_type: Type of document to retrieve
            status: Status filter (default 'active')
            db_path: Override files.db path (for testing)

        Returns:
            List of document dicts, sorted by created_at DESC
        """
        with _docs_connection(db_path) as c:
            rows = c.execute(
                """SELECT * FROM ds_documents
                   WHERE doc_type = ? AND status = ?
                   ORDER BY created_at DESC""",
                (doc_type, status),
            ).fetchall()

            results = []
            for row in rows:
                doc = dict(row)

                # Deserialize JSON fields
                if doc.get("metadata"):
                    try:
                        doc["metadata"] = json.loads(doc["metadata"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                if doc.get("tags"):
                    try:
                        doc["tags"] = json.loads(doc["tags"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                results.append(doc)

            return results

    @staticmethod
    def get_skill(pack: str, mode: str, *, db_path: Path | None = None) -> dict | None:
        """
        Get a skill document by pack and mode.

        Args:
            pack: Pack name (e.g., 'core', 'quality')
            mode: Mode name (e.g., 'build', 'debug')
            db_path: Override files.db path (for testing)

        Returns:
            Skill document dict or None if not found
        """
        skill_id = f"{pack}:{mode}"
        with _docs_connection(db_path) as c:
            row = c.execute(
                """SELECT * FROM ds_documents
                   WHERE doc_type = 'skill' AND skill_id = ? AND status = ?
                   LIMIT 1""",
                (skill_id, _ACTIVE),
            ).fetchone()

            if not row:
                return None

            doc = dict(row)

            # Deserialize JSON fields
            if doc.get("metadata"):
                try:
                    doc["metadata"] = json.loads(doc["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass

            if doc.get("tags"):
                try:
                    doc["tags"] = json.loads(doc["tags"])
                except (json.JSONDecodeError, TypeError):
                    pass

            return doc

    @staticmethod
    def get_skill_gotchas(pack: str, mode: str, *, db_path: Path | None = None) -> list[dict]:
        """
        Get gotcha documents for a specific skill mode.

        Args:
            pack: Pack name (e.g., 'core', 'quality')
            mode: Mode name (e.g., 'build', 'debug')
            db_path: Override files.db path (for testing)

        Returns:
            List of gotcha document dicts
        """
        skill_id = f"{pack}:{mode}"
        with _docs_connection(db_path) as c:
            rows = c.execute(
                """SELECT * FROM ds_documents
                   WHERE doc_type = 'gotcha' AND skill_id = ? AND status = ?
                   ORDER BY created_at DESC""",
                (skill_id, _ACTIVE),
            ).fetchall()

            results = []
            for row in rows:
                doc = dict(row)

                # Deserialize JSON fields
                if doc.get("metadata"):
                    try:
                        doc["metadata"] = json.loads(doc["metadata"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                if doc.get("tags"):
                    try:
                        doc["tags"] = json.loads(doc["tags"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                results.append(doc)

            return results

    @staticmethod
    def get_team_gotchas(*, db_path: Path | None = None) -> list[dict]:
        """
        Get team-wide gotcha documents (not associated with a specific skill).

        Args:
            db_path: Override files.db path (for testing)

        Returns:
            List of gotcha document dicts
        """
        with _docs_connection(db_path) as c:
            rows = c.execute(
                """SELECT * FROM ds_documents
                   WHERE doc_type = 'gotcha' AND skill_id IS NULL AND status = ?
                   ORDER BY created_at DESC""",
                (_ACTIVE,),
            ).fetchall()

            results = []
            for row in rows:
                doc = dict(row)

                # Deserialize JSON fields
                if doc.get("metadata"):
                    try:
                        doc["metadata"] = json.loads(doc["metadata"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                if doc.get("tags"):
                    try:
                        doc["tags"] = json.loads(doc["tags"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                results.append(doc)

            return results
