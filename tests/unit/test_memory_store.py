"""Unit tests for core.memory.store — semantic memory authority."""

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
)


@pytest.fixture()
def store(tmp_path: Path, monkeypatch) -> MemoryStore:
    """MemoryStore backed by a temp DB."""
    db_path = str(tmp_path / "test.db")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()

    monkeypatch.setattr("core.memory.store.transaction", _make_tx(db_path))
    monkeypatch.setattr("core.memory.store.get_connection", _make_gc(db_path))

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


# ── Store + retrieve ─────────────────────────────────────────────────────────


def test_store_and_retrieve(store):
    entry = MemoryEntry(
        memory_id="test-1",
        memory_type="lesson",
        category="debugging",
        content="Always check logs before debugging",
        source_type="raw_lessons",
        source_id="lesson-001",
        lifecycle_state="ACTIVE",
        importance=0.8,
        tags=["debugging"],
    )
    mid = store.store(entry)
    assert mid == "test-1"

    results = store.retrieve(MemoryQuery(text="check logs"))
    assert len(results) >= 1
    assert results[0].entry.memory_id == "test-1"
    assert results[0].entry.memory_type == "lesson"
    assert results[0].entry.source_type == "raw_lessons"


def test_retrieve_filters_by_memory_type(store):
    store.store(
        MemoryEntry(
            memory_id="l1",
            memory_type="lesson",
            category="general",
            content="A lesson",
            lifecycle_state="ACTIVE",
        )
    )
    store.store(
        MemoryEntry(
            memory_id="g1",
            memory_type="gotcha",
            category="general",
            content="A gotcha",
            lifecycle_state="ACTIVE",
        )
    )

    lessons = store.retrieve(MemoryQuery(memory_type="lesson"))
    assert all(r.entry.memory_type == "lesson" for r in lessons)


def test_retrieve_excludes_archived(store):
    store.store(
        MemoryEntry(
            memory_id="a1",
            memory_type="lesson",
            category="general",
            content="Archived lesson",
            lifecycle_state="ARCHIVED",
            importance=1.0,
        )
    )
    results = store.retrieve(MemoryQuery(text="archived"))
    assert len(results) == 0


def test_retrieve_includes_active_promoted_candidate(store):
    for state in ["ACTIVE", "PROMOTED", "CANDIDATE"]:
        store.store(
            MemoryEntry(
                memory_id=f"s-{state}",
                memory_type="lesson",
                category="general",
                content=f"Entry in {state}",
                lifecycle_state=state,
                importance=0.9,
            )
        )

    results = store.retrieve(MemoryQuery(text="Entry"))
    assert len(results) == 3


# ── Lifecycle transitions ────────────────────────────────────────────────────


def test_valid_transition(store):
    store.store(
        MemoryEntry(
            memory_id="t1",
            memory_type="lesson",
            category="general",
            content="Draft lesson",
            lifecycle_state="DRAFT",
        )
    )
    store.transition("t1", "CANDIDATE")
    entry = store.get_entry("t1")
    assert entry.lifecycle_state == "CANDIDATE"


def test_invalid_transition_raises(store):
    store.store(
        MemoryEntry(
            memory_id="t2",
            memory_type="lesson",
            category="general",
            content="Draft lesson",
            lifecycle_state="DRAFT",
        )
    )
    with pytest.raises(ValueError, match="Invalid transition"):
        store.transition("t2", "ACTIVE")


def test_full_promotion_chain(store):
    store.store(
        MemoryEntry(
            memory_id="chain",
            memory_type="lesson",
            category="general",
            content="Promotion chain test",
            lifecycle_state="DRAFT",
        )
    )
    store.transition("chain", "CANDIDATE")
    store.transition("chain", "PROMOTED")
    store.transition("chain", "ACTIVE")
    entry = store.get_entry("chain")
    assert entry.lifecycle_state == "ACTIVE"


def test_archived_is_terminal(store):
    store.store(
        MemoryEntry(
            memory_id="term",
            memory_type="lesson",
            category="general",
            content="Archived",
            lifecycle_state="ARCHIVED",
        )
    )
    with pytest.raises(ValueError, match="Invalid transition"):
        store.transition("term", "ACTIVE")


# ── Upsert by provenance ────────────────────────────────────────────────────


def test_upsert_creates_new(store):
    entry = MemoryEntry(
        memory_id="",
        memory_type="lesson",
        category="general",
        content="New lesson",
        source_type="raw_lessons",
        source_id="L-001",
        lifecycle_state="DRAFT",
    )
    mid = store.upsert_by_provenance(entry)
    assert mid

    fetched = store.get_entry(mid)
    assert fetched.content == "New lesson"
    assert fetched.source_type == "raw_lessons"


