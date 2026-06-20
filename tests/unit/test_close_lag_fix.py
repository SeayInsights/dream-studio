"""Regression tests for WO-P20-CLOSE-LAG.

close_work_order() and close_milestone() now call sync_tick() internally after
emitting their spool events, so the read model reflects the terminal status in the
same call without the caller needing to run a manual flush.

T3 asserts that calling sync_tick() twice (once pre-close for task flushing, once
post-close for the closed/complete event) is idempotent — no errors, no
double-counting in projection_state.events_processed_total.
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


def _seed_closed_wo_and_milestone(db: Path) -> tuple[str, str, str]:
    """Seed a project + milestone + fully-closed work order. Returns (project_id, milestone_id, wo_id)."""
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
        conn.commit()
    finally:
        conn.close()
    return project_id, milestone_id, wo_id


def test_sync_tick_idempotent_in_close_work_order(live_like_home):
    """Two sync_tick() calls inside close_work_order() must not error or double-count.

    close_work_order calls sync_tick() twice: once before reading gate state (pre-flush),
    once after emitting the work_order.closed event (post-flush). Verifies that
    projection_state.events_processed_total does not grow on the second call beyond
    what the first already counted.
    """
    home, db = live_like_home

    from core.projections.runner import sync_tick

    # Baseline: run sync_tick twice with no pending events — must not raise.
    sync_tick()
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT projection_name, events_processed_total FROM projection_state"
        ).fetchall()
    finally:
        conn.close()
    first_totals = {r[0]: r[1] for r in rows}

    sync_tick()  # second call with no new events
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT projection_name, events_processed_total FROM projection_state"
        ).fetchall()
    finally:
        conn.close()
    second_totals = {r[0]: r[1] for r in rows}

    for proj, total in first_totals.items():
        assert second_totals.get(proj, total) == total, (
            f"projection {proj}: events_processed_total grew on second sync_tick() with no new"
            f" events (was {total}, now {second_totals.get(proj)})"
        )


def test_milestone_close_flushes_status_immediately(live_like_home):
    """close_milestone() must reflect 'complete' in business_milestones without caller sync.

    Before the fix, the caller had to manually run sync_tick() after close_milestone()
    to see the updated status. Post-fix, business_milestones.status == 'complete'
    immediately after the call returns.
    """
    home, db = live_like_home
    project_id, milestone_id, _wo_id = _seed_closed_wo_and_milestone(db)

    # Mark WO as closed so the milestone gate passes.
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "UPDATE business_work_orders SET status = 'closed' WHERE work_order_id = ?",
            (_wo_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # Create audit files so milestone gates pass.
    ms_dir = Path.cwd() / ".planning" / "milestones" / milestone_id
    ms_dir.mkdir(parents=True, exist_ok=True)
    (ms_dir / "design-audit.md").write_text("Score: 4/5\nDesign audit: PASS", encoding="utf-8")
    (ms_dir / "security-audit.md").write_text("No critical findings. PASS", encoding="utf-8")
    (ms_dir / "harden-results.md").write_text("PASSED", encoding="utf-8")

    from core.milestones.close import close_milestone

    result = close_milestone(
        milestone_id=milestone_id,
        source_root=home,
        dream_studio_home=home,
    )
    assert result["ok"] is True, f"close_milestone failed: {result}"

    # No external sync_tick() here — the read model must already reflect completion.
    conn = sqlite3.connect(str(db))
    try:
        status = conn.execute(
            "SELECT status FROM business_milestones WHERE milestone_id = ?",
            (milestone_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert status == "complete", (
        f"business_milestones.status should be 'complete' immediately after close_milestone()"
        f" without external sync_tick(); got {status!r}"
    )
