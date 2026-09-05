"""WO-GRADER-ERROR-UNREVIEWABLE: a grader that could not run is not evidence.

Discovered dogfooding 2026-08-19: the completion grader hit the provider
session limit and returned prose. Only EMPTY grader output was treated as
unreviewable, so the non-JSON hard error fell through to scoring —
completion_score 0.0 → verdict FAILED with an empty summary. An infrastructure
failure silently became a substantive negative verdict (a false-fail, the
mirror of false-done), blocking two real work orders from closing.
"""

from __future__ import annotations

import json

from tests.helpers.stored_verdict import read_stored_verdict
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-16T00:00:00.000000Z"
QUOTA_MSG = "Grader returned non-JSON.\nRaw:\nYou've hit your session limit · resets 12:10pm\n"


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


def _seed(db_path: Path) -> str:
    project_id, milestone_id, work_order_id = (str(uuid.uuid4()) for _ in range(3))
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "Test", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description,"
        "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,'in_progress',1,?,?,?)",
        (work_order_id, project_id, milestone_id, "Test WO", "d", "cleanup", NOW, NOW, NOW),
    )
    for i in range(4):
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            "  created_at, updated_at)"
            " VALUES (?,?,?,?,?, 'complete', ?, ?)",
            (str(uuid.uuid4()), work_order_id, project_id, f"T{i}", "do", NOW, NOW),
        )
    conn.commit()
    conn.close()
    return work_order_id


def _run(db_path: Path, tmp_path: Path, work_order_id: str, graders: dict) -> dict:
    with _patch_db(db_path):
        with patch("core.work_orders.verify_graders._run_graders_parallel", return_value=graders):
            with patch(
                "core.work_orders.verify_git._collect_git_commits",
                return_value="diff --git a/x.py b/x.py\n+change",
            ):
                from core.work_orders.verify import verify_work_order

                return verify_work_order(
                    work_order_id=work_order_id,
                    source_root=REPO_ROOT,
                    dream_studio_home=tmp_path,
                    planning_root=tmp_path / "planning",
                )


_CLEAN_CORRECTNESS = {
    "correctness_passed": True,
    "correctness_score": 1.0,
    "violations": [],
    "coverage_gaps": [],
    "migration_gaps": [],
}
_CLEAN_QUALITY = {"quality_passed": True, "quality_score": 1.0, "issues": []}


def test_grader_quota_error_is_unreviewable(tmp_path, monkeypatch):
    """A provider quota error must yield UNREVIEWABLE — not completion 0.0 and a
    FAILED verdict — and must name the provider error so quota is
    distinguishable from missing work."""
    monkeypatch.delenv("DREAM_STUDIO_VERIFY_MOCK", raising=False)
    db_path = _make_db(tmp_path)
    work_order_id = _seed(db_path)

    result = _run(
        db_path,
        tmp_path,
        work_order_id,
        {
            "completion": {"_grader_error": QUOTA_MSG},
            "correctness": _CLEAN_CORRECTNESS,
            "quality": _CLEAN_QUALITY,
        },
    )
    assert result["ok"] is True
    assert result["passed"] is False
    assert result["unreviewable"] is True, result
    assert "completion" in result["unreviewable_graders"]
    assert "session limit" in result["summary"]
    assert "GRADER failure" in result["summary"]
    # No false-fail artifacts: nothing spawned, no gaps invented.
    assert result["spawned_work_orders"] == []
    assert result["gaps"] == []

    # The persisted verdict carries the provider error verbatim for the operator.
    from core.work_orders.artifact_envelope import unwrap

    # DB-or-disk, matching the independent_review gate. Reading the disk path
    # unconditionally failed on a healthy authority, where the verdict lands in
    # business_work_order_artifacts and the disk fallback never fires.
    verdict = read_stored_verdict(
        work_order_id, db_path=db_path, planning_root=tmp_path / "planning"
    )
    assert verdict["unreviewable"] is True
    assert "session limit" in verdict["grader_errors"]["completion"]


def test_empty_output_path_unchanged(tmp_path, monkeypatch):
    """The pre-existing empty-output unreviewable behavior still holds."""
    monkeypatch.delenv("DREAM_STUDIO_VERIFY_MOCK", raising=False)
    db_path = _make_db(tmp_path)
    work_order_id = _seed(db_path)

    result = _run(
        db_path,
        tmp_path,
        work_order_id,
        {
            "completion": {"unreviewable": True, "reason": "grader_no_summary"},
            "correctness": _CLEAN_CORRECTNESS,
            "quality": _CLEAN_QUALITY,
        },
    )
    assert result["unreviewable"] is True
    assert "empty output" in result["summary"]


def test_clean_graders_still_score(tmp_path, monkeypatch):
    """A fully-successful grader set is unaffected — still scored and passed."""
    monkeypatch.delenv("DREAM_STUDIO_VERIFY_MOCK", raising=False)
    db_path = _make_db(tmp_path)
    work_order_id = _seed(db_path)

    result = _run(
        db_path,
        tmp_path,
        work_order_id,
        {
            "completion": {
                "passed": True,
                "completion_score": 1.0,
                "tasks_verified": [],
                "summary": "all done",
                "gaps": [],
            },
            "correctness": _CLEAN_CORRECTNESS,
            "quality": _CLEAN_QUALITY,
        },
    )
    assert result.get("unreviewable") is not True
    assert result["passed"] is True
    assert result["scores"]["composite_score"] == pytest.approx(1.0)
