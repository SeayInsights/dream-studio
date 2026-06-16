"""Unit coverage for the tasks_done close gate's projection-lag defense (T2).

WO-TASKS-DONE-ENFORCE adds a `tasks_done` gate to ``close_work_order``: a WO with
any task that is not done cannot close without ``force=True``. Because task
completion is event-sourced (``mark_task_done`` emits ``task.completed`` then ticks
the projection), close must run a projection tick BEFORE reading task statuses —
otherwise a freshly marked-done task could be misread as still-pending and wrongly
block the close.

``test_sync_tick_before_status_read`` proves the ordering: sync_tick is patched to
flip the WO's only task from ``pending`` to ``complete`` in the read model. If close
reads task statuses *after* sync_tick, it sees ``complete`` and closes; if it read
*before*, it would see ``pending`` and block. A clean close is therefore proof that
the tick runs first.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from unittest.mock import MagicMock, patch

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-01-01T00:00:00.000000Z"


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


@contextmanager
def _patch_db(db_path: Path):
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        yield


def _seed_wo_with_pending_task(db_path: Path) -> tuple[str, str, str]:
    """Seed project + milestone + cleanup WO + one PENDING task carrying a passing
    SQL-CHECK AC (so the always-on executable-AC gate is satisfied and the only
    thing standing between us and a clean close is the tasks_done gate).

    Returns (project_id, work_order_id, task_id).
    """
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects"
            " (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (project_id, "Test", "", "active", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description,"
            "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
            " VALUES (?,?,?,?,?,'cleanup','in_progress',1,?,?,?)",
            (work_order_id, project_id, milestone_id, "Test WO", "desc", NOW, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description,"
            "  acceptance_criteria, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,'pending',?,?)",
            (
                task_id,
                work_order_id,
                project_id,
                "T1",
                "do it",
                (
                    "SQL-CHECK: SELECT COUNT(*) FROM business_projects"
                    f" WHERE project_id='{project_id}'"
                ),
                NOW,
                NOW,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id, work_order_id, task_id


def test_sync_tick_before_status_read(tmp_path: Path) -> None:
    """close_work_order runs sync_tick() before reading task statuses (T2).

    AC: tests/unit/test_tasks_done_gate.py::test_sync_tick_before_status_read
    """
    db_path = _make_db(tmp_path)
    _project_id, work_order_id, task_id = _seed_wo_with_pending_task(db_path)
    planning_root = tmp_path / "planning"

    called = {"n": 0}

    def _fake_sync_tick() -> None:
        # Stand in for the real projection cycle: flip the task to complete in the
        # read model. If close reads statuses AFTER this runs, the WO closes cleanly.
        called["n"] += 1
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE business_tasks SET status = 'complete' WHERE task_id = ?",
                (task_id,),
            )
            conn.commit()
        finally:
            conn.close()

    with (
        _patch_db(db_path),
        patch("core.projections.runner.sync_tick", side_effect=_fake_sync_tick),
    ):
        from core.work_orders.close import close_work_order

        result = close_work_order(
            work_order_id=work_order_id,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=False,
        )

    assert called["n"] >= 1, "close_work_order must call sync_tick() at least once"
    assert result["ok"] is True, (
        "Expected a clean close: sync_tick flipped the task to complete before the "
        f"status read, so tasks_done should not block. Got: {result}"
    )
    assert result["status"] == "closed"

    # And the read model agrees the task is done.
    conn = sqlite3.connect(str(db_path))
    try:
        status = conn.execute(
            "SELECT status FROM business_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert status == "complete"
