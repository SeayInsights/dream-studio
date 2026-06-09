"""Tests for DuckDB execution event projection (WO-TS3 task 7)."""

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

    def test_unknown_event_type_silent(self, tmp_path):
        conn = _db(tmp_path)
        result = dispatch_to_duckdb(_evt("unknown.x"), conn)
        conn.close()
        assert result == 0
