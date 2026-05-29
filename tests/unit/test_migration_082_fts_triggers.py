"""Tests for migration 082: defensive restoration of memory_entries FTS triggers."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _run_full_migrations(tmp_path: Path) -> sqlite3.Connection:
    from core.event_store.studio_db import _connect, _run_migrations

    db = tmp_path / "test.db"
    with _connect(db) as conn:
        _run_migrations(conn)
        conn.commit()
    return sqlite3.connect(str(db))


_EXPECTED_TRIGGERS = {
    "memory_entries_fts_insert",
    "memory_entries_fts_update",
    "memory_entries_fts_delete",
}


def test_migration_082_restores_fts_triggers(tmp_path):
    """Fresh DB ends with all 3 memory_fts triggers present after full migration run."""
    conn = _run_full_migrations(tmp_path)
    triggers = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='trigger' AND name LIKE 'memory_entries_fts%'"
        ).fetchall()
    }
    conn.close()
    assert triggers == _EXPECTED_TRIGGERS, f"Missing triggers: {_EXPECTED_TRIGGERS - triggers}"


def test_migration_082_idempotent(tmp_path):
    """Running migrations twice does not error on existing triggers."""
    from core.event_store.studio_db import _connect, _run_migrations

    db = tmp_path / "test.db"
    with _connect(db) as conn:
        _run_migrations(conn)
        conn.commit()
    # Second run is a no-op on the already-migrated DB
    with _connect(db) as conn:
        _run_migrations(conn)
        conn.commit()

    conn2 = sqlite3.connect(str(db))
    triggers = {
        row[0]
        for row in conn2.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='trigger' AND name LIKE 'memory_entries_fts%'"
        ).fetchall()
    }
    conn2.close()
    assert triggers == _EXPECTED_TRIGGERS


def test_migration_082_triggers_fire_correctly(tmp_path):
    """After migration 082, INSERT/DELETE on memory_entries syncs to memory_fts."""
    conn = _run_full_migrations(tmp_path)

    # Insert a row into memory_entries
    conn.execute(
        "INSERT INTO memory_entries(memory_id, source, category, content, created_at) "
        "VALUES ('m1', 'gotcha', 'general', 'test content', datetime('now'))"
    )
    conn.commit()

    # Trigger should have synced to memory_fts
    fts_row = conn.execute(
        "SELECT memory_id FROM memory_fts WHERE memory_id = 'm1'"
    ).fetchone()
    assert fts_row is not None, "Insert trigger did not sync to memory_fts"

    # Delete the row
    conn.execute("DELETE FROM memory_entries WHERE memory_id = 'm1'")
    conn.commit()

    # Delete trigger should have removed from memory_fts
    fts_row_after = conn.execute(
        "SELECT memory_id FROM memory_fts WHERE memory_id = 'm1'"
    ).fetchone()
    assert fts_row_after is None, "Delete trigger did not remove from memory_fts"

    conn.close()
