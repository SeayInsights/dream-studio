"""Module runtime-profile fit derivation.

WO-GF-API-ROUTES: split out of project_helpers.py.
"""

from __future__ import annotations

from typing import Any

# ── Module runtime fit ───────────────────────────────────────────────────────


def _module_runtime_fit(
    project: dict[str, Any],
    stack_evidence: dict[str, Any],
    dependency_graph: dict[str, Any],
) -> dict[str, Any]:
    from core.module_contracts import module_contract_map
    from core.module_profiles import module_profile_map

    contracts = module_contract_map()
    profiles = module_profile_map()
    candidate_profiles = ["core"]
    reasons = ["core fits every installed Dream Studio project authority view"]
    if project.get("security_package_status", {}).get("open_findings", 0) or project.get(
        "security_lifecycle_status"
    ):
        candidate_profiles.append("security_only")
        reasons.append("security authority or lifecycle status is present")
    if stack_evidence.get("classification") == "confirmed" or dependency_graph.get("edge_count"):
        candidate_profiles.append("analytics_only")
        reasons.append("stack/dependency evidence can be consumed by analytics-only")
    if project.get("telemetry_status", {}).get("event_count") or project.get(
        "telemetry_status", {}
    ).get("validation_passed_count"):
        candidate_profiles.append("telemetry_only")
        reasons.append("telemetry or validation evidence exists")
    if project.get("project_id") == "dream-studio":
        candidate_profiles.extend(["shared_intelligence_only", "adapter_router_only", "full"])
        reasons.append(
            "Dream Studio project exposes shared-intelligence and adapter-router surfaces"
        )
    candidate_profiles = list(dict.fromkeys(candidate_profiles))
    fit_modules = [
        module_id
        for module_id, contract in contracts.items()
        if set(contract.get("install_runtime_profile_membership", [])).intersection(
            candidate_profiles
        )
    ]
    return {
        "classification": "evidence_backed_profile_fit",
        "candidate_profiles": [
            {
                "profile_id": profile_id,
                "commands": profiles.get(profile_id, {}).get("exposed_commands", []),
                "routes": profiles.get(profile_id, {}).get("exposed_routes", []),
                "docker_required": profiles.get(profile_id, {}).get("docker_required"),
                "empty_state": profiles.get(profile_id, {}).get("honest_empty_state"),
            }
            for profile_id in candidate_profiles
            if profile_id in profiles
        ],
        "fit_modules": sorted(fit_modules),
        "reasons": reasons,
        "source_refs": ["core.module_profiles", "core.module_contracts"],
        "derived_view": True,
        "primary_authority": False,
    }
