"""WO-VERIFY-GAP-RESOLUTION: closed gap WOs resolve verdicts; violations never do.

Discovered dogfooding WO-VERIFY-PROVENANCE: verify grades only WO-attributed
commits, so remediation committed under a spawned gap WO's own id is invisible
to the original WO's re-verify — a remediated-and-closed coverage gap failed
the original WO forever and blocked its close on independent_review.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-08-19T00:00:00.000000Z"


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


@contextmanager
def _patch_db(db_path: Path):
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        yield


def _seed(db_path: Path, *, project_id: str, milestone_id: str, work_order_id: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "Test", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO business_milestones"
        " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description,"
        "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,'in_progress',1,?,?,?)",
        (work_order_id, project_id, milestone_id, "Test WO", "desc", "cleanup", NOW, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, description, status,"
        "  created_at, updated_at)"
        " VALUES (?,?,?,?,?, 'complete', ?, ?)",
        (str(uuid.uuid4()), work_order_id, project_id, "T1", "do it", NOW, NOW),
    )
    conn.commit()
    conn.close()


def _grader_results(*, violations: list | None = None, coverage_gaps: list | None = None) -> dict:
    """Completion + quality pass; correctness fails on the given drivers."""
    return {
        "completion": {
            "passed": True,
            "completion_score": 1.0,
            "tasks_verified": [{"task_title": "T1", "evidence": "done", "verdict": "pass"}],
            "summary": "All tasks addressed.",
            "gaps": [],
        },
        "correctness": {
            "correctness_passed": False,
            "correctness_score": 1.0,
            "violations": violations or [],
            "coverage_gaps": coverage_gaps or [],
            "migration_gaps": [],
        },
        "quality": {"quality_passed": True, "quality_score": 1.0, "issues": []},
    }


def _run_verify(db_path: Path, tmp_path: Path, work_order_id: str, grader_results: dict) -> dict:
    planning_root = tmp_path / "planning"
    with _patch_db(db_path):
        with patch(
            "core.work_orders.verify_graders._run_graders_parallel",
            return_value=grader_results,
        ):
            with patch(
                "core.work_orders.verify_git._collect_git_commits",
                return_value="diff --git a/fake.py b/fake.py\n+# change",
            ):
                from core.work_orders.verify import verify_work_order

                return verify_work_order(
                    work_order_id=work_order_id,
                    source_root=REPO_ROOT,
                    dream_studio_home=tmp_path,
                    planning_root=planning_root,
                )


def _set_status(db_path: Path, work_order_id: str, status: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE business_work_orders SET status=? WHERE work_order_id=?", (status, work_order_id)
    )
    conn.commit()
    conn.close()


def test_closed_gap_wo_resolves_verdict(tmp_path: pytest.TempPathFactory) -> None:
    """Run 1 spawns a coverage-gap WO and fails; while that WO is open a re-run
    still fails; once it is CLOSED the re-run passes with resolved_gaps."""
    db_path = _make_db(tmp_path)
    project_id, milestone_id, work_order_id = (str(uuid.uuid4()) for _ in range(3))
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    graders = _grader_results(
        coverage_gaps=[{"function": "helper_fn", "file": "core/x.py"}],
    )

    first = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert first["passed"] is False
    assert first["resolved_gaps"] == []
    spawned_id = first["spawned_work_orders"][0]["work_order_id"]

    # Gap WO still open: no discount.
    second = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert second["passed"] is False

    # Gap WO closed: the gap is resolved, the verdict passes and names the WO.
    _set_status(db_path, spawned_id, "closed")
    third = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert third["passed"] is True, third.get("gaps")
    assert third["resolved_gaps"] == [spawned_id]


def test_violation_never_discounted(tmp_path: pytest.TempPathFactory) -> None:
    """A rule violation keeps the verdict failed even when its spawned WO is closed."""
    db_path = _make_db(tmp_path)
    project_id, milestone_id, work_order_id = (str(uuid.uuid4()) for _ in range(3))
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    graders = _grader_results(
        violations=[
            {
                "rule": "LAYER-MAP Rule 1",
                "file": "runtime/hooks/x.py",
                "detail": "hook writes to authority table",
            }
        ],
    )

    first = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert first["passed"] is False
    for s in first["spawned_work_orders"]:
        _set_status(db_path, s["work_order_id"], "closed")

    second = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert second["passed"] is False
    assert second["resolved_gaps"] == []
