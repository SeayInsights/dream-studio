"""WO 05fc434d: a deleted work order is TERMINAL and must not block milestone close.

close_milestone's open-WO precondition treated only {closed, cancelled} as terminal, so a
WO retired via a work_order.deleted event (status='deleted') read as still-open and blocked
the milestone — a hard precondition not even force can bypass. A deleted WO is removed, not
outstanding, so it belongs in the terminal set alongside cancelled.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.milestones.close import close_milestone

REPO = Path(__file__).resolve().parents[2]
NOW = "2026-07-23T00:00:00Z"
PROJECT_ID = "p-msdel"
MILESTONE_ID = "m-msdel"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id,name,description,status,created_at,updated_at)"
            " VALUES (?,'P','','active',?,?)",
            (PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id,project_id,title,description,due_date,status,created_at,updated_at)"
            " VALUES (?,?,'Infra MS',NULL,NULL,'active',?,?)",
            (MILESTONE_ID, PROJECT_ID, NOW, NOW),
        )
        # One genuinely closed WO + one retired via work_order.deleted (status='deleted').
        for wo_id, status in (("wo-closed", "closed"), ("wo-deleted", "deleted")):
            conn.execute(
                "INSERT INTO business_work_orders"
                " (work_order_id,project_id,milestone_id,title,description,status,"
                " work_order_type,created_at,updated_at)"
                " VALUES (?,?,?,?,NULL,?,'infrastructure',?,?)",
                (wo_id, PROJECT_ID, MILESTONE_ID, wo_id, status, NOW, NOW),
            )
        conn.commit()
    finally:
        conn.close()
    return tmp_path


def _write_passing_gates(planning_root: Path) -> None:
    d = planning_root / "milestones" / MILESTONE_ID
    d.mkdir(parents=True, exist_ok=True)
    (d / "design-audit.md").write_text("Score: 3/4\nok\n", encoding="utf-8")
    (d / "security-audit.md").write_text("All clear.\n", encoding="utf-8")
    (d / "harden-results.md").write_text("PASSED\n", encoding="utf-8")
    (d / "cwv-results.md").write_text("PASSED\n", encoding="utf-8")


def test_deleted_work_order_does_not_block_milestone_close(home: Path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(home / "spool"))
    planning_root = home / ".planning"
    _write_passing_gates(planning_root)

    result = close_milestone(
        milestone_id=MILESTONE_ID,
        source_root=REPO,
        dream_studio_home=home,
        planning_root=planning_root,
    )

    # The deleted WO must not appear as open; with gates passing the milestone closes.
    assert result.get("error") != "Cannot close milestone: open work orders remain", result
    assert result["ok"] is True, result
    assert result["status"] == "complete"
