from __future__ import annotations

from core.telemetry.docker_profiles import (
    DOCKER_MODULE_PROFILES,
    docker_profile_map,
    validate_docker_profile_contracts,
    validate_registered_module_profiles,
)
from core.telemetry.execution_spine import DASHBOARD_MODULES


def test_docker_profiles_are_optional_and_non_authoritative() -> None:
    assert validate_docker_profile_contracts() == []

    for profile in DOCKER_MODULE_PROFILES:
        assert profile["optional"] is True
        assert profile["host_state_mount_default"] is False
        assert profile["creates_authority_db"] is False
        assert profile["runtime_authority"] == "local_sqlite_path_explicitly_configured"
        assert profile["fallback_execution_mode"]


def test_required_profile_roles_are_declared() -> None:
    profiles = docker_profile_map()

    assert "security-scanners" in profiles
    assert "agent-workers" in profiles
    assert "workflow-workers" in profiles
    assert "validation-sandboxes" in profiles
    assert "dashboard-api" in profiles
    assert "adapters" in profiles


def test_registered_dashboard_modules_use_known_optional_profiles() -> None:
    assert validate_registered_module_profiles(DASHBOARD_MODULES) == []


def test_validation_rejects_competing_authority_db() -> None:
    bad = [
        {
            "profile": "unsafe",
            "optional": True,
            "host_state_mount_default": False,
            "creates_authority_db": True,
            "runtime_authority": "local_sqlite_path_explicitly_configured",
            "fallback_execution_mode": "local",
        }
    ]

    errors = validate_docker_profile_contracts(bad)

    assert "docker profile must not create authority DB: unsafe" in errors


def test_validation_rejects_unknown_module_profile() -> None:
    errors = validate_registered_module_profiles(
        [{"module_id": "unknown_module", "docker_profile": "mystery-profile"}]
    )

    assert "unknown docker profile for module unknown_module: mystery-profile" in errors
