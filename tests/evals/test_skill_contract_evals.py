"""C3 — Skill output contract evals.

Verifies the function contracts backing the seven core ds-project / ds-core
skill modes. These are deterministic function-call tests — no live AI, no
subprocess. Each test maps to one skill's output contract.

  eval_scope    — register_project() + create_milestone() produce correct shapes
  eval_plan     — create_work_order() + create_task() produce correct shapes
  eval_build    — start_work_order() writes context.md, status → in_progress
  eval_resume   — get_project_state() dict has required structural keys
  eval_brief    — full brief lifecycle: create → update_field → lock
  eval_review   — design_critique gate enforces Score: N/M threshold
  eval_handoff  — evaluate_handoff_prompt() returns structured evaluation dict
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-20T00:00:00+00:00"
PROJECT_ID = "cccc1111-cccc-cccc-cccc-cccccccc1111"
WO_ID = "cccc2222-cccc-cccc-cccc-cccccccc2222"
WO_UI_ID = "cccc3333-cccc-cccc-cccc-cccccccc3333"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute(
            "INSERT INTO business_projects VALUES (?, 'Contract Project', '', 'active', ?, ?)",
            (PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'Docs WO', '', 'created', 'documentation', ?, ?)",
            (WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'UI WO', '', 'in_progress', 'ui_component', ?, ?)",
            (WO_UI_ID, PROJECT_ID, NOW, NOW),
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
        yield fake


# ── eval_scope ────────────────────────────────────────────────────────────────


def test_eval_scope_contract(patched_paths, db_path: Path, tmp_path: Path) -> None:
    """scope: register_project() and create_milestone() produce correct output shapes."""
    from core.milestones.mutations import create_milestone
    from core.projects.mutations import register_project

    proj_result = register_project(
        name="Scoped Project",
        description="A scoped project",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert proj_result["ok"] is True
    assert "project_id" in proj_result
    assert proj_result["status"] == "active"
    assert len(proj_result["project_id"]) == 36

    ms_result = create_milestone(
        project_id=proj_result["project_id"],
        title="Milestone 1",
        order_index=0,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert ms_result["ok"] is True
    assert "milestone_id" in ms_result
    assert ms_result["status"] == "pending"

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT name FROM business_projects WHERE project_id = ?", (proj_result["project_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "Scoped Project"


# ── eval_plan ─────────────────────────────────────────────────────────────────


def test_eval_plan_contract(patched_paths, db_path: Path, tmp_path: Path) -> None:
    """plan: create_work_order() and create_task() produce correct output shapes."""
    from core.work_orders.mutations import create_task, create_work_order

    wo_result = create_work_order(
        project_id=PROJECT_ID,
        title="Plan work order",
        work_order_type="documentation",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert wo_result["ok"] is True
    assert "work_order_id" in wo_result
    assert wo_result["status"] == "created"

    task_result = create_task(
        work_order_id=wo_result["work_order_id"],
        project_id=PROJECT_ID,
        title="Write plan section",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert task_result["ok"] is True
    assert "task_id" in task_result
    assert task_result["work_order_id"] == wo_result["work_order_id"]
    assert task_result["status"] == "pending"


# ── eval_build ────────────────────────────────────────────────────────────────


def test_eval_build_contract(patched_paths, db_path: Path, tmp_path: Path) -> None:
    """build: start_work_order() writes context.md, transitions WO to in_progress."""
    from core.work_orders.start import start_work_order

    result = start_work_order(
        work_order_id=WO_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert "context_path" in result
    context_path = Path(result["context_path"])
    assert context_path.is_file()

    conn = sqlite3.connect(str(db_path))
    try:
        status = conn.execute(
            "SELECT status FROM business_work_orders WHERE work_order_id = ?", (WO_ID,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert status == "in_progress"


# ── eval_resume ───────────────────────────────────────────────────────────────


def test_eval_resume_contract(patched_paths, tmp_path: Path) -> None:
    """resume: get_project_state() return dict has required structural keys."""
    from core.projects.queries import get_project_state

    result = get_project_state(
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert "projects" in result
    assert result["projects"]

    project = result["projects"][0]
    required_keys = {"project_id", "name", "status", "next_work_order", "next_action"}
    assert required_keys.issubset(
        project.keys()
    ), f"Missing keys in project: {required_keys - set(project.keys())}"
    wo = project["next_work_order"]
    assert wo is not None
    assert "work_order_id" in wo
    assert "title" in wo
    assert "status" in wo


# ── eval_brief ────────────────────────────────────────────────────────────────


def test_eval_brief_contract(patched_paths, db_path: Path, tmp_path: Path) -> None:
    """brief: create → update_field → lock lifecycle produces correct DB state."""
    from core.design_briefs.mutations import (
        create_design_brief,
        lock_design_brief,
        update_design_brief_field,
    )

    create_result = create_design_brief(
        project_id=PROJECT_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert create_result["ok"] is True
    assert create_result["status"] == "draft"
    brief_id = create_result["brief_id"]

    update_result = update_design_brief_field(
        brief_id=brief_id,
        field="purpose",
        value="Track project progress",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert update_result["ok"] is True
    assert update_result["field"] == "purpose"
    assert update_result["value"] == "Track project progress"

    lock_result = lock_design_brief(
        brief_id=brief_id,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert lock_result["ok"] is True
    assert lock_result["status"] == "locked"

    # DB state updates (lock, field write) are now deferred to DesignBriefProjection.
    # Return-value assertions above confirm the writer contract; projection behavior
    # is covered by tests/unit/test_phase18_2_4_design_brief_projection.py.


# ── eval_review ───────────────────────────────────────────────────────────────


def test_eval_review_contract(tmp_path: Path) -> None:
    """review: design_critique gate validates Score: N/M format at threshold ≥ 3."""
    from core.work_orders.close import run_gate_check

    WO = "review-eval-wo-0001"
    planning_root = tmp_path / ".planning"
    wo_dir = planning_root / "work-orders" / WO
    wo_dir.mkdir(parents=True)

    (wo_dir / "design-critique.md").write_text("Score: 4/5\nLooks solid.", encoding="utf-8")
    passed, reason = run_gate_check(
        "design_critique",
        planning_root=planning_root,
        work_order_id=WO,
        project_id="proj-review-test",
        conn=None,
    )
    assert passed is True

    (wo_dir / "design-critique.md").write_text("Score: 2/5\nNeeds work.", encoding="utf-8")
    passed, reason = run_gate_check(
        "design_critique",
        planning_root=planning_root,
        work_order_id=WO,
        project_id="proj-review-test",
        conn=None,
    )
    assert passed is False
    assert "design_critique" in reason


# ── eval_handoff ──────────────────────────────────────────────────────────────


def test_eval_handoff_contract() -> None:
    """handoff: evaluate_handoff_prompt() returns a structured dict keyed by eval type."""
    from core.work_orders.handoff import (
        HANDOFF_CONSTRAINT_PRESERVATION,
        HANDOFF_FRESH_SESSION_SUFFICIENCY,
        HANDOFF_PROMPT_COMPLETENESS,
        evaluate_handoff_prompt,
    )

    minimal_prompt = (
        "# Handoff Packet\n"
        "handoff_type: standard\n"
        "Assume you have no prior conversation context."
        " Use only this prompt and referenced artifacts.\n"
        "work_order_id: test-wo-001\n"
        "stay within the module_boundary\n"
        "forbidden_actions: none\n"
        "approval_mode: observe_only\n"
        "validation_commands: none\n"
    )

    result = evaluate_handoff_prompt(
        minimal_prompt,
        readiness="READY",
        can_continue=True,
        target_repo_required=False,
    )

    assert isinstance(result, dict), "evaluate_handoff_prompt must return a dict"
    for key in (
        HANDOFF_PROMPT_COMPLETENESS,
        HANDOFF_CONSTRAINT_PRESERVATION,
        HANDOFF_FRESH_SESSION_SUFFICIENCY,
    ):
        assert key in result, f"Missing eval key: {key}"
        eval_result = result[key]
        assert "pass_fail" in eval_result, f"Eval {key} missing pass_fail"
        assert eval_result["pass_fail"] in {
            "pass",
            "fail",
            "incomplete",
        }, f"Invalid pass_fail value for {key}: {eval_result['pass_fail']}"
