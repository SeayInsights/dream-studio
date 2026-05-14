from __future__ import annotations

from pathlib import Path


def _work_order(target_path: Path) -> dict:
    return {
        "work_order_id": "wo-gate-001",
        "project_name": "Operator Gate Test",
        "target_path": str(target_path),
        "objective": "Generate an approved mutation execution handoff.",
        "approval_mode": "approval_required",
        "risk_level": "medium",
        "scope": {"include": ["src/app/a.ts"], "exclude": ["src/app/forbidden.ts"]},
        "allowed_skills": ["ds-core"],
        "allowed_agents": [],
        "workflow": "operator gate",
        "forbidden_actions": [
            "no push",
            "no schema changes",
            "no target repo mutation without approval",
        ],
        "validation_commands": ["python -m pytest -q"],
        "expected_outputs": ["operator decision gate"],
        "stop_conditions": ["missing operator decision"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "reported",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def _metadata() -> dict:
    return {
        "raw_output_ref": "result.md",
        "next_work_order_recommendation": (
            "wo-next-approved-001; Objective: execute approved mutation; Risk: medium; "
            "Approval: approval_required; Non-goals: broad mutation; Validation: focused tests."
        ),
    }


def _request() -> dict:
    return {
        "decision_request_id": "wo-gate-001.approved_mutation.decision",
        "work_order_id": "wo-gate-001",
        "phase_type": "approved_mutation",
        "required_decision_taxonomy": ["MUTATION_COMPLETE", "NEEDS_REMEDIATION", "HOLD", "FAIL"],
        "status": "pending_operator_decision",
        "question": "Proceed to execution handoff?",
        "allowed_decisions": ["MUTATION_COMPLETE", "NEEDS_REMEDIATION", "HOLD", "FAIL"],
        "recommended_decision": "MUTATION_COMPLETE",
        "risk_summary": "execution handoff requires operator decision",
        "required_evidence": ["report"],
        "requires_reason": True,
        "created_at": "2026-05-11T00:00:00Z",
        "_path": "/tmp/request.json",
    }


def _decision() -> dict:
    return {
        "decision_request_id": "wo-gate-001.approved_mutation.decision",
        "work_order_id": "wo-gate-001",
        "decision": "MUTATION_COMPLETE",
        "decided_by": "operator",
        "decided_at": "2026-05-11T00:00:00Z",
        "reason": "Approved after review.",
        "approved_next_handoff_type": "approved_mutation_execution",
        "constraints": ["no push"],
        "privacy_export_classification": "local_only",
        "_path": "/tmp/operator_decision.json",
    }


def test_execution_handoff_is_blocked_when_operator_decision_missing(tmp_path) -> None:
    from core.work_orders.handoff import build_handoff_sections

    sections = build_handoff_sections(
        work_order=_work_order(tmp_path / "target"),
        result_metadata=_metadata(),
        eval_artifacts=[],
        report_path=tmp_path / "report.md",
        decision_request=_request(),
    )

    assert sections["readiness"]["readiness"] == "HOLD"
    assert (
        "operator decision artifact missing for execution handoff"
        in sections["readiness"]["blockers"]
    )
    assert "## Handoff Type\nrecovery_decision" in sections["prompt"]
    assert (
        "operator_decision artifact required before generating an execution handoff"
        in sections["prompt"]
    )


def test_execution_handoff_can_be_generated_after_valid_operator_decision(tmp_path) -> None:
    from core.work_orders.handoff import build_handoff_sections

    sections = build_handoff_sections(
        work_order=_work_order(tmp_path / "target"),
        result_metadata=_metadata(),
        eval_artifacts=[],
        report_path=tmp_path / "report.md",
        decision_request=_request(),
        operator_decision=_decision(),
    )

    assert sections["readiness"]["readiness"] == "READY"
    assert sections["decision"]["final_decision"] == "MUTATION_COMPLETE"
    assert sections["decision"]["handoff_type"] == "approved_mutation_execution"
    assert "## Handoff Type\napproved_mutation_execution" in sections["prompt"]
    assert "decision: MUTATION_COMPLETE" in sections["prompt"]


def test_operator_decision_evals_block_execution_without_decision(tmp_path) -> None:
    from core.work_orders.evals import create_operator_decision_evals

    artifacts, _ = create_operator_decision_evals(
        work_order=_work_order(tmp_path / "target"),
        decision_required=True,
        execution_handoff_requested=True,
        decision_request=_request(),
        decision_request_path=tmp_path / "request.json",
        operator_decision=None,
        operator_decision_path=tmp_path / "operator_decision.json",
        storage_root=tmp_path / "store",
    )
    by_type = {artifact["eval_type"]: artifact for artifact in artifacts}

    assert by_type["operator_decision_request_completeness"]["pass_fail"] == "pass"
    assert by_type["operator_decision_validity"]["pass_fail"] == "incomplete"
    assert by_type["operator_decision_required_before_execution"]["pass_fail"] == "fail"


def test_operator_decision_evals_pass_after_valid_decision(tmp_path) -> None:
    from core.work_orders.evals import create_operator_decision_evals

    artifacts, _ = create_operator_decision_evals(
        work_order=_work_order(tmp_path / "target"),
        decision_required=True,
        execution_handoff_requested=True,
        decision_request=_request(),
        decision_request_path=tmp_path / "request.json",
        operator_decision=_decision(),
        operator_decision_path=tmp_path / "operator_decision.json",
        storage_root=tmp_path / "store",
    )

    assert all(artifact["pass_fail"] == "pass" for artifact in artifacts)
