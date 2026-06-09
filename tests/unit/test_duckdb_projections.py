"""Tests for DuckDB milestone, project, work order, task, and design brief projections (WO-TS3)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema  # noqa: E402
from core.projections.duckdb_projections import dispatch_to_duckdb  # noqa: E402


def _db(tmp_path: Path):
    db = tmp_path / "agg.db"
    conn = connect_analytics(db, read_only=False)
    ensure_analytics_schema(conn)
    return conn


def _evt(event_type, **kwargs):
    base = {
        "event_id": "evt-001",
        "event_type": event_type,
        "event_timestamp": "2026-01-01T00:00:00",
        "trace": {},
        "payload": {},
    }
    base.update(kwargs)
    return base


class TestMilestoneProjection:
    def test_created(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "milestone.created",
                event_id="e1",
                milestone_id="ms-1",
                project_id="p1",
                payload={"title": "Alpha", "order_index": 2},
            ),
            conn,
        )
        row = conn.execute(
            "SELECT title, status, order_index FROM duckdb_milestones WHERE milestone_id='ms-1'"
        ).fetchone()
        conn.close()
        assert row[0] == "Alpha" and row[1] == "pending" and row[2] == 2

    def test_completed(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "milestone.created",
                event_id="e1",
                milestone_id="ms-2",
                project_id="p",
                payload={"title": "B"},
            ),
            conn,
        )
        dispatch_to_duckdb(
            _evt("milestone.completed", event_id="e2", milestone_id="ms-2", project_id="p"), conn
        )
        row = conn.execute(
            "SELECT status FROM duckdb_milestones WHERE milestone_id='ms-2'"
        ).fetchone()
        conn.close()
        assert row[0] == "complete"

    def test_idempotent_insert(self, tmp_path):
        conn = _db(tmp_path)
        evt = _evt(
            "milestone.created",
            event_id="e1",
            milestone_id="ms-3",
            project_id="p",
            payload={"title": "X"},
        )
        dispatch_to_duckdb(evt, conn)
        dispatch_to_duckdb(evt, conn)
        count = conn.execute("SELECT COUNT(*) FROM duckdb_milestones").fetchone()[0]
        conn.close()
        assert count == 1

    def test_no_milestone_id_returns_zero(self, tmp_path):
        conn = _db(tmp_path)
        result = dispatch_to_duckdb(_evt("milestone.created", event_id="e1"), conn)
        conn.close()
        assert result == 0


class TestProjectProjection:
    def test_created(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt("project.created", event_id="e1", project_id="proj-a", payload={"name": "Studio"}),
            conn,
        )
        row = conn.execute(
            "SELECT name, status FROM duckdb_projects WHERE project_id='proj-a'"
        ).fetchone()
        conn.close()
        assert row[0] == "Studio" and row[1] == "active"

    def test_deleted(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt("project.created", event_id="e1", project_id="proj-b", payload={"name": "B"}), conn
        )
        dispatch_to_duckdb(_evt("project.deleted", event_id="e2", project_id="proj-b"), conn)
        row = conn.execute(
            "SELECT status FROM duckdb_projects WHERE project_id='proj-b'"
        ).fetchone()
        conn.close()
        assert row[0] == "deleted"

    def test_unknown_event_type_silent(self, tmp_path):
        conn = _db(tmp_path)
        result = dispatch_to_duckdb(_evt("unknown.x"), conn)
        conn.close()
        assert result == 0


class TestWorkOrderProjection:
    def test_created_and_closed(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "work_order.created",
                event_id="e1",
                work_order_id="wo-1",
                project_id="p",
                milestone_id="ms",
                payload={"title": "Do X", "work_order_type": "infrastructure"},
            ),
            conn,
        )
        dispatch_to_duckdb(
            _evt("work_order.closed", event_id="e2", work_order_id="wo-1"),
            conn,
        )
        row = conn.execute(
            "SELECT title, status, work_order_type FROM duckdb_work_orders WHERE work_order_id='wo-1'"
        ).fetchone()
        conn.close()
        assert row[0] == "Do X"
        assert row[1] == "closed"
        assert row[2] == "infrastructure"

    def test_started(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt("work_order.created", event_id="e1", work_order_id="wo-2", payload={"title": "Y"}),
            conn,
        )
        dispatch_to_duckdb(_evt("work_order.started", event_id="e2", work_order_id="wo-2"), conn)
        row = conn.execute(
            "SELECT status FROM duckdb_work_orders WHERE work_order_id='wo-2'"
        ).fetchone()
        conn.close()
        assert row[0] == "active"

    def test_no_work_order_id_returns_zero(self, tmp_path):
        conn = _db(tmp_path)
        result = dispatch_to_duckdb(_evt("work_order.created", event_id="e1"), conn)
        conn.close()
        assert result == 0


class TestTaskProjection:
    def test_created_and_done(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "task.created",
                event_id="e1",
                task_id="t-1",
                work_order_id="wo-1",
                project_id="p",
                payload={"title": "Task A"},
            ),
            conn,
        )
        dispatch_to_duckdb(_evt("task.done", event_id="e2", task_id="t-1"), conn)
        row = conn.execute("SELECT title, status FROM duckdb_tasks WHERE task_id='t-1'").fetchone()
        conn.close()
        assert row[0] == "Task A"
        assert row[1] == "complete"

    def test_deleted(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "task.created",
                event_id="e1",
                task_id="t-2",
                work_order_id="wo",
                project_id="p",
                payload={"title": "B"},
            ),
            conn,
        )
        dispatch_to_duckdb(_evt("task.deleted", event_id="e2", task_id="t-2"), conn)
        row = conn.execute("SELECT status FROM duckdb_tasks WHERE task_id='t-2'").fetchone()
        conn.close()
        assert row[0] == "deleted"


class TestDesignBriefProjection:
    def test_created(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "design_brief.created",
                event_id="e1",
                brief_id="br-1",
                project_id="proj-1",
                payload={"purpose": "Sell widgets", "audience": "Consumers"},
            ),
            conn,
        )
        row = conn.execute(
            "SELECT status, purpose, audience FROM duckdb_design_briefs WHERE brief_id='br-1'"
        ).fetchone()
        conn.close()
        assert row[0] == "draft"
        assert row[1] == "Sell widgets"
        assert row[2] == "Consumers"

    def test_updated_allowed_field(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "design_brief.created",
                event_id="e1",
                brief_id="br-2",
                project_id="proj-1",
                payload={"purpose": "Original"},
            ),
            conn,
        )
        dispatch_to_duckdb(
            _evt(
                "design_brief.updated",
                event_id="e2",
                brief_id="br-2",
                payload={"field": "tone", "value": "Professional"},
            ),
            conn,
        )
        row = conn.execute("SELECT tone FROM duckdb_design_briefs WHERE brief_id='br-2'").fetchone()
        conn.close()
        assert row[0] == "Professional"

    def test_updated_disallowed_field_is_noop(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "design_brief.created",
                event_id="e1",
                brief_id="br-3",
                project_id="proj-1",
                payload={"purpose": "Stay"},
            ),
            conn,
        )
        dispatch_to_duckdb(
            _evt(
                "design_brief.updated",
                event_id="e2",
                brief_id="br-3",
                payload={"field": "status", "value": "hacked"},
            ),
            conn,
        )
        row = conn.execute(
            "SELECT status FROM duckdb_design_briefs WHERE brief_id='br-3'"
        ).fetchone()
        conn.close()
        assert row[0] == "draft"

    def test_locked(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "design_brief.created",
                event_id="e1",
                brief_id="br-4",
                project_id="proj-1",
                payload={},
            ),
            conn,
        )
        dispatch_to_duckdb(
            _evt("design_brief.locked", event_id="e2", brief_id="br-4"),
            conn,
        )
        row = conn.execute(
            "SELECT status FROM duckdb_design_briefs WHERE brief_id='br-4'"
        ).fetchone()
        conn.close()
        assert row[0] == "locked"

    def test_no_brief_id_returns_zero(self, tmp_path):
        conn = _db(tmp_path)
        result = dispatch_to_duckdb(_evt("design_brief.created", event_id="e1"), conn)
        conn.close()
        assert result == 0


class TestExecutionEventProjection:
    def test_execution_started_inserted(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "execution.started",
                event_id="exec-1",
                session_id="sess-1",
                trace={"project_id": "proj-1", "skill_id": "sk-1"},
                payload={"event_name": "skill_invoke"},
            ),
            conn,
        )
        row = conn.execute(
            "SELECT event_type, event_name, project_id, skill_id, outcome_status"
            " FROM duckdb_execution_events WHERE event_id='exec-1'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "execution.started"
        assert row[1] == "skill_invoke"
        assert row[2] == "proj-1"
        assert row[3] == "sk-1"
        assert row[4] is None

    def test_execution_completed_captures_outcome(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "execution.completed",
                event_id="exec-2",
                trace={"project_id": "proj-2", "tool_id": "tool-x"},
                payload={"event_name": "tool_use", "outcome_status": "success"},
            ),
            conn,
        )
        row = conn.execute(
            "SELECT outcome_status, tool_id FROM duckdb_execution_events WHERE event_id='exec-2'"
        ).fetchone()
        conn.close()
        assert row[0] == "success"
        assert row[1] == "tool-x"

    def test_execution_failed_creates_row(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "execution.failed",
                event_id="exec-3",
                trace={"workflow_id": "wf-1"},
                payload={"event_name": "workflow_run", "outcome_status": "error"},
            ),
            conn,
        )
        row = conn.execute(
            "SELECT event_type, outcome_status FROM duckdb_execution_events WHERE event_id='exec-3'"
        ).fetchone()
        conn.close()
        assert row[0] == "execution.failed"
        assert row[1] == "error"

    def test_dispatch_routes_execution_event(self, tmp_path):
        conn = _db(tmp_path)
        result = dispatch_to_duckdb(
            _evt("execution.started", event_id="exec-4", payload={"event_name": "hook_run"}),
            conn,
        )
        conn.close()
        assert result == 1

    def test_non_execution_event_not_routed(self, tmp_path):
        conn = _db(tmp_path)
        result = dispatch_to_duckdb(
            _evt("tool.execution.completed", event_id="exec-5"),
            conn,
        )
        conn.close()
        assert result == 0