def test_upsert_updates_existing(store):
    entry = MemoryEntry(
        memory_id="",
        memory_type="lesson",
        category="general",
        content="Original",
        source_type="raw_lessons",
        source_id="L-002",
        lifecycle_state="DRAFT",
        importance=0.5,
    )
    mid1 = store.upsert_by_provenance(entry)

    entry2 = MemoryEntry(
        memory_id="",
        memory_type="lesson",
        category="debugging",
        content="Updated content",
        source_type="raw_lessons",
        source_id="L-002",
        lifecycle_state="ACTIVE",
        importance=0.9,
    )
    mid2 = store.upsert_by_provenance(entry2)

    assert mid1 == mid2

    fetched = store.get_entry(mid1)
    assert fetched.content == "Updated content"
    assert fetched.lifecycle_state == "DRAFT"
    assert fetched.importance == 0.5


def test_upsert_requires_provenance(store):
    entry = MemoryEntry(
        memory_id="",
        memory_type="lesson",
        category="general",
        content="No provenance",
    )
    with pytest.raises(ValueError, match="source_type and source_id"):
        store.upsert_by_provenance(entry)


# ── Ingest methods ───────────────────────────────────────────────────────────


def test_ingest_lesson(store):
    mid = store.ingest_lesson(
        lesson_path="test.md",
        content="Security vulnerability in auth flow",
        source_id="lesson-123",
        confidence=0.8,
    )
    entry = store.get_entry(mid)
    assert entry.memory_type == "lesson"
    assert entry.source_type == "raw_lessons"
    assert entry.source_id == "lesson-123"
    assert entry.lifecycle_state == "DRAFT"
    assert entry.provenance["source_type"] == "raw_lessons"


def test_ingest_gotcha(store):
    mid = store.ingest_gotcha(
        title="Ctrl+Z hits global undo",
        fix="Use undo manager",
        severity="high",
        skill="playwright",
        source_id="gotcha-42",
    )
    entry = store.get_entry(mid)
    assert entry.memory_type == "gotcha"
    assert entry.lifecycle_state == "PROMOTED"
    assert entry.importance == 0.8


def test_ingest_decision(store):
    mid = store.ingest_decision(
        decision_type="architecture",
        outcome="Use event sourcing",
        reasoning="Better audit trail",
        confidence=0.9,
        subsystem="core",
        source_id="evt-123",
    )
    entry = store.get_entry(mid)
    assert entry.memory_type == "decision"
    assert entry.confidence == 0.9


# ── Stats ────────────────────────────────────────────────────────────────────


def test_stats(store):
    store.store(
        MemoryEntry(
            memory_id="s1",
            memory_type="lesson",
            category="general",
            content="Lesson",
            lifecycle_state="ACTIVE",
        )
    )
    store.store(
        MemoryEntry(
            memory_id="s2",
            memory_type="gotcha",
            category="general",
            content="Gotcha",
            lifecycle_state="PROMOTED",
        )
    )

    stats = store.stats()
    assert stats["total_entries"] == 2
    assert stats["by_memory_type"]["lesson"] == 1
    assert stats["by_memory_type"]["gotcha"] == 1
    assert "by_lifecycle_state" in stats
    assert "by_source_type" in stats


# ── Access + importance ──────────────────────────────────────────────────────


def test_record_access(store):
    store.store(
        MemoryEntry(
            memory_id="acc",
            memory_type="lesson",
            category="general",
            content="Test",
            lifecycle_state="ACTIVE",
        )
    )
    store.record_access("acc")
    store.record_access("acc")
    entry = store.get_entry("acc")
    assert entry.access_count == 2
    assert entry.last_accessed != ""


def test_boost_importance(store):
    store.store(
        MemoryEntry(
            memory_id="imp",
            memory_type="lesson",
            category="general",
            content="Test",
            importance=0.5,
            lifecycle_state="ACTIVE",
        )
    )
    store.boost_importance("imp", 0.3)
    entry = store.get_entry("imp")
    assert abs(entry.importance - 0.8) < 0.01


def test_importance_caps_at_one(store):
    store.store(
        MemoryEntry(
            memory_id="cap",
            memory_type="lesson",
            category="general",
            content="Test",
            importance=0.9,
            lifecycle_state="ACTIVE",
        )
    )
    store.boost_importance("cap", 0.5)
    entry = store.get_entry("cap")
    assert entry.importance == 1.0
