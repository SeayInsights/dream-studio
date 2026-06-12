"""Gate tests: gap WO deduplication in _insert_gap_work_orders (WO-SPAWN-DEDUPE).

Proving gate:
  fresh-spawn:  no open WO with same title → new WO created, tasks appended to it
  merge-into-existing: open WO with matching title exists → tasks merged, no new WO
  merge-reports-existing-id: merged result carries the existing WO id and merged_into_existing=True
  no-milestone-skips-dedup: None milestone → dedup query skipped, new WO always spawned
"""

from __future__ import annotations

import sqlite3
import uuid

_DDL = """
CREATE TABLE IF NOT EXISTS business_work_orders (
    work_order_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    milestone_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    work_order_type TEXT NOT NULL DEFAULT 'cleanup',
    status TEXT NOT NULL DEFAULT 'created',
    sequence_order INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS business_tasks (
    task_id TEXT PRIMARY KEY,
    work_order_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_PROJECT_ID = "proj-test-001"
_MILESTONE_ID = "ms-test-001"


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_DDL)
    conn.commit()
    return conn


def _seed_open_wo(conn: sqlite3.Connection, title: str, *, wo_id: str | None = None) -> str:
    wo_id = wo_id or str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, status)"
        " VALUES (?, ?, ?, ?, 'created')",
        (wo_id, _PROJECT_ID, _MILESTONE_ID, title),
    )
    conn.commit()
    return wo_id


def _gaps(title: str, *, tasks: list[str] | None = None) -> list[dict]:
    task_list = [{"title": t, "description": ""} for t in (tasks or [title + " task"])]
    return [
        {
            "title": title,
            "description": "gap desc",
            "work_order_type": "infrastructure",
            "tasks": task_list,
        }
    ]


class TestGapWODedup:
    def test_fresh_spawn_creates_new_wo(self):
        """No open WO with same title → new WO inserted."""
        from core.work_orders.verify import _insert_gap_work_orders

        conn = _make_conn()
        gaps = _gaps("Fix missing coverage")
        result = _insert_gap_work_orders(
            conn,
            gaps=gaps,
            project_id=_PROJECT_ID,
            milestone_id=_MILESTONE_ID,
            reviewed_wo_title="Parent WO",
            reviewed_wo_sequence=10,
        )

        assert len(result) == 1
        assert result[0]["title"] == "Fix missing coverage"
        assert result[0].get("merged_into_existing") is not True

        rows = conn.execute("SELECT work_order_id FROM business_work_orders").fetchall()
        assert len(rows) == 1

    def test_fresh_spawn_attaches_tasks_to_new_wo(self):
        """Tasks from the gap are inserted under the newly created WO."""
        from core.work_orders.verify import _insert_gap_work_orders

        conn = _make_conn()
        gaps = _gaps("Fix missing coverage", tasks=["Task A", "Task B"])
        result = _insert_gap_work_orders(
            conn,
            gaps=gaps,
            project_id=_PROJECT_ID,
            milestone_id=_MILESTONE_ID,
            reviewed_wo_title="Parent WO",
            reviewed_wo_sequence=10,
        )

        new_wo_id = result[0]["work_order_id"]
        tasks = conn.execute(
            "SELECT title FROM business_tasks WHERE work_order_id = ?", (new_wo_id,)
        ).fetchall()
        assert {t[0] for t in tasks} == {"Task A", "Task B"}

    def test_merge_into_existing_wo_when_title_matches(self):
        """Open WO with same title → tasks merged, no new WO created."""
        from core.work_orders.verify import _insert_gap_work_orders

        conn = _make_conn()
        existing_id = _seed_open_wo(conn, "Fix missing coverage")

        gaps = _gaps("Fix missing coverage")
        result = _insert_gap_work_orders(
            conn,
            gaps=gaps,
            project_id=_PROJECT_ID,
            milestone_id=_MILESTONE_ID,
            reviewed_wo_title="Parent WO",
            reviewed_wo_sequence=10,
        )

        assert len(result) == 1
        assert result[0]["work_order_id"] == existing_id
        assert result[0].get("merged_into_existing") is True

        wo_rows = conn.execute("SELECT work_order_id FROM business_work_orders").fetchall()
        assert len(wo_rows) == 1

    def test_merge_appends_tasks_to_existing_wo(self):
        """Tasks from the gap are appended to the existing WO's task list."""
        from core.work_orders.verify import _insert_gap_work_orders

        conn = _make_conn()
        existing_id = _seed_open_wo(conn, "Fix missing coverage")
        conn.execute(
            "INSERT INTO business_tasks (task_id, work_order_id, project_id, title)"
            " VALUES ('old-task', ?, ?, 'Pre-existing task')",
            (existing_id, _PROJECT_ID),
        )
        conn.commit()

        gaps = _gaps("Fix missing coverage", tasks=["New task from gap"])
        _insert_gap_work_orders(
            conn,
            gaps=gaps,
            project_id=_PROJECT_ID,
            milestone_id=_MILESTONE_ID,
            reviewed_wo_title="Parent WO",
            reviewed_wo_sequence=10,
        )

        tasks = conn.execute(
            "SELECT title FROM business_tasks WHERE work_order_id = ?", (existing_id,)
        ).fetchall()
        titles = {t[0] for t in tasks}
        assert "Pre-existing task" in titles
        assert "New task from gap" in titles

    def test_no_milestone_always_spawns_new_wo(self):
        """milestone_id=None skips dedup query; new WO always created."""
        from core.work_orders.verify import _insert_gap_work_orders

        conn = _make_conn()
        gaps = _gaps("Fix missing coverage")
        result = _insert_gap_work_orders(
            conn,
            gaps=gaps,
            project_id=_PROJECT_ID,
            milestone_id=None,
            reviewed_wo_title="Parent WO",
            reviewed_wo_sequence=10,
        )

        assert len(result) == 1
        assert result[0].get("merged_into_existing") is not True

    def test_multiple_gaps_independent_dedup(self):
        """Each gap independently deduped: one merges, one spawns fresh."""
        from core.work_orders.verify import _insert_gap_work_orders

        conn = _make_conn()
        _seed_open_wo(conn, "Gap A — existing")

        gaps = [
            {
                "title": "Gap A — existing",
                "description": "",
                "work_order_type": "cleanup",
                "tasks": [],
            },
            {"title": "Gap B — new", "description": "", "work_order_type": "cleanup", "tasks": []},
        ]
        result = _insert_gap_work_orders(
            conn,
            gaps=gaps,
            project_id=_PROJECT_ID,
            milestone_id=_MILESTONE_ID,
            reviewed_wo_title="Parent WO",
            reviewed_wo_sequence=10,
        )

        assert len(result) == 2
        merged = [r for r in result if r.get("merged_into_existing")]
        fresh = [r for r in result if not r.get("merged_into_existing")]
        assert len(merged) == 1
        assert merged[0]["title"] == "Gap A — existing"
        assert len(fresh) == 1
        assert fresh[0]["title"] == "Gap B — new"

        wo_count = conn.execute("SELECT COUNT(*) FROM business_work_orders").fetchone()[0]
        assert wo_count == 2
