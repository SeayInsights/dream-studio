"""WO-GATE-HARDEN-CLEANUP: three LOW-severity hardening fixes from the milestone
audit sign-offs.

1. `_find_migration_files` rejects path-traversal in untrusted git-diff filenames.
2. `mark_escalated` raises RuntimeError (not AssertionError) when the row is
   unreadable after the upsert.
3. studio_db read helpers close their connection even when the query raises.
"""

from __future__ import annotations

import sqlite3

import pytest

from core.config.sqlite_bootstrap import bootstrap_database


def test_find_migration_files_rejects_path_traversal(tmp_path) -> None:
    from core.work_orders.verify import _find_migration_files

    migrations = tmp_path / "core" / "event_store" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "099_legit.sql").write_text("-- legit", encoding="utf-8")
    # A real file OUTSIDE the migrations dir that a traversal would resolve to.
    (tmp_path / "outside.sql").write_text("-- escaped", encoding="utf-8")

    diff = (
        "core/event_store/migrations/099_legit.sql\n"
        "core/event_store/migrations/../../../outside.sql\n"
    )
    found = _find_migration_files(tmp_path, diff)

    names = {p.name for p in found}
    assert "099_legit.sql" in names
    # The traversal target is a real file but lives outside the migrations dir:
    # it must be rejected by the containment check.
    assert "outside.sql" not in names
    migrations_resolved = migrations.resolve()
    assert all(p.resolve().is_relative_to(migrations_resolved) for p in found)


def test_mark_escalated_raises_runtimeerror_when_row_missing(tmp_path, monkeypatch) -> None:
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)

    from core.work_orders import escalation

    # Simulate the DB becoming unreadable between the upsert and the re-read.
    monkeypatch.setattr(escalation, "read_escalation", lambda wo, *, db_path: None)

    with pytest.raises(RuntimeError):
        escalation.mark_escalated("wo-missing", db_path=db, reason="not fixed")


def test_read_helper_closes_connection_on_query_error(tmp_path, monkeypatch) -> None:
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)

    import core.event_store.studio_db as sdb

    real_connect = sdb._connect
    closed = {"count": 0}

    class _TrackingConn:
        def __init__(self, conn: sqlite3.Connection) -> None:
            self._conn = conn

        def execute(self, *_a, **_k):
            raise sqlite3.OperationalError("forced failure mid-read")

        def close(self) -> None:
            closed["count"] += 1
            self._conn.close()

    monkeypatch.setattr(sdb, "_connect", lambda p=None: _TrackingConn(real_connect(p)))

    # The read helper swallows the exception and returns its default ...
    assert sdb.last_run("any-workflow", db_path=db) is None
    # ... but the connection must still have been closed (try/finally fix).
    assert closed["count"] == 1
