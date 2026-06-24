"""Phase 4D integration tests — catalog-backed document lifecycle validation.

Proves that DocumentStore uses the catalog for advisory state validation,
that persisted lowercase DB strings are preserved, and that no Enum objects leak
into SQLite.

Updated for three-store architecture: DocumentStore now writes to files.db,
not studio.db.  Test isolation is via the doc_store fixture, which monkeypatches
core.files.store.files_db_path() to a per-test temp file — the same mechanism
FileStore tests use.  DocumentStore's public method signatures are unchanged;
no db_path argument is threaded through them.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.ontology.lifecycles import (
    LIFECYCLE_CATALOG,
    DocumentLifecycle,
    ExecutionLifecycle,
    MemoryLifecycle,
    to_db_value,
    from_db_value,
)


@pytest.fixture()
def doc_store(tmp_path, monkeypatch):
    """DocumentStore backed by a temp files.db with event emission stubbed out.

    Redirects files_db_path() to a per-test temp file so connect_files() — and
    therefore every DocumentStore operation — uses an isolated database.  Returns
    (DocumentStore, db_path); db_path is the temp file for direct inspection.
    """
    db_path = tmp_path / "test_files.db"

    # Redirect files.db resolution to the temp path (same isolation pattern as
    # FileStore tests). connect_files() with no arg resolves files_db_path().
    monkeypatch.setattr("core.files.store.files_db_path", lambda: db_path)

    # Stub out event emission so tests don't need a live spool
    monkeypatch.setattr(
        "core.storage.document_store.write_envelopes", lambda envelopes, **kwargs: None
    )

    from core.storage.document_store import DocumentStore

    return DocumentStore, db_path


def _raw_status(db_path: Path, doc_id: int) -> str:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT status FROM ds_documents WHERE doc_id = ?",
        (doc_id,),
    ).fetchone()
    conn.close()
    return row[0] if row else None


# ── Module-level constants ──────────────────────────────────────────────────


class TestDocumentConstants:
    def test_active_constant_is_lowercase(self):
        from core.storage.document_store import _ACTIVE

        assert _ACTIVE == "active"

    def test_archived_constant_is_lowercase(self):
        from core.storage.document_store import _ARCHIVED

        assert _ARCHIVED == "archived"

    def test_constants_are_plain_strings(self):
        from core.storage.document_store import _ACTIVE, _ARCHIVED

        assert type(_ACTIVE) is str
        assert type(_ARCHIVED) is str

    def test_constants_derived_from_enum(self):
        from core.storage.document_store import _ACTIVE, _ARCHIVED

        assert to_db_value(DocumentLifecycle.ACTIVE) == _ACTIVE
        assert to_db_value(DocumentLifecycle.ARCHIVED) == _ARCHIVED


# ── Document creation persists lowercase string ─────────────────────────────


class TestDocumentCreationStatus:
    def test_new_document_defaults_to_active(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test Spec", "Content here")
        raw = _raw_status(db_path, doc_id)
        assert raw == "active"

    def test_default_status_matches_enum(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test Spec", "Content here")
        raw = _raw_status(db_path, doc_id)
        assert raw == to_db_value(DocumentLifecycle.ACTIVE)

    def test_default_status_is_plain_string(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test Spec", "Content here")
        raw = _raw_status(db_path, doc_id)
        assert type(raw) is str
        assert not isinstance(raw, DocumentLifecycle)


# ── Archive persists lowercase string ───────────────────────────────────────


class TestArchiveStringPreservation:
    def test_archived_persisted_as_lowercase(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test Spec", "Content here")
        store.archive(doc_id)
        assert _raw_status(db_path, doc_id) == "archived"

    def test_archived_matches_enum_value(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test Spec", "Content here")
        store.archive(doc_id)
        assert _raw_status(db_path, doc_id) == to_db_value(DocumentLifecycle.ARCHIVED)

    def test_archived_status_is_plain_string(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test Spec", "Content here")
        store.archive(doc_id)
        raw = _raw_status(db_path, doc_id)
        assert type(raw) is str


# ── Status update preserves lowercase strings ───────────────────────────────


class TestStatusUpdateStringPreservation:
    def test_update_active_persisted_as_lowercase(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test Spec", "Content here")
        store.archive(doc_id)
        store.update(doc_id, status="active")
        assert _raw_status(db_path, doc_id) == "active"

    def test_update_archived_persisted_as_lowercase(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test Spec", "Content here")
        store.update(doc_id, status="archived")
        assert _raw_status(db_path, doc_id) == "archived"

    def test_all_document_states_accepted(self, doc_store):
        store, db_path = doc_store
        for member in DocumentLifecycle:
            state = to_db_value(member)
            doc_id = store.create("spec", f"Test {state}", "Content")
            store.update(doc_id, status=state)
            assert _raw_status(db_path, doc_id) == state


# ── No Enum objects in SQLite ───────────────────────────────────────────────


class TestNoEnumInSQLite:
    def test_status_typeof_is_text(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test", "Content")

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT status, typeof(status) FROM ds_documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        conn.close()

        assert row[0] == "active"
        assert row[1] == "text"

    def test_archived_typeof_is_text(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test", "Content")
        store.archive(doc_id)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT status, typeof(status) FROM ds_documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        conn.close()

        assert row[0] == "archived"
        assert row[1] == "text"

    def test_no_enum_repr_in_db(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test", "Content")

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT status FROM ds_documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        conn.close()

        assert "DocumentLifecycle" not in row[0]
        assert "<" not in row[0]


# ── Advisory catalog validation ─────────────────────────────────────────────


class TestAdvisoryValidation:
    def test_valid_status_no_warning(self, doc_store, caplog):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test", "Content")
        with caplog.at_level(logging.WARNING, logger="core.storage.document_store"):
            store.update(doc_id, status="archived")
        assert "Unrecognized document status" not in caplog.text

    def test_invalid_status_logs_warning(self, doc_store, caplog):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test", "Content")
        with caplog.at_level(logging.WARNING, logger="core.storage.document_store"):
            store.update(doc_id, status="NONEXISTENT")
        assert "Unrecognized document status" in caplog.text

    def test_uppercase_active_logs_warning(self, doc_store, caplog):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test", "Content")
        with caplog.at_level(logging.WARNING, logger="core.storage.document_store"):
            store.update(doc_id, status="ACTIVE")
        assert "Unrecognized document status" in caplog.text

    def test_memory_state_logs_warning(self, doc_store, caplog):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test", "Content")
        with caplog.at_level(logging.WARNING, logger="core.storage.document_store"):
            store.update(doc_id, status="DRAFT")
        assert "Unrecognized document status" in caplog.text

    def test_invalid_status_still_persisted(self, doc_store):
        """Advisory validation does not block writes."""
        store, db_path = doc_store
        doc_id = store.create("spec", "Test", "Content")
        store.update(doc_id, status="NONEXISTENT")
        assert _raw_status(db_path, doc_id) == "NONEXISTENT"

    def test_non_status_update_no_warning(self, doc_store, caplog):
        store, db_path = doc_store
        doc_id = store.create("spec", "Test", "Content")
        with caplog.at_level(logging.WARNING, logger="core.storage.document_store"):
            store.update(doc_id, title="New Title")
        assert "Unrecognized document status" not in caplog.text
