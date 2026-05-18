"""Phase 4D integration tests — catalog-backed document lifecycle validation.

Proves that DocumentStore uses the catalog for advisory state validation,
that persisted lowercase DB strings are preserved, and that no Enum objects leak
into SQLite.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

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

_DOCUMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS ds_documents (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    project_id TEXT,
    skill_id TEXT,
    session_id TEXT,
    format TEXT DEFAULT 'markdown',
    metadata TEXT,
    tags TEXT,
    keywords TEXT,
    version INTEGER DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT,
    updated_at TEXT,
    access_count INTEGER DEFAULT 0,
    ttl_days INTEGER,
    expires_at TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS ds_documents_fts USING fts5(
    title, content, keywords, tags, content=ds_documents, content_rowid=doc_id
);
"""


@pytest.fixture()
def doc_store(tmp_path, monkeypatch):
    """DocumentStore backed by a temp DB with event emission stubbed out."""
    db_path = str(tmp_path / "test_doc.db")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DOCUMENT_SCHEMA)
    conn.close()

    monkeypatch.setattr("core.storage.document_store.get_connection", _make_gc(db_path))
    monkeypatch.setattr("core.storage.document_store.transaction", _make_tx(db_path))
    monkeypatch.setattr("core.storage.document_store.write_envelopes", lambda envelopes, **kwargs: None)

    from core.storage.document_store import DocumentStore

    return DocumentStore, db_path


def _make_gc(db_path):
    @contextmanager
    def _gc():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    return _gc


def _make_tx(db_path):
    @contextmanager
    def _tx():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return _tx


def _raw_status(db_path: str, doc_id: int) -> str:
    conn = sqlite3.connect(db_path)
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

        assert _ACTIVE == to_db_value(DocumentLifecycle.ACTIVE)
        assert _ARCHIVED == to_db_value(DocumentLifecycle.ARCHIVED)


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

        conn = sqlite3.connect(db_path)
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

        conn = sqlite3.connect(db_path)
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

        conn = sqlite3.connect(db_path)
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


# ── Catalog domain key verification ─────────────────────────────────────────


class TestCatalogDomainKey:
    def test_artifact_domain_registered(self):
        assert LIFECYCLE_CATALOG.has_lifecycle("artifact") is True

    def test_artifact_uses_document_lifecycle(self):
        assert LIFECYCLE_CATALOG.get_lifecycle("artifact") is DocumentLifecycle

    def test_all_document_states_valid_in_catalog(self):
        for member in DocumentLifecycle:
            assert LIFECYCLE_CATALOG.validate_state("artifact", member.value) is True

    def test_catalog_transitions_match_document_states(self):
        assert LIFECYCLE_CATALOG.validate_transition("artifact", "active", "archived") is True
        assert LIFECYCLE_CATALOG.validate_transition("artifact", "archived", "active") is True
        assert LIFECYCLE_CATALOG.validate_transition("artifact", "active", "active") is False

    def test_execution_states_invalid_in_artifact_domain(self):
        assert LIFECYCLE_CATALOG.validate_state("artifact", "pending") is False
        assert LIFECYCLE_CATALOG.validate_state("artifact", "completed") is False
        assert LIFECYCLE_CATALOG.validate_state("artifact", "failed") is False

    def test_memory_states_invalid_in_artifact_domain(self):
        assert LIFECYCLE_CATALOG.validate_state("artifact", "DRAFT") is False
        assert LIFECYCLE_CATALOG.validate_state("artifact", "PROMOTED") is False


# ── Cross-domain isolation ──────────────────────────────────────────────────


class TestCrossDomainIsolation:
    def test_document_active_not_equal_to_raw_string(self):
        assert DocumentLifecycle.ACTIVE != "active"

    def test_document_active_not_equal_to_execution_active(self):
        assert DocumentLifecycle.ACTIVE != ExecutionLifecycle.ACTIVE

    def test_document_active_not_equal_to_memory_active(self):
        assert DocumentLifecycle.ACTIVE != MemoryLifecycle.ACTIVE

    def test_same_persisted_value_different_domains(self):
        assert to_db_value(DocumentLifecycle.ACTIVE) == to_db_value(ExecutionLifecycle.ACTIVE)
        assert DocumentLifecycle.ACTIVE != ExecutionLifecycle.ACTIVE

    def test_document_lifecycle_is_not_str(self):
        assert not isinstance(DocumentLifecycle.ACTIVE, str)
        assert not isinstance(DocumentLifecycle.ARCHIVED, str)


# ── Document lifecycle flow ─────────────────────────────────────────────────


class TestDocumentLifecycleFlow:
    def test_active_to_archived(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Lifecycle test", "Content")
        assert _raw_status(db_path, doc_id) == to_db_value(DocumentLifecycle.ACTIVE)

        store.archive(doc_id)
        assert _raw_status(db_path, doc_id) == to_db_value(DocumentLifecycle.ARCHIVED)

    def test_active_to_archived_to_active(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Lifecycle test", "Content")
        store.archive(doc_id)
        store.update(doc_id, status=to_db_value(DocumentLifecycle.ACTIVE))
        assert _raw_status(db_path, doc_id) == to_db_value(DocumentLifecycle.ACTIVE)


# ── Persisted string compatibility ──────────────────────────────────────────


class TestPersistedStringCompatibility:
    def test_existing_active_string_still_valid(self):
        member = from_db_value("active", DocumentLifecycle)
        assert member is DocumentLifecycle.ACTIVE
        assert to_db_value(member) == "active"

    def test_existing_archived_string_still_valid(self):
        member = from_db_value("archived", DocumentLifecycle)
        assert member is DocumentLifecycle.ARCHIVED
        assert to_db_value(member) == "archived"

    def test_roundtrip_all_document_states(self):
        for member in DocumentLifecycle:
            db_val = to_db_value(member)
            parsed = from_db_value(db_val, DocumentLifecycle)
            assert parsed is member

    def test_case_insensitive_parse(self):
        assert from_db_value("Active", DocumentLifecycle) is DocumentLifecycle.ACTIVE
        assert from_db_value("ACTIVE", DocumentLifecycle) is DocumentLifecycle.ACTIVE
        assert from_db_value("ARCHIVED", DocumentLifecycle) is DocumentLifecycle.ARCHIVED


# ── get_by_type default status ──────────────────────────────────────────────


class TestGetByTypeDefault:
    def test_get_by_type_returns_active_by_default(self, doc_store):
        store, db_path = doc_store
        doc_id = store.create("spec", "Active Spec", "Content")
        results = store.get_by_type("spec")
        assert len(results) == 1
        assert results[0]["title"] == "Active Spec"

    def test_get_by_type_excludes_archived(self, doc_store):
        store, db_path = doc_store
        store.create("spec", "Active Spec", "Content")
        doc_id2 = store.create("spec", "Archived Spec", "Content")
        store.archive(doc_id2)
        results = store.get_by_type("spec")
        assert len(results) == 1
        assert results[0]["title"] == "Active Spec"

    def test_get_by_type_archived_filter(self, doc_store):
        store, db_path = doc_store
        store.create("spec", "Active Spec", "Content")
        doc_id2 = store.create("spec", "Archived Spec", "Content")
        store.archive(doc_id2)
        results = store.get_by_type("spec", status="archived")
        assert len(results) == 1
        assert results[0]["title"] == "Archived Spec"


# ── No memory/execution behavior alteration ─────────────────────────────────


class TestNoSideEffects:
    def test_document_integration_does_not_alter_memory_catalog(self):
        assert LIFECYCLE_CATALOG.has_lifecycle("memory") is True
        assert LIFECYCLE_CATALOG.get_lifecycle("memory") is MemoryLifecycle
        assert LIFECYCLE_CATALOG.validate_state("memory", "ACTIVE") is True

    def test_document_integration_does_not_alter_execution_catalog(self):
        assert LIFECYCLE_CATALOG.has_lifecycle("workflow") is True
        assert LIFECYCLE_CATALOG.get_lifecycle("workflow") is ExecutionLifecycle
        assert LIFECYCLE_CATALOG.validate_state("workflow", "pending") is True

    def test_catalog_still_has_six_bindings(self):
        assert len(LIFECYCLE_CATALOG.specs) == 6
