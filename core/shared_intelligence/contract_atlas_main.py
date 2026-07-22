"""Contract Atlas assembly — build_contract_atlas.

WO-GF-SHARED-INTEL-SPLIT: extracted from contract_atlas.py. Composes the
section/graph/scorecard/boundary/validate siblings plus ~20 cross-module
read-model builders into the full Contract Atlas payload.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, UTC
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
from core.shared_intelligence.contract_registry import contract_registry
from core.production_readiness import (
    build_secure_production_readiness_gate,
    production_readiness_control_catalog,
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

from .contract_atlas_boundary import (
    _active_adapter_execution_validation,
    _boundary_violation_report,
)
from .contract_atlas_graph import _confirmed_dependency_graph
from .contract_atlas_scorecard import _github_cicd_profile, _maturity_scorecard
from .contract_atlas_sections import (
    _adapter_projection_contracts,
    _analytics_only_profile,
    _dashboard_private_export_boundaries,
    _docs_freshness_tracking,
    _interface_contracts,
    _layer_contracts,
    _runtime_profiles,
    _source_tables,
    _whole_system_contract,
)
from .contract_atlas_validate import sanitize_contract_atlas_for_public_export

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
        "generated_at": datetime.now(UTC).isoformat(),
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
