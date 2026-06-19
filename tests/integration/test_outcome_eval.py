"""T2/T4 (WO-OUTCOME-EVAL): failed outcome auto-reopens the WO + escalates.

On a regressed outcome (symptom persists after close), the eval sets the WO back
to in_progress and writes an unresolved escalation file — the safety net behind
the close gate, feeding WO-ESCALATION-LADDER.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from core.eval.runner import run_outcome_eval

NOW = "2026-01-01T00:00:00+00:00"


def _seed_closed_wo(db_path: Path, *, symptom: str) -> str:
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
            "  status, closed_at, created_at, updated_at, last_updated_at, originating_symptom)"
            " VALUES (?,?,?,?,?,?, 'closed', ?, ?, ?, ?, ?)",
            (
                wo,
                project_id,
                milestone_id,
                "Defect WO",
                "d",
                "infrastructure",
                NOW,
                NOW,
                NOW,
                NOW,
                symptom,
            ),
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


def test_failed_outcome_reopens_wo(tmp_path: Path) -> None:
    """A regressed closed WO is set back to in_progress and an escalation is written."""
    home = tmp_path / "home"
    db = home / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)

    symptom = "SQL-CHECK: SELECT 1 WHERE EXISTS (SELECT 1 FROM business_projects WHERE project_id='nope')"
    wo = _seed_closed_wo(db, symptom=symptom)
    assert _status(db, wo) == "closed"

    result = run_outcome_eval(
        db_path=db, source_root=tmp_path, dream_studio_home=home, auto_reopen=True
    )

    # Outcome failed and the WO was reopened.
    assert wo in {f["work_order_id"] for f in result["failed"]}
    assert _status(db, wo) == "in_progress", "regressed WO must be reopened"

    # An unresolved escalation file was written where the pulse scan looks.
    esc_files = list((home / "meta").glob("ESC-*.md"))
    assert esc_files, "no escalation file written"
    text = esc_files[0].read_text(encoding="utf-8")
    assert "unresolved" in text.lower() and "ESC-" in text
    assert wo[:8] in esc_files[0].name


def test_no_reopen_when_auto_reopen_false(tmp_path: Path) -> None:
    """Detection without auto_reopen leaves the WO closed and writes no escalation."""
    home = tmp_path / "home"
    db = home / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    wo = _seed_closed_wo(
        db, symptom="SQL-CHECK: SELECT 1 WHERE EXISTS (SELECT 1 FROM business_projects WHERE project_id='nope')"
    )

    run_outcome_eval(db_path=db, source_root=tmp_path, dream_studio_home=home, auto_reopen=False)

    assert _status(db, wo) == "closed"
    assert not list((home / "meta").glob("ESC-*.md"))


def test_end_to_end(tmp_path: Path) -> None:
    """Full pipeline: one regressed WO reopens+escalates, one resolved WO stays closed."""
    home = tmp_path / "home"
    db = home / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)

    bad = _seed_closed_wo(
        db, symptom="SQL-CHECK: SELECT 1 WHERE EXISTS (SELECT 1 FROM business_projects WHERE project_id='nope')"
    )
    good = _seed_closed_wo(db, symptom="SQL-CHECK: SELECT 1 WHERE EXISTS (SELECT 1 FROM business_projects)")

    result = run_outcome_eval(
        db_path=db, source_root=tmp_path, dream_studio_home=home, auto_reopen=True
    )

    failed_ids = {f["work_order_id"] for f in result["failed"]}
    assert bad in failed_ids and good not in failed_ids
    assert _status(db, bad) == "in_progress"
    assert _status(db, good) == "closed"
    assert result["evaluated"] >= 2
