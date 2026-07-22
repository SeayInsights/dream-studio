"""Expert workflow catalog builder and per-workflow definition helpers.

WO-GF-SHARED-INTEL-SPLIT: extracted from expert_workflows.py.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, UTC
from typing import Any

from .expert_workflows_bases import _WORKFLOW_BASES
from .expert_workflows_constants import (
    APPLICATION_AUTOMATION_BOUNDARIES,
    AUTHORITY_WRITE_TARGETS,
    DESIGN_SPECIALIZED_SKILLS,
    EXPERT_WORKFLOW_CATALOG_SCHEMA,
    REQUIRED_WORKFLOW_IDS,
)


def expert_workflow_catalog(*, project_id: str | None = None) -> dict[str, Any]:
    """Return the repo-backed expert workflow catalog."""

    workflows = [_workflow_definition(workflow_id) for workflow_id in sorted(REQUIRED_WORKFLOW_IDS)]
    overlap = _overlap_matrix(workflows)
    decision_counts = Counter(row["decision"] for row in overlap)
    return {
        "schema": EXPERT_WORKFLOW_CATALOG_SCHEMA,
        "model_name": "dream_studio_expert_workflow_catalog",
        "generated_at": datetime.now(UTC).isoformat(),
        "project_id": project_id,
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "db_write_authorized": False,
        "execution_authorized": False,
        "policy_mutation_authorized": False,
        "workflow_count": len(workflows),
        "required_workflow_count": len(REQUIRED_WORKFLOW_IDS),
        "workflows": workflows,
        "overlap_matrix": overlap,
        "overlap_decision_counts": dict(sorted(decision_counts.items())),
        "specialized_skill_families": {
            "frontend_design_excellence_workflow": list(DESIGN_SPECIALIZED_SKILLS),
        },
        "application_automation_boundaries": list(APPLICATION_AUTOMATION_BOUNDARIES),
        "authority_write_targets": list(AUTHORITY_WRITE_TARGETS),
        "sqlite_authority_mode": (
            "workflow outputs should persist through current authority tables; "
            "this catalog does not create a competing skill database"
        ),
        "no_duplicate_skill_policy": (
            "strengthen or map existing skills when responsibilities overlap; create only "
            "when no owner exists or the responsibility is clearly separate"
        ),
        "empty_state": "No expert workflows are registered.",
    }


def workflow_by_id(workflow_id: str) -> dict[str, Any]:
    """Return a single workflow definition by id."""

    catalog = expert_workflow_catalog()
    for workflow in catalog["workflows"]:
        if workflow["workflow_id"] == workflow_id:
            return workflow
    raise ValueError(f"unknown expert workflow: {workflow_id}")


def _workflow_definition(workflow_id: str) -> dict[str, Any]:
    base = _WORKFLOW_BASES[workflow_id]
    return {
        "workflow_id": workflow_id,
        "workflow_owner": base["workflow_owner"],
        "skill_owner": base["skill_owner"],
        "purpose": base["purpose"],
        "when_to_run": base["when_to_run"],
        "when_not_to_run": base["when_not_to_run"],
        "input_contract": base["input_contract"],
        "output_contract": base["output_contract"],
        "scoring_rubric": _score_rubric(base["scores"]),
        "evidence_requirements": base["evidence_requirements"],
        "validation_requirements": base["validation_requirements"],
        "dashboard_project_details_visibility": base["dashboard_visibility"],
        "contract_atlas_impact": base["contract_atlas_impact"],
        "remediation_work_order_behavior": (
            "Create scoped remediation Work Orders only for evidence-backed findings; "
            "manual-review or missing-evidence items become dashboard attention."
        ),
        "privacy_publication_boundary": base["privacy_boundary"],
        "authority_write_targets": list(AUTHORITY_WRITE_TARGETS),
        "structured_output_contract": {
            "status_values": [
                "pass",
                "warn",
                "fail",
                "not_applicable",
                "manual_review_required",
                "unavailable",
            ],
            "required_fields": [
                "project_id",
                "workflow_id",
                "assessment_id",
                "status",
                "evidence_refs",
                "source_refs",
                "findings",
                "remediation_work_orders",
                "missing_evidence",
            ],
        },
        "skill_overlap_supersession_status": base["overlap_status"],
        "existing_owners": base["existing_owners"],
        "specialized_skills": base.get("specialized_skills", []),
    }


def _score_rubric(score_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {
            "score_id": score_id,
            "scale": "0_to_5_or_unavailable",
            "evidence_required": True,
            "confidence_required": True,
            "missing_evidence_behavior": "mark_unavailable_or_partial_with_reason",
            "fake_precision_allowed": False,
        }
        for score_id in score_ids
    ]


def _overlap_matrix(workflows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for workflow in workflows:
        status = workflow["skill_overlap_supersession_status"]
        rows.append(
            {
                "workflow_id": workflow["workflow_id"],
                "existing_skill_or_workflow": ", ".join(workflow["existing_owners"]),
                "proposed_canonical_owner": workflow["workflow_owner"],
                "overlap_reason": status["overlap_reason"],
                "decision": status["decision"],
                "evidence": status["evidence"],
                "validation_requirement": status["validation_requirement"],
                "rollback_supersession_plan": status["rollback_supersession_plan"],
                "dashboard_project_health_impact": status["dashboard_project_health_impact"],
                "contract_atlas_impact": workflow["contract_atlas_impact"],
                "existing_surfaces": workflow["existing_owners"],
                "separate_responsibility": status.get("separate_responsibility", False),
            }
        )
    return rows
