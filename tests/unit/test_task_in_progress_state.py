"""Tasks have a middle state, so something can be in progress.

WHY IT HAD TO EXIST. Tasks went ``created -> complete`` with nothing between, so at any
instant the authority could not answer "what is being worked on right now" — and token
spend could be charged to a work order and no further, because no task claimed to be
running.

``task.started`` was already a registered event type, described in the registry as "Work
began on a task". The schema anticipated the state for as long as the registry has
existed; nothing ever emitted it.
"""

from __future__ import annotations

import sqlite3
import uuid
from unittest import mock

import pytest

from core.work_orders.mutations import start_task


@pytest.fixture
def authority(tmp_path):
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE business_tasks (task_id TEXT PRIMARY KEY, work_order_id TEXT,
          project_id TEXT, title TEXT, description TEXT, status TEXT,
          created_at TEXT, updated_at TEXT, acceptance_criteria TEXT);
        CREATE TABLE business_work_orders (work_order_id TEXT PRIMARY KEY,
          milestone_id TEXT, project_id TEXT, status TEXT, title TEXT, description TEXT);
        """)
    conn.execute(
        "INSERT INTO business_work_orders VALUES (?,?,?,?,?,?)",
        ("wo-1", "ms-1", "p-1", "in_progress", "T", "D"),
    )
    tasks = [str(uuid.uuid4()) for _ in range(2)]
    for t in tasks:
        conn.execute(
            "INSERT INTO business_tasks VALUES (?,?,?,?,?,?,?,?,?)",
            (t, "wo-1", "p-1", f"task {t[:4]}", "", "created", "n", "n", "TEST-CHECK: x"),
        )
    conn.commit()
    conn.close()
    return db, tasks


def _start(db, tmp_path, task_id, work_order_id="wo-1"):
    with mock.patch("core.work_orders.mutations._require_db", return_value=db):
        return start_task(work_order_id=work_order_id, task_id=task_id, source_root=tmp_path)


def test_a_started_task_is_in_progress(authority, tmp_path):
    db, (t1, _) = authority
    result = _start(db, tmp_path, t1)
    assert result["ok"] is True
    assert result["status"] == "in_progress"
    status = (
        sqlite3.connect(db)
        .execute("SELECT status FROM business_tasks WHERE task_id = ?", (t1,))
        .fetchone()[0]
    )
    assert status == "in_progress"


def test_starting_twice_is_not_an_error(authority, tmp_path):
    """A mutation that raised on a retry would make a lost response worse than it is."""
    db, (t1, _) = authority
    _start(db, tmp_path, t1)
    again = _start(db, tmp_path, t1)
    assert again["ok"] is True
    assert again["already"] is True


def test_a_second_in_progress_task_is_reported_not_refused(authority, tmp_path):
    """Several tasks in progress is a real state — the model advances more than one in a
    turn — and refusing the second would push callers into not recording the first. What
    the caller gets is the ambiguity, stated."""
    db, (t1, t2) = authority
    assert _start(db, tmp_path, t1)["siblings_in_progress"] == 0
    assert _start(db, tmp_path, t2)["siblings_in_progress"] == 1


def test_a_task_from_another_work_order_is_refused(authority, tmp_path):
    db, (t1, _) = authority
    result = _start(db, tmp_path, t1, work_order_id="wo-other")
    assert result["ok"] is False
    assert "belongs to work order" in result["error"]


def test_a_complete_task_cannot_be_restarted(authority, tmp_path):
    db, (t1, _) = authority
    conn = sqlite3.connect(db)
    conn.execute("UPDATE business_tasks SET status='complete' WHERE task_id=?", (t1,))
    conn.commit()
    conn.close()
    result = _start(db, tmp_path, t1)
    assert result["ok"] is False
    assert "already complete" in result["error"]


def test_the_event_type_was_registered_all_along():
    """The schema anticipated this state; the mutation never provided it."""
    from canonical.events.types import EventType

    assert EventType.TASK_STARTED.value == "task.started"


# ── the projection reproduces the state, and does not reverse a finished one ──


def _projected_status(tmp_path, events):
    """Replay `events` through the real TaskProjection and return the row's status.

    The real projection, not a stand-in: the defect this covers was that
    `task.started` was emitted, written directly to the row, and consumed by nothing --
    so the row and a rebuild of the same history disagreed. Only running the handler
    can show that.
    """
    import sqlite3 as _sqlite3

    from core.projections.task_projection import TaskProjection

    db = tmp_path / "projected.db"
    conn = _sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE business_tasks (task_id TEXT PRIMARY KEY, work_order_id TEXT,
          project_id TEXT, title TEXT, description TEXT, status TEXT,
          created_at TEXT, updated_at TEXT, acceptance_criteria TEXT,
          source_event_id TEXT, last_event_id TEXT);
        """)
    projection = TaskProjection()
    for index, event_type in enumerate(events):
        projection.handle(
            {
                "event_id": f"e{index}",
                "event_type": event_type,
                "event_timestamp": "2026-09-22T00:00:00+00:00",
                # Denormalized onto the canonical row, which is where the projection
                # reads them from -- not out of the payload.
                "task_id": "t-1",
                "work_order_id": "wo-1",
                "project_id": "p-1",
                "payload": {"title": "A task"},
            },
            conn,
        )
    conn.commit()
    row = conn.execute("SELECT status FROM business_tasks WHERE task_id = 't-1'").fetchone()
    conn.close()
    return row[0] if row else None


def test_a_rebuild_reproduces_the_started_state(tmp_path):
    """The row and a replay of its own history have to agree.

    `start_task` wrote `in_progress` and emitted `task.started`; the projection consumed
    no such event, so a rebuild dropped the task back to `pending` and the authority's
    answer depended on whether anyone had rebuilt it.
    """
    assert _projected_status(tmp_path, ["task.created", "task.started"]) == "in_progress"


def test_a_late_start_does_not_un_finish_a_completed_task(tmp_path):
    """The only backward transition in this projection, so the only guarded one.

    Every other event here moves a task toward a terminal state, which makes applying one
    twice or out of order harmless. A `task.started` replayed after the completion it
    preceded is not harmless: it would return a finished task to `in_progress`, and the
    rebuild would contradict the history it was built from.
    """
    assert _projected_status(tmp_path, ["task.created", "task.completed", "task.started"]) == (
        "complete"
    )


@pytest.mark.parametrize("terminal_event", ["task.cancelled", "task.deleted"])
def test_a_late_start_does_not_revive_an_abandoned_task(tmp_path, terminal_event):
    """Cancelled and deleted are as finished as complete.

    Guarding on `!= 'complete'` would have let a late start revive an abandoned task --
    the same distinction WO 654a54d7 found on work orders, where a cancelled one read as
    reopened and had its delivery boundary widened to HEAD.
    """
    status = _projected_status(tmp_path, ["task.created", terminal_event, "task.started"])
    assert status != "in_progress", f"a late start revived a {terminal_event} task"
