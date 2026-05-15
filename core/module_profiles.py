"""Installed runtime module profiles for Dream Studio."""

from __future__ import annotations

from typing import Any

PROFILE_IDS: tuple[str, ...] = (
    "core",
    "analytics_only",
    "security_only",
    "telemetry_only",
    "dashboard_only",
    "adapter_router_only",
    "shared_intelligence_only",
    "full",
)

MODULE_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "profile_id": "core",
        "includes": ["runtime_config", "sqlite_bootstrap", "global_ds_commands"],
        "excludes": ["dashboard_server", "hooks", "agents", "workflows", "docker"],
        "required_dependencies": ["python", "sqlite"],
        "optional_dependencies": [],
        "exposed_commands": ["ds status", "ds validate", "ds modules"],
        "exposed_routes": [],
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "expected_dashboard_api_behavior": "not_started_empty_state",
        "honest_empty_state": "Core runtime can report state without dashboard/API process.",
    },
    {
        "profile_id": "analytics_only",
        "includes": ["telemetry_read_models", "dashboard_readonly_routes", "global_ds_commands"],
        "excludes": ["hooks", "agents", "workflows", "claude", "codex", "docker", "repo_mutation"],
        "required_dependencies": ["python", "sqlite"],
        "optional_dependencies": ["fastapi_testclient_for_validation"],
        "exposed_commands": ["ds status", "ds validate", "ds modules"],
        "exposed_routes": ["/api/telemetry/*", "/api/shared-intelligence/status"],
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "expected_dashboard_api_behavior": "read_only_with_honest_empty_states",
        "honest_empty_state": "Analytics routes return empty sections when no facts exist.",
    },
    {
        "profile_id": "security_only",
        "includes": ["security_read_models", "security_dashboard_routes"],
        "excludes": ["agent_execution", "docker_required_scanners"],
        "required_dependencies": ["python", "sqlite"],
        "optional_dependencies": ["security_scanner_tools"],
        "exposed_commands": ["ds status", "ds modules"],
        "exposed_routes": ["/api/v1/security/*"],
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "expected_dashboard_api_behavior": "security_empty_state_when_no_findings",
        "honest_empty_state": "No security findings recorded for the selected scope.",
    },
    {
        "profile_id": "telemetry_only",
        "includes": ["telemetry_tables", "telemetry_read_models"],
        "excludes": ["dashboard_frontend", "adapter_router", "docker"],
        "required_dependencies": ["python", "sqlite"],
        "optional_dependencies": [],
        "exposed_commands": ["ds status", "ds validate"],
        "exposed_routes": ["/api/telemetry/*"],
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "expected_dashboard_api_behavior": "telemetry_readonly_or_empty",
        "honest_empty_state": "No telemetry records have been captured yet.",
    },
    {
        "profile_id": "dashboard_only",
        "includes": ["dashboard_frontend", "dashboard_api_read_models"],
        "excludes": ["hooks", "agent_execution", "adapter_config_writes", "docker"],
        "required_dependencies": ["python", "sqlite", "fastapi"],
        "optional_dependencies": [],
        "exposed_commands": ["ds dashboard", "ds validate"],
        "exposed_routes": ["/dashboard", "/api/telemetry/*", "/api/v1/hooks/*"],
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "expected_dashboard_api_behavior": "dashboard_loads_with_derived_views",
        "honest_empty_state": "Dashboard displays derived empty states when sources are empty.",
    },
    {
        "profile_id": "adapter_router_only",
        "includes": ["adapter_router", "adapter_health", "context_packet_preview"],
        "excludes": ["dashboard_frontend_required", "live_adapter_execution", "docker"],
        "required_dependencies": ["python", "sqlite"],
        "optional_dependencies": ["mcp_client"],
        "exposed_commands": ["ds adapters", "ds context-packet", "ds router"],
        "exposed_routes": ["/api/shared-intelligence/adapter-router"],
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "expected_dashboard_api_behavior": "router_read_model_available",
        "honest_empty_state": "Unsupported adapters are listed as unsupported or context-packet-only.",
    },
    {
        "profile_id": "shared_intelligence_only",
        "includes": ["adapter_profiles", "model_profiles", "context_packets", "contract_atlas"],
        "excludes": ["dashboard_frontend_required", "hooks_required", "docker"],
        "required_dependencies": ["python", "sqlite"],
        "optional_dependencies": [],
        "exposed_commands": ["ds contract-atlas", "ds context-packet", "ds adapters"],
        "exposed_routes": ["/api/shared-intelligence/*"],
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "expected_dashboard_api_behavior": "shared_intelligence_read_models_only",
        "honest_empty_state": "Shared-intelligence sections report their own empty states.",
    },
    {
        "profile_id": "full",
        "includes": ["core", "dashboard", "telemetry", "shared_intelligence", "adapter_router"],
        "excludes": ["docker_required", "cleanup_execution", "deployment"],
        "required_dependencies": ["python", "sqlite", "fastapi"],
        "optional_dependencies": ["claude", "codex", "mcp_client", "docker"],
        "exposed_commands": [
            "ds status",
            "ds dashboard",
            "ds validate",
            "ds contract-atlas",
            "ds adapters",
            "ds context-packet",
            "ds modules",
            "ds router",
        ],
        "exposed_routes": ["/dashboard", "/api/telemetry/*", "/api/shared-intelligence/*"],
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "expected_dashboard_api_behavior": "all_local_read_models_available",
        "honest_empty_state": "Optional integrations show empty or unavailable state honestly.",
    },
)


