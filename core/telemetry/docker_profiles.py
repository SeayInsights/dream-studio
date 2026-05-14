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
        "runtime_authority": "local_sqlite_path_explicitly_configured",
        "host_state_mount_default": False,
        "creates_authority_db": False,
        "optional": True,
        "fallback_execution_mode": "local_unavailable_empty_state",
    },
    {
        "profile": "agent-workers",
        "role": "agent_worker_isolation",
        "runtime_authority": "local_sqlite_path_explicitly_configured",
        "host_state_mount_default": False,
        "creates_authority_db": False,
        "optional": True,
        "fallback_execution_mode": "local",
    },
    {
        "profile": "workflow-workers",
        "role": "workflow_worker_isolation",
        "runtime_authority": "local_sqlite_path_explicitly_configured",
        "host_state_mount_default": False,
        "creates_authority_db": False,
        "optional": True,
        "fallback_execution_mode": "local",
    },
    {
        "profile": "validation-sandboxes",
        "role": "validation_sandbox_isolation",
        "runtime_authority": "local_sqlite_path_explicitly_configured",
        "host_state_mount_default": False,
        "creates_authority_db": False,
        "optional": True,
        "fallback_execution_mode": "approved_local_tests",
    },
    {
        "profile": "dashboard-api",
        "role": "dashboard_api_runtime",
        "runtime_authority": "local_sqlite_path_explicitly_configured",
        "host_state_mount_default": False,
        "creates_authority_db": False,
        "optional": True,
        "fallback_execution_mode": "native_fastapi_runtime",
    },
    {
        "profile": "adapters",
        "role": "external_adapter_isolation",
        "runtime_authority": "local_sqlite_path_explicitly_configured",
        "host_state_mount_default": False,
        "creates_authority_db": False,
        "optional": True,
        "fallback_execution_mode": "adapter_disabled_empty_state",
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
