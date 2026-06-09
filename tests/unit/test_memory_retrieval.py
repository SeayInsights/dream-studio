"""Unit tests for core.memory.retrieval — FTS5-accelerated memory search."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.memory.retrieval import FTS5MemoryRetriever
from core.memory.store import MemoryEntry, MemoryQuery, MemoryStore


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture()
def store(db_path, monkeypatch) -> MemoryStore:
    from core.config.sqlite_bootstrap import run_migrations

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    run_migrations(conn)
    conn.close()

    monkeypatch.setattr("core.memory.store.transaction", _make_tx(db_path))
    monkeypatch.setattr("core.memory.store.get_connection", _make_gc(db_path))
    monkeypatch.setattr("core.memory.retrieval.transaction", _make_tx(db_path))
    monkeypatch.setattr("core.memory.retrieval.get_connection", _make_gc(db_path))

    return MemoryStore(db_path)


@pytest.fixture()
def retriever(store, db_path, monkeypatch) -> FTS5MemoryRetriever:
    return FTS5MemoryRetriever(store)


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


def _seed_entries(store):
    store.store(
        MemoryEntry(
            memory_id="m1",
            memory_type="lesson",
            category="security",
            content="Always validate user input to prevent SQL injection attacks",
            lifecycle_state="ACTIVE",
            importance=0.9,
            tags=["security", "sql"],
        )
    )
    store.store(
        MemoryEntry(
            memory_id="m2",
            memory_type="gotcha",
            category="debugging",
            content="Playwright Ctrl+Z hits global undo not text element",
            lifecycle_state="ACTIVE",
            importance=0.8,
            tags=["playwright", "keyboard"],
        )
    )
    store.store(
        MemoryEntry(
            memory_id="m3",
            memory_type="decision",
            category="architecture",
            content="Use event sourcing for audit trail and temporal queries",
            lifecycle_state="PROMOTED",
            importance=0.7,
            tags=["architecture", "events"],
        )
    )
    store.store(
        MemoryEntry(
            memory_id="m4",
            memory_type="lesson",
            category="general",
            content="Run tests before pushing to verify no regressions",
            lifecycle_state="ARCHIVED",
            importance=0.5,
            tags=["testing"],
        )
    )


# ── FTS5 search ──────────────────────────────────────────────────────────────


def test_fts_search_returns_results(store, retriever):
    _seed_entries(store)
    retriever.rebuild_index()
    results = retriever.search("SQL injection")
    assert len(results) >= 1
    assert results[0].entry.memory_id == "m1"


def test_fts_search_excludes_archived(store, retriever):
    _seed_entries(store)
    retriever.rebuild_index()
    results = retriever.search("tests regressions")
    assert all(r.entry.lifecycle_state != "ARCHIVED" for r in results)


def test_fts_search_empty_query(store, retriever):
    _seed_entries(store)
    retriever.rebuild_index()
    assert retriever.search("") == []
    assert retriever.search("   ") == []


def test_fts_search_irrelevant_query(store, retriever):
    _seed_entries(store)
    retriever.rebuild_index()
    results = retriever.search("xyzzy frobnicator")
    for r in results:
        assert "fts_match" not in r.match_reason


def test_fts_search_respects_top_k(store, retriever):
    _seed_entries(store)
    retriever.rebuild_index()
    results = retriever.search("the", top_k=1)
    assert len(results) <= 1


def test_fts_search_filters_by_type(store, retriever):
    _seed_entries(store)
    retriever.rebuild_index()
    results = retriever.search(
        "input validate",
        filters=MemoryQuery(memory_type="gotcha"),
    )
    assert all(r.entry.memory_type == "gotcha" for r in results)


def test_fts_search_filters_by_category(store, retriever):
    _seed_entries(store)
    retriever.rebuild_index()
    results = retriever.search(
        "undo keyboard",
        filters=MemoryQuery(category="debugging"),
    )
    assert all(r.entry.category == "debugging" for r in results)


# ── Rebuild index ────────────────────────────────────────────────────────────


def test_rebuild_index_counts(store, retriever):
    _seed_entries(store)
    count = retriever.rebuild_index()
    assert count == 3


def test_rebuild_excludes_archived(store, retriever):
    _seed_entries(store)
    count = retriever.rebuild_index()
    assert count == 3


# ── Fallback to keyword search ───────────────────────────────────────────────


def test_keyword_fallback_when_no_fts(store, retriever, monkeypatch):
    _seed_entries(store)
    monkeypatch.setattr(retriever, "_fts_available", lambda: False)
    results = retriever.search("SQL injection")
    assert len(results) >= 1


# ── Ranking ──────────────────────────────────────────────────────────────────


def test_high_importance_ranked_higher(store, retriever):
    store.store(
        MemoryEntry(
            memory_id="hi",
            memory_type="lesson",
            category="general",
            content="Important security lesson about validation",
            lifecycle_state="ACTIVE",
            importance=0.95,
        )
    )
    store.store(
        MemoryEntry(
            memory_id="lo",
            memory_type="lesson",
            category="general",
            content="Low priority security note about validation",
            lifecycle_state="ACTIVE",
            importance=0.2,
        )
    )
    retriever.rebuild_index()
    results = retriever.search("security validation")
    if len(results) >= 2:
        assert results[0].entry.memory_id == "hi"


def test_relevance_score_is_bounded(store, retriever):
    _seed_entries(store)
    retriever.rebuild_index()
    results = retriever.search("SQL injection security")
    for r in results:
        assert 0.0 <= r.relevance_score <= 1.0
