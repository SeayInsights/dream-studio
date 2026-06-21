"""WO-SPAWN-LOOP-FIX gate: verify.py must not spawn duplicate remediation WOs.

Root cause of the spiral: the review grader re-flagged the same gap on every run
(rephrasing its title each time), and the dedup query keyed on the free-text
title, required a matching milestone_id, and only looked at open WOs. Combined
with a grader that fabricated numeric thresholds absent from the acceptance
criteria, a single WO could spawn an unbounded chain of near-duplicate gaps.

These tests pin the four fixes:
  T1 stable gap key      → rephrased titles dedup on (reviewed_wo + category)
  T2 no invented gaps    → gaps citing thresholds absent from the AC are rejected
  T3 null-milestone dedup → dedup is scoped by project_id, not milestone_id
  T4 respawn cap         → a gap key already spawned in ANY status is never re-spawned
"""

from __future__ import annotations

import sqlite3

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

_PROJECT_ID = "proj-spawn-001"
_MILESTONE_ID = "ms-spawn-001"
_REVIEWED_WO = "reviewed-wo-spawn-001"


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_DDL)
    conn.commit()
    return conn


def _gap(title: str, *, category: str, description: str = "gap desc") -> dict:
    return {
        "title": title,
        "category": category,
        "description": description,
        "work_order_type": "infrastructure",
        "tasks": [],
    }


def _spawn(conn, gaps, *, milestone_id=_MILESTONE_ID):
    from core.work_orders.verify import _insert_gap_work_orders

    return _insert_gap_work_orders(
        conn,
        gaps=gaps,
        project_id=_PROJECT_ID,
        milestone_id=milestone_id,
        reviewed_work_order_id=_REVIEWED_WO,
        reviewed_wo_title="Parent WO",
        reviewed_wo_sequence=10,
    )


def _wo_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM business_work_orders").fetchone()[0]


def test_rephrased_title_dedupes():
    """T1: same (reviewed_wo + category), reworded title → one WO, not two."""
    conn = _make_conn()
    _spawn(conn, [_gap("Reduce ds.py to <=50 lines", category="ds-py-reduction")])
    second = _spawn(conn, [_gap("Complete the ds.py hub reduction", category="ds-py-reduction")])

    assert _wo_count(conn) == 1
    assert second[0].get("merged_into_existing") is True


def test_grader_rejects_invented_threshold():
    """T2: a gap inventing a numeric threshold absent from the AC is dropped."""
    from core.work_orders.verify import _filter_invented_threshold_gaps

    acceptance_text = "Split ds.py into a hub and per-group command modules. No behavior change."
    gaps = [
        _gap("Reduce ds.py to <=50 lines", category="ds-py-reduction"),  # 50 not in AC
        _gap("Add the missing module facade", category="facade"),  # no threshold
    ]
    kept = _filter_invented_threshold_gaps(gaps, acceptance_text)

    kept_categories = {g["category"] for g in kept}
    assert "ds-py-reduction" not in kept_categories  # invented "<=50 lines" rejected
    assert "facade" in kept_categories  # threshold-free gap survives


def test_grader_keeps_threshold_present_in_ac():
    """T2 (converse): a threshold that IS in the AC is legitimate and kept."""
    from core.work_orders.verify import _filter_invented_threshold_gaps

    acceptance_text = "Achieve at least 90% test coverage on the new module."
    gaps = [_gap("Raise coverage to 90%", category="coverage")]
    kept = _filter_invented_threshold_gaps(gaps, acceptance_text)

    assert {g["category"] for g in kept} == {"coverage"}


def test_null_milestone_still_dedupes():
    """T3: dedup is scoped by project_id, so null-milestone gaps still dedup."""
    conn = _make_conn()
    _spawn(conn, [_gap("Fix the flaky import", category="flaky-import")], milestone_id=None)
    _spawn(conn, [_gap("Repair the flaky import path", category="flaky-import")], milestone_id=None)

    assert _wo_count(conn) == 1


def test_respawn_cap_blocks_repeat():
    """T4: a gap key already spawned in ANY status (incl. closed) is never re-spawned."""
    conn = _make_conn()
    first = _spawn(conn, [_gap("Reduce ds.py to <=50 lines", category="ds-py-reduction")])
    spawned_id = first[0]["work_order_id"]

    # The operator force-closes the spawned gap WO.
    conn.execute(
        "UPDATE business_work_orders SET status = 'closed' WHERE work_order_id = ?",
        (spawned_id,),
    )
    conn.commit()

    # A later re-review surfaces the same gap key → must be suppressed, not re-spawned.
    second = _spawn(conn, [_gap("Finish reducing ds.py", category="ds-py-reduction")])

    assert _wo_count(conn) == 1  # no new WO created
    assert second[0].get("respawn_suppressed") is True
    assert second[0]["work_order_id"] == spawned_id
