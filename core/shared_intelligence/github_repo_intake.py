"""GitHub repository intake and integration evaluation workflow."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

GITHUB_REPO_INTAKE_SCHEMA = "dream_studio.github_repo_intake.v1"

GITHUB_REPO_TABLES: tuple[str, ...] = (
    "github_repo_evaluations",
    "github_repo_adoption_decisions",
)

OUTCOME_CLASSES: tuple[str, ...] = (
    "reject",
    "reference_only",
    "learn_pattern_only",
    "create_design_note",
    "create_skill_candidate",
    "create_workflow_candidate",
    "create_adapter_candidate",
    "create_dependency_candidate",
    "fork_or_vendor_candidate",
    "manual_review_required",
    "legal_review_required",
    "security_review_required",
    "integration_work_order_ready",
)

WORKFLOW_STEPS: tuple[dict[str, Any], ...] = (
    {
        "step_id": "repo_metadata_review",
        "purpose": "Capture URL, owner/name, commit SHA, activity, README, and public docs.",
    },
    {
        "step_id": "license_and_attribution_review",
        "purpose": "Classify license, attribution obligations, copy/fork/vendor approval needs.",
    },
    {
        "step_id": "security_supply_chain_review",
        "purpose": "Review security policy, dependency manifests, package health, and risk signals.",
    },
    {
        "step_id": "dependency_health_review",
        "purpose": "Classify dependency, maintenance, and update risk before any adoption.",
    },
    {
        "step_id": "architecture_pattern_review",
        "purpose": "Learn patterns and integration ideas without copying code by default.",
    },
    {
        "step_id": "duplication_overlap_review",
        "purpose": "Check existing Dream Studio skills, workflows, modules, and adapters first.",
    },
    {
        "step_id": "extraction_strategy_review",
        "purpose": "Prefer pattern learning and original implementation; require approvals for copying.",
    },
    {
        "step_id": "implementation_plan_generation",
        "purpose": "Create an integration Work Order only after evidence-backed decision classes pass.",
    },
)


def github_repo_intake_workflow() -> dict[str, Any]:
    """Return the repo intake workflow definition without inspecting a remote repo."""

    return {
        "schema": GITHUB_REPO_INTAKE_SCHEMA,
        "model_name": "dream_studio_github_repo_intake_workflow",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "db_write_authorized": False,
        "execution_authorized": False,
        "workflow_id": "github_repo_intake_and_integration_evaluation_workflow",
        "do_not_copy_code_without_approval": True,
        "do_not_add_dependencies_without_review": True,
        "preferred_order": [
            "learn_pattern_or_concept",
            "write_original_implementation",
            "use_dependency_if_review_passes",
            "fork_or_vendor_only_with_explicit_approval",
            "copy_code_only_with_license_attribution_legal_approval",
        ],
        "steps": list(WORKFLOW_STEPS),
        "outcome_classes": list(OUTCOME_CLASSES),
        "source_tables": list(GITHUB_REPO_TABLES),
        "empty_state": "No GitHub repositories have been evaluated.",
    }


def classify_github_repo_evaluation(metadata: dict[str, Any]) -> dict[str, Any]:
    """Classify a proposed repo evaluation from supplied metadata only."""

    license_value = str(metadata.get("license") or "").strip().lower()
    commit_sha = str(metadata.get("commit_sha_reviewed") or "").strip()
    security_files = metadata.get("security_files") or []
    overlaps = metadata.get("overlap_components") or []
    copy_requested = bool(metadata.get("code_copy_requested"))
    dependency_requested = bool(metadata.get("dependency_requested"))

    legal_review_required = (
        not license_value or license_value in {"unknown", "none"} or copy_requested
    )
    security_review_required = not security_files or dependency_requested
    manual_review_required = not commit_sha or bool(overlaps)

    if legal_review_required:
        decision = "legal_review_required"
    elif security_review_required:
        decision = "security_review_required"
    elif manual_review_required:
        decision = "manual_review_required"
    elif dependency_requested:
        decision = "create_dependency_candidate"
    elif metadata.get("candidate_components"):
        decision = "integration_work_order_ready"
    else:
        decision = "learn_pattern_only"

    return {
        "integration_decision": decision,
        "manual_review_required": manual_review_required,
        "legal_review_required": legal_review_required,
        "security_review_required": security_review_required,
        "recommended_action": _recommended_action(decision),
        "risk_score": _risk_score(
            legal_review_required, security_review_required, manual_review_required
        ),
        "fit_score": _fit_score(metadata),
        "outcome_classes": list(OUTCOME_CLASSES),
        "copy_code_allowed": False,
        "dependency_add_allowed": False,
        "fork_or_vendor_allowed": False,
    }


def validate_github_repo_intake_workflow(workflow: dict[str, Any] | None = None) -> list[str]:
    payload = workflow or github_repo_intake_workflow()
    errors: list[str] = []
    if payload.get("do_not_copy_code_without_approval") is not True:
        errors.append("workflow must block unapproved code copy")
    if set(payload.get("outcome_classes", [])) != set(OUTCOME_CLASSES):
        errors.append("workflow outcome classes are incomplete")
    step_ids = {step.get("step_id") for step in payload.get("steps", [])}
    for required in (
        "repo_metadata_review",
        "license_and_attribution_review",
        "security_supply_chain_review",
        "duplication_overlap_review",
        "implementation_plan_generation",
    ):
        if required not in step_ids:
            errors.append(f"missing workflow step: {required}")
    return errors


def _recommended_action(decision: str) -> str:
    if decision == "legal_review_required":
        return "Hold adoption until license, attribution, and legal approval are recorded."
    if decision == "security_review_required":
        return "Hold adoption until security and supply-chain review are recorded."
    if decision == "manual_review_required":
        return "Run overlap/manual review before creating an integration Work Order."
    if decision == "create_dependency_candidate":
        return "Create a dependency candidate only after maintenance, license, and security review pass."
    if decision == "integration_work_order_ready":
        return "Create a scoped integration Work Order that writes original Dream Studio implementation."
    return "Use as reference or pattern only; do not copy code."


def _risk_score(
    legal_review_required: bool, security_review_required: bool, manual_review_required: bool
) -> float:
    score = 0.2
    if legal_review_required:
        score += 0.35
    if security_review_required:
        score += 0.3
    if manual_review_required:
        score += 0.15
    return min(score, 1.0)


def _fit_score(metadata: dict[str, Any]) -> float:
    score = 0.2
    if metadata.get("candidate_components"):
        score += 0.3
    if metadata.get("architecture_notes"):
        score += 0.2
    if metadata.get("overlap_components"):
        score -= 0.2
    return max(0.0, min(score, 1.0))


def _json(value: Any, default: Any = None) -> str:
    return json.dumps(default if value is None else value, sort_keys=True)


def _decode(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
