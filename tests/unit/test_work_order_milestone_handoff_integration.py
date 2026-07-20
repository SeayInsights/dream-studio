from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config.database import DB_PATH_ENV, DatabaseRuntime


@pytest.fixture(autouse=True)
def _isolate_telemetry_db(tmp_path, monkeypatch):
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "telemetry.db"))
    DatabaseRuntime.reset_instance()
    yield
    DatabaseRuntime.reset_instance()


def _work_order(target_path: Path) -> dict:
    return {
        "work_order_id": "wo-milestone-routing-001",
        "project_name": "Milestone Routing Test",
        "target_path": str(target_path),
        "objective": "Route from PRD milestone authority before handoff generation.",
        "approval_mode": "observe_only",
        "risk_level": "low",
        "scope": {"include": ["core/work_orders/milestones.py"], "exclude": ["runtime"]},
        "allowed_skills": ["ds-core"],
        "allowed_agents": [],
        "workflow": "milestone routing",
        "forbidden_actions": ["no commits", "no migrations", "no external project work"],
        "validation_commands": [
            "python -m pytest tests/unit/test_work_order_milestone_handoff_integration.py -q"
        ],
        "expected_outputs": ["routing decision"],
        "stop_conditions": ["stage gate invalid", "approval missing"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "reported",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def _milestone_state(step: dict, **milestone_overrides) -> dict:
    milestone = {
        "id": "milestone-controller",
        "status": "in_progress",
        "pending_internal_steps": [step],
        "next_milestone": "generated_handoff_self_validation",
        "handoff_policy": "stop_gate_or_milestone_completion",
        "auto_continue_low_risk": True,
    }
    milestone.update(milestone_overrides)
    return {
        "prd": {"prd_id": "prd-dream-studio", "product_goals": ["handoff-light milestones"]},
        "stage_gate": {
            "stage_gate_id": "operational_loop_authority",
            "milestone_sequence": ["milestone-controller", "generated_handoff_self_validation"],
            "blocked_milestones": ["torii_resume"],
        },
        "milestone": milestone,
        "strategic_constraints": {
            "paused_external_projects": ["Bill Stack", "DreamySuite", "TORII"]
        },
    }


def _sections(tmp_path: Path, milestone_state: dict) -> dict:
    from core.work_orders.handoff import build_handoff_sections

    return build_handoff_sections(
        work_order=_work_order(tmp_path / "target"),
        result_metadata={
            "raw_output_ref": "result.md",
            "next_work_order_recommendation": (
                "Phase 99 - Naive Next Prompt; Next Work Order: wo-naive-001; "
                "Objective: naive handoff routing; Risk: low; Approval: observe_only."
            ),
            "milestone_state": milestone_state,
        },
        eval_artifacts=[{"eval_type": "target_repo_mutation", "pass_fail": "incomplete"}],
        report_path=tmp_path / "report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
    )


def test_low_risk_milestone_step_suppresses_next_handoff_prompt(tmp_path) -> None:
    sections = _sections(
        tmp_path,
        _milestone_state({"id": "checklist", "type": "checklist_review"}),
    )

    assert sections["decision"]["recommended_action"] == "continue_internal"
    assert sections["decision"]["handoff_required"] is False
    assert "# Continuation Packet" in sections["prompt"]
    assert "# Handoff Packet" not in sections["prompt"]
    assert "artifact_type: continuation_packet" in sections["prompt"]
    assert "is_handoff: false" in sections["prompt"]
    assert "operator_action_required: false" in sections["prompt"]
    assert sections["self_validation"]["pass_fail"] == "pass"


def test_report_marks_internal_continuation_as_no_operator_action(tmp_path) -> None:
    from core.work_orders.reporting import generate_report
    from core.work_orders.results import record_result
    from core.work_orders.storage import save_work_order

    storage_root = tmp_path / "store"
    target = tmp_path / "target"
    target.mkdir()
    work_order = _work_order(target)
    work_order["forbidden_actions"] = [
        "no edits",
        "no deletes",
        "no commits",
        "no schema changes",
        "no dependency changes",
        "no external actions",
        "no target repo mutation",
    ]
    save_work_order(work_order, storage_root=storage_root)
    result_source = tmp_path / "result.md"
    result_source.write_text("Focused validation complete.\n", encoding="utf-8")
    record_result(work_order["work_order_id"], source_path=result_source, storage_root=storage_root)
    # WO-FILESDB-C5: results + report live in the authority-free packet store.
    from core.work_orders.packet_store import get_packet_artifact, set_packet_artifact

    wo_id = work_order["work_order_id"]
    result_metadata = json.loads(
        get_packet_artifact(wo_id, "result_meta", storage_root=storage_root)
    )
    result_metadata["milestone_state"] = _milestone_state(
        {"id": "checklist", "type": "checklist_review"}
    )
    result_metadata["next_work_order_recommendation"] = (
        "Phase 99 - Naive Next Prompt; Next Work Order: wo-naive-001; "
        "Objective: naive handoff routing; Risk: low; Approval: observe_only."
    )
    set_packet_artifact(
        wo_id,
        "result_meta",
        json.dumps(result_metadata, indent=2, sort_keys=True) + "\n",
        storage_root=storage_root,
    )

    generate_report(wo_id, storage_root=storage_root)
    report_text = get_packet_artifact(wo_id, "report", storage_root=storage_root)

    assert "- route_decision: continue_internal" in report_text
    assert "- handoff_required: false" in report_text
    assert "- operator_action_required: false" in report_text
    assert "- recommended_next_work_order: none" in report_text
    assert "# Continuation Packet" in report_text
    assert "# Handoff Packet" not in report_text


def test_stage_gate_overrides_naive_next_handoff_routing(tmp_path) -> None:
    sections = _sections(
        tmp_path,
        _milestone_state(
            {"id": "complete", "type": "report_generation"},
            pending_internal_steps=[],
            status="complete",
            next_milestone="torii_resume",
        ),
    )

    assert sections["decision"]["recommended_action"] == "hold_for_review"
    assert sections["decision"]["handoff_required"] is True
    assert sections["readiness"]["readiness"] == "HOLD"
    assert "stage_gate_blocks_next_milestone" in sections["readiness"]["blockers"]


def test_mutation_without_approval_routes_to_human_approval_handoff(tmp_path) -> None:
    sections = _sections(
        tmp_path,
        _milestone_state(
            {"id": "mutate", "type": "source_code_mutation", "requires_approval": True}
        ),
    )

    assert sections["decision"]["recommended_action"] == "request_human_approval"
    assert sections["decision"]["human_approval_required"] is True
    assert sections["decision"]["handoff_required"] is True
    assert sections["readiness"]["readiness"] == "HOLD"


def test_failed_validation_routes_to_required_handoff(tmp_path) -> None:
    sections = _sections(
        tmp_path,
        _milestone_state(
            {
                "id": "validate",
                "type": "non_mutating_validation",
                "validation_result": "failed",
            }
        ),
    )

    assert sections["decision"]["recommended_action"] == "generate_handoff"
    assert sections["decision"]["handoff_required"] is True
    assert sections["decision"]["handoff_reason"] == "failed_validation"


def test_structured_authority_projection_stage_starts_next_milestone_without_planning_handoff(
    tmp_path,
) -> None:
    sections = _sections(
        tmp_path,
        {
            "prd": {
                "prd_id": "prd-dream-studio",
                "product_goals": ["structured authority projection"],
            },
            "stage_gate": {
                "stage_gate_id": "structured_authority_projection",
                "milestone_sequence": [
                    "structured_state_authority_projection",
                    "dashboard_projection_mapping",
                ],
                "blocked_milestones": [],
            },
            "milestone": {
                "id": "structured_state_authority_projection",
                "status": "complete",
                "pending_internal_steps": [],
                "completed_internal_steps": ["review", "report_writing"],
                "next_milestone": "dashboard_projection_mapping",
                "handoff_policy": "stop_gate_or_milestone_completion",
            },
            "strategic_constraints": {
                "paused_external_projects": ["Bill Stack", "DreamySuite", "TORII"]
            },
        },
    )

    assert sections["decision"]["recommended_action"] == "start_next_milestone"
    assert sections["decision"]["handoff_required"] is False
    assert "# Continuation Packet" in sections["prompt"]
    assert "Phase 99 - Naive Next Prompt" not in sections["prompt"]


def test_user_requested_export_can_generate_valid_handoff(tmp_path) -> None:
    work_order = _work_order(tmp_path / "target")
    work_order["handoff_context"] = {
        "handoff_reason": "user_requested_export_or_continuation",
        "source_authority_refs": ["PRD", "stage gates"],
        "evidence_refs": ["result.md"],
        "validation_refs": ["focused tests"],
    }
    from core.work_orders.handoff import build_handoff_sections

    sections = build_handoff_sections(
        work_order=work_order,
        result_metadata={
            "raw_output_ref": "result.md",
            "next_work_order_recommendation": (
                "Phase 99 - User Requested Export; Next Work Order: wo-export-001; "
                "Objective: export continuation packet; Risk: low; Approval: observe_only."
            ),
        },
        eval_artifacts=[{"eval_type": "target_repo_mutation", "pass_fail": "incomplete"}],
        report_path=tmp_path / "report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
    )

    assert sections["decision"]["handoff_required"] is True
    assert sections["decision"]["handoff_reason"] == "user_requested_export_or_continuation"
    assert sections["self_validation"]["pass_fail"] == "pass"
