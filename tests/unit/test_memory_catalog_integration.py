"""Phase 4B integration tests — catalog-backed memory lifecycle validation.

Proves that MemoryStore uses the immutable TypeCatalog for lifecycle validation,
that persisted DB strings are unchanged, and that no Enum objects leak into SQLite.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.memory.store import (
    MemoryEntry,
    MemoryQuery,
    MemoryStore,
    _DEFAULT_RETRIEVE_STATES,
)
from core.ontology.lifecycles import (
    LIFECYCLE_CATALOG,
    MemoryLifecycle,
    to_db_value,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path: Path, monkeypatch) -> MemoryStore:
    from core.config.sqlite_bootstrap import run_migrations

    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    run_migrations(conn)
    conn.close()

    monkeypatch.setattr("core.memory.store_main.transaction", _make_tx(db_path))
    monkeypatch.setattr("core.memory.store_main.get_connection", _make_gc(db_path))
    return MemoryStore(db_path)


def _make_tx(db_path):
    from contextlib import contextmanager

    @contextmanager
    def _tx():
        conn = sqlite3.connect(db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    return _tx


def _make_gc(db_path):
    from contextlib import contextmanager

    @contextmanager
    def _gc(read_only=False):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    return _gc


def _raw_lifecycle(db_path: str, memory_id: str) -> str:
    """Read lifecycle_state directly from SQLite, bypassing MemoryStore."""
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT lifecycle_state FROM memory_entries WHERE memory_id = ?",
        (memory_id,),
    ).fetchone()
    conn.close()
    return row[0] if row else None


# ── _DEFAULT_RETRIEVE_STATES constant ───────────────────────────────────────


class TestDefaultRetrieveStates:
    def test_contains_expected_states(self):
        assert "ACTIVE" in _DEFAULT_RETRIEVE_STATES
        assert "PROMOTED" in _DEFAULT_RETRIEVE_STATES
        assert "CANDIDATE" in _DEFAULT_RETRIEVE_STATES

    def test_excludes_non_retrievable(self):
        assert "DRAFT" not in _DEFAULT_RETRIEVE_STATES
        assert "ARCHIVED" not in _DEFAULT_RETRIEVE_STATES
        assert "STALE" not in _DEFAULT_RETRIEVE_STATES
        assert "SUPERSEDED" not in _DEFAULT_RETRIEVE_STATES

    def test_values_are_plain_strings(self):
        for s in _DEFAULT_RETRIEVE_STATES:
            assert type(s) is str

    def test_derived_from_enum(self):
        assert (
            to_db_value(MemoryLifecycle.ACTIVE),
            to_db_value(MemoryLifecycle.PROMOTED),
            to_db_value(MemoryLifecycle.CANDIDATE),
        ) == _DEFAULT_RETRIEVE_STATES


# ── Catalog-backed transition validation ────────────────────────────────────


class TestCatalogBackedTransition:
    def test_valid_transition_uses_catalog(self, store):
        store.store(
            MemoryEntry(
                memory_id="cat-1",
                memory_type="lesson",
                category="general",
                content="Draft entry",
                lifecycle_state="DRAFT",
            )
        )
        store.transition("cat-1", "CANDIDATE")
        assert store.get_entry("cat-1").lifecycle_state == "CANDIDATE"

    def test_invalid_transition_rejected_by_catalog(self, store):
        store.store(
            MemoryEntry(
                memory_id="cat-2",
                memory_type="lesson",
                category="general",
                content="Draft entry",
                lifecycle_state="DRAFT",
            )
        )
        with pytest.raises(ValueError, match="Invalid transition"):
            store.transition("cat-2", "ACTIVE")

    def test_invalid_state_rejected_by_catalog(self, store):
        store.store(
            MemoryEntry(
                memory_id="cat-3",
                memory_type="lesson",
                category="general",
                content="Entry",
                lifecycle_state="ACTIVE",
            )
        )
        with pytest.raises(ValueError, match="Invalid state"):
            store.transition("cat-3", "NONEXISTENT")

    def test_archived_terminal_via_catalog(self, store):
        store.store(
            MemoryEntry(
                memory_id="cat-4",
                memory_type="lesson",
                category="general",
                content="Archived",
                lifecycle_state="ARCHIVED",
            )
        )
        with pytest.raises(ValueError, match="Invalid transition"):
            store.transition("cat-4", "ACTIVE")

    def test_full_promotion_chain_via_catalog(self, store):
        store.store(
            MemoryEntry(
                memory_id="chain",
                memory_type="lesson",
                category="general",
                content="Full chain",
                lifecycle_state="DRAFT",
            )
        )
        for target in ("CANDIDATE", "PROMOTED", "ACTIVE"):
            store.transition("chain", target)
        assert store.get_entry("chain").lifecycle_state == "ACTIVE"

    def test_catalog_and_store_agree_on_transitions(self):
        for member in MemoryLifecycle:
            state = to_db_value(member)
            assert LIFECYCLE_CATALOG.validate_state("memory", state) is True

    def test_lowercase_execution_state_rejected_for_memory(self, store):
        store.store(
            MemoryEntry(
                memory_id="cat-5",
                memory_type="lesson",
                category="general",
                content="Entry",
                lifecycle_state="ACTIVE",
            )
        )
        with pytest.raises(ValueError, match="Invalid state"):
            store.transition("cat-5", "active")


# ── DB string preservation ──────────────────────────────────────────────────


class TestDBStringPreservation:
    def test_stored_lifecycle_is_plain_string(self, store, tmp_path):
        db_path = str(tmp_path / "test.db")
        store.store(
            MemoryEntry(
                memory_id="str-1",
                memory_type="lesson",
                category="general",
                content="Test",
                lifecycle_state="DRAFT",
            )
        )
        raw = _raw_lifecycle(db_path, "str-1")
        assert raw == "DRAFT"
        assert type(raw) is str

    def test_transition_persists_string_not_enum(self, store, tmp_path):
        db_path = str(tmp_path / "test.db")
        store.store(
            MemoryEntry(
                memory_id="str-2",
                memory_type="lesson",
                category="general",
                content="Test",
                lifecycle_state="DRAFT",
            )
        )
        store.transition("str-2", "CANDIDATE")
        raw = _raw_lifecycle(db_path, "str-2")
        assert raw == "CANDIDATE"
        assert type(raw) is str
        assert not isinstance(raw, MemoryLifecycle)

    def test_all_existing_db_strings_accepted(self, store):
        db_strings = ["DRAFT", "CANDIDATE", "PROMOTED", "ACTIVE", "STALE", "SUPERSEDED", "ARCHIVED"]
        for i, state in enumerate(db_strings):
            store.store(
                MemoryEntry(
                    memory_id=f"compat-{i}",
                    memory_type="lesson",
                    category="general",
                    content=f"Entry {state}",
                    lifecycle_state=state,
                )
            )
            entry = store.get_entry(f"compat-{i}")
            assert entry.lifecycle_state == state

    def test_entry_lifecycle_state_is_str_type(self, store):
        store.store(
            MemoryEntry(
                memory_id="type-1",
                memory_type="lesson",
                category="general",
                content="Test",
                lifecycle_state="ACTIVE",
            )
        )
        entry = store.get_entry("type-1")
        assert type(entry.lifecycle_state) is str

    def test_no_enum_objects_in_sqlite(self, store, tmp_path):
        db_path = str(tmp_path / "test.db")
        store.store(
            MemoryEntry(
                memory_id="enum-check",
                memory_type="lesson",
                category="general",
                content="Test",
                lifecycle_state="DRAFT",
            )
        )
        store.transition("enum-check", "CANDIDATE")

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT lifecycle_state, typeof(lifecycle_state) FROM memory_entries WHERE memory_id = ?",
            ("enum-check",),
        ).fetchone()
        conn.close()

        assert row[0] == "CANDIDATE"
        assert row[1] == "text"


# ── Ingestion uses enum-derived strings ─────────────────────────────────────


class TestIngestionCatalogIntegration:
    def test_ingest_lesson_uses_draft_from_enum(self, store, tmp_path):
        db_path = str(tmp_path / "test.db")
        mid = store.ingest_lesson(
            lesson_path="test.md",
            content="Lesson content",
            source_id="lesson-int-1",
            confidence=0.8,
        )
        raw = _raw_lifecycle(db_path, mid)
        assert raw == "DRAFT"
        assert raw == to_db_value(MemoryLifecycle.DRAFT)

    def test_ingest_gotcha_uses_promoted_from_enum(self, store, tmp_path):
        db_path = str(tmp_path / "test.db")
        mid = store.ingest_gotcha(
            title="Test gotcha",
            fix="Fix it",
            severity="high",
            skill="test",
            source_id="gotcha-int-1",
        )
        raw = _raw_lifecycle(db_path, mid)
        assert raw == "PROMOTED"
        assert raw == to_db_value(MemoryLifecycle.PROMOTED)

    def test_ingest_decision_uses_promoted_from_enum(self, store, tmp_path):
        db_path = str(tmp_path / "test.db")
        mid = store.ingest_decision(
            decision_type="architecture",
            outcome="Use X",
            reasoning="Because",
            confidence=0.9,
            subsystem="core",
            source_id="dec-int-1",
        )
        raw = _raw_lifecycle(db_path, mid)
        assert raw == "PROMOTED"
        assert raw == to_db_value(MemoryLifecycle.PROMOTED)

    def test_ingested_entries_retrievable_by_default_filter(self, store):
        store.ingest_gotcha(
            title="Retrievable gotcha",
            fix="Fix",
            severity="high",
            skill="test",
            source_id="gotcha-ret-1",
        )
        results = store.retrieve(MemoryQuery(text="Retrievable gotcha"))
        assert len(results) >= 1


# ── Retrieve respects _DEFAULT_RETRIEVE_STATES ──────────────────────────────


class TestRetrieveFilterIntegration:
    def test_default_filter_matches_constant(self, store):
        for state in _DEFAULT_RETRIEVE_STATES:
            store.store(
                MemoryEntry(
                    memory_id=f"rf-{state}",
                    memory_type="lesson",
                    category="general",
                    content=f"Content {state}",
                    lifecycle_state=state,
                    importance=0.9,
                )
            )

        results = store.retrieve(MemoryQuery(text="Content"))
        ids = {r.entry.memory_id for r in results}
        for state in _DEFAULT_RETRIEVE_STATES:
            assert f"rf-{state}" in ids

    def test_draft_excluded_from_default_retrieve(self, store):
        store.store(
            MemoryEntry(
                memory_id="rf-draft",
                memory_type="lesson",
                category="general",
                content="Draft should not appear",
                lifecycle_state="DRAFT",
                importance=1.0,
            )
        )
        results = store.retrieve(MemoryQuery(text="Draft should not appear"))
        assert len(results) == 0

    def test_archived_excluded_from_default_retrieve(self, store):
        store.store(
            MemoryEntry(
                memory_id="rf-archived",
                memory_type="lesson",
                category="general",
                content="Archived should not appear",
                lifecycle_state="ARCHIVED",
                importance=1.0,
            )
        )
        results = store.retrieve(MemoryQuery(text="Archived should not appear"))
        assert len(results) == 0

    def test_explicit_lifecycle_filter_overrides_default(self, store):
        store.store(
            MemoryEntry(
                memory_id="rf-stale",
                memory_type="lesson",
                category="general",
                content="Stale entry",
                lifecycle_state="STALE",
                importance=1.0,
            )
        )
        results = store.retrieve(
            MemoryQuery(
                text="Stale entry",
                lifecycle_states=["STALE"],
            )
        )
        assert len(results) >= 1
        assert results[0].entry.memory_id == "rf-stale"
