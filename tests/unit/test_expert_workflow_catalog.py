from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.adapter_config_projection import adapter_config_projection_report
from core.shared_intelligence.contract_atlas import build_contract_atlas
from core.shared_intelligence.expert_workflows import (
    DESIGN_SPECIALIZED_SKILLS,
    REQUIRED_WORKFLOW_IDS,
    expert_workflow_catalog,
    validate_expert_workflow_catalog,
)


def test_expert_workflow_catalog_covers_required_workflows_and_overlap_decisions() -> None:
    catalog = expert_workflow_catalog(project_id="dream-studio")

    assert validate_expert_workflow_catalog(catalog) == []
    assert {workflow["workflow_id"] for workflow in catalog["workflows"]} == set(
        REQUIRED_WORKFLOW_IDS
    )
    assert catalog["workflow_count"] == 10
    assert catalog["db_write_authorized"] is False
    assert catalog["no_duplicate_skill_policy"].startswith("strengthen or map existing")
    decisions = {row["workflow_id"]: row["decision"] for row in catalog["overlap_matrix"]}
    assert decisions["root_cause_debugging_workflow"] == "keep_existing"
    assert decisions["frontend_design_excellence_workflow"] == "split_existing"
    assert "create_new" not in catalog["overlap_decision_counts"]


def test_intentional_implementation_workflow_requires_pre_change_contract() -> None:
    workflow = _workflow("intentional_implementation_workflow")

    required_inputs = set(workflow["input_contract"])
    assert "why code is needed" in required_inputs
    assert "alternatives considered" in required_inputs
    assert "affected layer/module/contract" in required_inputs
    assert "validation plan" in required_inputs
    assert "rollback plan" in required_inputs
    assert workflow["skill_overlap_supersession_status"]["decision"] == "strengthen_existing"


def test_design_workflow_uses_specialized_lenses_without_new_monolith() -> None:
    catalog = expert_workflow_catalog()
    workflow = _workflow("frontend_design_excellence_workflow")

    assert set(workflow["specialized_skills"]) == set(DESIGN_SPECIALIZED_SKILLS)
    assert catalog["specialized_skill_families"]["frontend_design_excellence_workflow"] == list(
        DESIGN_SPECIALIZED_SKILLS
    )
    assert workflow["skill_overlap_supersession_status"]["decision"] == "split_existing"
    score_ids = {score["score_id"] for score in workflow["scoring_rubric"]}
    assert {
        "ux_clarity",
        "visual_hierarchy",
        "accessibility",
        "responsive_behavior",
        "component_consistency",
        "data_visualization",
        "implementation_feasibility",
    } <= score_ids


def test_score_rubrics_are_evidence_backed_and_honest_when_missing() -> None:
    for workflow in expert_workflow_catalog()["workflows"]:
        assert workflow["scoring_rubric"]
        for score in workflow["scoring_rubric"]:
            assert score["evidence_required"] is True
            assert score["confidence_required"] is True
            assert score["fake_precision_allowed"] is False
            assert "unavailable" in score["missing_evidence_behavior"]


def test_contract_atlas_exposes_expert_workflow_system(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    repo_root = tmp_path / "repo"
    _write_current_hook_surfaces(home)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    with _connect(tmp_path / "studio.db") as conn:
        register_default_adapter_authority_profiles(conn)
        projection_report = adapter_config_projection_report(conn, project_id="dream-studio")
        _write_projection_files(repo_root, projection_report)
        atlas = build_contract_atlas(conn, repo_root=repo_root, project_id="dream-studio")

    assert atlas["expert_workflow_system"]["workflow_count"] == 10
    assert atlas["expert_workflow_system"]["validation_status"] == "pass"
    assert any(
        item["area"] == "expert_workflow_system" and item["status"] == "validated"
        for item in atlas["maturity_scorecard"]
    )
    graph = atlas["confirmed_dependency_graph"]
    assert any(
        edge["source"] == "module:expert_workflow_system"
        and edge["target"] == "workflow:intentional_implementation_workflow"
        for edge in graph["edges"]
    )


def _workflow(workflow_id: str) -> dict:
    return next(
        workflow
        for workflow in expert_workflow_catalog()["workflows"]
        if workflow["workflow_id"] == workflow_id
    )


def _write_projection_files(repo_root: Path, projection_report: dict) -> None:
    for projection in projection_report["projections"]:
        _write(repo_root / projection["projection_path"], projection["content"])
    _write(
        repo_root / "AGENTS.md",
        "Dream Studio SQLite authority projection for Codex.\nadapter-projections/codex/AGENTS.md\n",
    )
    _write(
        repo_root / "CLAUDE.md",
        "Dream Studio SQLite authority projection for Claude.\nadapter-projections/claude/CLAUDE.md\n",
    )


def _write_current_hook_surfaces(home: Path) -> None:
    _write(
        home / ".claude" / "settings.json",
        """
{
  "hooks": {
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "python \\"C:/Example/hooks/run.py\\" on-prompt-dispatch"}]}
    ]
  }
}
""".lstrip(),
    )
    _write(
        home / ".codex" / "hooks.json",
        """
{
  "hooks": {
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "\\"C:/Example/hooks/run.cmd\\" on-prompt-dispatch"}]}
    ]
  }
}
""".lstrip(),
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
