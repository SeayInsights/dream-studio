"""Tests for the WO-EXEC-LOOP autonomous close flow in core.work_orders.close.

Scenarios exercised:
1. auto-verify triggers — verify_work_order called inline when independent_review
   gate applies and no verdict file exists.
2. auto-verify skipped — verify_work_order NOT called when verdict file already exists.
3. pass path — after verify passes, close succeeds and next WO is auto-started.
4. gap path — after verify returns gaps, remediation WO is registered and auto-started;
   original WO still closes.
5. T4c: correctness fail — completion passes but correctness grader finds an
   architectural violation; remediation WO registered, original WO still closes.
6. T4d: composite below threshold — quality issues tank composite below 0.70;
   gap WO registered, auto-continue blocked.
7. T4d: _compute_scores weights — unit test of composite score formula.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-20T00:00:00+00:00"
PROJECT_ID = "p-exec-loop-0001"
MILESTONE_ID = "ms-exec-loop-0001"
WO_INFRA = "wo-infra-exec-loop-0001"
WO_NEXT = "wo-next-exec-loop-0002"
GAP_WO_ID = "gap-wo-exec-loop-9999"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute(
            "INSERT INTO business_projects"
            " (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'active', ?, ?)",
            (PROJECT_ID, "ExecLoop Project", "", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, description, status, order_index,"
            " created_at, updated_at)"
            " VALUES (?, ?, 'M1', '', 'pending', 0, ?, ?)",
            (MILESTONE_ID, PROJECT_ID, NOW, NOW),
        )
        # Primary WO — infrastructure type has post_build_gate='independent_review'
        # (set by migration 114).
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, sequence_order, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Infra WO', '', 'in_progress', 'infrastructure', 10, ?, ?)",
            (WO_INFRA, PROJECT_ID, MILESTONE_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, 'T1', 'do thing', 'complete', ?, ?)",
            ("task-exec-1", WO_INFRA, PROJECT_ID, NOW, NOW),
        )
        # Next WO used by the pass-path auto-start.
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, sequence_order, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Next WO', '', 'created', 'documentation', 20, ?, ?)",
            (WO_NEXT, PROJECT_ID, MILESTONE_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return target


@pytest.fixture
def patched_paths(db_path: Path, tmp_path: Path):
    fake = MagicMock()
    fake.sqlite_path = db_path
    fake.source_root = REPO_ROOT
    fake.dream_studio_home = tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake):
        yield fake, db_path, tmp_path


def _planning(tmp_path: Path, wo_id: str) -> Path:
    p = tmp_path / ".planning"
    (p / "work-orders" / wo_id).mkdir(parents=True, exist_ok=True)
    return p


def _write_pass_verdict(planning: Path, wo_id: str) -> None:
    """Write a passing verdict file — required for the independent_review gate to pass."""
    path = planning / "work-orders" / wo_id / "review-verdict.json"
    path.write_text(json.dumps({"passed": True, "gaps": [], "summary": "ok"}), encoding="utf-8")


def _write_fail_verdict(planning: Path, wo_id: str) -> None:
    """Write a failing verdict file with one spawned gap WO."""
    path = planning / "work-orders" / wo_id / "review-verdict.json"
    path.write_text(
        json.dumps(
            {
                "passed": False,
                "summary": "T1 partial",
                "tasks_verified": [
                    {"task_title": "T1", "evidence": "missing", "verdict": "partial"}
                ],
                "gaps": [
                    {
                        "title": "Fix T1",
                        "description": "T1 was partial",
                        "work_order_type": "cleanup",
                    }
                ],
                "spawned_work_orders": [
                    {"work_order_id": GAP_WO_ID, "title": "Fix T1", "type": "cleanup"}
                ],
                "work_order_id": wo_id,
                "verified_at": NOW,
            }
        ),
        encoding="utf-8",
    )


def _mock_verify_pass(*, work_order_id, planning_root, **_kw):
    """Fake verify_work_order that writes a passing verdict and returns passed=True."""
    _write_pass_verdict(planning_root, work_order_id)
    return {
        "ok": True,
        "work_order_id": work_order_id,
        "passed": True,
        "summary": "all tasks verified",
        "tasks_verified": [],
        "gaps": [],
        "spawned_work_orders": [],
        "verdict_path": str(planning_root / "work-orders" / work_order_id / "review-verdict.json"),
    }


def _mock_verify_gap(*, work_order_id, planning_root, **_kw):
    """Fake verify_work_order that writes a failing verdict and returns passed=False."""
    _write_fail_verdict(planning_root, work_order_id)
    return {
        "ok": True,
        "work_order_id": work_order_id,
        "passed": False,
        "summary": "T1 partial",
        "tasks_verified": [{"task_title": "T1", "evidence": "missing", "verdict": "partial"}],
        "gaps": [{"title": "Fix T1", "description": "T1 partial", "work_order_type": "cleanup"}],
        "spawned_work_orders": [{"work_order_id": GAP_WO_ID, "title": "Fix T1", "type": "cleanup"}],
        "verdict_path": str(planning_root / "work-orders" / work_order_id / "review-verdict.json"),
    }


def _mock_verify_correctness_fail(*, work_order_id, planning_root, **_kw):
    """Completion passes but correctness grader found an architectural violation (T4c)."""
    verdict = {
        "passed": False,
        "summary": "Completion ok but architectural violation detected",
        "completion": {
            "passed": True,
            "tasks_verified": [{"task_title": "T1", "evidence": "done", "verdict": "pass"}],
            "gaps": [],
            "completion_score": 1.0,
        },
        "correctness": {
            "correctness_passed": False,
            "correctness_score": 0.857,
            "violations": [
                {
                    "rule": "Rule 3: business_* writes",
                    "file": "projections/foo.py",
                    "line": "42",
                    "detail": "business_tasks INSERT from projections/ module",
                }
            ],
            "coverage_gaps": [],
            "migration_gaps": [],
        },
        "quality": {"quality_passed": True, "quality_score": 1.0, "issues": []},
        "scores": {
            "completion_score": 1.0,
            "correctness_score": 0.857,
            "quality_score": 1.0,
            "composite_score": 0.757,
        },
        "gaps": [
            {
                "title": "Fix architectural violations flagged by correctness grader",
                "description": "1 architectural rule violation(s) detected.",
                "work_order_type": "cleanup",
                "tasks": [
                    {
                        "title": "Fix Rule 3 in projections/foo.py",
                        "description": "business_tasks INSERT from projections/ module",
                    }
                ],
            }
        ],
        "spawned_work_orders": [
            {
                "work_order_id": GAP_WO_ID,
                "title": "Fix architectural violations flagged by correctness grader",
                "type": "cleanup",
            }
        ],
        "work_order_id": work_order_id,
        "verified_at": NOW,
    }
    path = planning_root / "work-orders" / work_order_id / "review-verdict.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(verdict), encoding="utf-8")
    return {"ok": True, **verdict, "verdict_path": str(path)}


def _mock_verify_low_composite(*, work_order_id, planning_root, **_kw):
    """All tasks pass + no architectural violations, but quality issues tank composite
    below 0.70 (T4d threshold test)."""
    verdict = {
        "passed": False,
        "summary": "Low composite score due to quality errors",
        "scores": {
            "completion_score": 1.0,
            "correctness_score": 1.0,
            "quality_score": 0.2,
            "composite_score": 0.64,
        },
        "completion": {
            "passed": True,
            "tasks_verified": [{"task_title": "T1", "evidence": "done", "verdict": "pass"}],
            "gaps": [],
            "completion_score": 1.0,
        },
        "correctness": {
            "correctness_passed": True,
            "correctness_score": 1.0,
            "violations": [],
            "coverage_gaps": [],
            "migration_gaps": [],
        },
        "quality": {
            "quality_passed": False,
            "quality_score": 0.2,
            "issues": [
                {
                    "category": "SECURITY",
                    "file": "core/foo.py",
                    "line": "10",
                    "detail": "bare eval() call",
                    "severity": "error",
                }
            ],
        },
        "gaps": [
            {
                "title": "Fix error-severity quality issues",
                "description": "1 error-severity quality issue(s) detected.",
                "work_order_type": "cleanup",
                "tasks": [
                    {
                        "title": "Fix SECURITY issue in core/foo.py",
                        "description": "bare eval() call",
                    }
                ],
            }
        ],
        "spawned_work_orders": [
            {
                "work_order_id": GAP_WO_ID,
                "title": "Fix error-severity quality issues",
                "type": "cleanup",
            }
        ],
        "work_order_id": work_order_id,
        "verified_at": NOW,
    }
    path = planning_root / "work-orders" / work_order_id / "review-verdict.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(verdict), encoding="utf-8")
    return {"ok": True, **verdict, "verdict_path": str(path)}


_MOCK_START_OK = {"ok": True, "work_order_id": WO_NEXT, "title": "Next WO"}
_MOCK_START_GAP_OK = {"ok": True, "work_order_id": GAP_WO_ID, "title": "Fix T1"}
_MOCK_NEXT_WO = {
    "ok": True,
    "work_order": {
        "work_order_id": WO_NEXT,
        "title": "Next WO",
        "work_order_type": "documentation",
        "milestone": "M1",
        "next_command": f"ds work-order start {WO_NEXT}",
    },
}


# ── Scenario 1: auto-verify triggers ────────────────────────────────────────


def test_auto_verify_triggered_when_no_verdict_file(patched_paths) -> None:
    """verify_work_order is called inline when independent_review gate applies
    and no review-verdict.json exists yet."""
    _fake, db_path, tmp_path = patched_paths
    planning = _planning(tmp_path, WO_INFRA)

    with (
        patch("core.work_orders.verify.verify_work_order", side_effect=_mock_verify_pass) as mock_v,
        patch("core.work_orders.start.start_work_order", return_value=_MOCK_START_OK),
        patch("core.projects.queries.get_next_work_order", return_value=_MOCK_NEXT_WO),
    ):
        from core.work_orders.close import close_work_order

        result = close_work_order(
            work_order_id=WO_INFRA,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning,
        )

    assert mock_v.called, "verify_work_order should be called inline when no verdict file exists"
    assert result["ok"] is True


def test_auto_verify_skipped_when_verdict_exists(patched_paths) -> None:
    """verify_work_order is NOT called when review-verdict.json already exists."""
    _fake, db_path, tmp_path = patched_paths
    planning = _planning(tmp_path, WO_INFRA)
    _write_pass_verdict(planning, WO_INFRA)

    with (
        patch("core.work_orders.verify.verify_work_order") as mock_v,
        patch("core.work_orders.start.start_work_order", return_value=_MOCK_START_OK),
        patch("core.projects.queries.get_next_work_order", return_value=_MOCK_NEXT_WO),
    ):
        from core.work_orders.close import close_work_order

        result = close_work_order(
            work_order_id=WO_INFRA,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning,
        )

    assert not mock_v.called, "verify_work_order must not be called when verdict already exists"
    assert result["ok"] is True


# ── Scenario 2: pass path auto-starts next WO ────────────────────────────────


def test_pass_path_auto_starts_next_wo(patched_paths) -> None:
    """When verify passes, close succeeds and the next WO is auto-started."""
    _fake, db_path, tmp_path = patched_paths
    planning = _planning(tmp_path, WO_INFRA)

    with (
        patch("core.work_orders.verify.verify_work_order", side_effect=_mock_verify_pass),
        patch("core.projects.queries.get_next_work_order", return_value=_MOCK_NEXT_WO),
        patch("core.work_orders.start.start_work_order", return_value=_MOCK_START_OK) as mock_start,
    ):
        from core.work_orders.close import close_work_order

        result = close_work_order(
            work_order_id=WO_INFRA,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning,
        )

    assert result["ok"] is True
    assert result["status"] == "closed"
    assert "auto_started" in result, "auto_started key should be present on pass path"
    assert result["auto_started"]["work_order_id"] == WO_NEXT
    assert mock_start.called
    assert mock_start.call_args.kwargs.get("work_order_id") == WO_NEXT


# ── Scenario 3: gap path closes original and auto-starts gap WO ──────────────


def test_gap_path_closes_original_and_auto_starts_gap_wo(patched_paths) -> None:
    """When verify returns gaps, the original WO still closes and the first
    spawned gap WO is auto-started."""
    _fake, db_path, tmp_path = patched_paths
    planning = _planning(tmp_path, WO_INFRA)

    with (
        patch("core.work_orders.verify.verify_work_order", side_effect=_mock_verify_gap),
        patch(
            "core.work_orders.start.start_work_order", return_value=_MOCK_START_GAP_OK
        ) as mock_start,
    ):
        from core.work_orders.close import close_work_order

        result = close_work_order(
            work_order_id=WO_INFRA,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning,
        )

    assert result["ok"] is True, f"Original WO should close even when gaps found: {result}"
    assert result["status"] == "closed"
    assert "gaps_block" in result, "gaps_block should be present when gaps are found"
    assert "GAPS FOUND" in result["gaps_block"]
    assert "REMEDIATION WO" in result["gaps_block"]
    assert "auto_started" in result
    assert result["auto_started"]["work_order_id"] == GAP_WO_ID
    assert mock_start.called
    assert mock_start.call_args.kwargs.get("work_order_id") == GAP_WO_ID


# ── T4c: correctness fail registers remediation WO ──────────────────────────────


def test_correctness_fail_registers_remediation_wo_and_closes_original(patched_paths) -> None:
    """When completion passes but the correctness grader finds an architectural
    violation, the original WO still closes and the violation gap WO is auto-started."""
    _fake, db_path, tmp_path = patched_paths
    planning = _planning(tmp_path, WO_INFRA)

    with (
        patch(
            "core.work_orders.verify.verify_work_order",
            side_effect=_mock_verify_correctness_fail,
        ),
        patch(
            "core.work_orders.start.start_work_order", return_value=_MOCK_START_GAP_OK
        ) as mock_start,
    ):
        from core.work_orders.close import close_work_order

        result = close_work_order(
            work_order_id=WO_INFRA,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning,
        )

    assert result["ok"] is True, f"WO should close even with correctness failure: {result}"
    assert result["status"] == "closed"
    assert "gaps_block" in result, "gaps_block must surface correctness violation gaps"
    assert "GAPS FOUND" in result["gaps_block"]
    assert "auto_started" in result
    assert result["auto_started"]["work_order_id"] == GAP_WO_ID
    assert mock_start.called
    assert mock_start.call_args.kwargs.get("work_order_id") == GAP_WO_ID


# ── T4d: composite below threshold triggers gap ──────────────────────────────────


def test_composite_below_threshold_triggers_gap(patched_paths) -> None:
    """When quality issues tank composite below 0.70, auto-continue is blocked and
    a quality gap WO is registered and auto-started."""
    _fake, db_path, tmp_path = patched_paths
    planning = _planning(tmp_path, WO_INFRA)

    with (
        patch(
            "core.work_orders.verify.verify_work_order",
            side_effect=_mock_verify_low_composite,
        ),
        patch(
            "core.work_orders.start.start_work_order", return_value=_MOCK_START_GAP_OK
        ) as mock_start,
    ):
        from core.work_orders.close import close_work_order

        result = close_work_order(
            work_order_id=WO_INFRA,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning,
        )

    assert result["ok"] is True
    assert result["status"] == "closed"
    assert "gaps_block" in result
    assert "GAPS FOUND" in result["gaps_block"]
    assert "auto_started" in result
    assert result["auto_started"]["work_order_id"] == GAP_WO_ID
    assert mock_start.called


# ── T4d: _compute_scores unit test ───────────────────────────────────────────────


def test_compute_scores_composite_weights() -> None:
    """Composite = completion*0.5 + correctness*0.3 + quality*0.2."""
    from core.work_orders.verify import _compute_scores

    scores = _compute_scores(
        completion={"passed": True, "completion_score": 1.0, "tasks_verified": []},
        correctness={"correctness_passed": True, "correctness_score": 1.0},
        quality={"quality_passed": True, "quality_score": 0.8},
        total_tasks=2,
    )
    assert scores["completion_score"] == 1.0
    assert scores["correctness_score"] == 1.0
    assert scores["quality_score"] == 0.8
    # 1.0*0.5 + 1.0*0.3 + 0.8*0.2 = 0.96
    assert abs(scores["composite_score"] - 0.96) < 0.001


def test_compute_scores_below_threshold() -> None:
    """Composite < 0.70 when correctness and quality are both degraded."""
    from core.work_orders.verify import _compute_scores

    # 1.0*0.5 + 0.5*0.3 + 0.0*0.2 = 0.65
    scores = _compute_scores(
        completion={"passed": True, "completion_score": 1.0},
        correctness={"correctness_passed": False, "correctness_score": 0.5},
        quality={"quality_passed": False, "quality_score": 0.0},
        total_tasks=1,
    )
    assert scores["composite_score"] < 0.70


# ── WO 0d1166fa: verify exception propagation ─────────────────────────────────────


def test_verify_exception_returns_ok_false(patched_paths) -> None:
    """If verify_work_order() raises, close_work_order() returns ok=False instead of crashing."""
    _fake, db_path, tmp_path = patched_paths
    planning = _planning(tmp_path, WO_INFRA)

    with patch(
        "core.work_orders.verify.verify_work_order",
        side_effect=RuntimeError("subprocess spawn failed"),
    ):
        from core.work_orders.close import close_work_order

        result = close_work_order(
            work_order_id=WO_INFRA,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning,
        )

    assert result["ok"] is False
    assert "Auto-verify raised an exception" in result["error"]
    assert "subprocess spawn failed" in result["error"]
