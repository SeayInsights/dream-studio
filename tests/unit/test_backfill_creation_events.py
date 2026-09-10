"""WO 17466550 task 2: the rows that predate the fix must survive a rebuild too.

Task 1 stopped the spawn path creating unreplayable rows. It did nothing for the 493 work
orders and 1706 tasks already in the authority with no creation event — and those are
still deleted by the recovery tool.

AS WITH TASK 1, THESE TESTS DRIVE A REAL REBUILD. Asserting that events were written
proves events were written; the claim is that the row COMES BACK, and only a replay shows
that. So each test runs the genuine `ProjectionEngine.rebuild()` against the genuine
projections, truncating `pre_rebuild` included.

Nothing here is stubbed: the backfill calls the ingestor's own `_write_to_dual_canonical`,
so these tests exercise production code end to end against a temporary authority.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.backfill_creation_events import RECONSTRUCTED_KEY, backfill

_THEN = "2026-01-15T08:30:00+00:00"


@pytest.fixture
def authority(tmp_path, monkeypatch):
    db_path = tmp_path / "studio.db"
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path))
    try:
        from core.config.database import DatabaseRuntime

        DatabaseRuntime.reset_instance()
    except Exception:
        pass
    bootstrap_database(db_path)
    yield db_path
    try:
        from core.config.database import DatabaseRuntime

        DatabaseRuntime.reset_instance()
    except Exception:
        pass


def _seed_eventless(db_path: Path) -> tuple[str, str, str]:
    """A work order and a task written straight into the projections, as history did."""
    project_id, milestone_id = str(uuid.uuid4()), str(uuid.uuid4())
    wo_id, task_id = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, status, created_at, updated_at)"
            " VALUES (?, 'T', 'active', ?, ?)",
            (project_id, _THEN, _THEN),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, 'M', 'active', ?, ?)",
            (milestone_id, project_id, _THEN, _THEN),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description,"
            "  work_order_type, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Historic work order', 'a description',"
            "  'infrastructure', 'created', ?, ?)",
            (wo_id, project_id, milestone_id, _THEN, _THEN),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            "  created_at, updated_at)"
            " VALUES (?, ?, ?, 'Historic task', 'task description', 'pending', ?, ?)",
            (task_id, wo_id, project_id, _THEN, _THEN),
        )
        conn.commit()
    finally:
        conn.close()
    return wo_id, task_id, project_id


def _rebuild(db_path: Path) -> None:
    from core.projections.framework_engine import ProjectionEngine
    from core.projections.task_projection import TaskProjection
    from core.projections.work_order_projection import WorkOrderProjection

    engine = ProjectionEngine(db_path=str(db_path))
    for proj in (WorkOrderProjection(), TaskProjection()):
        engine.register(proj)
        engine.rebuild(proj.name)


def _exists(db_path: Path, table: str, column: str, value: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(f"SELECT 1 FROM {table} WHERE {column} = ?", (value,)).fetchone()
    finally:
        conn.close()
    return row is not None


def test_without_the_backfill_a_historic_row_is_destroyed_by_a_rebuild(authority):
    """The defect this task exists for, shown going wrong first.

    If this ever passes without the backfill, the premise is gone and every other test
    here is measuring nothing.
    """
    wo_id, task_id, _ = _seed_eventless(authority)

    _rebuild(authority)

    assert not _exists(authority, "business_work_orders", "work_order_id", wo_id)
    assert not _exists(authority, "business_tasks", "task_id", task_id)


def test_a_backfilled_row_survives_a_rebuild(authority):
    """The claim: after the repair, the recovery tool stops destroying the record."""
    wo_id, task_id, _ = _seed_eventless(authority)

    report = backfill(db_path=authority, apply=True)
    assert report["ok"], report
    assert report["written"] == {"work_orders": 1, "tasks": 1}, report
    assert report["after"] == {"work_orders": 0, "tasks": 0}, report

    _rebuild(authority)

    assert _exists(authority, "business_work_orders", "work_order_id", wo_id)
    assert _exists(authority, "business_tasks", "task_id", task_id)


def test_a_dry_run_changes_nothing(authority):
    """It reports thousands of writes against a live authority; it must not do them."""
    _seed_eventless(authority)

    report = backfill(db_path=authority, apply=False)

    assert report["applied"] is False
    assert report["would_write"] == {"work_orders": 1, "tasks": 1}
    assert report["before"] == report["after"] == {"work_orders": 1, "tasks": 1}
    conn = sqlite3.connect(str(authority))
    try:
        events = conn.execute("SELECT COUNT(*) FROM business_canonical_events").fetchone()[0]
    finally:
        conn.close()
    assert events == 0, "a dry run wrote canonical events"


def test_running_it_twice_writes_nothing_the_second_time(authority):
    """Idempotent, because a half-finished repair will be re-run by someone."""
    _seed_eventless(authority)

    first = backfill(db_path=authority, apply=True)
    second = backfill(db_path=authority, apply=True)

    assert first["written"] == {"work_orders": 1, "tasks": 1}
    assert second["written"] == {"work_orders": 0, "tasks": 0}, second
    assert second["after"] == {"work_orders": 0, "tasks": 0}


def test_the_event_says_it_is_a_reconstruction_and_keeps_the_original_date(authority):
    """A synthetic event that passed as original would make the record lie about itself.

    The timestamp is the row's own `created_at`, not the repair time, so a replay
    reproduces the real order of history rather than collapsing it onto today.
    """
    wo_id, _, _ = _seed_eventless(authority)
    backfill(db_path=authority, apply=True)

    conn = sqlite3.connect(str(authority))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT payload, event_timestamp FROM business_canonical_events"
            " WHERE event_type = 'work_order.created' AND work_order_id = ?",
            (wo_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    import json

    payload = json.loads(row["payload"])
    assert payload.get(RECONSTRUCTED_KEY) is True, payload
    assert "reconstructed_at" in payload
    assert row["event_timestamp"] == _THEN, (
        "the event must carry the row's original created_at, not the repair time, or a "
        "replay reorders history"
    )


def test_a_row_that_already_has_an_event_is_left_alone(authority):
    """Only the gap is filled — an original event is never duplicated or overwritten."""
    wo_id, _, _ = _seed_eventless(authority)
    backfill(db_path=authority, apply=True)

    conn = sqlite3.connect(str(authority))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM business_canonical_events"
            " WHERE event_type = 'work_order.created' AND work_order_id = ?",
            (wo_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    backfill(db_path=authority, apply=True)

    conn = sqlite3.connect(str(authority))
    try:
        after = conn.execute(
            "SELECT COUNT(*) FROM business_canonical_events"
            " WHERE event_type = 'work_order.created' AND work_order_id = ?",
            (wo_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert count == 1
    assert after == 1, "a second run duplicated the creation event"
