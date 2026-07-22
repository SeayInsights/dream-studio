"""Tests for the BEHAVIORAL AC CHECK block in _COMPLETION_PROMPT_TEMPLATE.

WO-SKILL-COUPLING remediation (e8cc5b1e):
  T1: Assert the prompt text is present in the template.
  T2: Assert the warning gap flows through to spawned_work_orders when the
      completion grader returns it for a feature/infrastructure WO with no
      observable behavioral AC in task descriptions.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-01-01T00:00:00.000000Z"

_WARNING_GAP_TITLE = "Add observable behavioral acceptance criteria to task descriptions"


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


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
        " VALUES (?,?,?,?,?,'infrastructure','in_progress',1,?,?,?)",
        (work_order_id, project_id, milestone_id, "Test WO", "desc", NOW, NOW, NOW),
    )
    conn.commit()
    conn.close()


def _add_task(db_path: Path, *, work_order_id: str, project_id: str, desc: str) -> str:
    task_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,'complete',?,?)",
        (task_id, work_order_id, project_id, "T1", desc, NOW, NOW),
    )
    conn.commit()
    conn.close()
    return task_id


# ── T1: template content assertion ────────────────────────────────────────────


def test_completion_prompt_template_contains_behavioral_ac_check() -> None:
    """_COMPLETION_PROMPT_TEMPLATE must contain the BEHAVIORAL AC CHECK section.

    This catches any future edit that accidentally removes or renames the block
    (which would silently stop warning gaps from being requested of graders).
    """
    from core.work_orders.verify import _COMPLETION_PROMPT_TEMPLATE

    assert (
        "BEHAVIORAL AC CHECK" in _COMPLETION_PROMPT_TEMPLATE
    ), "BEHAVIORAL AC CHECK section missing from _COMPLETION_PROMPT_TEMPLATE"
    assert (
        "warning only" in _COMPLETION_PROMPT_TEMPLATE
    ), "'warning only' qualifier missing — grader must know this is non-blocking"
    assert (
        "never causes passed=false" in _COMPLETION_PROMPT_TEMPLATE
    ), "'never causes passed=false' qualifier missing — grader must not fail on missing AC"
    assert (
        '"feature"' in _COMPLETION_PROMPT_TEMPLATE or "feature" in _COMPLETION_PROMPT_TEMPLATE
    ), "work_order_type 'feature' not referenced in behavioral AC check"
    assert (
        '"infrastructure"' in _COMPLETION_PROMPT_TEMPLATE
        or "infrastructure" in _COMPLETION_PROMPT_TEMPLATE
    ), "work_order_type 'infrastructure' not referenced in behavioral AC check"
    assert (
        "{work_order_type}" in _COMPLETION_PROMPT_TEMPLATE
    ), "{work_order_type} placeholder missing — grader never sees the WO type"


# ── T2: warning gap propagation path ──────────────────────────────────────────


def test_behavioral_ac_warning_gap_creates_work_order(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """When the completion grader emits the warning gap for an infrastructure WO
    with no observable behavioral AC, verify_work_order must register it as a
    spawned documentation WO in SQLite.

    The grader (LLM) decides whether to emit the gap based on the BEHAVIORAL AC
    CHECK instruction. This test verifies that once the grader returns the gap,
    the Python pipeline (gap aggregation + _register_gap_work_orders) propagates
    it correctly — the same path used by all other grader-returned gaps.
    """
    from unittest.mock import MagicMock

    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    _add_task(
        db_path,
        work_order_id=work_order_id,
        project_id=project_id,
        # Task description has no 'Acceptance:', 'operator can', etc. — no behavioral AC.
        desc="Add the coupling domain entries to contract_registry.py.",
    )

    warning_gap = {
        "title": _WARNING_GAP_TITLE,
        "description": (
            "No task in this work order describes end-to-end observable behavior from the "
            "operator's perspective."
        ),
        "work_order_type": "documentation",
        "tasks": [
            {
                "title": "Add behavioral AC to task descriptions",
                "description": "Rewrite each task description to include an Acceptance: clause.",
            }
        ],
    }

    # Completion grader says the single task passed (not a code failure), but
    # emits the behavioral AC warning gap because no task has observable AC.
    completion_result = {
        "passed": True,
        "completion_score": 1.0,
        "tasks_verified": [{"task_title": "T1", "evidence": "found in diff", "verdict": "pass"}],
        "summary": "Task addressed. Warning: no behavioral AC found.",
        "gaps": [warning_gap],
    }
    # Correctness and quality return clean results so the composite passes.
    correctness_result = {
        "correctness_passed": True,
        "correctness_score": 1.0,
        "violations": [],
        "coverage_gaps": [],
        "migration_gaps": [],
    }
    quality_result = {
        "quality_passed": True,
        "quality_score": 1.0,
        "issues": [],
    }

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path
    planning_root = tmp_path / "planning"

    fake_diff = "diff --git a/core/shared_intelligence/contract_registry.py b/core/shared_intelligence/contract_registry.py\n+new domain entry"

    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        with patch(
            "core.work_orders.verify_graders._run_graders_parallel",
            return_value={
                "completion": completion_result,
                "correctness": correctness_result,
                "quality": quality_result,
            },
        ):
            with patch(
                "core.work_orders.verify_git._collect_git_commits",
                return_value=fake_diff,
            ):
                from core.work_orders.verify import verify_work_order

                result = verify_work_order(
                    work_order_id=work_order_id,
                    source_root=REPO_ROOT,
                    dream_studio_home=tmp_path,
                    planning_root=planning_root,
                )

    # The overall result should pass (warning gap doesn't cause passed=False).
    assert result["ok"] is True
    assert result["passed"] is True, (
        f"verify_work_order must pass when completion_score=1.0 and warning gap only; "
        f"got passed={result['passed']}"
    )

    # The warning gap must appear as a spawned documentation WO.
    spawned = result["spawned_work_orders"]
    assert any(
        _WARNING_GAP_TITLE in s["title"] for s in spawned
    ), f"Warning gap '{_WARNING_GAP_TITLE}' missing from spawned_work_orders: {spawned}"

    # Verify it is registered in SQLite as a documentation WO under the same milestone.
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT title, work_order_type, milestone_id"
        " FROM business_work_orders"
        " WHERE project_id = ? AND work_order_id != ?",
        (project_id, work_order_id),
    ).fetchall()
    conn.close()

    assert len(rows) == 1, f"Expected exactly 1 spawned WO; got: {rows}"
    title, wo_type, m_id = rows[0]
    assert _WARNING_GAP_TITLE in title, f"Unexpected spawned WO title: {title}"
    assert wo_type == "documentation", f"Warning gap WO must be type 'documentation'; got {wo_type}"
    assert m_id == milestone_id, "Spawned WO must be under the same milestone"
