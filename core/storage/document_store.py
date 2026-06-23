"""Universal CRUD API for the document store (ds_documents table)."""

from __future__ import annotations
import json
import logging
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config.database import transaction, get_connection
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


class DocumentStore:
    """Universal CRUD interface for ds_documents table with FTS5 search."""

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

        with transaction() as c:
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

            # Emit event BEFORE commit (STABILITY: fail if event fails) — via spool (Slice 3)
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
    def read(doc_id: int) -> dict | None:
        """
        Read a document by ID and increment access_count.

        Args:
            doc_id: Document ID to retrieve

        Returns:
            Complete document record as dict, or None if not found

        Note:
            Automatically increments access_count and updates last_accessed
        """
        with transaction() as c:
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
    def search(query: str, doc_type: str | None = None, limit: int = 50) -> list[dict]:
        """
        Search documents using FTS5 full-text search.

        Args:
            query: FTS5 search query (searches title, content, keywords, tags)
            doc_type: Optional filter by document type
            limit: Maximum number of results (default 50)

        Returns:
            List of matching document dicts, sorted by relevance

        Note:
            Uses FTS5 MATCH syntax. Simple keywords work, but you can also use
            advanced FTS5 operators like AND, OR, NOT, "phrase", etc.
        """
        with get_connection() as c:
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
    def update(doc_id: int, **fields: Any) -> bool:
        """
        Update specified fields of a document.

        Args:
            doc_id: Document ID to update
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

        with transaction() as c:
            cursor = c.execute(
                f"UPDATE ds_documents SET {set_clause} WHERE doc_id = ?",  # noqa: S608
                values,
            )
            success = cursor.rowcount > 0

            # Emit event BEFORE commit (STABILITY: fail if event fails) — via spool (Slice 3)
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
    def archive(doc_id: int) -> bool:
        """
        Archive a document by setting status to 'archived'.

        Args:
            doc_id: Document ID to archive

        Returns:
            True if successful, False if document not found
        """
        success = DocumentStore.update(doc_id, status=_ARCHIVED)

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
    def get_by_type(doc_type: str, status: str = _ACTIVE) -> list[dict]:
        """
        Get all documents of a given type with a given status.

        Args:
            doc_type: Type of document to retrieve
            status: Status filter (default 'active')

        Returns:
            List of document dicts, sorted by created_at DESC
        """
        with get_connection() as c:
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
    def get_skill(pack: str, mode: str) -> dict | None:
        """
        Get a skill document by pack and mode.

        Args:
            pack: Pack name (e.g., 'core', 'quality')
            mode: Mode name (e.g., 'build', 'debug')

        Returns:
            Skill document dict or None if not found
        """
        skill_id = f"{pack}:{mode}"
        with get_connection() as c:
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
    def get_skill_gotchas(pack: str, mode: str) -> list[dict]:
        """
        Get gotcha documents for a specific skill mode.

        Args:
            pack: Pack name (e.g., 'core', 'quality')
            mode: Mode name (e.g., 'build', 'debug')

        Returns:
            List of gotcha document dicts
        """
        skill_id = f"{pack}:{mode}"
        with get_connection() as c:
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
    def get_team_gotchas() -> list[dict]:
        """
        Get team-wide gotcha documents (not associated with a specific skill).

        Returns:
            List of gotcha document dicts
        """
        with get_connection() as c:
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
