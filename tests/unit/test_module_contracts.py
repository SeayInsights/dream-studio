from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from core.module_contracts import (
    MODULE_CONTRACT_IDS,
    module_contract_map,
    module_contracts,
    validate_module_contracts,
)
from core.module_profiles import module_profile_map, validate_module_profiles
from projections.api.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_major_module_contracts_cover_required_boundaries() -> None:
    payload = module_contracts()
    contracts = module_contract_map()

    assert validate_module_contracts() == []
    assert payload["schema"] == "dream_studio.module_contracts.v1"
    assert payload["derived_view"] is True
    assert payload["primary_authority"] is False
    assert payload["db_write_authorized"] is False
    assert set(contracts) == set(MODULE_CONTRACT_IDS)
    assert {
        "core",
        "telemetry",
        "dashboard",
        "security_only",
        "token_only",
        "analytics_only",
        "shared_intelligence",
        "adapter_router",
        "adapter_projection",
        "external_project",
        "capability_center",
        "scoped_agents",
        "github_repo_intake",
        "docker_optional",
        "full",
    } <= set(contracts)


def test_each_module_contract_declares_operational_contract_fields() -> None:
    profile_ids = set(module_profile_map())

    for contract in module_contract_map().values():
        assert contract["purpose"]
        assert contract["disabled_module_behavior"]
        assert contract["empty_state_behavior"]
        assert contract["security_readiness_impact"]
        assert contract["contract_atlas_maturity_level"]
        assert contract["validation_tests"]
        assert set(contract["install_runtime_profile_membership"]) <= profile_ids
        for test_path in contract["validation_tests"]:
            assert (REPO_ROOT / test_path).is_file(), test_path


def test_independent_runtime_profiles_keep_optional_dependencies_optional() -> None:
    profiles = module_profile_map()

    assert validate_module_profiles() == []
    analytics = profiles["analytics_only"]
    assert analytics["hooks_required"] is False
    assert analytics["agents_required"] is False
    assert analytics["workflows_required"] is False
    assert analytics["claude_required"] is False
    assert analytics["codex_required"] is False
    assert analytics["docker_required"] is False
    assert "repo_mutation" in analytics["excludes"]

    security = profiles["security_only"]
    assert security["docker_required"] is False
    assert security["claude_required"] is False
    assert security["codex_required"] is False

    token = profiles["token_only"]
    assert token["docker_required"] is False
    assert "fake_cost_estimation" in token["excludes"]
    assert token["cost_policy"].startswith("unknown_cost_stays_unknown")

    dashboard = profiles["dashboard_only"]
    assert dashboard["expected_dashboard_api_behavior"] == "dashboard_loads_with_derived_views"
    assert dashboard["hooks_required"] is False

    shared = profiles["shared_intelligence_only"]
    assert shared["claude_required"] is False
    assert shared["codex_required"] is False

    router = profiles["adapter_router_only"]
    assert "dashboard_frontend_required" in router["excludes"]

    core = profiles["core"]
    assert core["docker_required"] is False
    assert "dashboard_server" in core["excludes"]


def test_token_contract_preserves_usage_without_fake_cost() -> None:
    token = module_contract_map()["token_only"]

    assert token["policy"] == (
        "Tokens are usage telemetry; cost remains unknown unless provider-reported or configured."
    )
    assert "token_usage_records" in token["owned_tables"]
    assert "ai_usage_operational_records" in token["owned_tables"]
    assert all("fake" not in dependency.lower() for dependency in token["write_dependencies"])


def test_optional_modules_do_not_own_forbidden_authority() -> None:
    contracts = module_contract_map()

    assert contracts["dashboard"]["owned_tables"] == []
    assert contracts["adapter_projection"]["owned_tables"] == []
    assert contracts["docker_optional"]["owned_tables"] == []
    assert "container-local temp state only" in contracts["docker_optional"]["write_dependencies"]
    assert (
        "Docker unavailable never disables core authority"
        in contracts["docker_optional"]["disabled_module_behavior"]
    )


def test_safe_import_boundaries_for_standalone_modules() -> None:
    standalone_files = {
        "analytics_only": REPO_ROOT / "core" / "analytics_ingestion.py",
        "module_profiles": REPO_ROOT / "core" / "module_profiles.py",
        "module_contracts": REPO_ROOT / "core" / "module_contracts.py",
    }
    forbidden_roots = {
        "hooks",
        "agents",
        "workflows",
        "docker",
        "claude",
        "codex",
    }

    for module_name, path in standalone_files.items():
        imports = _import_roots(path)
        assert imports.isdisjoint(
            forbidden_roots
        ), f"{module_name} imports {imports & forbidden_roots}"


def test_shared_intelligence_route_exposes_module_contracts() -> None:
    client = TestClient(app)

    response = client.get("/api/shared-intelligence/module-contracts")
    status = client.get("/api/shared-intelligence/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema"] == "dream_studio.module_contracts.v1"
    assert payload["contract_count"] == 15
    assert payload["db_write_authorized"] is False
    assert any(contract["module_id"] == "token_only" for contract in payload["contracts"])
    assert any(surface["surface_id"] == "module-contracts" for surface in status.json()["surfaces"])


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots
