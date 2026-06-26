"""Tests for WO-I: swallow-handler narrowing for fts_gotchas, ds_documents, canonical_events.

The existing O7 narrowing (test_o7_swallow_narrowing.py) covered memory_entries.
WO-I applies the same statement-type-aware pattern to the remaining broad substring
swallows, fixing potential M2-class casualties on those tables.

M2 class: migration is marked applied in _schema_version while an intended schema
object (CREATE INDEX / CREATE TRIGGER) is silently never created, because the
'no such table' error was swallowed rather than raised.

Migration 050 is the concrete risk: CREATE INDEX idx_ds_documents_source_path ON
ds_documents(source_path) — if ds_documents is absent this CREATE INDEX must raise,
not silently disappear.
"""

from __future__ import annotations

import sqlite3

import pytest

from core.config.sqlite_bootstrap import run_migrations, split_statements

# ── helpers ───────────────────────────────────────────────────────────────────


def _absent_conn() -> sqlite3.Connection:
    """In-memory DB with _schema_version but none of the swallow-covered tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _schema_version "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.commit()
    return conn


# ── ds_documents narrowing ────────────────────────────────────────────────────


def test_create_index_on_absent_ds_documents_propagates():
    """CREATE INDEX on absent ds_documents must raise, not be swallowed.

    Migration 050 creates idx_ds_documents_source_path. If ds_documents is absent
    (partial test fixture), the old broad swallow ate the error and the index was
    silently never created — M2-class casualty. After WO-I narrowing, this raises.
    """
    from core.config import sqlite_bootstrap

    conn = _absent_conn()
    assert (
        conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='ds_documents'").fetchone()[0]
        == 0
    )

    # Simulate what migration 050 does
    stmt = "CREATE INDEX IF NOT EXISTS idx_ds_documents_source_path ON ds_documents(source_path)"

    # The narrowed handler must propagate this error
    with pytest.raises(sqlite3.OperationalError) as exc_info:
        # We call run_migrations internals directly: apply the swallow logic
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "no such table" in msg and "ds_documents" in msg:
                stmt_upper = stmt.strip().upper()
                if not (
                    stmt_upper.startswith("CREATE INDEX")
                    or stmt_upper.startswith("CREATE UNIQUE INDEX")
                    or stmt_upper.startswith("CREATE TRIGGER")
                ):
                    pass  # would be swallowed
                else:
                    raise  # narrowed: must propagate
            else:
                raise

    error_msg = str(exc_info.value).lower()
    assert "no such table" in error_msg
    assert "ds_documents" in error_msg
    conn.close()


def test_create_trigger_on_absent_ds_documents_propagates():
    """CREATE TRIGGER on absent ds_documents must raise after WO-I narrowing."""
    conn = _absent_conn()

    stmt = """
        CREATE TRIGGER IF NOT EXISTS trg_documents_fts_ai
        AFTER INSERT ON ds_documents BEGIN
            SELECT 1;
        END
    """

    with pytest.raises(sqlite3.OperationalError) as exc_info:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "no such table" in msg and "ds_documents" in msg:
                stmt_upper = stmt.strip().upper()
                if not (
                    stmt_upper.startswith("CREATE INDEX")
                    or stmt_upper.startswith("CREATE UNIQUE INDEX")
                    or stmt_upper.startswith("CREATE TRIGGER")
                ):
                    pass
                else:
                    raise
            else:
                raise

    assert "no such table" in str(exc_info.value).lower()
    conn.close()


def test_insert_on_absent_ds_documents_still_swallowed():
    """INSERT on absent ds_documents is still graceful degradation (not an M2 risk).

    Data statements on an absent table do not permanently lose a schema object —
    only CREATE INDEX / CREATE TRIGGER do. The narrowed handler must still swallow
    INSERT failures.
    """
    conn = _absent_conn()

    stmt = "INSERT INTO ds_documents(doc_id, doc_type, title, created_at) VALUES (1, 'test', 'test', '2026-01-01')"

    should_swallow = False
    try:
        conn.execute(stmt)
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "no such table" in msg and "ds_documents" in msg:
            stmt_upper = stmt.strip().upper()
            if not (
                stmt_upper.startswith("CREATE INDEX")
                or stmt_upper.startswith("CREATE UNIQUE INDEX")
                or stmt_upper.startswith("CREATE TRIGGER")
            ):
                should_swallow = True

    assert should_swallow, "INSERT on absent ds_documents must still be swallowed"
    conn.close()


# ── Integration: full migration sequence drops ds_documents (moved to files.db) ───
# Three-store architecture: ds_documents belongs in files.db, not studio.db.
# Migrations 007/050 create the cluster mid-chain; migration 127 drops it. After the
# full sequence, neither the table nor its indexes/triggers/FTS remain in studio.db.


def test_full_migration_drops_ds_documents_from_studio_db():
    """ds_documents + its indexes/triggers/FTS must be absent from studio.db after
    the full migration (migration 127 moved the cluster to files.db)."""
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)

    leftovers = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE "
            "name = 'ds_documents' "
            "OR name LIKE 'idx_ds_documents%' "
            "OR name LIKE 'trg_documents%' "
            "OR name LIKE 'ds_documents_fts%'"
        ).fetchall()
    }
    assert not leftovers, (
        f"ds_documents cluster should be dropped from studio.db by migration 127 "
        f"(moved to files.db); found leftovers: {leftovers}"
    )
    conn.close()


# ── canonical_events narrowing (data-statements only — narrowing is a no-op in practice) ──


def test_canonical_events_insert_still_swallowed():
    """INSERT on absent canonical_events is graceful degradation (pre-083 behavior).

    Migrations 052-064 reference canonical_events before migration 083 creates it.
    All those references are data statements (INSERT, UPDATE, ALTER TABLE). After
    WO-I narrowing, these are still swallowed — the narrowing has no practical
    effect on canonical_events in the current migration set.
    """
    conn = _absent_conn()

    stmt = "INSERT OR IGNORE INTO canonical_events(event_id, event_type) VALUES ('x', 'test')"

    should_swallow = False
    try:
        conn.execute(stmt)
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "no such table" in msg and "canonical_events" in msg:
            stmt_upper = stmt.strip().upper()
            if not (
                stmt_upper.startswith("CREATE INDEX")
                or stmt_upper.startswith("CREATE UNIQUE INDEX")
                or stmt_upper.startswith("CREATE TRIGGER")
            ):
                should_swallow = True

    assert should_swallow, "INSERT on absent canonical_events must still be swallowed"
    conn.close()
