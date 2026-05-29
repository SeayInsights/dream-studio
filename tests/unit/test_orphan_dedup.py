"""Tests for core/memory/orphan_dedup.py — NULL-source_type orphan cleanup."""

from __future__ import annotations

import sqlite3

import pytest

from core.memory.orphan_dedup import (
    DedupResult,
    count_unmatched_nulls,
    dedup_orphans,
    find_orphan_candidates,
)

_SCHEMA = """
CREATE TABLE memory_entries (
    memory_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'unknown',
    category TEXT NOT NULL DEFAULT 'general',
    content TEXT NOT NULL,
    source_type TEXT,
    source_id TEXT,
    importance REAL NOT NULL DEFAULT 0.5,
    tags TEXT,
    project TEXT,
    skill TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    memory_id UNINDEXED, content, category, tags
);
"""


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    return conn


def _insert(conn, memory_id, content, source_type=None, source_id=None):
    conn.execute(
        "INSERT INTO memory_entries(memory_id, content, source_type, source_id) VALUES(?,?,?,?)",
        (memory_id, content, source_type, source_id),
    )
    conn.execute(
        "INSERT INTO memory_fts(memory_id, content, category, tags) VALUES(?,?,'general','')",
        (memory_id, content),
    )


class TestEmptyDb:
    def test_empty_db_returns_zeros(self):
        conn = _db()
        result = dedup_orphans(conn, dry_run=False)
        assert result == DedupResult(candidates_found=0, deleted=0, preserved_null=0)
        conn.close()


class TestAllNullNoKeyed:
    def test_null_entries_with_no_keyed_counterpart_are_preserved(self):
        conn = _db()
        _insert(conn, "n1", "content A")
        _insert(conn, "n2", "content B")
        _insert(conn, "n3", "content C")
        conn.commit()

        result = dedup_orphans(conn, dry_run=False)
        assert result.candidates_found == 0
        assert result.deleted == 0
        assert result.preserved_null == 3
        assert conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0] == 3
        conn.close()


class TestStandardCase:
    def test_null_entries_with_keyed_twins_are_deleted(self):
        conn = _db()
        # 3 keyed entries
        _insert(conn, "k1", "gotcha: avoid X", source_type="reg_gotchas", source_id="g1")
        _insert(conn, "k2", "gotcha: avoid Y", source_type="reg_gotchas", source_id="g2")
        _insert(conn, "k3", "gotcha: avoid Z", source_type="reg_gotchas", source_id="g3")
        # 3 NULL twins (identical content)
        _insert(conn, "n1", "gotcha: avoid X")
        _insert(conn, "n2", "gotcha: avoid Y")
        _insert(conn, "n3", "gotcha: avoid Z")
        conn.commit()

        result = dedup_orphans(conn, dry_run=False)
        assert result.candidates_found == 3
        assert result.deleted == 3
        assert result.preserved_null == 0
        assert result.errors == []

        remaining = conn.execute(
            "SELECT memory_id FROM memory_entries ORDER BY memory_id"
        ).fetchall()
        assert [r[0] for r in remaining] == ["k1", "k2", "k3"]

        # FTS should have been cleaned up
        fts_remaining = conn.execute(
            "SELECT memory_id FROM memory_fts ORDER BY memory_id"
        ).fetchall()
        assert [r[0] for r in fts_remaining] == ["k1", "k2", "k3"]
        conn.close()


class TestMixedCase:
    def test_only_matched_nulls_are_deleted(self):
        conn = _db()
        # 3 keyed entries
        _insert(conn, "k1", "content alpha", source_type="reg_gotchas", source_id="g1")
        _insert(conn, "k2", "content beta", source_type="raw_lessons", source_id="l1")
        _insert(conn, "k3", "content gamma", source_type="reg_gotchas", source_id="g3")
        # 3 NULL entries that match keyed content
        _insert(conn, "n1", "content alpha")
        _insert(conn, "n2", "content beta")
        _insert(conn, "n3", "content gamma")
        # 2 NULL entries with no match
        _insert(conn, "n4", "content delta — unique")
        _insert(conn, "n5", "content epsilon — unique")
        conn.commit()

        result = dedup_orphans(conn, dry_run=False)
        assert result.candidates_found == 3
        assert result.deleted == 3
        assert result.preserved_null == 2
        assert result.errors == []

        remaining_ids = sorted(
            r[0] for r in conn.execute("SELECT memory_id FROM memory_entries").fetchall()
        )
        assert remaining_ids == ["k1", "k2", "k3", "n4", "n5"]
        conn.close()


class TestIdempotency:
    def test_second_run_finds_zero_candidates(self):
        conn = _db()
        _insert(conn, "k1", "some content", source_type="reg_gotchas", source_id="g1")
        _insert(conn, "n1", "some content")
        conn.commit()

        first = dedup_orphans(conn, dry_run=False)
        assert first.deleted == 1

        second = dedup_orphans(conn, dry_run=False)
        assert second.candidates_found == 0
        assert second.deleted == 0
        conn.close()


class TestDryRunSafety:
    def test_dry_run_returns_count_without_deleting(self):
        conn = _db()
        _insert(conn, "k1", "same content", source_type="reg_gotchas", source_id="g1")
        _insert(conn, "n1", "same content")
        conn.commit()

        result = dedup_orphans(conn, dry_run=True)
        assert result.candidates_found == 1
        assert result.deleted == 0
        assert conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0] == 2
        conn.close()


class TestFindCandidates:
    def test_find_orphan_candidates_returns_memory_ids(self):
        conn = _db()
        _insert(conn, "k1", "X", source_type="reg_gotchas", source_id="g1")
        _insert(conn, "n1", "X")
        _insert(conn, "n2", "Y")  # no keyed twin — not a candidate
        conn.commit()

        candidates = find_orphan_candidates(conn)
        assert candidates == ["n1"]
        assert count_unmatched_nulls(conn) == 1
        conn.close()
