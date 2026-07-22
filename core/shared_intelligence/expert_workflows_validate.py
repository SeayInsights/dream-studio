"""Expert workflow catalog validation.

WO-GF-SHARED-INTEL-SPLIT: extracted from expert_workflows.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .expert_workflows_catalog import expert_workflow_catalog
from .expert_workflows_constants import (
    APPLICATION_AUTOMATION_BOUNDARIES,
    DECISION_VALUES,
    DESIGN_SPECIALIZED_SKILLS,
    REQUIRED_WORKFLOW_IDS,
)


def validate_expert_workflow_catalog(catalog: Mapping[str, Any] | None = None) -> list[str]:
    """Validate catalog completeness, overlap decisions, and privacy boundaries."""

    payload = dict(catalog or expert_workflow_catalog())
    errors: list[str] = []
    if payload.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if payload.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    if payload.get("db_write_authorized") is not False:
        errors.append("db_write_authorized must be false")
    workflow_ids = {str(item.get("workflow_id")) for item in payload.get("workflows", [])}
    missing = sorted(REQUIRED_WORKFLOW_IDS - workflow_ids)
    if missing:
        errors.append(f"missing workflows: {missing}")
    for workflow in payload.get("workflows", []):
        workflow_id = str(workflow.get("workflow_id") or "")
        for key in (
            "purpose",
            "when_to_run",
            "when_not_to_run",
            "input_contract",
            "output_contract",
            "scoring_rubric",
            "evidence_requirements",
            "validation_requirements",
            "dashboard_project_details_visibility",
            "contract_atlas_impact",
            "remediation_work_order_behavior",
            "privacy_publication_boundary",
            "skill_overlap_supersession_status",
            "authority_write_targets",
        ):
            if not workflow.get(key):
                errors.append(f"workflow {workflow_id} missing {key}")
        for score in workflow.get("scoring_rubric", []):
            if score.get("evidence_required") is not True:
                errors.append(f"workflow {workflow_id} score lacks evidence requirement")
            if "unavailable" not in str(score.get("missing_evidence_behavior", "")):
                errors.append(f"workflow {workflow_id} score lacks unavailable state")
    for row in payload.get("overlap_matrix", []):
        decision = row.get("decision")
        owner = row.get("proposed_canonical_owner")
        if decision not in DECISION_VALUES:
            errors.append(f"invalid overlap decision: {decision}")
        if not owner:
            errors.append(f"overlap row {row.get('workflow_id')} missing owner")
        if (
            decision == "create_new"
            and row.get("existing_surfaces")
            and not row.get("separate_responsibility")
        ):
            errors.append(f"overlap row {row.get('workflow_id')} creates duplicate owner")
    design_skills = set(
        payload.get("specialized_skill_families", {}).get("frontend_design_excellence_workflow", [])
    )
    missing_design = sorted(set(DESIGN_SPECIALIZED_SKILLS) - design_skills)
    if missing_design:
        errors.append(f"missing design specialized skills: {missing_design}")
    missing_boundaries = sorted(
        set(APPLICATION_AUTOMATION_BOUNDARIES)
        - set(payload.get("application_automation_boundaries", []))
    )
    if missing_boundaries:
        errors.append(f"application automation boundaries missing: {missing_boundaries}")
    return errors
