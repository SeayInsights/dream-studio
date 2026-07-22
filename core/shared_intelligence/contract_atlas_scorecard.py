"""Contract Atlas GitHub CI/CD profile and maturity scorecard.

WO-GF-SHARED-INTEL-SPLIT: extracted from contract_atlas.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.release.github_pr_cicd_gate import (
    build_dream_studio_cicd_profile,
    discover_workflow_files,
    validate_cicd_profile,
)


def _github_cicd_profile(repo_root: Path) -> dict[str, Any]:
    profile = build_dream_studio_cicd_profile(str(repo_root))
    discovered = discover_workflow_files(repo_root)
    validation_errors = validate_cicd_profile(profile, discovered_workflows=discovered)
    return {
        "model_name": "dream_studio_github_cicd_profile",
        "derived_view": True,
        "primary_authority": False,
        "github_actions_role": profile.github_actions_role,
        "heavy_validation_layer": profile.heavy_validation_layer,
        "github_actions_minutes_policy": profile.github_actions_minutes_policy,
        "github_actions_unavailable_policy": profile.github_actions_unavailable_policy,
        "workflow_files": list(profile.workflow_files),
        "discovered_workflow_files": list(discovered),
        "required_checks": list(profile.required_checks),
        "optional_checks": list(profile.optional_checks),
        "manual_workflows": list(profile.manual_workflows),
        "release_workflows": list(profile.release_workflows),
        "local_preflight_commands": list(profile.local_preflight_commands),
        "merge_policy": profile.merge_policy,
        "deployment_policy": profile.deployment_policy,
        "validation_errors": validation_errors,
        "status": "pass" if not validation_errors else "attention_required",
        "github_api_calls_performed": False,
        "workflow_mutation_authorized": False,
    }


def _maturity_scorecard(
    *,
    staleness_report: Mapping[str, Any],
    module_errors: list[str],
    docker_errors: list[str],
    maturity_errors: list[str],
    profile_errors: list[str],
    security_lifecycle_gate: Mapping[str, Any],
    production_readiness_gate: Mapping[str, Any],
    usage_accounting: Mapping[str, Any],
    task_attribution: Mapping[str, Any],
    task_attribution_errors: list[str],
    prd_authority: Mapping[str, Any],
    prd_authority_errors: list[str],
    analytics_only_status: Mapping[str, Any],
    github_cicd_profile: Mapping[str, Any],
    expert_workflows: Mapping[str, Any],
    expert_workflow_errors: list[str],
    capability_center: Mapping[str, Any],
    capability_center_errors: list[str],
    scoped_agents: Mapping[str, Any],
    scoped_agent_errors: list[str],
    github_repo_intake: Mapping[str, Any],
    github_repo_intake_errors: list[str],
    platform_hardening: Mapping[str, Any],
    platform_hardening_errors: list[str],
) -> list[dict[str, Any]]:
    adapter_status = (
        "validated_command_level_alignment"
        if not staleness_report.get("repair_work_order_candidates")
        else "repair_candidates_present"
    )
    return [
        {
            "area": "adapter_surfaces",
            "status": adapter_status,
            "live_execution_proven": False,
            "reason": "Staleness and hook command compatibility can be checked safely; live Claude/Codex execution is not proven by this read model.",
        },
        {
            "area": "dashboard_modules",
            "status": "validated" if not module_errors else "contract_errors_present",
            "error_count": len(module_errors),
        },
        {
            "area": "runtime_profiles",
            "status": "documented_optional" if not docker_errors else "contract_errors_present",
            "error_count": len(docker_errors),
        },
        {
            "area": "installed_module_profiles",
            "status": "validated" if not profile_errors else "contract_errors_present",
            "error_count": len(profile_errors),
        },
        {
            "area": "module_boundary_contracts",
            "status": "validated" if not module_errors else "contract_errors_present",
            "error_count": len(module_errors),
        },
        {
            "area": "dependency_graph",
            "status": "confirmed_edges_only",
            "reason": "Edges are generated from repo constants, route declarations, and adapter authority profiles.",
        },
        {
            "area": "public_export_boundary",
            "status": "sanitized_export_available",
            "reason": "Private atlas is default; public export removes local paths and local user-surface detail.",
        },
        {
            "area": "current_maturity_ledger",
            "status": "validated" if not maturity_errors else "contract_errors_present",
            "error_count": len(maturity_errors),
        },
        {
            "area": "security_lifecycle_gate",
            "status": security_lifecycle_gate.get("security_status"),
            "canonical_framework": security_lifecycle_gate.get("source_framework", {}).get(
                "canonical_framework"
            ),
            "source_control_count": security_lifecycle_gate.get("source_framework", {}).get(
                "source_control_count"
            ),
            "release_readiness_effect": security_lifecycle_gate.get("release_readiness_effect"),
        },
        {
            "area": "secure_production_readiness_gate",
            "status": production_readiness_gate.get("release_readiness", {}).get("status"),
            "workflow_id": production_readiness_gate.get("workflow_id"),
            "control_total": production_readiness_gate.get("control_summary", {}).get("total"),
            "readiness_score_status": production_readiness_gate.get(
                "project_readiness_score", {}
            ).get("status"),
        },
        {
            "area": "adapter_usage_accounting",
            "status": usage_accounting.get("schema_status", "available"),
            "profile_count": usage_accounting.get("profile_count"),
            "token_record_count": usage_accounting.get("token_record_count"),
            "operational_record_count": usage_accounting.get("operational_record_count"),
            "cost_policy": usage_accounting.get("policy", {}),
        },
        {
            "area": "task_attribution_outcome_tracking",
            "status": "validated" if not task_attribution_errors else "attention_required",
            "record_count": task_attribution.get("record_count", 0),
            "outcome_counts": task_attribution.get("summary", {}).get("outcome_counts", {}),
            "validation_counts": task_attribution.get("summary", {}).get("validation_counts", {}),
            "no_fake_cost_precision": task_attribution.get("policy", {}).get(
                "token_cost_precision_not_inferred"
            ),
            "error_count": len(task_attribution_errors),
        },
        {
            "area": "prd_authority_lifecycle",
            "status": "validated" if not prd_authority_errors else "attention_required",
            "prd_count": prd_authority.get("prd_count", 0),
            "lifecycle_counts": prd_authority.get("lifecycle_counts", {}),
            "pending_change_order_count": len(prd_authority.get("pending_change_orders", [])),
            "route_reconciliation_status": prd_authority.get("route_reconciliation_status", {}).get(
                "status"
            ),
            "sqlite_is_prd_authority": prd_authority.get("policy", {}).get(
                "sqlite_is_prd_authority"
            ),
            "change_orders_required": prd_authority.get("policy", {}).get(
                "change_orders_required_for_material_changes"
            ),
            "error_count": len(prd_authority_errors),
        },
        {
            "area": "analytics_only_ingestion",
            "status": "available",
            "profile_id": analytics_only_status.get("profile_id"),
            "hooks_required": analytics_only_status.get("hooks_required"),
            "agents_required": analytics_only_status.get("agents_required"),
            "docker_required": analytics_only_status.get("docker_required"),
            "write_authorization": analytics_only_status.get("write_authorization"),
        },
        {
            "area": "github_cicd_profile",
            "status": github_cicd_profile.get("status"),
            "github_actions_role": github_cicd_profile.get("github_actions_role"),
            "heavy_validation_layer": github_cicd_profile.get("heavy_validation_layer"),
            "required_checks": github_cicd_profile.get("required_checks"),
            "manual_workflows": github_cicd_profile.get("manual_workflows"),
        },
        {
            "area": "expert_workflow_system",
            "status": "validated" if not expert_workflow_errors else "contract_errors_present",
            "workflow_count": expert_workflows.get("workflow_count"),
            "overlap_decision_counts": expert_workflows.get("overlap_decision_counts"),
            "no_duplicate_skill_policy": expert_workflows.get("no_duplicate_skill_policy"),
            "error_count": len(expert_workflow_errors),
        },
        {
            "area": "capability_center",
            "status": "validated" if not capability_center_errors else "contract_errors_present",
            "section_ids": sorted(capability_center.get("sections", {})),
            "error_count": len(capability_center_errors),
        },
        {
            "area": "scoped_agent_execution",
            "status": "validated" if not scoped_agent_errors else "contract_errors_present",
            "agent_count": scoped_agents.get("agent_count"),
            "agent_is_authority": scoped_agents.get("agent_is_authority"),
            "forbidden_context_count": len(scoped_agents.get("forbidden_context_by_default", [])),
            "error_count": len(scoped_agent_errors),
        },
        {
            "area": "github_repo_intake",
            "status": "validated" if not github_repo_intake_errors else "contract_errors_present",
            "workflow_id": github_repo_intake.get("workflow_id"),
            "evaluation_count": github_repo_intake.get("evaluation_count", 0),
            "copy_code_allowed_without_approval": False,
            "error_count": len(github_repo_intake_errors),
        },
        {
            "area": "platform_hardening_sequence",
            "status": "validated" if not platform_hardening_errors else "contract_errors_present",
            "milestone_ids": sorted(platform_hardening.get("milestones", {})),
            "source_status": platform_hardening.get("source_status"),
            "error_count": len(platform_hardening_errors),
        },
    ]
