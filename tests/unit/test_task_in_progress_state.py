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
