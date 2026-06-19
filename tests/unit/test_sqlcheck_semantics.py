"""WO-LIVE-DATA-GATE T1: a SQL-CHECK that returns ZERO rows is a hard FAIL.

The convention is `SELECT 1 WHERE <condition>` — a false condition yields zero
rows = fail. This pins the close AC gate's SQL-CHECK semantics so dashboard/
telemetry WOs can't false-close on vacuous checks.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database

NOW = "2026-01-01T00:00:00.000000Z"


def _seed_wo_with_ac(db_path: Path, ac: str) -> tuple[sqlite3.Connection, str]:
    """Bootstrap a temp authority with one in_progress WO + one complete task carrying `ac`."""
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    pid, mid, wid, tid = (str(uuid.uuid4()) for _ in range(4))
    conn.execute(
        "INSERT OR IGNORE INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (pid, "Test", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO business_milestones"
        " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (mid, pid, "M1", "active", 1, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description,"
        "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?, 'in_progress', 1, ?, ?, ?)",
        (wid, pid, mid, "Test WO", "d", "cleanup", NOW, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, description,"
        "  acceptance_criteria, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?, 'complete', ?, ?)",
        (tid, wid, pid, "T1", "d", ac, NOW, NOW),
    )
    conn.commit()
    return conn, wid


def test_zero_row_sqlcheck_fails_close(tmp_path):
    """A SQL-CHECK whose condition is false (zero rows) must FAIL the AC gate;
    the same check made true must PASS."""
    from core.work_orders.close import _run_ac_gate

    # Zero-row form: `SELECT 1 WHERE 1=0` returns no rows → hard fail.
    db_fail = tmp_path / "fail" / "studio.db"
    db_fail.parent.mkdir(parents=True)
    conn_fail, wid_fail = _seed_wo_with_ac(db_fail, "SQL-CHECK: SELECT 1 WHERE 1=0")
    try:
        failures = _run_ac_gate(conn_fail, work_order_id=wid_fail, db_path=db_fail)
    finally:
        conn_fail.close()
    assert failures, "a zero-row SQL-CHECK must produce an AC-gate failure"
    assert any("SQL-CHECK" in f and "SELECT 1 WHERE 1=0" in f for f in failures), failures

    # True form: `SELECT 1 WHERE 1=1` returns a row → pass (no failures).
    db_ok = tmp_path / "ok" / "studio.db"
    db_ok.parent.mkdir(parents=True)
    conn_ok, wid_ok = _seed_wo_with_ac(db_ok, "SQL-CHECK: SELECT 1 WHERE 1=1")
    try:
        ok_failures = _run_ac_gate(conn_ok, work_order_id=wid_ok, db_path=db_ok)
    finally:
        conn_ok.close()
    assert ok_failures == [], f"a true SQL-CHECK should pass the AC gate, got {ok_failures}"


def test_zero_row_sqlcheck_error_message_is_explicit(tmp_path):
    """The zero-row failure carries the explicit 'returned no rows' diagnostic."""
    from core.work_orders.verify import _run_one_sql_check

    db = tmp_path / "studio.db"
    bootstrap_database(db)
    result = _run_one_sql_check("SELECT 1 WHERE 1=0", db)
    assert result["passed"] is False
    assert "no rows" in (result["error"] or "").lower()
