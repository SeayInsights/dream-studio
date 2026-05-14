"""Telemetry module registry declaration contracts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from core.telemetry.docker_profiles import validate_registered_module_profiles

REQUIRED_MODULE_FIELDS = (
    "module_id",
    "module_name",
    "module_type",
    "owns_tables",
    "source_tables",
    "dashboard_cards",
    "drilldown_paths",
    "empty_state",
)


def normalize_module_declaration(module: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a dashboard module into the registry contract shape."""
    owns_tables = list(module.get("owns_tables", []))
    source_tables = list(module.get("source_tables", []))
    dashboard_cards = list(module.get("dashboard_cards", []))
    drilldown_paths = list(module.get("drilldown_paths", []))
    docker_profile = module.get("docker_profile")
    return {
        "module_id": module.get("module_id"),
        "module_name": module.get("module_name"),
        "module_type": module.get("module_type"),
        "runtime_mode": module.get("runtime_mode", "local"),
        "docker_profile": docker_profile,
        "schema": {
            "owns_tables": owns_tables,
            "source_tables": source_tables,
        },
        "facts": source_tables,
        "dashboard_cards": dashboard_cards,
        "drilldown_paths": drilldown_paths,
        "health_check": {
            "status": module.get("health_status", "declared"),
            "required": True,
        },
        "dependencies": {
            "source_tables": source_tables,
            "docker_profile": docker_profile,
            "optional_docker": docker_profile is not None,
        },
        "empty_state": module.get("empty_state"),
    }


def build_module_registry_contracts(
    modules: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build normalized module registry contracts from module declarations."""
    declarations = [normalize_module_declaration(module) for module in modules]
    return {
        "artifact_type": "telemetry_module_registry_contracts",
        "schema_migration_required": False,
        "runtime_loading_required": False,
        "db_write_required": False,
        "modules": declarations,
    }


def validate_module_registry_contracts(
    modules: Iterable[Mapping[str, Any]],
) -> list[str]:
    """Validate dashboard module declarations have complete registry metadata."""
    rows = list(modules)
    errors = validate_registered_module_profiles(rows)
    seen: set[str] = set()
    for module in rows:
        module_id = module.get("module_id")
        if module_id in seen:
            errors.append(f"duplicate module_id: {module_id}")
        seen.add(str(module_id))
        for field in REQUIRED_MODULE_FIELDS:
            value = module.get(field)
            if value in (None, "", [], {}):
                errors.append(f"module {module_id} missing {field}")
        normalized = normalize_module_declaration(module)
        if normalized["runtime_mode"] not in {"local", "local_unavailable", "docker_optional"}:
            errors.append(f"module {module_id} has invalid runtime mode")
        if normalized["health_check"]["status"] not in {
            "declared",
            "healthy",
            "degraded",
            "disabled",
        }:
            errors.append(f"module {module_id} has invalid health status")
    return errors
