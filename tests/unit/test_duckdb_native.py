"""WO-DUCKDB-REAL (derived-only reframe): the analytics store must be a NATIVE
DuckDB file, and a wrong-format file must be rejected loudly rather than opened
silently via DuckDB's SQLite compat layer.

Operator decision 2026-07-04: DuckDB stays derived-analytics only; business
entity authority stays in studio.db (T3/T4 mirror tasks cancelled). These tests
cover the store-hardening scope: native format (T1) and fail-loud (T2).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.analytics.duckdb_store import (
    AnalyticsStoreFormatError,
    AnalyticsStoreMissingError,
    _ensure_native_duckdb,
    connect_analytics,
    ensure_analytics_schema,
)


def _magic(path: Path) -> bytes:
    return path.read_bytes()[:16]


class TestNativeDuckDB:
    def test_analytics_file_is_native_duckdb(self, tmp_path):
        """A freshly created analytics store is a native DuckDB file (DUCK magic
        at offset 8), never a SQLite file."""
        db = tmp_path / "aggregate_metrics.db"
        conn = connect_analytics(db, read_only=False)
        ensure_analytics_schema(conn)
        conn.close()

        head = _magic(db)
        assert b"DUCK" in head, f"analytics store is not native DuckDB: header={head!r}"
        assert not head.startswith(b"SQLite format 3"), "analytics store is a SQLite file"

    def test_read_only_missing_store_raises_and_creates_no_file(self, tmp_path):
        """read_only=True on an absent store raises AnalyticsStoreMissingError and
        fabricates NO file. A read path must never manufacture an empty store — an
        empty DuckDB would serve zero-row analytics as if they were real ("no cost /
        no findings" instead of "analytics not built yet"). Only the write path
        (read_only=False, the projection runner) creates the store."""
        db = tmp_path / "ro.db"
        with pytest.raises(AnalyticsStoreMissingError):
            connect_analytics(db, read_only=True)
        assert not db.exists(), "read-only connect must not create the store file"

    def test_write_open_creates_native_store(self, tmp_path):
        """read_only=False (the sole store-creating path) yields a native DuckDB file."""
        db = tmp_path / "rw.db"
        connect_analytics(db, read_only=False).close()
        assert b"DUCK" in _magic(db)


class TestFailLoud:
    def test_sqlite_file_rejected(self, tmp_path):
        """A SQLite file masquerading at the DuckDB path is deleted and recreated
        native — never opened via DuckDB's SQLite compat layer (the row-store bug)."""
        db = tmp_path / "aggregate_metrics.db"
        # Plant a real SQLite database at the analytics path.
        sq = sqlite3.connect(str(db))
        sq.execute("CREATE TABLE legacy_masquerade (x INTEGER)")
        sq.commit()
        sq.close()
        assert _magic(db).startswith(b"SQLite format 3")

        conn = connect_analytics(db, read_only=False)
        ensure_analytics_schema(conn)
        # Its table did NOT survive (proof it was not opened via the SQLite compat layer).
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
        conn.close()  # release the DuckDB file lock before reading magic bytes (Windows)
        assert "legacy_masquerade" not in tables
        # The SQLite masquerade was replaced by a native DuckDB store.
        assert b"DUCK" in _magic(db)

    def test_corrupt_file_raises_fail_loud(self, tmp_path):
        """A file that is neither SQLite nor DuckDB is rejected with a clear,
        actionable error instead of a cryptic open failure or a silent None."""
        db = tmp_path / "corrupt.db"
        db.write_bytes(b"\x00\x01\x02not-a-database-at-all\xff\xff")

        with pytest.raises(AnalyticsStoreFormatError) as exc:
            connect_analytics(db, read_only=False)
        assert "not a native DuckDB store" in str(exc.value)
        assert "delete" in str(exc.value).lower()

    def test_ensure_native_noops_on_absent_and_empty(self, tmp_path):
        """Absent and empty files are left for DuckDB to initialise (no raise)."""
        absent = tmp_path / "absent.db"
        _ensure_native_duckdb(absent)  # no-op, no raise

        empty = tmp_path / "empty.db"
        empty.write_bytes(b"")
        _ensure_native_duckdb(empty)  # no-op, no raise


class TestRunnerResilience:
    def test_runner_open_returns_none_and_warns_on_wrong_format(
        self, tmp_path, monkeypatch, caplog
    ):
        """The projection runner stays resilient (returns None, never crashes the
        SDLC write path) on a wrong-format store, but logs the rejection LOUD."""
        import logging

        from core.analytics import duckdb_store
        from core.projections.runner import ProjectionRunner

        db = tmp_path / "aggregate_metrics.db"
        db.write_bytes(b"\x00\x01\x02not-a-database\xff")
        monkeypatch.setattr(duckdb_store, "analytics_db_path", lambda: db)

        with caplog.at_level(logging.WARNING):
            conn = ProjectionRunner._open_analytics_conn()

        assert conn is None  # resilient — no crash on the write path
        assert any(
            "rejected" in r.message.lower() for r in caplog.records
        ), "wrong-format store must be logged LOUD (WARNING), not silently swallowed"
