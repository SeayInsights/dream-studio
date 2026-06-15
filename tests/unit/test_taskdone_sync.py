"""Regression test for WO-TASKDONE-SYNC.

mark_task_done() emits a task.completed spool event but historically did NOT call
_sync_tick() — unlike its sibling mutations (create_task, create_work_order,
block/unblock, milestone mutations). The business_tasks read model therefore
reported a stale 'pending' status until some unrelated operation triggered a
projection sync, misleading `ds work-order tasks` and the close-gate task view.

This test asserts the fix: after mark_task_done() returns, business_tasks.status
reflects 'complete' with NO external sync_tick() call by the caller.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

NOW = "2026-01-01T00:00:00.000000Z"


def _reset_db_runtime() -> None:
    from core.config.database import DatabaseRuntime

    DatabaseRuntime.reset_instance()


@pytest.fixture
def live_like_home(tmp_path, monkeypatch):
    """A bootstrapped studio.db wired as the resolved authority for both the
    mutation (via dream_studio_home → sqlite_path) and the projection engine
    (via DREAM_STUDIO_DB_PATH + DS_SPOOL_ROOT + a DatabaseRuntime singleton reset),
    so the mutation's internal sync_tick() reads/writes this temp DB, not the live one.
    """
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    _reset_db_runtime()
    bootstrap_database(db)
    yield tmp_path, db
    _reset_db_runtime()


def _seed_pending_task(db) -> tuple[str, str]:
    """Seed a project, milestone, work order, and a single pending task.

    Returns (work_order_id, task_id).
    """
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
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
            " VALUES (?,?,?,?,?,?,'in_progress',1,?,?,?)",
            (
                work_order_id,
                project_id,
                milestone_id,
                "Test WO",
                "desc",
                "infrastructure",
                NOW,
                NOW,
                NOW,
            ),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,'pending',?,?)",
            (task_id, work_order_id, project_id, "T1", "do it", NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return work_order_id, task_id


def test_mark_task_done_syncs_status_without_external_tick(live_like_home):
    """mark_task_done() must materialize the 'complete' status itself.

    The caller does NOT run sync_tick() — the mutation is responsible for it,
    mirroring create_task/create_work_order. Pre-fix this fails (status stays
    'pending'); post-fix it passes.
    """
    home, db = live_like_home
    work_order_id, task_id = _seed_pending_task(db)

    from core.work_orders.mutations import mark_task_done

    result = mark_task_done(
        work_order_id=work_order_id,
        task_id=task_id,
        source_root=home,
        dream_studio_home=home,
    )
    assert result["ok"] is True, f"mark_task_done failed: {result}"

    # No external sync_tick() here — the read model must already reflect completion.
    conn = sqlite3.connect(str(db))
    try:
        status = conn.execute(
            "SELECT status FROM business_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert status == "complete", (
        f"business_tasks.status should be 'complete' immediately after mark_task_done"
        f" with no external sync_tick(); got {status!r}"
    )
