"""WO-DASH-DRILLDOWN: the project drill-down routes return the
project -> milestones -> work orders -> tasks hierarchy from the SQLite authority.

Read-only over business_milestones / business_work_orders / business_tasks — no new
table, no authority write. Assertions go through the real async routes against a
seeded DB (same harness as test_project_list_client_field.py).
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from projections.api.routes import project_drilldown


def _seed(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, status, created_at, updated_at,"
            " project_path, total_sessions) VALUES (?,?,?,?,?,?,?)",
            ("proj-1", "Demo", "active", "t", "t", r"C:\b\demo", 0),
        )
        conn.executemany(
            "INSERT INTO business_milestones (milestone_id, project_id, title, status, created_at,"
            " updated_at) VALUES (?,?,?,?,?,?)",
            [
                ("ms-1", "proj-1", "Milestone One", "in_progress", "2026-01-01", "2026-01-01"),
                ("ms-2", "proj-1", "Milestone Two", "complete", "2026-01-02", "2026-01-02"),
            ],
        )
        conn.executemany(
            "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id, title,"
            " status, work_order_type, created_at) VALUES (?,?,?,?,?,?,?)",
            [
                (
                    "wo-1",
                    "proj-1",
                    "ms-1",
                    "Build the thing",
                    "in_progress",
                    "ui_page",
                    "2026-01-01",
                ),
                ("wo-2", "proj-1", "ms-1", "Test the thing", "created", "testing", "2026-01-02"),
                (
                    "wo-3",
                    "proj-1",
                    "ms-2",
                    "Other milestone WO",
                    "closed",
                    "infrastructure",
                    "2026-01-03",
                ),
            ],
        )
        conn.executemany(
            "INSERT INTO business_tasks (task_id, work_order_id, project_id, title, status,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            [
                ("t-1", "wo-1", "proj-1", "Task A", "complete", "2026-01-01", "2026-01-01"),
                ("t-2", "wo-1", "proj-1", "Task B", "pending", "2026-01-02", "2026-01-02"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _fresh(db: Path) -> sqlite3.Connection:
    # Each route closes its connection in a finally, so every call needs a fresh one.
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


def test_project_milestones_route(tmp_path, monkeypatch):
    db = _seed(tmp_path)
    monkeypatch.setattr(project_drilldown, "get_db_connection", lambda: _fresh(db))
    result = asyncio.run(project_drilldown.get_project_milestones("proj-1"))
    assert result["count"] == 2
    assert [m["milestone_id"] for m in result["milestones"]] == ["ms-1", "ms-2"]
    assert result["milestones"][0]["title"] == "Milestone One"
    assert result["milestones"][0]["status"] == "in_progress"


def test_milestone_work_orders_route(tmp_path, monkeypatch):
    db = _seed(tmp_path)
    monkeypatch.setattr(project_drilldown, "get_db_connection", lambda: _fresh(db))
    result = asyncio.run(project_drilldown.get_milestone_work_orders("ms-1"))
    # Only the two WOs under ms-1 (wo-3 belongs to ms-2).
    assert [w["work_order_id"] for w in result["work_orders"]] == ["wo-1", "wo-2"]
    assert result["work_orders"][0]["type"] == "ui_page"


def test_work_order_tasks_route(tmp_path, monkeypatch):
    db = _seed(tmp_path)
    monkeypatch.setattr(project_drilldown, "get_db_connection", lambda: _fresh(db))
    result = asyncio.run(project_drilldown.get_work_order_tasks("wo-1"))
    assert [t["task_id"] for t in result["tasks"]] == ["t-1", "t-2"]
    assert result["tasks"][0]["status"] == "complete"


def test_full_hierarchy_reachable(tmp_path, monkeypatch):
    """The three routes chain into project -> milestone -> work order -> task."""
    db = _seed(tmp_path)
    monkeypatch.setattr(project_drilldown, "get_db_connection", lambda: _fresh(db))
    ms = asyncio.run(project_drilldown.get_project_milestones("proj-1"))["milestones"]
    first_ms = ms[0]["milestone_id"]
    wos = asyncio.run(project_drilldown.get_milestone_work_orders(first_ms))["work_orders"]
    first_wo = wos[0]["work_order_id"]
    tasks = asyncio.run(project_drilldown.get_work_order_tasks(first_wo))["tasks"]
    assert first_ms == "ms-1" and first_wo == "wo-1"
    assert [t["title"] for t in tasks] == ["Task A", "Task B"]


def test_empty_hierarchy_is_honest_not_error(tmp_path, monkeypatch):
    """Unknown ids return empty lists, not 500s."""
    db = _seed(tmp_path)
    monkeypatch.setattr(project_drilldown, "get_db_connection", lambda: _fresh(db))
    assert asyncio.run(project_drilldown.get_project_milestones("nope"))["milestones"] == []
    assert asyncio.run(project_drilldown.get_milestone_work_orders("nope"))["work_orders"] == []
    assert asyncio.run(project_drilldown.get_work_order_tasks("nope"))["tasks"] == []


def test_frontend_drilldown_is_wired():
    """The dashboard Projects modal has a Milestones tab that drills the hierarchy
    via the three routes with breadcrumb back-nav."""
    frontend = Path(project_drilldown.__file__).resolve().parents[2] / "frontend"
    js = (frontend / "static" / "dashboard.js").read_text(encoding="utf-8")
    html = (frontend / "dashboard.html").read_text(encoding="utf-8")
    combined = js + html
    # The three drill-down fetches.
    assert "/api/v1/projects/${projectId}/milestones" in js
    assert "/api/v1/milestones/${milestoneId}/work-orders" in js
    assert "/api/v1/work-orders/${workOrderId}/tasks" in js
    # The tab + its drill functions + back-nav.
    assert 'data-project-tab="milestones"' in html
    assert 'id="modal-milestones-content"' in html
    for fn in ("loadProjectMilestones", "drilldownMilestone", "drilldownWorkOrder"):
        assert fn in combined, f"drill-down function {fn!r} must be wired"
