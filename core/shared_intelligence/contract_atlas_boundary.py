"""Contract Atlas boundary-violation and active-adapter-execution reports.

WO-GF-SHARED-INTEL-SPLIT: extracted from contract_atlas.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _boundary_violation_report(
    *,
    staleness_report: Mapping[str, Any],
    module_errors: list[str],
    docker_errors: list[str],
    staleness_errors: list[str],
    maturity_errors: list[str],
    profile_errors: list[str],
    security_lifecycle_gate: Mapping[str, Any],
    production_readiness_gate: Mapping[str, Any],
    expert_workflow_errors: list[str],
    capability_center_errors: list[str],
    scoped_agent_errors: list[str],
    github_repo_intake_errors: list[str],
    task_attribution_errors: list[str],
    prd_authority_errors: list[str],
    platform_hardening_errors: list[str],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for error in module_errors:
        issues.append({"severity": "error", "area": "module_registry", "message": error})
    for error in docker_errors:
        issues.append({"severity": "error", "area": "docker_profiles", "message": error})
    for error in staleness_errors:
        issues.append({"severity": "error", "area": "adapter_staleness", "message": error})
    for error in maturity_errors:
        issues.append({"severity": "error", "area": "maturity_ledger", "message": error})
    for error in profile_errors:
        issues.append({"severity": "error", "area": "installed_module_profiles", "message": error})
    for error in expert_workflow_errors:
        issues.append({"severity": "error", "area": "expert_workflow_system", "message": error})
    for error in capability_center_errors:
        issues.append({"severity": "error", "area": "capability_center", "message": error})
    for error in scoped_agent_errors:
        issues.append({"severity": "error", "area": "scoped_agents", "message": error})
    for error in github_repo_intake_errors:
        issues.append({"severity": "error", "area": "github_repo_intake", "message": error})
    for error in task_attribution_errors:
        issues.append({"severity": "error", "area": "task_attribution", "message": error})
    for error in prd_authority_errors:
        issues.append({"severity": "error", "area": "prd_authority", "message": error})
    for error in platform_hardening_errors:
        issues.append({"severity": "error", "area": "platform_hardening", "message": error})
    security_status = security_lifecycle_gate.get("security_status")
    if security_status not in {"ready", "needs_manual_review"}:
        issues.append(
            {
                "severity": "error",
                "area": "security_lifecycle_gate",
                "message": f"security lifecycle status requires release attention: {security_status}",
            }
        )
    readiness_status = production_readiness_gate.get("project_readiness_score", {}).get("status")
    if readiness_status == "unknown":
        issues.append(
            {
                "severity": "error",
                "area": "secure_production_readiness_gate",
                "message": "production readiness status is unknown",
            }
        )
    for candidate in staleness_report.get("repair_work_order_candidates", []):
        issues.append(
            {
                "severity": "warning",
                "area": "adapter_projection",
                "message": candidate["reason"],
                "adapter_id": candidate["adapter_id"],
                "requires_operator_approval": candidate["requires_operator_approval"],
            }
        )
    return {
        "status": "pass" if not issues else "attention_required",
        "issue_count": len(issues),
        "issues": issues,
        "cleanup_execution_authorized": False,
        "config_write_authorized": False,
    }


def _active_adapter_execution_validation(staleness_report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "command_level_hook_smoke_available": True,
        "active_config_alignment_checked": True,
        "staleness_status": {
            "adapter_count": staleness_report.get("adapter_count"),
            "aligned_count": staleness_report.get("aligned_count"),
            "repair_candidate_count": len(staleness_report.get("repair_work_order_candidates", [])),
        },
        "live_claude_execution_proven": False,
        "live_codex_execution_proven": False,
        "claim_boundary": (
            "The atlas can report command-level hook compatibility and active config "
            "alignment. It does not prove a real Claude or Codex process consumed the config."
        ),
    }
