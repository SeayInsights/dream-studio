"""TA6 End-to-end attribution test: full chain from SDLC hierarchy to token.consumed event.

Proves that token.consumed events emitted via the PostToolUse hook carry
attribution_status: "fully_attributed" when an active task is set, and that
the task_id → work_order_id → milestone_id → project_id chain is consistent
across canonical_events and the ds_* tables.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Source root: 4 levels up from tests/integration/spool/
_SOURCE_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bootstrap_db(db_path: Path) -> None:
    """Create a fully-migrated test DB at db_path."""
    from core.config.sqlite_bootstrap import run_migrations

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        run_migrations(conn)
    finally:
        conn.close()


def _insert_project(conn: sqlite3.Connection, project_id: str, name: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO ds_projects (project_id, name, status, created_at, updated_at)"
        " VALUES (?, ?, 'active', ?, ?)",
        (project_id, name, now, now),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ta6_db(tmp_path, monkeypatch):
    """Fully-migrated isolated DB with DREAM_STUDIO_DB_PATH and DREAM_STUDIO_HOME set.

    Both env vars are needed:
    - DREAM_STUDIO_DB_PATH: used by _default_db_path() → set_active_task(),
      get_connection() in attribution queries, and ingestor fallback.
    - DREAM_STUDIO_HOME: used by resolve_installed_runtime_paths() in
      _require_db() inside milestone/work-order mutations. The sqlite_path
      it derives is dream_studio_home / "state" / "studio.db".
    Both are pointed at the same DB file so all callers share state.
    """
    ds_home = tmp_path / "ds_home"
    state_dir = ds_home / "state"
    state_dir.mkdir(parents=True)
    db_path = state_dir / "studio.db"

    _bootstrap_db(db_path)

    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(ds_home))

    # Reset the DatabaseRuntime singleton so it picks up the new DREAM_STUDIO_DB_PATH.
    from core.config.database import DatabaseRuntime

    DatabaseRuntime.reset_instance()

    yield db_path

    # Clean up singleton after test so later tests start fresh.
    DatabaseRuntime.reset_instance()


@pytest.fixture()
def sdlc_hierarchy(ta6_db):
    """Create a full project → milestone → work_order → task hierarchy.

    Returns a dict with all four IDs and the db_path.
    Uses direct SQL for the project row (no CLI dependency), then the
    canonical mutation functions for milestone, work order, and task.
    """
    db_path = ta6_db

    # 1. Project (inserted directly — no mutation function for projects).
    project_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        _insert_project(conn, project_id, "TA6 Integration Test Project")
    finally:
        conn.close()

    # 2. Milestone via canonical mutation.
    from core.milestones.mutations import create_milestone

    ms_result = create_milestone(
        project_id=project_id,
        title="TA6 Test Milestone",
        source_root=_SOURCE_ROOT,
    )
    assert ms_result["ok"], f"create_milestone failed: {ms_result}"
    milestone_id = ms_result["milestone_id"]

    # 3. Work order via canonical mutation.
    from core.work_orders.mutations import create_work_order

    wo_result = create_work_order(
        project_id=project_id,
        milestone_id=milestone_id,
        title="TA6 Test Work Order",
        source_root=_SOURCE_ROOT,
    )
    assert wo_result["ok"], f"create_work_order failed: {wo_result}"
    work_order_id = wo_result["work_order_id"]

    # 4. Task via canonical mutation.
    from core.work_orders.mutations import create_task

    task_result = create_task(
        work_order_id=work_order_id,
        project_id=project_id,
        title="TA6 test task",
        source_root=_SOURCE_ROOT,
    )
    assert task_result["ok"], f"create_task failed: {task_result}"
    task_id = task_result["task_id"]

    return {
        "project_id": project_id,
        "milestone_id": milestone_id,
        "work_order_id": work_order_id,
        "task_id": task_id,
        "db_path": db_path,
    }


# ---------------------------------------------------------------------------
# PostToolUse payload factory
# ---------------------------------------------------------------------------


def _make_post_tool_use_payload(session_id: str = "sess_ta6_test") -> dict:
    return {
        "tool_name": "Read",
        "tool_use_id": f"toolu_{uuid.uuid4().hex[:12]}",
        "tool_input": {"file_path": "relative/path.py"},
        "tool_response": "file contents",
        "is_error": False,
        "session_id": session_id,
        "model": "claude-sonnet-4-6",
        "usage": {
            "input_tokens": 500,
            "output_tokens": 200,
            "cache_creation_input_tokens": 50,
            "cache_read_input_tokens": 25,
        },
    }


# ---------------------------------------------------------------------------
# Test 1: Full chain — token.consumed lands fully_attributed
# ---------------------------------------------------------------------------


def test_token_consumed_fully_attributed_when_active_task_set(spool_root, sdlc_hierarchy):
    """Full chain: SDLC hierarchy → active task → PostToolUse → ingest → fully_attributed.

    Asserts:
    - token.consumed event exists in canonical_events
    - trace["attribution_status"] == "fully_attributed"
    - trace carries the full SDLC chain (task, work_order, milestone, project)
    - attribution_coverage() reports fully_attributed_pct > 0
    - token_spend_by_task() reports total_tokens == 700 (500 + 200)
    """
    from core.sdlc.active_task import clear_active_task, set_active_task
    from core.telemetry.token_capture import handle_post_tool_use
    from projections.api.queries.token_attribution import (
        attribution_coverage,
        token_spend_by_task,
    )
    from spool.ingestor import ingest_pending

    project_id = sdlc_hierarchy["project_id"]
    milestone_id = sdlc_hierarchy["milestone_id"]
    work_order_id = sdlc_hierarchy["work_order_id"]
    task_id = sdlc_hierarchy["task_id"]
    db_path = sdlc_hierarchy["db_path"]

    # Set active task — resolves chain from DB.
    ctx = set_active_task(task_id)
    assert ctx.task_id == task_id
    assert ctx.work_order_id == work_order_id
    assert ctx.milestone_id == milestone_id
    assert ctx.project_id == project_id

    try:
        # Emit token.consumed via PostToolUse handler.
        payload = _make_post_tool_use_payload()
        handle_post_tool_use(payload)

        # Brief pause to ensure spool file is flushed to disk.
        time.sleep(0.3)

        # Ingest spool → canonical_events.
        ingest_pending(root=spool_root, db_path=db_path)

        # Query canonical_events for our token.consumed event.
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT event_id, event_type, payload, trace"
                " FROM canonical_events"
                " WHERE event_type = 'token.consumed'"
                "   AND json_extract(trace, '$.task_id') = ?",
                (task_id,),
            ).fetchall()
        finally:
            conn.close()

        assert len(rows) >= 1, (
            f"Expected at least one token.consumed row for task_id={task_id}; "
            f"found none. Spool root: {spool_root}"
        )

        row = rows[0]
        assert row["event_type"] == "token.consumed"

        trace = json.loads(row["trace"])
        assert (
            trace["attribution_status"] == "fully_attributed"
        ), f"Expected fully_attributed, got: {trace['attribution_status']}"
        assert trace["task_id"] == task_id
        assert trace["work_order_id"] == work_order_id
        assert trace["milestone_id"] == milestone_id
        assert trace["project_id"] == project_id

        # Attribution coverage query.
        coverage = attribution_coverage(project_id=project_id)
        assert coverage["total_events"] > 0, "attribution_coverage returned 0 events"
        assert (
            coverage["fully_attributed_pct"] > 0
        ), f"Expected fully_attributed_pct > 0; got: {coverage}"

        # Token spend query.
        spend = token_spend_by_task(task_id)
        assert spend["total_tokens"] > 0, "token_spend_by_task returned 0 tokens"
        assert (
            spend["total_tokens"] == 700
        ), f"Expected total_tokens == 700 (500 input + 200 output); got: {spend['total_tokens']}"

    finally:
        clear_active_task()


# ---------------------------------------------------------------------------
# Test 2: Hierarchical chain resolves consistently across ds_* tables
# ---------------------------------------------------------------------------


def test_attribution_chain_resolves_task_to_project(spool_root, sdlc_hierarchy):
    """Verify task_id → work_order_id → milestone_id → project_id chain is consistent.

    After a token.consumed event is ingested, query canonical_events for the
    trace fields and verify each ID maps correctly in the corresponding ds_*
    table, proving the attribution resolution is end-to-end correct.
    """
    from core.sdlc.active_task import clear_active_task, set_active_task
    from core.telemetry.token_capture import handle_post_tool_use
    from spool.ingestor import ingest_pending

    project_id = sdlc_hierarchy["project_id"]
    milestone_id = sdlc_hierarchy["milestone_id"]
    work_order_id = sdlc_hierarchy["work_order_id"]
    task_id = sdlc_hierarchy["task_id"]
    db_path = sdlc_hierarchy["db_path"]

    set_active_task(task_id)

    try:
        handle_post_tool_use(_make_post_tool_use_payload(session_id="sess_ta6_chain"))
        time.sleep(0.3)
        ingest_pending(root=spool_root, db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            # 1. Retrieve the token.consumed event from canonical_events.
            event_row = conn.execute(
                "SELECT trace FROM canonical_events"
                " WHERE event_type = 'token.consumed'"
                "   AND json_extract(trace, '$.task_id') = ?",
                (task_id,),
            ).fetchone()
            assert event_row is not None, f"No token.consumed event found for task_id={task_id}"

            trace = json.loads(event_row["trace"])
            ev_task_id = trace["task_id"]
            ev_work_order_id = trace["work_order_id"]
            ev_milestone_id = trace["milestone_id"]
            ev_project_id = trace["project_id"]

            # All IDs must match what we created.
            assert ev_task_id == task_id
            assert ev_work_order_id == work_order_id
            assert ev_milestone_id == milestone_id
            assert ev_project_id == project_id

            # 2. ds_tasks row exists and links to the correct work order.
            task_row = conn.execute(
                "SELECT task_id, work_order_id, project_id" " FROM ds_tasks WHERE task_id = ?",
                (ev_task_id,),
            ).fetchone()
            assert task_row is not None, f"ds_tasks has no row for task_id={ev_task_id}"
            assert task_row["work_order_id"] == ev_work_order_id, (
                f"ds_tasks.work_order_id mismatch: "
                f"{task_row['work_order_id']} != {ev_work_order_id}"
            )
            assert task_row["project_id"] == ev_project_id

            # 3. ds_work_orders row exists and links to the correct milestone.
            wo_row = conn.execute(
                "SELECT work_order_id, milestone_id, project_id"
                " FROM ds_work_orders WHERE work_order_id = ?",
                (ev_work_order_id,),
            ).fetchone()
            assert (
                wo_row is not None
            ), f"ds_work_orders has no row for work_order_id={ev_work_order_id}"
            assert wo_row["milestone_id"] == ev_milestone_id, (
                f"ds_work_orders.milestone_id mismatch: "
                f"{wo_row['milestone_id']} != {ev_milestone_id}"
            )
            assert wo_row["project_id"] == ev_project_id

            # 4. ds_milestones row exists and links to the correct project.
            ms_row = conn.execute(
                "SELECT milestone_id, project_id" " FROM ds_milestones WHERE milestone_id = ?",
                (ev_milestone_id,),
            ).fetchone()
            assert (
                ms_row is not None
            ), f"ds_milestones has no row for milestone_id={ev_milestone_id}"
            assert ms_row["project_id"] == ev_project_id, (
                f"ds_milestones.project_id mismatch: " f"{ms_row['project_id']} != {ev_project_id}"
            )

            # 5. ds_projects row exists.
            proj_row = conn.execute(
                "SELECT project_id FROM ds_projects WHERE project_id = ?",
                (ev_project_id,),
            ).fetchone()
            assert proj_row is not None, f"ds_projects has no row for project_id={ev_project_id}"

        finally:
            conn.close()

    finally:
        clear_active_task()
