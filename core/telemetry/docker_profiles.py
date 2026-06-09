"""Optional Docker module profile contracts.

Docker profiles describe future isolation boundaries for modules. They do not
start containers, mount host state, or create a competing authority database.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

DOCKER_MODULE_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "profile": "security-scanners",
        "role": "scanner_isolation",
        "enabled_modules": ["security_only", "full"],
        "required_mounts": ["read_only_repo_source", "explicit_runtime_config"],
        "sqlite_authority_path": "explicit_host_path_required",
        "secrets_config_handling": "injected_read_only_when_approved_never_printed",
        "network_exposure": "disabled_by_default",
        "read_write_boundaries": {
            "read": ["repo_source", "runtime_config"],
            "write": ["container_temp_only"],
            "host_write": False,
        },
        "telemetry_emitted": ["docker_profile_checked", "security_scan_summary"],
        "runtime_authority": "local_sqlite_path_explicitly_configured",
        "host_state_mount_default": False,
        "creates_authority_db": False,
        "optional": True,
        "fallback_execution_mode": "local_unavailable_empty_state",
        "fallback_when_unavailable": "security dashboard shows docker scanner unavailable",
        "validation_requirements": ["profile_contract_static_validation"],
        "approval_requirements": ["docker_execution_approval_before_container_start"],
    },
    {
        "profile": "agent-workers",
        "role": "agent_worker_isolation",
        "enabled_modules": ["full"],
        "required_mounts": ["explicit_runtime_config", "scoped_worktree_when_approved"],
        "sqlite_authority_path": "explicit_host_path_required",
        "secrets_config_handling": "no_secrets_by_default",
        "network_exposure": "disabled_by_default",
        "read_write_boundaries": {
            "read": ["scoped_worktree_when_approved"],
            "write": ["container_temp_only"],
            "host_write": False,
        },
        "telemetry_emitted": ["docker_profile_checked", "adapter_worker_status"],
        "runtime_authority": "local_sqlite_path_explicitly_configured",
        "host_state_mount_default": False,
        "creates_authority_db": False,
        "optional": True,
        "fallback_execution_mode": "local",
        "fallback_when_unavailable": "worker execution remains native or disabled",
        "validation_requirements": ["profile_contract_static_validation"],
        "approval_requirements": ["docker_execution_approval_before_container_start"],
    },
    {
        "profile": "workflow-workers",
        "role": "workflow_worker_isolation",
        "enabled_modules": ["full"],
        "required_mounts": ["explicit_runtime_config"],
        "sqlite_authority_path": "explicit_host_path_required",
        "secrets_config_handling": "no_secrets_by_default",
        "network_exposure": "disabled_by_default",
        "read_write_boundaries": {
            "read": ["runtime_config"],
            "write": ["container_temp_only"],
            "host_write": False,
        },
        "telemetry_emitted": ["docker_profile_checked", "workflow_worker_status"],
        "runtime_authority": "local_sqlite_path_explicitly_configured",
        "host_state_mount_default": False,
        "creates_authority_db": False,
        "optional": True,
        "fallback_execution_mode": "local",
        "fallback_when_unavailable": "workflow execution remains native or disabled",
        "validation_requirements": ["profile_contract_static_validation"],
        "approval_requirements": ["docker_execution_approval_before_container_start"],
    },
    {
        "profile": "validation-sandboxes",
        "role": "validation_sandbox_isolation",
        "enabled_modules": ["security_only", "analytics_only", "full"],
        "required_mounts": ["read_only_repo_source", "explicit_runtime_config"],
        "sqlite_authority_path": "explicit_host_path_required",
        "secrets_config_handling": "secrets_not_mounted",
        "network_exposure": "disabled_by_default",
        "read_write_boundaries": {
            "read": ["repo_source"],
            "write": ["container_temp_only"],
            "host_write": False,
        },
        "telemetry_emitted": ["docker_profile_checked", "validation_sandbox_result"],
        "runtime_authority": "local_sqlite_path_explicitly_configured",
        "host_state_mount_default": False,
        "creates_authority_db": False,
        "optional": True,
        "fallback_execution_mode": "approved_local_tests",
        "fallback_when_unavailable": "approved local tests remain authoritative validation path",
        "validation_requirements": ["profile_contract_static_validation"],
        "approval_requirements": ["docker_execution_approval_before_container_start"],
    },
    {
        "profile": "dashboard-api",
        "role": "dashboard_api_runtime",
        "enabled_modules": ["dashboard_only", "analytics_only", "full"],
        "required_mounts": ["explicit_runtime_config"],
        "sqlite_authority_path": "explicit_host_path_required",
        "secrets_config_handling": "read_only_config_only_no_secret_printing",
        "network_exposure": "localhost_only_by_default",
        "read_write_boundaries": {
            "read": ["sqlite_authority"],
            "write": ["container_temp_only"],
            "host_write": False,
        },
        "telemetry_emitted": ["docker_profile_checked", "dashboard_api_health"],
        "runtime_authority": "local_sqlite_path_explicitly_configured",
        "host_state_mount_default": False,
        "creates_authority_db": False,
        "optional": True,
        "fallback_execution_mode": "native_fastapi_runtime",
        "fallback_when_unavailable": "native dashboard/API remains supported",
        "validation_requirements": ["profile_contract_static_validation"],
        "approval_requirements": ["docker_execution_approval_before_container_start"],
    },
    {
        "profile": "adapters",
        "role": "external_adapter_isolation",
        "enabled_modules": ["adapter_router_only", "full"],
        "required_mounts": ["explicit_runtime_config", "adapter_runtime_dir_when_approved"],
        "sqlite_authority_path": "explicit_host_path_required",
        "secrets_config_handling": "provider_credentials_never_inspected_or_printed",
        "network_exposure": "disabled_by_default",
        "read_write_boundaries": {
            "read": ["adapter_runtime_config"],
            "write": ["container_temp_only"],
            "host_write": False,
        },
        "telemetry_emitted": ["docker_profile_checked", "adapter_worker_status"],
        "runtime_authority": "local_sqlite_path_explicitly_configured",
        "host_state_mount_default": False,
        "creates_authority_db": False,
        "optional": True,
        "fallback_execution_mode": "adapter_disabled_empty_state",
        "fallback_when_unavailable": "adapter router reports docker adapter workers unavailable",
        "validation_requirements": ["profile_contract_static_validation"],
        "approval_requirements": ["docker_execution_approval_before_container_start"],
    },
)


def docker_profile_map() -> dict[str, dict[str, Any]]:
    """Return profiles keyed by profile name."""
    return {profile["profile"]: dict(profile) for profile in DOCKER_MODULE_PROFILES}


def validate_docker_profile_contracts(
    profiles: Iterable[Mapping[str, Any]] = DOCKER_MODULE_PROFILES,
) -> list[str]:
    """Validate optional/non-authoritative Docker profile contracts."""
    errors: list[str] = []
    names: set[str] = set()
    for profile in profiles:
        name = str(profile.get("profile", ""))
        if not name:
            errors.append("profile name is required")
        if name in names:
            errors.append(f"duplicate docker profile: {name}")
        names.add(name)
        if profile.get("optional") is not True:
            errors.append(f"docker profile must be optional: {name}")
        if profile.get("host_state_mount_default") is not False:
            errors.append(f"host state mount default must be false: {name}")
        if profile.get("creates_authority_db") is not False:
            errors.append(f"docker profile must not create authority DB: {name}")
        if profile.get("runtime_authority") != "local_sqlite_path_explicitly_configured":
            errors.append(f"docker profile must use explicit local SQLite authority: {name}")
        if not profile.get("fallback_execution_mode"):
            errors.append(f"fallback execution mode required: {name}")
        for key in (
            "enabled_modules",
            "required_mounts",
            "sqlite_authority_path",
            "secrets_config_handling",
            "network_exposure",
            "read_write_boundaries",
            "telemetry_emitted",
            "fallback_when_unavailable",
            "validation_requirements",
            "approval_requirements",
        ):
            if not profile.get(key):
                errors.append(f"docker profile missing {key}: {name}")
        if profile.get("sqlite_authority_path") != "explicit_host_path_required":
            errors.append(f"docker profile must declare explicit sqlite path: {name}")
        boundaries = profile.get("read_write_boundaries")
        if isinstance(boundaries, Mapping) and boundaries.get("host_write") is not False:
            errors.append(f"docker profile must not write host by default: {name}")
    return errors


def validate_registered_module_profiles(module_rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Validate docker_profile values declared by telemetry modules."""
    errors = validate_docker_profile_contracts()
    known = docker_profile_map()
    for module in module_rows:
        profile = module.get("docker_profile")
        if profile is None:
            continue
        if profile not in known:
            errors.append(f"unknown docker profile for module {module.get('module_id')}: {profile}")
    return errors
