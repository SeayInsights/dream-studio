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

from core.analytics_ingestion import analytics_only_profile_status
from core.installed_runtime import installed_runtime_model
from core.module_contracts import module_contracts, validate_module_contracts
from core.module_profiles import module_profiles, validate_module_profiles
from core.shared_intelligence.adapter_config_projection import adapter_config_projection_report
from core.shared_intelligence.adapter_staleness import (
    adapter_staleness_report,
    validate_adapter_staleness_report,
)
from core.shared_intelligence.authority import REQUIRED_SHARED_INTELLIGENCE_TABLES
from core.shared_intelligence.contract_registry import contract_registry
from core.production_readiness import (
    build_secure_production_readiness_gate,
    production_readiness_control_catalog,
)
from core.release.github_pr_cicd_gate import (
    build_dream_studio_cicd_profile,
    discover_workflow_files,
    validate_cicd_profile,
)
from core.security.lifecycle import build_security_lifecycle_gate
from core.shared_intelligence.expert_workflows import (
    expert_workflow_catalog,
    validate_expert_workflow_catalog,
)
from core.shared_intelligence.capability_center import (
    capability_center_summary,
    validate_capability_center_summary,
)
from core.shared_intelligence.github_repo_intake import (
    github_repo_intake_workflow,
    validate_github_repo_intake_workflow,
)
from core.shared_intelligence.maturity_ledger import (
    maturity_ledger,
    validate_maturity_ledger,
)
from core.shared_intelligence.platform_hardening import (
    platform_hardening_summary,
    validate_platform_hardening_summary,
)
from core.shared_intelligence.scoped_agents import (
    scoped_agent_registry,
    validate_scoped_agent_registry,
)
from core.shared_intelligence.task_attribution import (
    task_attribution_summary,
    validate_task_attribution_summary,
)
from core.shared_intelligence.usage_accounting import adapter_usage_accounting_summary
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
    telemetry_module_contracts = build_module_registry_contracts(DASHBOARD_MODULES)
    telemetry_module_errors = validate_module_registry_contracts(DASHBOARD_MODULES)
    major_module_contracts = module_contracts()
    major_module_errors = validate_module_contracts()
    docker_errors = validate_docker_profile_contracts(DOCKER_MODULE_PROFILES)
    staleness_errors = validate_adapter_staleness_report(staleness_report)
    current_maturity_ledger = maturity_ledger(project_id=effective_project_id)
    maturity_errors = validate_maturity_ledger(current_maturity_ledger)
    profile_errors = validate_module_profiles()
    security_lifecycle_gate = build_security_lifecycle_gate(
        conn=conn,
        repo_root=root,
        project_id=effective_project_id,
        lifecycle_event="release_merge",
    )
    production_readiness_catalog = production_readiness_control_catalog(repo_root=root)
    production_readiness_gate = build_secure_production_readiness_gate(
        repo_root=root,
        project_id=effective_project_id,
        lifecycle_event="release_merge",
    )
    usage_accounting = adapter_usage_accounting_summary(conn, project_id=effective_project_id)
    task_attribution = task_attribution_summary(conn, project_id=effective_project_id)
    task_attribution_errors = validate_task_attribution_summary(task_attribution)
    prd_authority = {"source_tables": [], "data_status": "retired"}
    prd_authority_errors = []
    analytics_only_status = analytics_only_profile_status(conn)
    github_cicd_profile = _github_cicd_profile(root)
    expert_workflows = expert_workflow_catalog(project_id=effective_project_id)
    expert_workflow_errors = validate_expert_workflow_catalog(expert_workflows)
    capability_center = capability_center_summary(
        conn,
        project_id=effective_project_id,
        repo_root=root,
    )
    capability_center_errors = validate_capability_center_summary(capability_center)
    scoped_agents = scoped_agent_registry(conn)
    scoped_agent_errors = validate_scoped_agent_registry(scoped_agents)
    github_repo_intake = github_repo_intake_workflow()
    github_repo_intake_errors = validate_github_repo_intake_workflow(github_repo_intake)
    platform_hardening = platform_hardening_summary(conn)
    platform_hardening_errors = validate_platform_hardening_summary(conn)

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
        "module_contracts": major_module_contracts,
        "telemetry_module_contracts": telemetry_module_contracts["modules"],
        "interface_contracts": _interface_contracts(),
        "runtime_profiles": _runtime_profiles(),
        "installed_runtime_model": installed_runtime_model(
            source_root=root,
            dream_studio_home=Path.home() / ".dream-studio",
        ),
        "installed_module_profiles": module_profiles(),
        "analytics_only_profile": _analytics_only_profile(),
        "analytics_only_ingestion": analytics_only_status,
        "security_lifecycle_gate": security_lifecycle_gate,
        "production_readiness_control_catalog": {
            "control_count": production_readiness_catalog["control_count"],
            "control_families": production_readiness_catalog["control_families"],
            "no_duplicate_skill_policy": production_readiness_catalog["no_duplicate_skill_policy"],
            "overlap_decision_count": len(production_readiness_catalog["overlap_matrix"]),
        },
        "secure_production_readiness_gate": {
            "workflow_id": production_readiness_gate["workflow_id"],
            "full_review_required": production_readiness_gate["full_review_required"],
            "control_summary": production_readiness_gate["control_summary"],
            "release_readiness": production_readiness_gate["release_readiness"],
            "project_readiness_score": production_readiness_gate["project_readiness_score"],
        },
        "adapter_usage_accounting": {
            "profile_count": usage_accounting["profile_count"],
            "operational_record_count": usage_accounting["operational_record_count"],
            "token_record_count": usage_accounting["token_record_count"],
            "by_adapter": usage_accounting["by_adapter"],
            # task_attribution key removed: task_attribution_records dropped migration 131
            "policy": usage_accounting["policy"],
            "source_tables": usage_accounting["source_tables"],
            "schema_status": usage_accounting.get("schema_status", "available"),
        },
        "task_attribution_model": {
            "record_count": task_attribution["record_count"],
            "summary": task_attribution["summary"],
            "source_tables": task_attribution["source_tables"],
            "source_status": task_attribution["source_status"],
            "policy": task_attribution["policy"],
            "validation_status": "pass" if not task_attribution_errors else "attention_required",
            "validation_errors": task_attribution_errors,
        },
        "prd_authority_lifecycle": {
            "data_status": "retired",
            "reason": "prd_cluster_dropped_wo_f",
            "source_tables": [],
            "validation_status": "pass",
            "validation_errors": [],
        },
        "github_cicd_profile": github_cicd_profile,
        "expert_workflow_system": {
            "workflow_count": expert_workflows["workflow_count"],
            "overlap_decision_counts": expert_workflows["overlap_decision_counts"],
            "no_duplicate_skill_policy": expert_workflows["no_duplicate_skill_policy"],
            "application_automation_boundaries": expert_workflows[
                "application_automation_boundaries"
            ],
            "authority_write_targets": expert_workflows["authority_write_targets"],
            "validation_status": "pass" if not expert_workflow_errors else "attention_required",
            "validation_errors": expert_workflow_errors,
        },
        "capability_center": {
            "source_status": capability_center["source_status"],
            "section_ids": sorted(capability_center["sections"]),
            "agent_count": capability_center["sections"]["agents"]["count"],
            "workflow_count": capability_center["sections"]["workflows"]["count"],
            "control_count": capability_center["sections"]["controls"]["count"],
            "validation_status": "pass" if not capability_center_errors else "attention_required",
            "validation_errors": capability_center_errors,
        },
        "scoped_agent_execution": {
            "agent_count": scoped_agents["agent_count"],
            "agent_is_authority": scoped_agents["agent_is_authority"],
            "dream_studio_remains_canonical": scoped_agents["dream_studio_remains_canonical"],
            "forbidden_context_by_default": scoped_agents["forbidden_context_by_default"],
            "source_tables": scoped_agents["source_tables"],
            "validation_status": "pass" if not scoped_agent_errors else "attention_required",
            "validation_errors": scoped_agent_errors,
        },
        "github_repo_intake": {
            "workflow_id": github_repo_intake["workflow_id"],
            "schema_status": github_repo_intake.get("schema_status", "available"),
            "evaluation_count": github_repo_intake.get("evaluation_count", 0),
            "decision_counts": github_repo_intake.get("decision_counts", {}),
            "outcome_classes": github_repo_intake["outcome_classes"],
            "copy_code_allowed_without_approval": False,
            "source_tables": github_repo_intake["source_tables"],
            "validation_status": "pass" if not github_repo_intake_errors else "attention_required",
            "validation_errors": github_repo_intake_errors,
        },
        "platform_hardening": {
            "source_status": platform_hardening["source_status"],
            "milestone_ids": sorted(platform_hardening["milestones"]),
            "skill_evaluation_status": platform_hardening["milestones"]["skill_evaluation_harness"][
                "status"
            ],
            "policy_engine_status": platform_hardening["milestones"]["policy_permission_engine"][
                "status"
            ],
            "connector_ingestion_status": platform_hardening["milestones"][
                "engineering_connector_ingestion"
            ]["status"],
            # privacy_redaction_status, local_watch_status, team_rollup_status,
            # installer_distribution_status, demo_case_study_status removed —
            # those milestones' backing tables were dead and dropped in migration 128.
            "validation_status": "pass" if not platform_hardening_errors else "attention_required",
            "validation_errors": platform_hardening_errors,
        },
        "docs_freshness_tracking": _docs_freshness_tracking(),
        "current_maturity_ledger": current_maturity_ledger,
        "adapter_projection_contracts": _adapter_projection_contracts(
            projection_report, staleness_report
        ),
        "dashboard_private_export_boundaries": _dashboard_private_export_boundaries(),
        "maturity_scorecard": _maturity_scorecard(
            staleness_report=staleness_report,
            module_errors=[*telemetry_module_errors, *major_module_errors],
            docker_errors=docker_errors,
            maturity_errors=maturity_errors,
            profile_errors=profile_errors,
            security_lifecycle_gate=security_lifecycle_gate,
            production_readiness_gate=production_readiness_gate,
            usage_accounting=usage_accounting,
            task_attribution=task_attribution,
            task_attribution_errors=task_attribution_errors,
            prd_authority=prd_authority,
            prd_authority_errors=prd_authority_errors,
            analytics_only_status=analytics_only_status,
            github_cicd_profile=github_cicd_profile,
            expert_workflows=expert_workflows,
            expert_workflow_errors=expert_workflow_errors,
            capability_center=capability_center,
            capability_center_errors=capability_center_errors,
            scoped_agents=scoped_agents,
            scoped_agent_errors=scoped_agent_errors,
            github_repo_intake=github_repo_intake,
            github_repo_intake_errors=github_repo_intake_errors,
            platform_hardening=platform_hardening,
            platform_hardening_errors=platform_hardening_errors,
        ),
        "confirmed_dependency_graph": _confirmed_dependency_graph(
            projection_report=projection_report,
            staleness_report=staleness_report,
            security_lifecycle_gate=security_lifecycle_gate,
            production_readiness_gate=production_readiness_gate,
            usage_accounting=usage_accounting,
            task_attribution=task_attribution,
            prd_authority=prd_authority,
            analytics_only_status=analytics_only_status,
            github_cicd_profile=github_cicd_profile,
            expert_workflows=expert_workflows,
            capability_center=capability_center,
            scoped_agents=scoped_agents,
            github_repo_intake=github_repo_intake,
            platform_hardening=platform_hardening,
        ),
        "boundary_violation_report": _boundary_violation_report(
            staleness_report=staleness_report,
            module_errors=[*telemetry_module_errors, *major_module_errors],
            docker_errors=docker_errors,
            staleness_errors=staleness_errors,
            maturity_errors=maturity_errors,
            profile_errors=profile_errors,
            security_lifecycle_gate=security_lifecycle_gate,
            production_readiness_gate=production_readiness_gate,
            expert_workflow_errors=expert_workflow_errors,
            capability_center_errors=capability_center_errors,
            scoped_agent_errors=scoped_agent_errors,
            github_repo_intake_errors=github_repo_intake_errors,
            task_attribution_errors=task_attribution_errors,
            prd_authority_errors=prd_authority_errors,
            platform_hardening_errors=platform_hardening_errors,
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
        "telemetry_module_contracts",
        "interface_contracts",
        "runtime_profiles",
        "installed_runtime_model",
        "installed_module_profiles",
        "analytics_only_profile",
        "analytics_only_ingestion",
        "security_lifecycle_gate",
        "production_readiness_control_catalog",
        "secure_production_readiness_gate",
        "adapter_usage_accounting",
        "task_attribution_model",
        "prd_authority_lifecycle",
        "github_cicd_profile",
        "expert_workflow_system",
        "capability_center",
        "scoped_agent_execution",
        "github_repo_intake",
        "platform_hardening",
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
        "role": "standalone_dashboard_reporting_and_explicit_ingestion",
        "db_mode": "read_only_by_default_explicit_ingestion_only",
        "writes_authorized": False,
        "ingestion_write_authorization": "ds analytics-ingest --execute",
        "execution_authorized": False,
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "repo_mutation_required": False,
        "allowed_surfaces": [
            "/api/telemetry/*",
            "/api/v1/projects*",
            "/api/v1/metrics/*",
            "/api/shared-intelligence/*",
        ],
        "disallowed_surfaces": [
            "adapter config writes",
            "cleanup execution",
            "live migrations",
            "hook_required_ingestion",
            "agent_required_ingestion",
        ],
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
            "career profiles, resumes, applications, contacts, automation evidence, and scorecards",
            "GitHub repo evaluation evidence until explicitly sanitized",
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


def _github_cicd_profile(repo_root: Path) -> dict[str, Any]:
    profile = build_dream_studio_cicd_profile(str(repo_root))
    discovered = discover_workflow_files(repo_root)
    validation_errors = validate_cicd_profile(profile, discovered_workflows=discovered)
    return {
        "model_name": "dream_studio_github_cicd_profile",
        "derived_view": True,
        "primary_authority": False,
        "github_actions_role": profile.github_actions_role,
        "heavy_validation_layer": profile.heavy_validation_layer,
        "github_actions_minutes_policy": profile.github_actions_minutes_policy,
        "github_actions_unavailable_policy": profile.github_actions_unavailable_policy,
        "workflow_files": list(profile.workflow_files),
        "discovered_workflow_files": list(discovered),
        "required_checks": list(profile.required_checks),
        "optional_checks": list(profile.optional_checks),
        "manual_workflows": list(profile.manual_workflows),
        "release_workflows": list(profile.release_workflows),
        "local_preflight_commands": list(profile.local_preflight_commands),
        "merge_policy": profile.merge_policy,
        "deployment_policy": profile.deployment_policy,
        "validation_errors": validation_errors,
        "status": "pass" if not validation_errors else "attention_required",
        "github_api_calls_performed": False,
        "workflow_mutation_authorized": False,
    }


def _maturity_scorecard(
    *,
    staleness_report: Mapping[str, Any],
    module_errors: list[str],
    docker_errors: list[str],
    maturity_errors: list[str],
    profile_errors: list[str],
    security_lifecycle_gate: Mapping[str, Any],
    production_readiness_gate: Mapping[str, Any],
    usage_accounting: Mapping[str, Any],
    task_attribution: Mapping[str, Any],
    task_attribution_errors: list[str],
    prd_authority: Mapping[str, Any],
    prd_authority_errors: list[str],
    analytics_only_status: Mapping[str, Any],
    github_cicd_profile: Mapping[str, Any],
    expert_workflows: Mapping[str, Any],
    expert_workflow_errors: list[str],
    capability_center: Mapping[str, Any],
    capability_center_errors: list[str],
    scoped_agents: Mapping[str, Any],
    scoped_agent_errors: list[str],
    github_repo_intake: Mapping[str, Any],
    github_repo_intake_errors: list[str],
    platform_hardening: Mapping[str, Any],
    platform_hardening_errors: list[str],
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
            "area": "module_boundary_contracts",
            "status": "validated" if not module_errors else "contract_errors_present",
            "error_count": len(module_errors),
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
        {
            "area": "security_lifecycle_gate",
            "status": security_lifecycle_gate.get("security_status"),
            "canonical_framework": security_lifecycle_gate.get("source_framework", {}).get(
                "canonical_framework"
            ),
            "source_control_count": security_lifecycle_gate.get("source_framework", {}).get(
                "source_control_count"
            ),
            "release_readiness_effect": security_lifecycle_gate.get("release_readiness_effect"),
        },
        {
            "area": "secure_production_readiness_gate",
            "status": production_readiness_gate.get("release_readiness", {}).get("status"),
            "workflow_id": production_readiness_gate.get("workflow_id"),
            "control_total": production_readiness_gate.get("control_summary", {}).get("total"),
            "readiness_score_status": production_readiness_gate.get(
                "project_readiness_score", {}
            ).get("status"),
        },
        {
            "area": "adapter_usage_accounting",
            "status": usage_accounting.get("schema_status", "available"),
            "profile_count": usage_accounting.get("profile_count"),
            "token_record_count": usage_accounting.get("token_record_count"),
            "operational_record_count": usage_accounting.get("operational_record_count"),
            "cost_policy": usage_accounting.get("policy", {}),
        },
        {
            "area": "task_attribution_outcome_tracking",
            "status": "validated" if not task_attribution_errors else "attention_required",
            "record_count": task_attribution.get("record_count", 0),
            "outcome_counts": task_attribution.get("summary", {}).get("outcome_counts", {}),
            "validation_counts": task_attribution.get("summary", {}).get("validation_counts", {}),
            "no_fake_cost_precision": task_attribution.get("policy", {}).get(
                "token_cost_precision_not_inferred"
            ),
            "error_count": len(task_attribution_errors),
        },
        {
            "area": "prd_authority_lifecycle",
            "status": "validated" if not prd_authority_errors else "attention_required",
            "prd_count": prd_authority.get("prd_count", 0),
            "lifecycle_counts": prd_authority.get("lifecycle_counts", {}),
            "pending_change_order_count": len(prd_authority.get("pending_change_orders", [])),
            "route_reconciliation_status": prd_authority.get("route_reconciliation_status", {}).get(
                "status"
            ),
            "sqlite_is_prd_authority": prd_authority.get("policy", {}).get(
                "sqlite_is_prd_authority"
            ),
            "change_orders_required": prd_authority.get("policy", {}).get(
                "change_orders_required_for_material_changes"
            ),
            "error_count": len(prd_authority_errors),
        },
        {
            "area": "analytics_only_ingestion",
            "status": "available",
            "profile_id": analytics_only_status.get("profile_id"),
            "hooks_required": analytics_only_status.get("hooks_required"),
            "agents_required": analytics_only_status.get("agents_required"),
            "docker_required": analytics_only_status.get("docker_required"),
            "write_authorization": analytics_only_status.get("write_authorization"),
        },
        {
            "area": "github_cicd_profile",
            "status": github_cicd_profile.get("status"),
            "github_actions_role": github_cicd_profile.get("github_actions_role"),
            "heavy_validation_layer": github_cicd_profile.get("heavy_validation_layer"),
            "required_checks": github_cicd_profile.get("required_checks"),
            "manual_workflows": github_cicd_profile.get("manual_workflows"),
        },
        {
            "area": "expert_workflow_system",
            "status": "validated" if not expert_workflow_errors else "contract_errors_present",
            "workflow_count": expert_workflows.get("workflow_count"),
            "overlap_decision_counts": expert_workflows.get("overlap_decision_counts"),
            "no_duplicate_skill_policy": expert_workflows.get("no_duplicate_skill_policy"),
            "error_count": len(expert_workflow_errors),
        },
        {
            "area": "capability_center",
            "status": "validated" if not capability_center_errors else "contract_errors_present",
            "section_ids": sorted(capability_center.get("sections", {})),
            "error_count": len(capability_center_errors),
        },
        {
            "area": "scoped_agent_execution",
            "status": "validated" if not scoped_agent_errors else "contract_errors_present",
            "agent_count": scoped_agents.get("agent_count"),
            "agent_is_authority": scoped_agents.get("agent_is_authority"),
            "forbidden_context_count": len(scoped_agents.get("forbidden_context_by_default", [])),
            "error_count": len(scoped_agent_errors),
        },
        {
            "area": "github_repo_intake",
            "status": "validated" if not github_repo_intake_errors else "contract_errors_present",
            "workflow_id": github_repo_intake.get("workflow_id"),
            "evaluation_count": github_repo_intake.get("evaluation_count", 0),
            "copy_code_allowed_without_approval": False,
            "error_count": len(github_repo_intake_errors),
        },
        {
            "area": "platform_hardening_sequence",
            "status": "validated" if not platform_hardening_errors else "contract_errors_present",
            "milestone_ids": sorted(platform_hardening.get("milestones", {})),
            "source_status": platform_hardening.get("source_status"),
            "error_count": len(platform_hardening_errors),
        },
    ]


def _confirmed_dependency_graph(
    *,
    projection_report: Mapping[str, Any],
    staleness_report: Mapping[str, Any],
    security_lifecycle_gate: Mapping[str, Any],
    production_readiness_gate: Mapping[str, Any],
    usage_accounting: Mapping[str, Any],
    task_attribution: Mapping[str, Any],
    prd_authority: Mapping[str, Any],
    analytics_only_status: Mapping[str, Any],
    github_cicd_profile: Mapping[str, Any],
    expert_workflows: Mapping[str, Any],
    capability_center: Mapping[str, Any],
    scoped_agents: Mapping[str, Any],
    github_repo_intake: Mapping[str, Any],
    platform_hardening: Mapping[str, Any],
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

    for contract in module_contracts()["contracts"]:
        module_id = f"module:{contract['module_id']}"
        add_node(module_id, "module", contract["module_id"])
        add_edge(
            "system:dream-studio",
            module_id,
            "declares_module_contract",
            "core.module_contracts.MODULE_CONTRACTS",
        )
        for table in contract.get("owned_tables", []):
            table_id = f"table:{table}"
            add_node(table_id, "sqlite_table", str(table))
            add_edge(
                module_id,
                table_id,
                "owns_or_writes_authority",
                "core.module_contracts.MODULE_CONTRACTS",
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

    add_node("module:security_lifecycle_gate", "module", "Security Lifecycle Gate")
    add_node(
        "contract:47_enterprise_security_controls",
        "contract",
        "47 Enterprise Security Controls",
    )
    add_node(
        "doc:docs/contracts/security-review-scan-catalog.yaml",
        "contract_doc",
        "Security Review Scan Catalog",
    )
    add_edge(
        "module:security_lifecycle_gate",
        "contract:47_enterprise_security_controls",
        "implements_control_framework",
        "core.security.lifecycle.build_security_lifecycle_gate",
    )
    add_edge(
        "contract:47_enterprise_security_controls",
        "doc:docs/contracts/security-review-scan-catalog.yaml",
        "mapped_by_catalog",
        str(security_lifecycle_gate.get("source_framework", {}).get("catalog_ref")),
    )
    add_node("module:production_readiness_workflow", "module", "Production Readiness Workflow")
    add_node(
        "contract:secure_production_readiness_gate",
        "contract",
        "Secure Production Readiness Gate",
    )
    add_edge(
        "module:production_readiness_workflow",
        "contract:secure_production_readiness_gate",
        "implements_readiness_gate",
        "core.production_readiness.controls.build_secure_production_readiness_gate",
    )
    add_edge(
        "module:production_readiness_workflow",
        "module:security_lifecycle_gate",
        "requires_security_lifecycle",
        str(production_readiness_gate.get("workflow_id")),
    )
    add_node("module:ai_usage_accounting", "module", "AI Usage Accounting")
    for table in usage_accounting.get("source_tables", []):
        table_id = f"table:{table}"
        add_node(table_id, "sqlite_table", str(table))
        add_edge(
            "module:ai_usage_accounting",
            table_id,
            "reads_source_table",
            "core.shared_intelligence.usage_accounting.adapter_usage_accounting_summary",
        )

    add_node("module:task_attribution_outcome_tracking", "module", "Task Attribution")
    add_edge(
        "module:task_attribution_outcome_tracking",
        "module:ai_usage_accounting",
        "feeds_adapter_usage_outcomes",
        "core.shared_intelligence.task_attribution.task_attribution_summary",
    )
    for table in task_attribution.get("source_tables", []):
        table_id = f"table:{table}"
        add_node(table_id, "sqlite_table", str(table))
        add_edge(
            "module:task_attribution_outcome_tracking",
            table_id,
            "reads_or_links_source_table",
            "core.shared_intelligence.task_attribution.TASK_ATTRIBUTION_SOURCE_TABLES",
        )

    add_node("module:analytics_only_ingestion", "module", "Analytics-Only Ingestion")
    for table in analytics_only_status.get("source_tables", []):
        table_id = f"table:{table}"
        add_node(table_id, "sqlite_table", str(table))
        add_edge(
            "module:analytics_only_ingestion",
            table_id,
            "imports_or_reads_current_authority",
            "core.analytics_ingestion.analytics_only_ingestion_contract",
        )

    add_node("module:github_cicd_profile", "module", "GitHub CI/CD Profile")
    add_node("workflow:pr-smoke", "github_workflow", "PR Smoke")
    add_node("workflow:full-ci", "github_workflow", "Manual Full CI")
    add_node("workflow:release-validation", "github_workflow", "Release Validation")
    add_edge(
        "module:github_cicd_profile",
        "workflow:pr-smoke",
        "requires_lightweight_remote_confidence",
        "core.release.github_pr_cicd_gate.build_dream_studio_cicd_profile",
    )
    add_edge(
        "module:github_cicd_profile",
        "workflow:full-ci",
        "manual_heavy_validation",
        str(github_cicd_profile.get("heavy_validation_layer")),
    )
    add_edge(
        "module:github_cicd_profile",
        "workflow:release-validation",
        "manual_or_tag_release_validation",
        "runtime/config/release-gates/dream-studio.json",
    )

    add_node("module:expert_workflow_system", "module", "Expert Workflow System")
    add_node(
        "module:skill_workflow_hook_telemetry",
        "module",
        "Skill, Workflow, And Hook Telemetry",
    )
    add_edge(
        "module:expert_workflow_system",
        "module:skill_workflow_hook_telemetry",
        "emits_structured_outputs_to",
        "core.shared_intelligence.expert_workflows.AUTHORITY_WRITE_TARGETS",
    )
    for workflow in expert_workflows.get("workflows", []):
        workflow_id = f"workflow:{workflow['workflow_id']}"
        add_node(workflow_id, "expert_workflow", workflow["workflow_id"])
        add_edge(
            "module:expert_workflow_system",
            workflow_id,
            "declares_expert_workflow",
            "core.shared_intelligence.expert_workflows.REQUIRED_WORKFLOW_IDS",
        )
        for owner in workflow.get("existing_owners", []):
            owner_id = f"skill:{owner}"
            add_node(owner_id, "skill_or_workflow_surface", str(owner))
            add_edge(
                workflow_id,
                owner_id,
                "maps_to_existing_owner",
                "core.shared_intelligence.expert_workflows.overlap_matrix",
            )

    add_node("module:capability_center", "module", "Capability Center")
    for section_id in capability_center.get("sections", {}):
        section_node = f"dashboard-section:capability-center:{section_id}"
        add_node(section_node, "dashboard_section", f"Capability Center {section_id}")
        add_edge(
            "module:capability_center",
            section_node,
            "exposes_derived_section",
            "core.shared_intelligence.capability_center.capability_center_summary",
        )

    add_node("module:scoped_agent_execution", "module", "Scoped Agent Execution")
    for agent in scoped_agents.get("agents", []):
        agent_id = f"agent:{agent['agent_id']}"
        add_node(agent_id, "scoped_agent", agent["agent_name"])
        add_edge(
            "module:scoped_agent_execution",
            agent_id,
            "declares_context_scoped_worker",
            "core.shared_intelligence.scoped_agents.DEFAULT_SCOPED_AGENTS",
        )
    add_edge(
        "module:scoped_agent_execution",
        "layer:sqlite_authority",
        "normalizes_results_to",
        "invocation/result authority tables",
    )

    add_node("module:github_repo_intake", "module", "GitHub Repo Intake")
    add_edge(
        "module:github_repo_intake",
        "module:security_lifecycle_gate",
        "requires_security_review_before_adoption",
        "core.shared_intelligence.github_repo_intake.WORKFLOW_STEPS",
    )
    add_edge(
        "module:github_repo_intake",
        "module:expert_workflow_system",
        "requires_overlap_review_before_new_skill_or_workflow",
        "core.shared_intelligence.github_repo_intake.WORKFLOW_STEPS",
    )
    for table in github_repo_intake.get("source_tables", []):
        table_id = f"table:{table}"
        add_node(table_id, "sqlite_table", str(table))
        add_edge(
            "module:github_repo_intake",
            table_id,
            "writes_evaluation_authority",
            "core.shared_intelligence.github_repo_intake.GITHUB_REPO_TABLES",
        )

    add_node("module:platform_hardening_sequence", "module", "Platform Hardening Sequence")
    add_edge(
        "module:platform_hardening_sequence",
        "module:contract_atlas",
        "feeds_maturity_and_docs_drift",
        "core.shared_intelligence.platform_hardening.platform_hardening_summary",
    )
    add_edge(
        "module:platform_hardening_sequence",
        "module:analytics_only_ingestion",
        "normalizes_connector_evidence",
        "core.shared_intelligence.platform_hardening.ingest_connector_payload",
    )
    for table in platform_hardening.get("source_tables", []):
        table_id = f"table:{table}"
        add_node(table_id, "sqlite_table", str(table))
        add_edge(
            "module:platform_hardening_sequence",
            table_id,
            "records_platform_hardening_authority",
            "core.shared_intelligence.platform_hardening.PLATFORM_HARDENING_TABLES",
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


def _source_tables() -> list[str]:
    tables = set(REQUIRED_SHARED_INTELLIGENCE_TABLES)
    tables.add("findings_current_status")
    tables.add("security_events")
    tables.update(
        {
            "ai_adapter_accounting_profiles",
            "ai_usage_operational_records",
            "token_usage_records",
            "reg_projects",
            # release_readiness_records: dropped migration 133
            "validation_results",
            "agent_registry_records",
            "agent_context_scope_policies",
            "github_repo_evaluations",
            "github_repo_adoption_decisions",
            "task_attribution_records",
            "skill_evaluation_runs",
            # policy_decision_records: dropped migration 133
            "connector_ingestion_runs",
            # github_repo_license_findings, github_repo_security_findings,
            # github_repo_dependency_findings, github_repo_integration_candidates,
            # github_repo_pattern_references, github_repo_attribution_records,
            # privacy_redaction_export_records, local_watch_schedule_records,
            # team_rollup_records, installer_distribution_checks,
            # demo_case_study_packets — dropped in migration 128 (dead tables).
        }
    )
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


# Private-path patterns the public atlas export must scrub. Kept in sync with
# `_PRIVATE_LEAK_PATTERNS` in core/shared_intelligence/contract_atlas_lifecycle.py
# — the lifecycle gate validates that no sanitized public atlas contains any of
# them. Each entry is (detector_regex, replacement_regex). The detector decides
# whether a string needs sanitization; the replacement_regex strips the
# offending fragment back to a token boundary. Detector and replacement differ
# because we want to detect even an unanchored hit (e.g. `.dream-studio/` mid-
# token) but replace the entire surrounding path token, not just the match.
# Token boundary for path sanitization. Must allow spaces — Windows user
# paths legitimately contain them (e.g. paths with spaces in usernames), and
# stopping at the first space would leave a tail fragment
# in the JSON-encoded output where the UNC-style leak pattern picks it up.
_SANITIZE_TOKEN_CHARS = r"[^\"'\n\r,}\]]"
_PRIVATE_PATH_RULES: tuple[tuple[re.Pattern[str], re.Pattern[str]], ...] = (
    (
        re.compile(r"[A-Za-z]:[\\/]"),
        re.compile(rf"[A-Za-z]:[\\/]{_SANITIZE_TOKEN_CHARS}*"),
    ),
    (
        re.compile(r"\\\\[^\\/\s]+[\\/]"),
        re.compile(rf"\\\\[^\\/\s]+[\\/]{_SANITIZE_TOKEN_CHARS}*"),
    ),
    (
        re.compile(r"/(?:home|Users|root|tmp|opt|var|mnt|srv)/[^/\s]+", re.IGNORECASE),
        re.compile(
            rf"/(?:home|Users|root|tmp|opt|var|mnt|srv)/{_SANITIZE_TOKEN_CHARS}*",
            re.IGNORECASE,
        ),
    ),
    (
        re.compile(r"\.dream-studio[\\/]", re.IGNORECASE),
        re.compile(
            rf"{_SANITIZE_TOKEN_CHARS}*\.dream-studio{_SANITIZE_TOKEN_CHARS}*", re.IGNORECASE
        ),
    ),
    (
        re.compile(r"Dream Studio Live Backups", re.IGNORECASE),
        re.compile(
            rf"{_SANITIZE_TOKEN_CHARS}*Dream Studio Live Backups{_SANITIZE_TOKEN_CHARS}*",
            re.IGNORECASE,
        ),
    ),
    (
        re.compile(r"\bAppData[\\/]", re.IGNORECASE),
        re.compile(rf"{_SANITIZE_TOKEN_CHARS}*\bAppData{_SANITIZE_TOKEN_CHARS}*", re.IGNORECASE),
    ),
)


def _contains_absolute_path(value: str) -> bool:
    return any(detector.search(value) for detector, _ in _PRIVATE_PATH_RULES)


def _sanitize_absolute_paths(value: str) -> str:
    sanitized = value
    for _, replacement in _PRIVATE_PATH_RULES:
        sanitized = replacement.sub("<sanitized-local-path>", sanitized)
    return sanitized
