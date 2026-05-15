"""Contract Atlas derived read model for Dream Studio.

The atlas explains Dream Studio's own layers, modules, interfaces, runtime
profiles, adapter projection boundaries, and dependency graph without creating
new authority. It is private/local by default; public exports are sanitized.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.shared_intelligence.adapter_config_projection import adapter_config_projection_report
from core.shared_intelligence.adapter_staleness import (
    adapter_staleness_report,
    validate_adapter_staleness_report,
)
from core.shared_intelligence.authority import REQUIRED_SHARED_INTELLIGENCE_TABLES
from core.shared_intelligence.contract_registry import contract_registry
from core.installed_runtime import installed_runtime_model
from core.module_profiles import module_profiles, validate_module_profiles
from core.shared_intelligence.maturity_ledger import (
    maturity_ledger,
    validate_maturity_ledger,
)
from core.telemetry.docker_profiles import (
    DOCKER_MODULE_PROFILES,
    validate_docker_profile_contracts,
)
from core.telemetry.execution_spine import DASHBOARD_MODULES
from core.telemetry.module_registry_contract import (
    build_module_registry_contracts,
    validate_module_registry_contracts,
)

CONTRACT_ATLAS_SCHEMA = "dream_studio.contract_atlas.v1"
EXPORT_SCOPES = frozenset({"private", "public"})
DEFAULT_CONTRACT_ATLAS_PROJECT_ID = "dream-studio"


def build_contract_atlas(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    project_id: str | None = None,
    export_scope: str = "private",
) -> dict[str, Any]:
    """Build Dream Studio's derived Contract Atlas.

    The function reads SQLite authority through injected connections and repo
    declarations from the provided repo root. It never writes to SQLite, adapter
    configs, or local runtime state.
    """

    if export_scope not in EXPORT_SCOPES:
        raise ValueError(f"unsupported export_scope: {export_scope}")

    root = Path(repo_root).resolve()
    effective_project_id = project_id or DEFAULT_CONTRACT_ATLAS_PROJECT_ID
    projection_report = adapter_config_projection_report(conn, project_id=effective_project_id)
    staleness_report = adapter_staleness_report(
        conn, config_root=root, project_id=effective_project_id
    )
    module_contracts = build_module_registry_contracts(DASHBOARD_MODULES)
    module_errors = validate_module_registry_contracts(DASHBOARD_MODULES)
    docker_errors = validate_docker_profile_contracts(DOCKER_MODULE_PROFILES)
    staleness_errors = validate_adapter_staleness_report(staleness_report)
    current_maturity_ledger = maturity_ledger(project_id=effective_project_id)
    maturity_errors = validate_maturity_ledger(current_maturity_ledger)
    profile_errors = validate_module_profiles()

    atlas = {
        "schema": CONTRACT_ATLAS_SCHEMA,
        "model_name": "dream_studio_contract_atlas",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": effective_project_id,
        "export_scope": "private",
        "private_by_default": True,
        "public_export_requires_sanitization": True,
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "execution_authorized": False,
        "policy_mutation_authorized": False,
        "db_write_authorized": False,
        "source_tables": _source_tables(),
        "repo_root": str(root),
        "whole_system_contract": _whole_system_contract(),
        "contract_registry": contract_registry(),
        "layer_contracts": _layer_contracts(),
        "module_contracts": module_contracts["modules"],
        "interface_contracts": _interface_contracts(),
        "runtime_profiles": _runtime_profiles(),
        "installed_runtime_model": installed_runtime_model(
            source_root=root,
            dream_studio_home=Path.home() / ".dream-studio",
        ),
        "installed_module_profiles": module_profiles(),
        "analytics_only_profile": _analytics_only_profile(),
        "docs_freshness_tracking": _docs_freshness_tracking(),
        "current_maturity_ledger": current_maturity_ledger,
        "adapter_projection_contracts": _adapter_projection_contracts(
            projection_report, staleness_report
        ),
        "dashboard_private_export_boundaries": _dashboard_private_export_boundaries(),
        "maturity_scorecard": _maturity_scorecard(
            staleness_report=staleness_report,
            module_errors=module_errors,
            docker_errors=docker_errors,
            maturity_errors=maturity_errors,
            profile_errors=profile_errors,
        ),
        "confirmed_dependency_graph": _confirmed_dependency_graph(
            projection_report=projection_report,
            staleness_report=staleness_report,
        ),
        "boundary_violation_report": _boundary_violation_report(
            staleness_report=staleness_report,
            module_errors=module_errors,
            docker_errors=docker_errors,
            staleness_errors=staleness_errors,
            maturity_errors=maturity_errors,
            profile_errors=profile_errors,
        ),
        "active_adapter_execution_validation": _active_adapter_execution_validation(
            staleness_report
        ),
        "empty_state": "Contract Atlas has no contracts to display.",
    }

    if export_scope == "public":
        return sanitize_contract_atlas_for_public_export(atlas)
    return atlas


def sanitize_contract_atlas_for_public_export(atlas: Mapping[str, Any]) -> dict[str, Any]:
    """Return a public-safe Contract Atlas export.

    Sanitization removes absolute local paths and local user-surface metadata but
    preserves the contract graph, source-table references, maturity state, and
    non-authoritative boundary notes.
    """

    sanitized = _sanitize_value(dict(atlas))
    sanitized["export_scope"] = "public"
    sanitized["sanitized_public_export"] = True
    sanitized["repo_root"] = "<sanitized-local-path>"
    for contract in sanitized.get("adapter_projection_contracts", []):
        contract.pop("local_user_surface", None)
        local_hook = contract.get("local_hook_surface")
        if isinstance(local_hook, dict):
            contract["local_hook_surface"] = {
                "exists": local_hook.get("exists"),
                "status": local_hook.get("status"),
                "state_classification": local_hook.get("state_classification"),
                "live_execution_observed": False,
                "secret_contents_read": False,
            }
    return sanitized


def validate_contract_atlas(atlas: Mapping[str, Any]) -> list[str]:
    """Validate Contract Atlas authority and boundary guarantees."""

    errors: list[str] = []
    if atlas.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if atlas.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    if atlas.get("routing_authority") is not False:
        errors.append("routing_authority must be false")
    if atlas.get("execution_authorized") is not False:
        errors.append("execution_authorized must be false")
    if atlas.get("db_write_authorized") is not False:
        errors.append("db_write_authorized must be false")
    required = (
        "whole_system_contract",
        "layer_contracts",
        "module_contracts",
        "interface_contracts",
        "runtime_profiles",
        "installed_runtime_model",
        "installed_module_profiles",
        "analytics_only_profile",
        "contract_registry",
        "docs_freshness_tracking",
        "current_maturity_ledger",
        "adapter_projection_contracts",
        "dashboard_private_export_boundaries",
        "maturity_scorecard",
        "confirmed_dependency_graph",
        "boundary_violation_report",
    )
    for section in required:
        if not atlas.get(section):
            errors.append(f"missing atlas section: {section}")
    if atlas.get("export_scope") == "public":
        payload = json.dumps(atlas, sort_keys=True)
        if _contains_absolute_path(payload):
            errors.append("public atlas export contains an absolute local path")
    graph = atlas.get("confirmed_dependency_graph") or {}
    for edge in graph.get("edges", []):
        if edge.get("edge_status") != "confirmed":
            errors.append(
                f"unconfirmed dependency edge: {edge.get('source')}->{edge.get('target')}"
            )
    return errors


def _whole_system_contract() -> dict[str, Any]:
    return {
        "contract_id": "dream-studio-system",
        "name": "Dream Studio Local-First AI Orchestration",
        "canonical_authority": [
            "repo source for product code and public contracts",
            "operator-local SQLite for structured runtime authority",
            "operator-local evidence packets for private audit exports",
        ],
        "derived_surfaces": ["dashboard", "API read models", "adapter projections"],
        "non_authority_surfaces": [
            "private model memory",
            "adapter-local config",
            "Docker runtime",
        ],
        "required_boundaries": [
            "dashboard is derived_view=true and primary_authority=false",
            "adapters do not own canonical state",
            "Docker profiles must not create a competing authority DB",
            "public exports are sanitized",
        ],
    }


def _layer_contracts() -> list[dict[str, Any]]:
    return [
        {
            "layer_id": "repo_source",
            "role": "product_source_and_public_contracts",
            "canonical_for": ["source code", "tests", "docs", "schemas", "repo adapter surfaces"],
            "not_canonical_for": ["operator runtime state", "private evidence", "live DB rows"],
            "boundary": "Repo files must not embed operator-local secrets or live state.",
        },
        {
            "layer_id": "sqlite_authority",
            "role": "local_structured_authority",
            "canonical_for": sorted(REQUIRED_SHARED_INTELLIGENCE_TABLES),
            "not_canonical_for": ["public docs", "source code"],
            "boundary": "SQLite writes require explicit runtime/tooling authorization.",
        },
        {
            "layer_id": "telemetry_read_models",
            "role": "derived_operational_intelligence",
            "canonical_for": [],
            "not_canonical_for": ["routing authority", "primary authority decisions"],
            "boundary": "Read models summarize facts and must keep authority metadata.",
        },
        {
            "layer_id": "dashboard_api",
            "role": "local_human_loop_surface",
            "canonical_for": [],
            "not_canonical_for": ["source of truth", "cleanup execution", "deployment"],
            "boundary": "Dashboard output is derived and non-authoritative.",
        },
        {
            "layer_id": "adapter_projection",
            "role": "tool_specific_context_surface",
            "canonical_for": [],
            "not_canonical_for": ["Dream Studio authority", "private model memory"],
            "boundary": "Claude, Codex, and other adapters consume projections only.",
        },
        {
            "layer_id": "runtime_profiles",
            "role": "execution_boundary_descriptions",
            "canonical_for": [],
            "not_canonical_for": ["SQLite authority DB creation"],
            "boundary": "Optional profiles must receive explicit SQLite paths.",
        },
    ]


def _interface_contracts() -> list[dict[str, Any]]:
    return [
        {
            "interface_id": "telemetry_api",
            "path_family": "/api/telemetry/*",
            "consumer": "dashboard",
            "source": "core.telemetry.read_models",
            "authority": "derived",
            "writes_authorized": False,
        },
        {
            "interface_id": "shared_intelligence_api",
            "path_family": "/api/shared-intelligence/*",
            "consumer": "dashboard and local tools",
            "source": "core.shared_intelligence.*",
            "authority": "derived",
            "writes_authorized": False,
        },
        {
            "interface_id": "legacy_dashboard_api",
            "path_family": "/api/v1/*",
            "consumer": "legacy dashboard sections",
            "source": "projections.api.routes.*",
            "authority": "compatibility_read_surface",
            "writes_authorized": False,
        },
        {
            "interface_id": "hook_launcher",
            "path_family": "hooks/run.py, hooks/run.cmd, hooks/run.sh",
            "consumer": "Claude/Codex hook surfaces",
            "source": "runtime/hooks/*",
            "authority": "execution_projection",
            "writes_authorized": False,
        },
        {
            "interface_id": "active_repo_adapter_surfaces",
            "path_family": "CLAUDE.md and AGENTS.md",
            "consumer": "Claude/Codex when loading repo context",
            "source": "repo-root files",
            "authority": "projection",
            "writes_authorized": False,
        },
    ]


def _runtime_profiles() -> list[dict[str, Any]]:
    native = {
        "profile": "native-local",
        "role": "default_local_runtime",
        "optional": False,
        "runtime_authority": "canonical_path_or_injected_sqlite_path",
        "creates_authority_db": False,
        "fallback_execution_mode": "not_applicable",
    }
    profiles = [native]
    profiles.extend(dict(profile) for profile in DOCKER_MODULE_PROFILES)
    return profiles


def _analytics_only_profile() -> dict[str, Any]:
    return {
        "profile": "analytics-only",
        "role": "read_only_dashboard_and_reporting",
        "db_mode": "read_only",
        "writes_authorized": False,
        "execution_authorized": False,
        "allowed_surfaces": ["/api/telemetry/*", "/api/shared-intelligence/*"],
        "disallowed_surfaces": ["adapter config writes", "cleanup execution", "live migrations"],
        "empty_state_policy": "show honest empty states from current authority",
    }


def _adapter_projection_contracts(
    projection_report: Mapping[str, Any],
    staleness_report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checks = {check["adapter_id"]: check for check in staleness_report.get("checks", [])}
    contracts: list[dict[str, Any]] = []
    for projection in projection_report.get("projections", []):
        adapter_id = str(projection["adapter_id"])
        check = checks.get(adapter_id, {})
        contracts.append(
            {
                "adapter_id": adapter_id,
                "adapter_type": projection["adapter_type"],
                "projection_path": projection["projection_path"],
                "projection_sha256": projection["content_sha256"],
                "source_authority": projection["source_authority"],
                "adapter_owns_source_of_truth": False,
                "config_write_authorized": False,
                "generated_projection": check.get("generated_projection"),
                "active_repo_surface": check.get("active_repo_surface"),
                "local_user_surface": check.get("local_user_surface"),
                "local_hook_surface": check.get("local_hook_surface"),
                "state_classifications": check.get("state_classifications", []),
                "live_execution_state": check.get("live_execution_state"),
            }
        )
    return contracts


def _dashboard_private_export_boundaries() -> dict[str, Any]:
    return {
        "dashboard_authority": "derived_view_only",
        "private_default": True,
        "public_exports_allowed": True,
        "public_export_policy": "sanitize local paths, local user surfaces, and sensitive metadata",
        "private_surfaces": [
            "operator-local evidence",
            "live SQLite rows",
            "local adapter configs",
            "backup and rollback paths",
        ],
        "public_surfaces": ["sanitized docs", "source-level contracts", "non-sensitive examples"],
    }


def _docs_freshness_tracking() -> dict[str, Any]:
    return {
        "tracking_mode": "changed_files_same_change_set",
        "release_gate": "interfaces/cli/contract_docs_drift_gate.py",
        "blocking_policy": (
            "Meaningful source/schema/dashboard/workflow/adapter/release-gate "
            "changes must include the required impacted contract or docs refs in "
            "the same change set."
        ),
        "stale_states": ["stale_docs_required", "registry_validation_error"],
        "non_blocking_states": ["not_impacted", "fresh"],
        "rewrite_every_doc_required": False,
    }


def _maturity_scorecard(
    *,
    staleness_report: Mapping[str, Any],
    module_errors: list[str],
    docker_errors: list[str],
    maturity_errors: list[str],
    profile_errors: list[str],
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
    ]


def _confirmed_dependency_graph(
    *,
    projection_report: Mapping[str, Any],
    staleness_report: Mapping[str, Any],
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(node_id: str, node_type: str, label: str) -> None:
        nodes.setdefault(node_id, {"id": node_id, "type": node_type, "label": label})

    def add_edge(source: str, target: str, relation: str, evidence: str) -> None:
        edges.append(
            {
                "source": source,
                "target": target,
                "relation": relation,
                "edge_status": "confirmed",
                "source_evidence": evidence,
            }
        )

    add_node("system:dream-studio", "system", "Dream Studio")
    for layer in _layer_contracts():
        layer_id = f"layer:{layer['layer_id']}"
        add_node(layer_id, "layer", layer["role"])
        add_edge(
            "system:dream-studio", layer_id, "contains_layer", "contract_atlas.layer_contracts"
        )

    for module in DASHBOARD_MODULES:
        module_id = f"module:{module['module_id']}"
        add_node(module_id, "module", module["module_name"])
        add_edge(
            "layer:telemetry_read_models",
            module_id,
            "declares_module",
            "core.telemetry.execution_spine.DASHBOARD_MODULES",
        )
        for table in module["source_tables"]:
            table_id = f"table:{table}"
            add_node(table_id, "sqlite_table", table)
            add_edge(
                module_id,
                table_id,
                "reads_source_table",
                "core.telemetry.execution_spine.DASHBOARD_MODULES",
            )
        if module.get("docker_profile"):
            profile_id = f"runtime:{module['docker_profile']}"
            add_node(profile_id, "runtime_profile", str(module["docker_profile"]))
            add_edge(
                module_id,
                profile_id,
                "optional_runtime_profile",
                "core.telemetry.execution_spine.DASHBOARD_MODULES",
            )

    for profile in DOCKER_MODULE_PROFILES:
        profile_id = f"runtime:{profile['profile']}"
        add_node(profile_id, "runtime_profile", profile["profile"])
        add_edge(
            "layer:runtime_profiles",
            profile_id,
            "declares_optional_profile",
            "core.telemetry.docker_profiles.DOCKER_MODULE_PROFILES",
        )

    for projection in projection_report.get("projections", []):
        adapter_id = f"adapter:{projection['adapter_id']}"
        projection_id = f"projection:{projection['projection_path']}"
        add_node(adapter_id, "adapter", projection["adapter_name"])
        add_node(projection_id, "adapter_projection", projection["projection_path"])
        add_edge(
            "layer:adapter_projection",
            adapter_id,
            "declares_adapter",
            "sqlite:adapter_authority_profiles",
        )
        add_edge(
            adapter_id,
            projection_id,
            "projects_config_to",
            "sqlite:adapter_authority_profiles",
        )

    for check in staleness_report.get("checks", []):
        active = check.get("active_repo_surface")
        if active:
            surface_id = f"active-surface:{active['path']}"
            add_node(surface_id, "active_repo_surface", active["path"])
            add_edge(
                f"adapter:{check['adapter_id']}",
                surface_id,
                "checked_active_surface",
                "core.shared_intelligence.adapter_staleness.ACTIVE_REPO_SURFACES",
            )

    return {
        "graph_type": "confirmed_dependency_graph",
        "inferred_edges_included": False,
        "unverified_edges_included": False,
        "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: (item["source"], item["target"], item["relation"])),
    }


def _boundary_violation_report(
    *,
    staleness_report: Mapping[str, Any],
    module_errors: list[str],
    docker_errors: list[str],
    staleness_errors: list[str],
    maturity_errors: list[str],
    profile_errors: list[str],
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


def _source_tables() -> list[str]:
    tables = set(REQUIRED_SHARED_INTELLIGENCE_TABLES)
    for module in DASHBOARD_MODULES:
        tables.update(module["source_tables"])
    return sorted(tables)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"resolved_path", "config_root"}:
                sanitized[key] = "<sanitized-local-path>"
            else:
                sanitized[key] = _sanitize_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str) and _contains_absolute_path(value):
        return _sanitize_absolute_paths(value)
    return value


def _contains_absolute_path(value: str) -> bool:
    return bool(re.search(r"[A-Za-z]:[\\/]", value))


def _sanitize_absolute_paths(value: str) -> str:
    return re.sub(r"[A-Za-z]:[\\/][^\"'\n\r,}\]]+", "<sanitized-local-path>", value)
