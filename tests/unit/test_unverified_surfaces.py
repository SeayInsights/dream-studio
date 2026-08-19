"""Gap WOs 5ed752d7 + 900ee40f: the UNVERIFIED ledger's read surfaces.

Both spawned by WO-FALSIFY-FIRST-PASS's own verify, which caught that the
ledger was recordable but under-surfaced (task said "aggregated in ds project
state"; only close output existed) and that the close-output branch had no test.
The quality grader additionally flagged, via rule 7, that a dual-store ledger is
durable state a read path trusts — so the single-source-of-truth guarantee is
pinned here too.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.unverified_summary import project_unverified_summary
from core.work_orders.verify_persist import (
    _persist_unverified_ledger,
    read_unverified_ledger,
)

NOW = "2026-05-16T00:00:00+00:00"
_SCENARIO = {
    "scenario_class": "reachability_vs_config",
    "surface": "core/x.py::issue_token",
    "scenario": "token valid against a host the guard never checks",
    "status": "UNVERIFIED",
    "evidence": "needs a real bound-host deploy",
    "severity": "error",
}


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db)
    return db


def _seed_wo(db: Path, project_id: str, *, status: str = "in_progress", title: str = "WO") -> str:
    wo_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT OR IGNORE INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at) VALUES (?,?,NULL,?,'d','cleanup',?,?,?)",
        (wo_id, project_id, title, status, NOW, NOW),
    )
    conn.commit()
    conn.close()
    return wo_id


# ── single source of truth (quality rule 7 on our own ledger) ───────────────────


def test_authority_write_removes_a_stale_disk_ledger(tmp_path):
    """Rule 7, caught by this stage's own verify: a WO whose earlier run fell back
    to disk and whose later run reached the authority would leave TWO ledgers, and
    an authority-first reader could serve the older one — version skew on durable
    state a read path trusts. Exactly one ledger may exist per WO."""
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    wo_id = str(uuid.uuid4())

    # Run 1: authority unavailable → disk fallback.
    with patch("core.work_orders.artifacts.set_wo_artifact", return_value=False):
        disk_path = _persist_unverified_ledger(
            wo_id, [_SCENARIO], planning_root=planning, db_path=db
        )
    assert disk_path is not None and disk_path.is_file()

    # Run 2: authority available → the stale disk copy must be gone.
    result = _persist_unverified_ledger(wo_id, [], planning_root=planning, db_path=db)
    assert result is None, "authority write should report no disk fallback"
    assert not disk_path.is_file(), "stale disk ledger must be removed"

    ledger = read_unverified_ledger(wo_id, planning_root=planning, db_path=db)
    assert ledger is not None and ledger["count"] == 0, "the authority copy is the live one"


def test_corrupt_ledger_reports_unreadable_not_empty(tmp_path):
    """'Corrupt' and 'absent' are different facts — collapsing them would let a
    broken ledger read as 'no residual risk' (quality rule 2)."""
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    wo_id = str(uuid.uuid4())
    ledger_dir = planning / "work-orders" / wo_id
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "unverified-risks.json").write_text("{not json", encoding="utf-8")

    ledger = read_unverified_ledger(wo_id, planning_root=planning, db_path=db)
    assert ledger is not None
    assert "not valid JSON" in ledger["unreadable"]
    assert ledger["unverified"] == []

    # A WO with no ledger at all still returns None — absence stays distinct.
    assert read_unverified_ledger(str(uuid.uuid4()), planning_root=planning, db_path=db) is None


# ── project-state aggregation (gap WO 5ed752d7) ─────────────────────────────────


def test_project_summary_aggregates_open_wo_ledgers(tmp_path):
    """Open UNVERIFIED risk is aggregated project-wide; CLOSED work orders are
    excluded (their residual risk was surfaced and accepted at close)."""
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    project_id = str(uuid.uuid4())

    open_a = _seed_wo(db, project_id, title="Open A")
    open_b = _seed_wo(db, project_id, title="Open B")
    closed = _seed_wo(db, project_id, status="closed", title="Closed C")

    for wo in (open_a, open_b, closed):
        _persist_unverified_ledger(wo, [_SCENARIO], planning_root=planning, db_path=db)
    # A second entry on one WO so the count is not just a WO count.
    _persist_unverified_ledger(
        open_b,
        [_SCENARIO, {**_SCENARIO, "scenario_class": "crash_mid_write"}],
        planning_root=planning,
        db_path=db,
    )

    summary = project_unverified_summary(project_id, planning_root=planning, db_path=db)
    assert summary["total"] == 3, summary
    ids = {w["work_order_id"] for w in summary["work_orders"]}
    assert ids == {open_a, open_b}, "closed WOs must be excluded"
    b = next(w for w in summary["work_orders"] if w["work_order_id"] == open_b)
    assert b["count"] == 2
    assert b["classes"] == ["crash_mid_write", "reachability_vs_config"]


def test_project_summary_reports_unreadable_separately(tmp_path):
    """One unreadable ledger must not hide the rest, and must not count as zero."""
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    project_id = str(uuid.uuid4())
    good = _seed_wo(db, project_id, title="Good")
    bad = _seed_wo(db, project_id, title="Bad")

    _persist_unverified_ledger(good, [_SCENARIO], planning_root=planning, db_path=db)
    bad_dir = planning / "work-orders" / bad
    bad_dir.mkdir(parents=True, exist_ok=True)
    (bad_dir / "unverified-risks.json").write_text("{broken", encoding="utf-8")

    summary = project_unverified_summary(project_id, planning_root=planning, db_path=db)
    assert summary["total"] == 1
    assert [w["work_order_id"] for w in summary["work_orders"]] == [good]
    assert [u["work_order_id"] for u in summary["unreadable"]] == [bad]


def test_project_state_carries_unverified_risks(tmp_path):
    """ds project state surfaces the aggregate where operators orient."""
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    project_id = str(uuid.uuid4())
    wo_id = _seed_wo(db, project_id, title="Open")
    _persist_unverified_ledger(wo_id, [_SCENARIO], planning_root=planning, db_path=db)

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        from core.projects.queries import get_project_state

        state = get_project_state(
            source_root=tmp_path, dream_studio_home=tmp_path, planning_root=planning
        )
    assert state["ok"] is True
    proj = next(p for p in state["projects"] if p["project_id"] == project_id)
    assert proj["unverified_risks"]["total"] == 1
    assert proj["unverified_risks"]["work_orders"][0]["work_order_id"] == wo_id


# ── close-output branch (gap WO 900ee40f) ───────────────────────────────────────


def _close(db: Path, planning: Path, tmp_path: Path, wo_id: str) -> dict:
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        from core.work_orders.close import close_work_order

        return close_work_order(
            work_order_id=wo_id,
            force=True,  # gate outcomes are not under test here; the ledger surfacing is
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=planning,
        )


def test_close_surfaces_open_unverified_risks(tmp_path):
    """close_work_order reports the WO's open residual risk — a closed WO must
    carry NAMED residual risk, never implied zero risk."""
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    project_id = str(uuid.uuid4())
    wo_id = _seed_wo(db, project_id)
    _persist_unverified_ledger(wo_id, [_SCENARIO], planning_root=planning, db_path=db)

    result = _close(db, planning, tmp_path, wo_id)
    assert result["ok"] is True, result
    assert result["unverified_risks"][0]["scenario_class"] == "reachability_vs_config"
    assert "remain UNVERIFIED" in result["unverified_risks_note"]


def test_close_reports_an_unreadable_ledger(tmp_path):
    """An unreadable ledger surfaces as unreadable at close — not as clean."""
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    project_id = str(uuid.uuid4())
    wo_id = _seed_wo(db, project_id)
    ledger_dir = planning / "work-orders" / wo_id
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "unverified-risks.json").write_text("{broken", encoding="utf-8")

    result = _close(db, planning, tmp_path, wo_id)
    assert result["ok"] is True, result
    assert "could not be read" in result["unverified_risks_note"]
    assert "unverified_risks" not in result


def test_close_is_silent_when_no_analysis_ever_ran(tmp_path):
    """No ledger → no note. Absence of analysis is not a residual-risk claim."""
    db = _db(tmp_path)
    planning = tmp_path / "planning"
    wo_id = _seed_wo(db, str(uuid.uuid4()))

    result = _close(db, planning, tmp_path, wo_id)
    assert result["ok"] is True, result
    assert "unverified_risks_note" not in result
