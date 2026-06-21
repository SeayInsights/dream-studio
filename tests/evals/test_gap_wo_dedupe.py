"""Gate tests: gap WO deduplication in _insert_gap_work_orders.

Dedup is keyed on a stable gap key — (reviewed_work_order_id + gap category) —
stored as a ``[gap-key: ...]`` marker on each spawned WO's description, NOT on the
free-text title (WO-SPAWN-LOOP-FIX). A re-review of the same gap therefore merges
into (or is suppressed against) the prior spawn even if the grader reworded the
title.

Proving gate:
  fresh-spawn:           first review of a gap → new WO created, tasks appended
  merge-into-existing:   re-review of the same gap key (open WO) → tasks merged, no new WO
  merge-reports-id:      merged result carries the existing WO id + merged_into_existing=True
  null-milestone-dedups: dedup is scoped by project_id, so null-milestone gaps still dedup
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
_REVIEWED_WO = "reviewed-wo-001"


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_DDL)
    conn.commit()
    return conn


def _gaps(title: str, *, category: str = "the-gap", tasks: list[str] | None = None) -> list[dict]:
    task_list = [{"title": t, "description": ""} for t in (tasks or [title + " task"])]
    return [
        {
            "title": title,
            "category": category,
            "description": "gap desc",
            "work_order_type": "infrastructure",
            "tasks": task_list,
        }
    ]


class TestGapWODedup:
    def test_fresh_spawn_creates_new_wo(self):
        """First review of a gap → a new WO is inserted."""
        from core.work_orders.verify import _insert_gap_work_orders

        conn = _make_conn()
        result = _insert_gap_work_orders(
            conn,
            gaps=_gaps("Fix missing coverage"),
            project_id=_PROJECT_ID,
            milestone_id=_MILESTONE_ID,
            reviewed_work_order_id=_REVIEWED_WO,
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
        result = _insert_gap_work_orders(
            conn,
            gaps=_gaps("Fix missing coverage", tasks=["Task A", "Task B"]),
            project_id=_PROJECT_ID,
            milestone_id=_MILESTONE_ID,
            reviewed_work_order_id=_REVIEWED_WO,
            reviewed_wo_title="Parent WO",
            reviewed_wo_sequence=10,
        )

        new_wo_id = result[0]["work_order_id"]
        tasks = conn.execute(
            "SELECT title FROM business_tasks WHERE work_order_id = ?", (new_wo_id,)
        ).fetchall()
        assert {t[0] for t in tasks} == {"Task A", "Task B"}

    def test_merge_into_existing_wo_on_re_review(self):
        """Re-reviewing the same gap key (open WO) merges; no new WO is created."""
        from core.work_orders.verify import _insert_gap_work_orders

        conn = _make_conn()
        first = _insert_gap_work_orders(
            conn,
            gaps=_gaps("Fix missing coverage", category="coverage"),
            project_id=_PROJECT_ID,
            milestone_id=_MILESTONE_ID,
            reviewed_work_order_id=_REVIEWED_WO,
            reviewed_wo_title="Parent WO",
            reviewed_wo_sequence=10,
        )
        existing_id = first[0]["work_order_id"]

        # Re-review: same category, reworded title → must merge into the prior spawn.
        second = _insert_gap_work_orders(
            conn,
            gaps=_gaps("Add the missing test coverage", category="coverage"),
            project_id=_PROJECT_ID,
            milestone_id=_MILESTONE_ID,
            reviewed_work_order_id=_REVIEWED_WO,
            reviewed_wo_title="Parent WO",
            reviewed_wo_sequence=10,
        )

        assert len(second) == 1
        assert second[0]["work_order_id"] == existing_id
        assert second[0].get("merged_into_existing") is True

        wo_rows = conn.execute("SELECT work_order_id FROM business_work_orders").fetchall()
        assert len(wo_rows) == 1

    def test_merge_appends_tasks_to_existing_wo(self):
        """Re-review tasks are appended to the existing WO's task list."""
        from core.work_orders.verify import _insert_gap_work_orders

        conn = _make_conn()
        first = _insert_gap_work_orders(
            conn,
            gaps=_gaps("Fix coverage", category="coverage", tasks=["Pre-existing task"]),
            project_id=_PROJECT_ID,
            milestone_id=_MILESTONE_ID,
            reviewed_work_order_id=_REVIEWED_WO,
            reviewed_wo_title="Parent WO",
            reviewed_wo_sequence=10,
        )
        existing_id = first[0]["work_order_id"]

        _insert_gap_work_orders(
            conn,
            gaps=_gaps("Fix coverage (again)", category="coverage", tasks=["New task from gap"]),
            project_id=_PROJECT_ID,
            milestone_id=_MILESTONE_ID,
            reviewed_work_order_id=_REVIEWED_WO,
            reviewed_wo_title="Parent WO",
            reviewed_wo_sequence=10,
        )

        tasks = conn.execute(
            "SELECT title FROM business_tasks WHERE work_order_id = ?", (existing_id,)
        ).fetchall()
        titles = {t[0] for t in tasks}
        assert "Pre-existing task" in titles
        assert "New task from gap" in titles

    def test_null_milestone_still_dedups(self):
        """milestone_id=None still dedups — the dedup query is scoped by project_id."""
        from core.work_orders.verify import _insert_gap_work_orders

        conn = _make_conn()
        for _ in range(2):
            _insert_gap_work_orders(
                conn,
                gaps=_gaps("Fix missing coverage", category="coverage"),
                project_id=_PROJECT_ID,
                milestone_id=None,
                reviewed_work_order_id=_REVIEWED_WO,
                reviewed_wo_title="Parent WO",
                reviewed_wo_sequence=10,
            )

        wo_count = conn.execute("SELECT COUNT(*) FROM business_work_orders").fetchone()[0]
        assert wo_count == 1

    def test_multiple_gaps_independent_dedup(self):
        """Distinct gap keys spawn independently; a repeated key merges."""
        from core.work_orders.verify import _insert_gap_work_orders

        conn = _make_conn()
        # First review: two distinct gaps → two WOs.
        _insert_gap_work_orders(
            conn,
            gaps=[
                {
                    "title": "Gap A",
                    "category": "a",
                    "description": "",
                    "work_order_type": "cleanup",
                    "tasks": [],
                },
                {
                    "title": "Gap B",
                    "category": "b",
                    "description": "",
                    "work_order_type": "cleanup",
                    "tasks": [],
                },
            ],
            project_id=_PROJECT_ID,
            milestone_id=_MILESTONE_ID,
            reviewed_work_order_id=_REVIEWED_WO,
            reviewed_wo_title="Parent WO",
            reviewed_wo_sequence=10,
        )
        # Second review: Gap A reworded (key 'a') merges; Gap C (key 'c') is new.
        result = _insert_gap_work_orders(
            conn,
            gaps=[
                {
                    "title": "Gap A reworded",
                    "category": "a",
                    "description": "",
                    "work_order_type": "cleanup",
                    "tasks": [],
                },
                {
                    "title": "Gap C",
                    "category": "c",
                    "description": "",
                    "work_order_type": "cleanup",
                    "tasks": [],
                },
            ],
            project_id=_PROJECT_ID,
            milestone_id=_MILESTONE_ID,
            reviewed_work_order_id=_REVIEWED_WO,
            reviewed_wo_title="Parent WO",
            reviewed_wo_sequence=10,
        )

        merged = [r for r in result if r.get("merged_into_existing")]
        fresh = [r for r in result if not r.get("merged_into_existing")]
        assert len(merged) == 1 and merged[0]["title"] == "Gap A reworded"
        assert len(fresh) == 1 and fresh[0]["title"] == "Gap C"

        wo_count = conn.execute("SELECT COUNT(*) FROM business_work_orders").fetchone()[0]
        assert wo_count == 3
