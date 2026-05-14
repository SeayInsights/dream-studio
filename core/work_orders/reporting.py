"""File-backed Work Order report generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evals import (
    create_handoff_prompt_evals,
    create_next_work_order_recommendation_eval,
    create_operator_decision_evals,
    create_result_report_completeness_eval,
)
from .decisions import (
    create_decision_request,
    load_decision_request,
    load_operator_decision,
)
from .handoff import DECISION_TAXONOMIES
from .handoff import build_handoff_sections
from .models import WorkOrderError
from .results import load_result_metadata, load_result_text
from .storage import load_work_order, work_order_dir, write_existing_work_order
from .validation import validate_work_order

REPORT_MD = "report.md"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ["unavailable"]


def _format_list(items: list[Any]) -> str:
    visible = [item for item in items if str(item).strip()]
    if not visible:
        return "- unavailable"
    return "\n".join(f"- {item}" for item in visible)


def _operator_action_required(decision: dict[str, Any]) -> bool:
    if bool(decision.get("human_approval_required")):
        return True
    required_action = str(decision.get("required_operator_action") or "").strip().lower()
    return required_action not in {"", "none", "unavailable", "not_applicable"}


def _load_eval_artifacts(
    work_order_id: str, *, storage_root: Path | str | None = None
) -> list[dict[str, Any]]:
    eval_dir = work_order_dir(work_order_id, storage_root=storage_root) / "evals"
    artifacts: list[dict[str, Any]] = []
    if not eval_dir.is_dir():
        return artifacts
    for path in sorted(eval_dir.glob("*.json")):
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
            artifact["_path"] = str(path)
            artifacts.append(artifact)
        except json.JSONDecodeError:
            artifacts.append(
                {
                    "eval_type": path.stem,
                    "pass_fail": "incomplete",
                    "observed_behavior": "eval artifact could not be parsed.",
                    "_path": str(path),
                }
            )
    return artifacts


def _rendered_packets(work_order_id: str, *, storage_root: Path | str | None = None) -> list[str]:
    rendered_dir = work_order_dir(work_order_id, storage_root=storage_root) / "rendered"
    if not rendered_dir.is_dir():
        return []
    return [str(path) for path in sorted(rendered_dir.glob("*.md"))]


def _eval_summary(artifacts: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
    proven: list[str] = []
    failed: list[str] = []
    incomplete: list[str] = []
    for artifact in artifacts:
        line = (
            f"{artifact.get('eval_type', 'unknown')}: "
            f"{artifact.get('pass_fail', 'incomplete')} - "
            f"{artifact.get('observed_behavior', 'unavailable')}"
        )
        status = artifact.get("pass_fail")
        if status == "pass":
            proven.append(line)
        elif status == "fail":
            failed.append(line)
        else:
            incomplete.append(line)
    return proven, failed, incomplete


def _approved_mutation_summary(artifacts: list[dict[str, Any]]) -> list[str]:
    matches = [
        artifact
        for artifact in artifacts
        if artifact.get("eval_type") == "approved_mutation_compliance"
    ]
    if not matches:
        return [
            "status: unavailable",
            "approved mutation compliance is not claimed without an approved_mutation_compliance eval.",
        ]
    artifact = matches[-1]
    status = artifact.get("pass_fail", "incomplete")
    return [
        f"status: {status}",
        f"observed: {artifact.get('observed_behavior', 'unavailable')}",
        (
            "claim: approved mutation compliance proven"
            if status == "pass"
            else "claim: approved mutation compliance not proven"
        ),
        f"evidence: {artifact.get('_path', 'unavailable')}",
    ]


def _load_decision_state(
    work_order_id: str,
    *,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any] | None, Path, dict[str, Any] | None, Path]:
    request, request_path = load_decision_request(work_order_id, storage_root=storage_root)
    decision, decision_path = load_operator_decision(work_order_id, storage_root=storage_root)
    if isinstance(request, dict):
        request = dict(request)
        request["_path"] = str(request_path)
    if isinstance(decision, dict):
        decision = dict(decision)
        decision["_path"] = str(decision_path)
    return request, request_path, decision, decision_path


def _execution_handoff_requested(handoff_sections: dict[str, Any]) -> bool:
    if handoff_sections.get("decision", {}).get("handoff_required") is False:
        return False
    handoff_type = str(handoff_sections.get("decision", {}).get("handoff_type", ""))
    return handoff_type in {
        "approved_mutation_execution",
        "commit_execution",
        "recovery_execution",
    }


def _separate_work_order_boundary(decision: dict[str, Any]) -> bool:
    reason = str(decision.get("handoff_reason") or "")
    return reason in {
        "commit_required",
        "push_or_deploy_required",
        "database_mutation_required",
        "migration_required",
        "ddl_or_dml_required",
        "package_or_dependency_operation_required",
        "runtime_or_browser_validation_required",
        "secret_or_sensitive_access_required",
        "artifact_compaction_deletion_archive_required",
        "external_project_resume_required",
        "operator_approval_required",
        "operator_decision_required",
    }


def _should_include_next_work_order_recommendation(handoff_sections: dict[str, Any]) -> bool:
    decision = handoff_sections.get("decision", {})
    return bool(decision.get("handoff_required")) or _separate_work_order_boundary(decision)


def _should_create_decision_request(
    handoff_sections: dict[str, Any],
    decision_request: dict[str, Any] | None,
) -> bool:
    if decision_request is not None:
        return False
    readiness = str(handoff_sections.get("readiness", {}).get("readiness", "HOLD"))
    return readiness == "HOLD"


def _create_report_decision_request(
    *,
    work_order_id: str,
    handoff_sections: dict[str, Any],
    storage_root: Path | str | None = None,
) -> dict[str, Any]:
    decision = handoff_sections.get("decision", {})
    phase_type = str(decision.get("phase_type") or "normal_next_work_order")
    allowed = DECISION_TAXONOMIES.get(phase_type, ("HOLD", "FAIL"))
    recommended = str(decision.get("final_decision") or "HOLD")
    if recommended not in allowed:
        recommended = "HOLD" if "HOLD" in allowed else allowed[0]
    return create_decision_request(
        work_order_id,
        phase_type=phase_type,
        question="Choose the next safe Work Order action before generating an execution handoff.",
        recommended_decision=recommended,
        risk_summary="Report readiness is HOLD or continuation requires an explicit operator decision.",
        required_evidence=[
            "Work Order report",
            "Sequential Execution Readiness",
            "Next Action Decision",
            "operator rationale for selected decision",
        ],
        storage_root=storage_root,
    )


def _report_text(
    *,
    work_order: dict[str, Any],
    packet_paths: list[str],
    result_metadata: dict[str, Any] | None,
    result_path: Path,
    eval_artifacts: list[dict[str, Any]],
    handoff_sections: dict[str, Any] | None = None,
) -> str:
    scope = work_order.get("scope", {})
    structured = result_metadata.get("structured_findings", {}) if result_metadata else {}
    warnings = (
        result_metadata.get("warnings", ["unavailable"]) if result_metadata else ["unavailable"]
    )
    risks = result_metadata.get("risks", ["unavailable"]) if result_metadata else ["unavailable"]
    next_work_order = (
        result_metadata.get("next_work_order_recommendation", "unavailable")
        if result_metadata
        else "unavailable"
    )
    proven, failed, incomplete = _eval_summary(eval_artifacts)
    approved_mutation = _approved_mutation_summary(eval_artifacts)
    result_ref = (
        result_metadata.get("raw_output_ref", "unavailable") if result_metadata else "unavailable"
    )
    readiness = (handoff_sections or {}).get("readiness", {})
    decision = (handoff_sections or {}).get("decision", {})
    decision_request = (handoff_sections or {}).get("decision_request")
    operator_decision = (handoff_sections or {}).get("operator_decision")
    ready_prompt = (handoff_sections or {}).get("prompt", "unavailable")
    include_next_work_order = _should_include_next_work_order_recommendation(handoff_sections or {})
    if not include_next_work_order:
        next_work_order = "not applicable - route decision continues internally or starts a stage-gate-valid milestone without a handoff"

    lines = [
        "# Work Order Report",
        "",
        "## Objective",
        str(work_order.get("objective", "unavailable")),
        "",
        "## Project Name",
        str(work_order.get("project_name", "unavailable")),
        "",
        "## Target Path",
        str(work_order.get("target_path", "unavailable")),
        "",
        "## Approval Mode",
        str(work_order.get("approval_mode", "unavailable")),
        "",
        "## Risk Level",
        str(work_order.get("risk_level", "unavailable")),
        "",
        "## Scope Include",
        _format_list(_as_list(scope.get("include"))),
        "",
        "## Scope Exclude",
        _format_list(_as_list(scope.get("exclude"))),
        "",
        "## Rendered Packet Paths",
        _format_list(packet_paths or ["unavailable"]),
        "",
        "## Raw Result Reference",
        result_ref,
        "",
        "## Structured Result Metadata",
        f"- summary: {(result_metadata or {}).get('summary', 'unavailable')}",
        f"- status: {(result_metadata or {}).get('status', 'unavailable')}",
        "",
        "## Files Inspected",
        _format_list(_as_list(structured.get("files_inspected"))),
        "",
        "## Files Changed",
        _format_list(_as_list(structured.get("files_changed"))),
        "",
        "## Commands And Tests",
        _format_list(_as_list(structured.get("commands_or_tests"))),
        "",
        "## Risks And Warnings",
        "**Risks**",
        _format_list(_as_list(risks)),
        "",
        "**Warnings**",
        _format_list(_as_list(warnings)),
        "",
        "## Eval Artifact Summary",
        _format_list(
            [
                f"{artifact.get('eval_type', 'unknown')} [{artifact.get('pass_fail', 'incomplete')}] {artifact.get('_path', 'unavailable')}"
                for artifact in eval_artifacts
            ]
            or ["unavailable"]
        ),
        "",
        "## Approved Mutation Compliance",
        _format_list(approved_mutation),
        "",
        "## Proven",
        _format_list(proven),
        "",
        "## Failed",
        _format_list(failed),
        "",
        "## Incomplete / Unavailable",
        _format_list(incomplete or (["result missing"] if result_metadata is None else [])),
        "",
        "## Next Recommended Work Order",
        str(next_work_order or "unavailable"),
        "",
        "## Route Decision",
        f"- route_decision: {decision.get('route_decision', decision.get('recommended_action', 'unavailable'))}",
        f"- current_stage_gate: {decision.get('current_stage_gate', 'unavailable')}",
        f"- current_milestone: {decision.get('current_milestone', 'unavailable')}",
        f"- completed_internal_steps: {decision.get('completed_internal_steps', 'unavailable')}",
        f"- pending_internal_steps: {decision.get('pending_internal_steps', 'unavailable')}",
        f"- stop_gate_active: {str(bool(decision.get('stop_gate'))).lower()}",
        f"- handoff_required: {str(bool(decision.get('handoff_required'))).lower()}",
        f"- operator_action_required: {str(_operator_action_required(decision)).lower()}",
        f"- next_internal_action: {decision.get('next_internal_action', 'unavailable')}",
        f"- next_stage_gate_valid_milestone: {decision.get('next_work_order_id', 'unavailable') if decision.get('recommended_action') == 'start_next_milestone' else 'unavailable'}",
        f"- recommended_next_work_order: {str(next_work_order or 'none') if include_next_work_order else 'none'}",
        "",
        "## Sequential Execution Readiness",
        f"- readiness: {readiness.get('readiness', 'HOLD')}",
        f"- can_continue: {str(readiness.get('can_continue', False)).lower()}",
        f"- reason: {readiness.get('reason', 'unavailable')}",
        f"- required_human_decision: {readiness.get('required_human_decision', 'unavailable')}",
        "- required_artifacts:",
        _format_list(_as_list(readiness.get("required_artifacts"))),
        "- blockers:",
        _format_list(_as_list(readiness.get("blockers"))),
        f"- safe_next_action: {readiness.get('safe_next_action', 'unavailable')}",
        "",
        "## Next Action Decision",
        f"- recommended_action: {decision.get('recommended_action', 'hold_for_review')}",
        f"- next_work_order_id: {decision.get('next_work_order_id', 'unavailable')}",
        f"- next_work_order_mode: {decision.get('next_work_order_mode', 'unavailable')}",
        f"- human_approval_required: {str(decision.get('human_approval_required', False)).lower()}",
        f"- phase_type: {decision.get('phase_type', 'unavailable')}",
        "- required_decision_taxonomy:",
        _format_list(_as_list(decision.get("required_decision_taxonomy"))),
        f"- final_decision: {decision.get('final_decision', 'unavailable')}",
        f"- decision_rationale: {decision.get('decision_rationale', 'unavailable')}",
        "- constraints:",
        _format_list(_as_list(decision.get("constraints"))),
        "",
        "## Operator Decision Gate",
        f"- decision_request_path: {(decision_request or {}).get('_path', 'unavailable') if decision_request else 'unavailable'}",
        f"- decision_request_status: {(decision_request or {}).get('status', 'unavailable') if decision_request else 'unavailable'}",
        f"- recommended_decision: {(decision_request or {}).get('recommended_decision', 'unavailable') if decision_request else 'unavailable'}",
        f"- operator_decision_path: {(operator_decision or {}).get('_path', 'unavailable') if operator_decision else 'unavailable'}",
        f"- operator_decision: {(operator_decision or {}).get('decision', 'unavailable') if operator_decision else 'unavailable'}",
        "",
        "## Ready-To-Copy Next Prompt",
        "```text",
        str(ready_prompt or "unavailable").rstrip(),
        "```",
        "",
        "## Remaining Gaps",
        _format_list(
            [
                "result evidence unavailable" if result_metadata is None else "",
                "target mutation eval requires explicit before/after snapshots",
                "do not claim compliance unless corresponding eval artifact passed",
            ]
        ),
        "",
        "Report status: complete" if result_metadata else "Report status: incomplete / unavailable",
    ]
    return "\n".join(lines) + "\n"


def report_path(
    work_order_id: str,
    *,
    storage_root: Path | str | None = None,
) -> Path:
    return work_order_dir(work_order_id, storage_root=storage_root) / REPORT_MD


def generate_report(
    work_order_id: str,
    *,
    storage_root: Path | str | None = None,
) -> dict[str, Any]:
    """Generate a file-backed report without inspecting target_path."""
    work_order, _ = load_work_order(work_order_id, storage_root=storage_root)
    validation = validate_work_order(work_order)
    if not validation.ok:
        raise WorkOrderError(validation.format())

    result_metadata, metadata_path = load_result_metadata(work_order_id, storage_root=storage_root)
    _, raw_result_path = load_result_text(work_order_id, storage_root=storage_root)
    packet_paths = _rendered_packets(work_order_id, storage_root=storage_root)
    report = report_path(work_order_id, storage_root=storage_root)
    decision_request, decision_request_path, operator_decision, operator_decision_path = (
        _load_decision_state(work_order_id, storage_root=storage_root)
    )

    eval_artifacts = _load_eval_artifacts(work_order_id, storage_root=storage_root)
    handoff_sections = build_handoff_sections(
        work_order=validation.work_order,
        result_metadata=result_metadata,
        eval_artifacts=eval_artifacts,
        report_path=report,
        decision_request=decision_request,
        operator_decision=operator_decision,
    )
    if _should_create_decision_request(handoff_sections, decision_request):
        _create_report_decision_request(
            work_order_id=work_order_id,
            handoff_sections=handoff_sections,
            storage_root=storage_root,
        )
        decision_request, decision_request_path, operator_decision, operator_decision_path = (
            _load_decision_state(work_order_id, storage_root=storage_root)
        )
        handoff_sections = build_handoff_sections(
            work_order=validation.work_order,
            result_metadata=result_metadata,
            eval_artifacts=eval_artifacts,
            report_path=report,
            decision_request=decision_request,
            operator_decision=operator_decision,
        )
    first_text = _report_text(
        work_order=validation.work_order,
        packet_paths=packet_paths,
        result_metadata=result_metadata,
        result_path=raw_result_path,
        eval_artifacts=eval_artifacts,
        handoff_sections=handoff_sections,
    )
    report_tmp = report.parent / f".{REPORT_MD}.tmp"
    report_tmp.write_text(first_text, encoding="utf-8")
    report_tmp.replace(report)

    report_eval, report_eval_path = create_result_report_completeness_eval(
        work_order=validation.work_order,
        report_path=report,
        report_text=first_text,
        result_exists=result_metadata is not None,
        storage_root=storage_root,
    )
    include_next_work_order = _should_include_next_work_order_recommendation(handoff_sections)
    if include_next_work_order:
        recommendation = (
            result_metadata.get("next_work_order_recommendation")
            if result_metadata
            else "unavailable"
        )
        next_eval, next_eval_path = create_next_work_order_recommendation_eval(
            work_order=validation.work_order,
            recommendation=recommendation,
            evidence_ref=str(metadata_path if result_metadata else report),
            storage_root=storage_root,
        )
    else:
        next_eval = None
        next_eval_path = None
    if handoff_sections.get("decision", {}).get("handoff_required") is False:
        handoff_evals = []
        handoff_eval_paths = []
    else:
        handoff_evals, handoff_eval_paths = create_handoff_prompt_evals(
            work_order=validation.work_order,
            prompt_text=handoff_sections["prompt"],
            readiness=str(handoff_sections["readiness"].get("readiness", "HOLD")),
            can_continue=bool(handoff_sections["readiness"].get("can_continue", False)),
            report_path=report,
            storage_root=storage_root,
        )
    decision_required = decision_request is not None
    operator_evals, operator_eval_paths = create_operator_decision_evals(
        work_order=validation.work_order,
        decision_required=decision_required,
        execution_handoff_requested=_execution_handoff_requested(handoff_sections),
        decision_request=decision_request,
        decision_request_path=decision_request_path,
        operator_decision=operator_decision,
        operator_decision_path=operator_decision_path,
        storage_root=storage_root,
    )

    final_evals = _load_eval_artifacts(work_order_id, storage_root=storage_root)
    final_handoff_sections = build_handoff_sections(
        work_order=validation.work_order,
        result_metadata=result_metadata,
        eval_artifacts=final_evals,
        report_path=report,
        decision_request=decision_request,
        operator_decision=operator_decision,
    )
    final_text = _report_text(
        work_order=validation.work_order,
        packet_paths=packet_paths,
        result_metadata=result_metadata,
        result_path=raw_result_path,
        eval_artifacts=final_evals,
        handoff_sections=final_handoff_sections,
    )
    report_tmp.write_text(final_text, encoding="utf-8")
    report_tmp.replace(report)

    if result_metadata is not None:
        updated = dict(validation.work_order)
        updated["status"] = "reported"
        write_existing_work_order(updated, storage_root=storage_root)

    return {
        "work_order_id": work_order_id,
        "report_path": str(report),
        "result_present": result_metadata is not None,
        "status": "reported" if result_metadata else validation.work_order.get("status"),
        "eval_paths": [
            str(report_eval_path),
            *([str(next_eval_path)] if next_eval_path else []),
            *[str(path) for path in handoff_eval_paths],
            *[str(path) for path in operator_eval_paths],
        ],
        "evals": [
            report_eval,
            *([next_eval] if next_eval else []),
            *handoff_evals,
            *operator_evals,
        ],
    }
