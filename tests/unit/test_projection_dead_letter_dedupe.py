"""Regression tests for issue #719 — stuck task events and the rows that count them.

WO c63cb42b-25d1-4f76-a781-f7ede555fd38.

Two defects behind one symptom, measured on the live authority: 96 active
dead-letter rows standing for only 36 distinct events, every one of them
``FOREIGN KEY constraint failed``.

* ``business_tasks`` declares a FK to ``business_projects``; ``business_work_orders``
  declares none. The same unvalidated project key is therefore accepted at one door
  and rejected at the other — 30 distinct project_ids in work orders against 8 real
  project rows — and 24 of the 36 stuck events carry the literal slug
  ``dream-studio`` where a UUID belongs.
* ``_dead_letter`` was a bare INSERT into a table with no unique constraint, beside a
  ``_schedule_retry`` that already used ON CONFLICT DO NOTHING, so every retry
  exhaustion appended another row for the same event.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

NOW = "2026-01-01T00:00:00.000000Z"
PROJECT_NAME = "Dream Studio"


@pytest.fixture
def db(tmp_path):
    """A bootstrapped authority with FK enforcement ON.

    SQLite defaults ``PRAGMA foreign_keys`` to OFF, which is why malformed keys
    reached the table at all; the projection path enforces them, so the test must.
    """
    path = tmp_path / "studio.db"
    bootstrap_database(path)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def _seed_project_and_wo(conn) -> tuple[str, str]:
    project_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, PROJECT_NAME, "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description,"
        "  work_order_type, status, created_at, updated_at)"
        " VALUES (?,?,NULL,?,?,?,'in_progress',?,?)",
        (work_order_id, project_id, "WO", "d", "infrastructure", NOW, NOW),
    )
    conn.commit()
    return project_id, work_order_id


def _created_event(task_id, work_order_id, project_key):
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "task.created",
        "event_timestamp": NOW,
        "payload": {"title": "T"},
        "trace": {},
        "task_id": task_id,
        "work_order_id": work_order_id,
        "project_id": project_key,
    }


def _apply(conn, event) -> int:
    from core.projections.task_projection import TaskProjection

    return TaskProjection().handle(event, conn)


# ── project-key resolution ────────────────────────────────────────────────────


def test_slug_project_key_resolves_to_the_registered_uuid(db):
    """The dream-studio case: 24 of the 36 stuck events carried this shape."""
    project_id, work_order_id = _seed_project_and_wo(db)
    task_id = str(uuid.uuid4())

    assert _apply(db, _created_event(task_id, work_order_id, "dream-studio")) == 1

    stored = db.execute(
        "SELECT project_id FROM business_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    assert stored is not None, "the task row must exist — this used to dead-letter"
    assert stored[0] == project_id, "the slug must resolve to the registered UUID"


def test_unknown_key_falls_back_to_the_work_orders_project(db):
    """A key that resolves to no project is taken from the work order on the event."""
    project_id, work_order_id = _seed_project_and_wo(db)
    task_id = str(uuid.uuid4())

    assert _apply(db, _created_event(task_id, work_order_id, "21800")) == 1

    stored = db.execute(
        "SELECT project_id FROM business_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    assert stored[0] == project_id


def test_an_unattributable_key_is_not_fabricated(db):
    """No work order, no matching project: the row must still fail, not be guessed.

    The 12 remaining stuck events are test-fixture residue whose projects were never
    registered. Silently reassigning them to a plausible project would be worse than
    leaving them stuck, so resolution returns the key unchanged and the FK still bites.
    """
    _seed_project_and_wo(db)
    task_id = str(uuid.uuid4())
    orphan_wo = str(uuid.uuid4())

    with pytest.raises(sqlite3.IntegrityError):
        _apply(db, _created_event(task_id, orphan_wo, str(uuid.uuid4())))


def test_a_registered_uuid_is_left_alone(db):
    """The ordinary path must not be rerouted by the resolver."""
    project_id, work_order_id = _seed_project_and_wo(db)
    task_id = str(uuid.uuid4())

    assert _apply(db, _created_event(task_id, work_order_id, project_id)) == 1

    stored = db.execute(
        "SELECT project_id FROM business_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    assert stored[0] == project_id


# ── dead-letter dedupe ────────────────────────────────────────────────────────


def _engine(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(tmp_path / "studio.db"))
    from core.config.database import DatabaseRuntime

    DatabaseRuntime.reset_instance()
    from core.projections.framework_engine import ProjectionEngine

    return ProjectionEngine()


def test_repeated_exhaustion_keeps_one_active_row_per_event(db, tmp_path, monkeypatch):
    """96 rows for 36 events: a second exhaustion must update, not append."""
    from core.config.database import DatabaseRuntime

    engine = _engine(tmp_path, monkeypatch)
    try:
        event_id = str(uuid.uuid4())
        engine._dead_letter("task_projection", event_id, "business", "first", "tb1", 3)
        engine._dead_letter("task_projection", event_id, "business", "second", "tb2", 4)

        rows = db.execute(
            "SELECT error_message, retry_count FROM projection_dead_letter"
            " WHERE event_id = ? AND projection_name = ? AND status = 'active'",
            (event_id, "task_projection"),
        ).fetchall()
        assert len(rows) == 1, f"one active row per stuck event, got {len(rows)}"
        assert rows[0][0] == "second", "the latest failure is what an operator acts on"
        assert rows[0][1] == 4
    finally:
        DatabaseRuntime.reset_instance()


def test_a_resolved_row_is_not_revived(db, tmp_path, monkeypatch):
    """An operator settled it, so a fresh failure opens a new row instead."""
    from core.config.database import DatabaseRuntime

    engine = _engine(tmp_path, monkeypatch)
    try:
        event_id = str(uuid.uuid4())
        engine._dead_letter("task_projection", event_id, "business", "first", "tb", 3)
        db.execute(
            "UPDATE projection_dead_letter SET status = 'resolved' WHERE event_id = ?",
            (event_id,),
        )
        db.commit()

        engine._dead_letter("task_projection", event_id, "business", "again", "tb", 3)

        statuses = [
            r[0]
            for r in db.execute(
                "SELECT status FROM projection_dead_letter WHERE event_id = ? ORDER BY id",
                (event_id,),
            ).fetchall()
        ]
        assert statuses == ["resolved", "active"], statuses
    finally:
        DatabaseRuntime.reset_instance()
