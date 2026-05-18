"""Workstream 3 gate: 048_project_spine.sql schema assertions."""
from __future__ import annotations
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "core" / "event_store" / "migrations" / "048_project_spine.sql"


def _apply(conn: sqlite3.Connection) -> None:
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))


def test_migration_file_exists():
    assert MIGRATION.is_file(), "048_project_spine.sql missing"


def test_migration_creates_ds_projects(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    _apply(conn)
    conn.execute(
        "INSERT INTO ds_projects (project_id, name, description, status, created_at, updated_at)"
        " VALUES ('p1', 'Test Project', 'desc', 'active', '2026-05-16T00:00:00+00:00', '2026-05-16T00:00:00+00:00')"
    )
    row = conn.execute("SELECT name, status FROM ds_projects WHERE project_id='p1'").fetchone()
    assert row == ("Test Project", "active")
    conn.close()


def test_migration_creates_ds_milestones(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    _apply(conn)
    now = "2026-05-16T00:00:00+00:00"
    conn.execute(
        "INSERT INTO ds_projects VALUES ('p1','Proj','',  'active', ?, ?)", (now, now)
    )
    conn.execute(
        "INSERT INTO ds_milestones (milestone_id, project_id, title, status, created_at, updated_at)"
        " VALUES ('m1', 'p1', 'M1', 'pending', ?, ?)", (now, now)
    )
    row = conn.execute("SELECT title FROM ds_milestones WHERE milestone_id='m1'").fetchone()
    assert row == ("M1",)
    conn.close()


def test_migration_creates_ds_work_orders(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    _apply(conn)
    now = "2026-05-16T00:00:00+00:00"
    conn.execute("INSERT INTO ds_projects VALUES ('p1','P','','active',?,?)", (now, now))
    conn.execute(
        "INSERT INTO ds_work_orders (work_order_id, project_id, title, status, created_at, updated_at)"
        " VALUES ('w1','p1','WO1','open',?,?)", (now, now)
    )
    row = conn.execute("SELECT title, status FROM ds_work_orders WHERE work_order_id='w1'").fetchone()
    assert row == ("WO1", "open")
    conn.close()


def test_migration_creates_ds_tasks(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    _apply(conn)
    now = "2026-05-16T00:00:00+00:00"
    conn.execute("INSERT INTO ds_projects VALUES ('p1','P','','active',?,?)", (now, now))
    conn.execute(
        "INSERT INTO ds_work_orders (work_order_id, project_id, title, status, created_at, updated_at)"
        " VALUES ('w1','p1','WO1','open',?,?)", (now, now)
    )
    conn.execute(
        "INSERT INTO ds_tasks (task_id, work_order_id, project_id, title, status, created_at, updated_at)"
        " VALUES ('t1','w1','p1','T1','pending',?,?)", (now, now)
    )
    row = conn.execute("SELECT title, status FROM ds_tasks WHERE task_id='t1'").fetchone()
    assert row == ("T1", "pending")
    conn.close()


def test_migration_enforces_fk_on_milestones(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("PRAGMA foreign_keys = ON")
    _apply(conn)
    now = "2026-05-16T00:00:00+00:00"
    try:
        conn.execute(
            "INSERT INTO ds_milestones (milestone_id, project_id, title, status, created_at, updated_at)"
            " VALUES ('m1','nonexistent','T','pending',?,?)", (now, now)
        )
        conn.commit()
        assert False, "Should have raised FK violation"
    except sqlite3.IntegrityError:
        pass
    conn.close()


def test_migration_contains_advisory_note():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "034_execution_graph" in text, "048 must reference 034_execution_graph.sql advisory"
    assert "project_id" in text
