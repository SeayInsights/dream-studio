"""WO-P20-CLOSE-LAG eval suite (WO 3ae8c557).

close_work_order() and close_milestone() call sync_tick() internally after emitting
their spool events, so the read model reflects the terminal status in the same call
— the caller does not need a manual flush. These are the AC-named eval-path tests
(test_close_flushes_projection / test_milestone_close_flushes_projection /
test_sync_tick_idempotent); they supersede the earlier misnamed
tests/unit/test_close_lag_fix.py so the pre-push eval gate can find them by the
names the acceptance criteria specify.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

NOW = "2026-01-01T00:00:00.000000Z"


def _reset_db_runtime() -> None:
    from core.config.database import DatabaseRuntime

    DatabaseRuntime.reset_instance()


@pytest.fixture
def live_like_home(tmp_path, monkeypatch):
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    _reset_db_runtime()
    bootstrap_database(db)
    yield tmp_path, db
    _reset_db_runtime()


def _seed_project_milestone_wo(db: Path) -> tuple[str, str, str]:
    """Seed a project + milestone + a work order (status 'created'). Returns ids."""
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    wo_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
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
            " VALUES (?,?,?,?,?,?,'created',1,?,?,?)",
            (wo_id, project_id, milestone_id, "Test WO", "desc", "infrastructure", NOW, NOW, NOW),
        )
        # One complete task with a passing executable AC so the close gates
        # (tasks_done, executable_ac) are satisfiable without force.
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            "  created_at, updated_at, acceptance_criteria)"
            " VALUES (?,?,?,?,?,'complete',?,?,?)",
            (str(uuid.uuid4()), wo_id, project_id, "T1", "do it", NOW, NOW, "SQL-CHECK: SELECT 1"),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id, milestone_id, wo_id


def _status(db: Path, table: str, id_col: str, id_val: str) -> str:
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(
            f"SELECT status FROM {table} WHERE {id_col} = ?", (id_val,)  # noqa: S608 - fixed idents
        ).fetchone()[0]
    finally:
        conn.close()


def test_close_flushes_projection(live_like_home, monkeypatch):
    """close_work_order() must reflect 'closed' in business_work_orders without the
    caller running a manual sync_tick(). Mock graders keep the independent-review
    gate deterministic; the WO-P20-CLOSE-LAG fix flushes the projection in-call."""
    monkeypatch.setenv("DREAM_STUDIO_VERIFY_MOCK", "1")
    home, db = live_like_home
    _project_id, _milestone_id, wo_id = _seed_project_milestone_wo(db)

    from core.work_orders.close import close_work_order

    result = close_work_order(
        work_order_id=wo_id,
        source_root=home,
        dream_studio_home=home,
        planning_root=home / ".planning",
    )
    assert result["ok"] is True, f"close_work_order failed: {result}"

    # No external sync_tick() — the read model must already reflect the closure.
    assert _status(db, "business_work_orders", "work_order_id", wo_id) == "closed", (
        "business_work_orders.status should be 'closed' immediately after close_work_order()"
        " without an external sync_tick()"
    )


def test_milestone_close_flushes_projection(live_like_home):
    """close_milestone() must reflect 'complete' in business_milestones without the
    caller running a manual sync_tick()."""
    home, db = live_like_home
    _project_id, milestone_id, wo_id = _seed_project_milestone_wo(db)

    # Close the WO so the milestone completion gate passes.
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "UPDATE business_work_orders SET status = 'closed' WHERE work_order_id = ?", (wo_id,)
        )
        conn.commit()
    finally:
        conn.close()

    # Milestone-close gate artifacts.
    ms_dir = Path.cwd() / ".planning" / "milestones" / milestone_id
    ms_dir.mkdir(parents=True, exist_ok=True)
    (ms_dir / "design-audit.md").write_text("Score: 4/5\nDesign audit: PASS", encoding="utf-8")
    (ms_dir / "security-audit.md").write_text("No critical findings. PASS", encoding="utf-8")
    (ms_dir / "harden-results.md").write_text("PASSED", encoding="utf-8")

    from core.milestones.close import close_milestone

    result = close_milestone(milestone_id=milestone_id, source_root=home, dream_studio_home=home)
    assert result["ok"] is True, f"close_milestone failed: {result}"

    assert _status(db, "business_milestones", "milestone_id", milestone_id) == "complete", (
        "business_milestones.status should be 'complete' immediately after close_milestone()"
        " without an external sync_tick()"
    )


def test_sync_tick_idempotent(live_like_home):
    """Two sync_tick() calls with no new pending events must not raise and must not
    grow projection_state.events_processed_total on the second call."""
    _home, db = live_like_home

    from core.projections.runner import sync_tick

    def _totals() -> dict[str, int]:
        conn = sqlite3.connect(str(db))
        try:
            return {
                r[0]: r[1]
                for r in conn.execute(
                    "SELECT projection_name, events_processed_total FROM projection_state"
                ).fetchall()
            }
        finally:
            conn.close()

    sync_tick()
    first = _totals()
    sync_tick()  # second call, no new events
    second = _totals()

    for proj, total in first.items():
        assert second.get(proj, total) == total, (
            f"projection {proj}: events_processed_total grew on the second sync_tick() with no"
            f" new events (was {total}, now {second.get(proj)})"
        )