def module_profiles() -> dict[str, Any]:
    """Return installed runtime module profiles."""

    profiles = [dict(profile) for profile in MODULE_PROFILES]
    return {
        "model_name": "dream_studio_installed_module_profiles",
        "derived_view": True,
        "primary_authority": False,
        "profile_count": len(profiles),
        "profiles": profiles,
    }


def module_profile_map() -> dict[str, dict[str, Any]]:
    """Return module profiles keyed by id."""

    return {profile["profile_id"]: dict(profile) for profile in MODULE_PROFILES}


def validate_module_profiles(profiles: tuple[dict[str, Any], ...] = MODULE_PROFILES) -> list[str]:
    """Validate independence and honesty guarantees for installed profiles."""

    errors: list[str] = []
    seen: set[str] = set()
    required_fields = {
        "profile_id",
        "includes",
        "excludes",
        "required_dependencies",
        "optional_dependencies",
        "exposed_commands",
        "exposed_routes",
        "hooks_required",
        "agents_required",
        "workflows_required",
        "claude_required",
        "codex_required",
        "docker_required",
        "expected_dashboard_api_behavior",
        "honest_empty_state",
    }
    for profile in profiles:
        profile_id = str(profile.get("profile_id") or "")
        if profile_id in seen:
            errors.append(f"duplicate profile_id: {profile_id}")
        seen.add(profile_id)
        missing = sorted(field for field in required_fields if field not in profile)
        if missing:
            errors.append(f"profile {profile_id} missing fields: {', '.join(missing)}")
        if not profile.get("honest_empty_state"):
            errors.append(f"profile {profile_id} missing honest empty state")
        if profile.get("docker_required") is not False:
            errors.append(f"profile {profile_id} must not require Docker")
    if set(PROFILE_IDS) != seen:
        errors.append("profile id set does not match required installed runtime profiles")
    analytics = next(
        (profile for profile in profiles if profile.get("profile_id") == "analytics_only"),
        {},
    )
    for field in (
        "hooks_required",
        "agents_required",
        "workflows_required",
        "claude_required",
        "codex_required",
        "docker_required",
    ):
        if analytics.get(field) is not False:
            errors.append(f"analytics_only must not require {field.removesuffix('_required')}")
    if "repo_mutation" not in analytics.get("excludes", []):
        errors.append("analytics_only must exclude repo mutation")
    return errors
