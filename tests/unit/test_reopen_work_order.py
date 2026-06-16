"""Coverage for core.work_orders.mutations.reopen_work_order (cd5b6e20).

reopen_work_order is the designated business-state writer that the outcome eval
uses to set a regressed closed WO back to in_progress (instead of a raw write
from the eval layer — dependency Rule 3). These tests exercise its behavior
directly: the status transition, the returned previous_status, and the
not-found path.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.mutations import reopen_work_order

NOW = "2026-01-01T00:00:00+00:00"


def _seed_closed_wo(db_path: Path) -> str:
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    wo = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (project_id, "Test", "", "active", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
            "  status, closed_at, created_at, updated_at, last_updated_at)"
            " VALUES (?,?,?,?,?,?, 'closed', ?, ?, ?, ?)",
            (wo, project_id, milestone_id, "Closed WO", "d", "infrastructure", NOW, NOW, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return wo


def _status(db_path: Path, wo: str) -> str:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT status FROM business_work_orders WHERE work_order_id = ?", (wo,)
        ).fetchone()[0]
    finally:
        conn.close()


def test_reopen_work_order_sets_in_progress(tmp_path: Path) -> None:
    """A closed WO is set back to in_progress; result reports the previous status."""
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    wo = _seed_closed_wo(db)
    assert _status(db, wo) == "closed"

    result = reopen_work_order(
        work_order_id=wo,
        reason="outcome regressed",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )

    assert result["ok"] is True
    assert result["status"] == "in_progress"
    assert result["previous_status"] == "closed"
    assert _status(db, wo) == "in_progress"


def test_reopen_work_order_not_found(tmp_path: Path) -> None:
    """Reopening an unknown work order returns ok=False without raising."""
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)

    result = reopen_work_order(
        work_order_id="does-not-exist",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )

    assert result["ok"] is False
    assert "not found" in result["error"].lower()
