"""Dashboard-consumable derived views for external project targets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.projects.external_validation import build_external_project_validation_pipeline
from core.projects.paused_targets import ROUTE_KEEP_PAUSED, ROUTE_RESUME_AFTER_OPERATOR_APPROVAL


def build_external_project_dashboard_view(targets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return a derived dashboard view for external project targets.

    The view consumes supplied registry/evidence metadata only.  It does not
    inspect target repositories and must not be treated as authority over resume
    approval, dirty state, validation results, or release readiness.
    """

    target_cards = [_target_card(target) for target in targets]
    return {
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "source_tables": [],
        "source_authority": "project_registry_and_work_order_evidence",
        "external_repo_inspected": False,
        "external_repo_mutated": False,
        "cards": target_cards,
        "summary": {
            "target_count": len(target_cards),
            "paused_count": sum(1 for card in target_cards if card["resume_state"] == "paused"),
            "resume_ready_count": sum(
                1 for card in target_cards if card["resume_state"] == "resume_ready"
            ),
            "dirty_or_unknown_count": sum(
                1 for card in target_cards if card["dirty_state"] in {"dirty", "unknown"}
            ),
            "approval_required_count": sum(
                1 for card in target_cards if card["approval_status"] == "approval_required"
            ),
        },
        "empty_state": len(target_cards) == 0,
    }


def _target_card(target: Mapping[str, Any]) -> dict[str, Any]:
    pipeline = build_external_project_validation_pipeline(target)
    policy = pipeline["target_policy"]
    route = str(policy["recommended_route"])
    resume_state = "resume_ready" if route == ROUTE_RESUME_AFTER_OPERATOR_APPROVAL else "paused"
    if route not in {ROUTE_RESUME_AFTER_OPERATOR_APPROVAL, ROUTE_KEEP_PAUSED}:
        resume_state = "review_required"

    risks = _risks_for_target(pipeline)
    return {
        "target_id": policy["target_id"],
        "status": policy["status"],
        "source_boundary": policy["source_boundary"],
        "validation_profile": policy["validation_profile"],
        "dirty_state": pipeline["dirty_state"],
        "resume_state": resume_state,
        "approval_status": (
            "approved_for_planning" if policy["approval_refs"] else "approval_required"
        ),
        "validation_status": "not_run",
        "work_order_sequence": pipeline["work_order_sequence"],
        "evidence_refs": pipeline["source_evidence_refs"],
        "approval_refs": pipeline["operator_approval_refs"],
        "risks": risks,
        "next_action": _next_action_for_card(resume_state, risks),
        "commit_policy": pipeline["commit_policy"],
        "mutation_allowed": False,
    }


def _risks_for_target(pipeline: Mapping[str, Any]) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []
    if pipeline["dirty_state"] in {"dirty", "unknown"}:
        risks.append(
            {
                "id": "dirty_state_not_clean",
                "severity": "medium",
                "summary": "Target dirty state must be captured or reviewed before validation can mature.",
            }
        )
    if pipeline["requires_operator_approval"]:
        risks.append(
            {
                "id": "operator_approval_required",
                "severity": "medium",
                "summary": "External validation or resume requires explicit operator approval.",
            }
        )
    if not pipeline["source_evidence_refs"]:
        risks.append(
            {
                "id": "evidence_refs_missing",
                "severity": "low",
                "summary": "Dashboard card has no linked evidence refs yet.",
            }
        )
    return risks


def _next_action_for_card(resume_state: str, risks: Sequence[Mapping[str, Any]]) -> str:
    risk_ids = {str(risk.get("id", "")) for risk in risks}
    if resume_state == "resume_ready" and "dirty_state_not_clean" not in risk_ids:
        return "prepare_read_only_validation_work_order"
    if "operator_approval_required" in risk_ids:
        return "await_operator_approval"
    return "record_missing_evidence_or_keep_paused"
