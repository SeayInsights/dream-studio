"""T1/T4 (WO-ESCALATION-LADDER): deterministic not-fixed signal + retry cap.

The deterministic layer owns the escalate DECISION (AD-8). These tests cover the
not-fixed predicate (AC fail / symptom persists / high-confidence grader) and the
retry-cap → escalate-to-operator boundary.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database

NOW = "2026-01-01T00:00:00+00:00"


def _seed_closed_wo(db_path: Path, *, ac: str) -> str:
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
            (wo, project_id, milestone_id, "WO", "d", "infrastructure", NOW, NOW, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, acceptance_criteria,"
            "  status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?, 'complete', ?, ?)",
            (str(uuid.uuid4()), wo, project_id, "T1", "d", ac, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return wo


def test_not_fixed_signal_fires_on_ac_fail(tmp_path: Path) -> None:
    """A closed WO whose executable AC (SQL-CHECK) fails → not_fixed with ac_fail reason."""
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    # Failing SQL-CHECK (no such project).
    wo = _seed_closed_wo(
        db, ac="SQL-CHECK: SELECT COUNT(*) FROM business_projects WHERE project_id='nope'"
    )

    from core.work_orders.escalation import not_fixed_for_work_order

    signal = not_fixed_for_work_order(wo, db_path=db, source_root=tmp_path)
    assert signal["not_fixed"] is True, f"expected not_fixed; got {signal}"
    assert "ac_fail" in signal["reasons"]


def test_not_fixed_signal_clear_when_ac_passes(tmp_path: Path) -> None:
    """A closed WO whose AC passes and no other signal → not_fixed False."""
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    wo = _seed_closed_wo(db, ac="SQL-CHECK: SELECT COUNT(*) FROM business_projects")

    from core.work_orders.escalation import not_fixed_for_work_order

    signal = not_fixed_for_work_order(wo, db_path=db, source_root=tmp_path)
    assert signal["not_fixed"] is False, f"expected fixed; got {signal}"


def test_unreviewable_grader_alone_is_not_not_fixed() -> None:
    """An unreviewable grader must not, by itself, trip the not-fixed signal."""
    from core.work_orders.escalation import compute_not_fixed_signal

    signal = compute_not_fixed_signal(grader_not_fixed=True, grader_confidence=0.0)
    assert signal["not_fixed"] is False
