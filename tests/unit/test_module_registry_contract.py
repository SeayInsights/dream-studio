from __future__ import annotations

from core.telemetry.execution_spine import DASHBOARD_MODULES
from core.telemetry.module_registry_contract import (
    build_module_registry_contracts,
    normalize_module_declaration,
    validate_module_registry_contracts,
)


def test_dashboard_modules_satisfy_registry_contract() -> None:
    assert validate_module_registry_contracts(DASHBOARD_MODULES) == []


def test_module_registry_contracts_expose_required_metadata() -> None:
    contracts = build_module_registry_contracts(DASHBOARD_MODULES)

    assert contracts["schema_migration_required"] is False
    assert contracts["runtime_loading_required"] is False
    assert contracts["db_write_required"] is False
    assert contracts["modules"]
    for module in contracts["modules"]:
        assert module["module_id"]
        assert module["schema"]["owns_tables"]
        assert module["schema"]["source_tables"]
        assert module["facts"]
        assert module["dashboard_cards"]
        assert module["drilldown_paths"]
        assert module["health_check"]["required"] is True
        assert module["empty_state"]


def test_normalized_module_declares_dependency_and_docker_profile() -> None:
    security = next(
        module for module in DASHBOARD_MODULES if module["module_id"] == "security_analytics"
    )

    normalized = normalize_module_declaration(security)

    assert normalized["runtime_mode"] == "local"
    assert normalized["dependencies"]["source_tables"] == security["source_tables"]
    assert normalized["dependencies"]["docker_profile"] == "security-scanners"
    assert normalized["dependencies"]["optional_docker"] is True


def test_validation_rejects_missing_dashboard_cards() -> None:
    bad = [{**DASHBOARD_MODULES[0], "dashboard_cards": []}]

    errors = validate_module_registry_contracts(bad)

    assert f"module {DASHBOARD_MODULES[0]['module_id']} missing dashboard_cards" in errors


def test_validation_rejects_unknown_docker_profile() -> None:
    bad = [{**DASHBOARD_MODULES[0], "docker_profile": "unknown-profile"}]

    errors = validate_module_registry_contracts(bad)

    assert "unknown docker profile for module security_analytics: unknown-profile" in errors
