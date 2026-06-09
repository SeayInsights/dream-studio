"""Substrate policy H4: read-after-write correctness under projection lag.

These tests verify the canonical-events fallback in close_milestone.
The setup deliberately mirrors the real failure mode:
  - business_work_orders shows stale state (projection not yet applied)
  - business_canonical_events holds the authoritative closed event

Each test writes events directly to business_canonical_events and does NOT
run the projection runner.  The function under test must handle the lag.

As new projections land (18.2.3+), add the corresponding writer→reader
chains to this file following the same pattern.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_PROJECT_ID = "proj-h4-test-00000000"
_MILESTONE_ID = "ms-h4-test-000000000"
_WO_CLOSED = "wo-h4-stale-000000000"
_WO_GENUINELY_OPEN = "wo-h4-open-000000000"
_NOW = "2026-05-23T12:00:00+00:00"


@pytest.fixture()
def db_home(tmp_path, monkeypatch):
    from core.config.sqlite_bootstrap import bootstrap_database

    db_path = tmp_path / "state" / "studio.db"
    bootstrap_database(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, 'H4 Test Milestone', 'active', ?, ?)",
            (_MILESTONE_ID, _PROJECT_ID, _NOW, _NOW),
        )
        # WO that is canonically closed but still in_progress in the projection.
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, status,"
            "  work_order_type, created_at, last_updated_at)"
            " VALUES (?, ?, ?, 'Stale WO', 'in_progress',"
            "  'api_endpoint', ?, ?)",
            (_WO_CLOSED, _PROJECT_ID, _MILESTONE_ID, _NOW, _NOW),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    return tmp_path


def _insert_closed_event(db_home: Path, work_order_id: str) -> None:
    """Write a work_order.closed canonical event without running the projection."""
    db_path = db_home / "state" / "studio.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_canonical_events"
            " (event_id, event_type, event_timestamp, work_order_id,"
            "  milestone_id, project_id, trace, payload)"
            " VALUES (?, 'work_order.closed', ?, ?, ?, ?, '{}', ?)",
            (
                str(uuid.uuid4()),
                _NOW,
                work_order_id,
                _MILESTONE_ID,
                _PROJECT_ID,
                json.dumps(
                    {
                        "work_order_id": work_order_id,
                        "title": "Stale WO",
                        "project_id": _PROJECT_ID,
                        "forced": False,
                    }
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _call_close_milestone(db_home: Path, force: bool = True) -> dict:
    from core.milestones.close import close_milestone

    return close_milestone(
        milestone_id=_MILESTONE_ID,
        force=force,
        source_root=REPO_ROOT,
        dream_studio_home=db_home,
        planning_root=db_home / ".planning",
    )


class TestCloseMilestoneH4:
    def test_fails_when_wo_in_projection_and_no_canonical_event(self, db_home):
        """Baseline: stale projection with no canonical event → milestone close is correctly blocked."""
        result = _call_close_milestone(db_home)
        assert result["ok"] is False
        assert "open work orders remain" in result["error"]
        open_ids = [r["work_order_id"] for r in result["open_work_orders"]]
        assert _WO_CLOSED in open_ids

    def test_passes_when_wo_stale_in_projection_but_closed_in_canonical(self, db_home):
        """H4-2 fix: canonical-events fallback allows milestone close despite projection lag."""
        _insert_closed_event(db_home, _WO_CLOSED)
        result = _call_close_milestone(db_home, force=True)
        assert result["ok"] is True, f"Expected ok=True but got: {result}"
        assert result["milestone_id"] == _MILESTONE_ID

    def test_partially_stale_projection_blocks_on_genuinely_open_wo(self, db_home):
        """Fallback only removes canonically-closed WOs; genuinely open WOs still block."""
        db_path = db_home / "state" / "studio.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO business_work_orders"
                " (work_order_id, project_id, milestone_id, title, status,"
                "  work_order_type, created_at, last_updated_at)"
                " VALUES (?, ?, ?, 'Genuinely Open WO', 'in_progress',"
                "  'api_endpoint', ?, ?)",
                (_WO_GENUINELY_OPEN, _PROJECT_ID, _MILESTONE_ID, _NOW, _NOW),
            )
            conn.commit()
        finally:
            conn.close()

        _insert_closed_event(db_home, _WO_CLOSED)

        result = _call_close_milestone(db_home)
        assert result["ok"] is False
        open_ids = [r["work_order_id"] for r in result["open_work_orders"]]
        assert _WO_GENUINELY_OPEN in open_ids
        assert _WO_CLOSED not in open_ids


# ── Phase 18.2.3 task writer→reader chains ───────────────────────────────────


class TestTaskH4:
    """H4 substrate: create_task / mark_task_done under TaskProjection lag.

    Phase 18.2.3 removed direct writes from create_task() and mark_task_done().
    Both functions now emit canonical events only; TaskProjection materialises the
    rows asynchronously.  These tests document the resulting lag contract:

      - create_task()   → task.created emitted; business_tasks row NOT written yet
      - mark_task_done() → reads from business_tasks; fails when row absent

    No canonical-events fallback was added to mark_task_done() in this phase;
    callers must allow the projection to run before attempting to mark tasks done.
    """

    def test_create_task_does_not_write_row_directly(self, db_home):
        """create_task() emits task.created event; business_tasks row is absent
        until TaskProjection applies the event."""
        from core.work_orders.mutations import create_task

        result = create_task(
            work_order_id=_WO_CLOSED,
            project_id=_PROJECT_ID,
            title="Read-after-write test task",
            source_root=REPO_ROOT,
            dream_studio_home=db_home,
        )
        assert result["ok"] is True
        task_id = result["task_id"]

        db_path = db_home / "state" / "studio.db"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT task_id FROM business_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        finally:
            conn.close()
        assert row is None, "business_tasks row must not be written synchronously"

    def test_mark_task_done_fails_when_task_not_yet_projected(self, db_home):
        """mark_task_done() reads business_tasks; fails with 'Task not found'
        when the task.created event has not yet been applied by TaskProjection."""
        from core.work_orders.mutations import create_task, mark_task_done

        result = create_task(
            work_order_id=_WO_CLOSED,
            project_id=_PROJECT_ID,
            title="Lag test task",
            source_root=REPO_ROOT,
            dream_studio_home=db_home,
        )
        assert result["ok"] is True
        task_id = result["task_id"]

        done = mark_task_done(
            work_order_id=_WO_CLOSED,
            task_id=task_id,
            source_root=REPO_ROOT,
            dream_studio_home=db_home,
        )
        assert done["ok"] is False
        assert "not found" in done["error"].lower()

    def test_mark_task_done_succeeds_after_projection_applied(self, db_home):
        """Once TaskProjection has materialised the row in business_tasks,
        mark_task_done() emits task.completed and returns ok=True."""
        from core.work_orders.mutations import mark_task_done

        task_id = str(uuid.uuid4())
        db_path = db_home / "state" / "studio.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO business_tasks"
                " (task_id, work_order_id, project_id, title, status, created_at, updated_at)"
                " VALUES (?, ?, ?, 'Projected task', 'pending', ?, ?)",
                (task_id, _WO_CLOSED, _PROJECT_ID, _NOW, _NOW),
            )
            conn.commit()
        finally:
            conn.close()

        done = mark_task_done(
            work_order_id=_WO_CLOSED,
            task_id=task_id,
            source_root=REPO_ROOT,
            dream_studio_home=db_home,
        )
        assert done["ok"] is True
        assert done["status"] == "complete"
        # DB row is NOT updated directly — MilestoneProjection owns the write.
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT status FROM business_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        finally:
            conn.close()
        assert row[0] == "pending", "DB row must remain pending until TaskProjection runs"
