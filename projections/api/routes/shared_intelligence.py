"""Shared-intelligence authority API routes.

These routes expose dashboard-consumable read models over SQLite authority.
They deliberately do not write adapter configs, persist generated context
packets, mutate routing policy, or authorize execution.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.analytics_ingestion import analytics_only_profile_status
from core.career_ops import career_ops_dashboard_summary
from core.config.database import get_connection
from core.installed_runtime import adapter_router_status
from core.module_contracts import module_contracts
from core.production_readiness import (
    build_secure_production_readiness_gate,
    production_readiness_control_catalog,
    production_readiness_dashboard_summary,
)
from core.security.lifecycle import build_security_lifecycle_gate
from core.shared_intelligence.adapter_config_projection import (
    adapter_config_projection_report,
)
from core.shared_intelligence.adapter_staleness import adapter_staleness_report
from core.shared_intelligence.capability_routing import (
    capability_route_summary,
    recommend_capability_route,
)
from core.shared_intelligence.capability_center import capability_center_summary
from core.shared_intelligence.contract_atlas import build_contract_atlas
from core.shared_intelligence.contract_atlas_lifecycle import (
    build_contract_atlas_freshness_manifest,
)
from core.shared_intelligence.contract_registry import change_impact_report
from core.shared_intelligence.context_packets import generate_shared_context_packet
from core.shared_intelligence.dashboard_views import learning_hardening_dashboard_view
from core.shared_intelligence.expert_workflows import expert_workflow_catalog
from core.shared_intelligence.github_repo_intake import github_repo_intake_dashboard_summary
from core.shared_intelligence.maturity_ledger import maturity_ledger
from core.shared_intelligence.model_registry import (
    model_provider_capability_matrix,
    model_provider_registry_summary,
)
from core.shared_intelligence.platform_hardening import (
    connector_ingestion_framework_status,
    demo_case_study_system_status,
    evaluate_policy_decision,
    installer_distribution_status,
    local_watch_scheduler_status,
    platform_hardening_summary,
    privacy_redaction_status,
    skill_evaluation_harness_status,
    team_pilot_rollup_status,
)
from core.shared_intelligence.prd_authority import project_prd_authority_summary
from core.shared_intelligence.scoped_agents import scoped_agent_registry, scoped_context_packet
from core.shared_intelligence.task_attribution import (
    task_attribution_summary,
    work_order_task_attribution,
)
from core.shared_intelligence.usage_accounting import adapter_usage_accounting_summary

router = APIRouter()


@router.get("/status")
async def get_shared_intelligence_status(
    project_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return the available shared-intelligence dashboard surfaces."""

    return _dashboard_response(
        {
            "model_name": "shared_intelligence_runtime_surface_status",
            "project_id": project_id,
            "surfaces": [
                {
                    "surface_id": "analytics-only",
                    "api_path": "/api/shared-intelligence/analytics-only",
                    "source_tables": [
                        "reg_projects",
                        "validation_results",
                        "findings",
                        "token_usage_records",
                        "ai_usage_operational_records",
                        "pi_dependencies",
                        "prd_documents",
                        "production_readiness_assessment_runs",
                    ],
                },
                {
                    "surface_id": "learning-dashboard",
                    "api_path": "/api/shared-intelligence/learning-dashboard",
                    "source_tables": [
                        "learning_event_records",
                        "hardening_candidate_records",
                        "adapter_result_records",
                        "model_provider_profiles",
                    ],
                },
                {
                    "surface_id": "adapter-projections",
                    "api_path": "/api/shared-intelligence/adapters/projections",
                    "source_tables": ["adapter_authority_profiles"],
                },
                {
                    "surface_id": "adapter-staleness",
                    "api_path": "/api/shared-intelligence/adapters/staleness",
                    "source_tables": ["adapter_authority_profiles"],
                },
                {
                    "surface_id": "context-packet-preview",
                    "api_path": "/api/shared-intelligence/context-packets/{adapter_id}",
                    "source_tables": [
                        "shared_context_packets",
                        "learning_event_records",
                        "adapter_authority_profiles",
                    ],
                },
                {
                    "surface_id": "capability-routes",
                    "api_path": "/api/shared-intelligence/capability-routes",
                    "source_tables": ["capability_route_records"],
                },
                {
                    "surface_id": "model-providers",
                    "api_path": "/api/shared-intelligence/model-providers",
                    "source_tables": ["model_provider_profiles"],
                },
                {
                    "surface_id": "ai-usage-accounting",
                    "api_path": "/api/shared-intelligence/ai-usage-accounting",
                    "source_tables": [
                        "ai_adapter_accounting_profiles",
                        "ai_usage_operational_records",
                        "token_usage_records",
                    ],
                },
                {
                    "surface_id": "task-attribution",
                    "api_path": "/api/shared-intelligence/task-attribution",
                    "source_tables": [
                        "task_attribution_records",
                        "ai_usage_operational_records",
                        "adapter_result_records",
                        "validation_results",
                    ],
                },
                {
                    "surface_id": "contract-atlas",
                    "api_path": "/api/shared-intelligence/contract-atlas",
                    "source_tables": [
                        "adapter_authority_profiles",
                        "telemetry_module_registry",
                        "execution_events",
                    ],
                },
                {
                    "surface_id": "module-contracts",
                    "api_path": "/api/shared-intelligence/module-contracts",
                    "source_tables": [],
                },
                {
                    "surface_id": "maturity-ledger",
                    "api_path": "/api/shared-intelligence/contract-atlas/maturity-ledger",
                    "source_tables": [],
                },
                {
                    "surface_id": "contract-docs-drift",
                    "api_path": "/api/shared-intelligence/contract-atlas/docs-drift",
                    "source_tables": [],
                },
                {
                    "surface_id": "contract-atlas-freshness",
                    "api_path": "/api/shared-intelligence/contract-atlas/freshness",
                    "source_tables": ["adapter_authority_profiles"],
                },
                {
                    "surface_id": "adapter-router",
                    "api_path": "/api/shared-intelligence/adapter-router",
                    "source_tables": [
                        "adapter_authority_profiles",
                        "shared_context_packets",
                        "adapter_result_records",
                        "capability_route_records",
                    ],
                },
                {
                    "surface_id": "security-lifecycle",
                    "api_path": "/api/shared-intelligence/security-lifecycle",
                    "source_tables": ["findings"],
                },
                {
                    "surface_id": "production-readiness",
                    "api_path": "/api/shared-intelligence/production-readiness",
                    "source_tables": [
                        "production_readiness_assessment_runs",
                        "production_readiness_control_results",
                        "project_readiness_scorecards",
                    ],
                },
                {
                    "surface_id": "expert-workflows",
                    "api_path": "/api/shared-intelligence/expert-workflows",
                    "source_tables": [],
                },
                {
                    "surface_id": "career-ops",
                    "api_path": "/api/shared-intelligence/career-ops",
                    "source_tables": [
                        "career_profiles",
                        "career_applications",
                        "career_scorecards",
                    ],
                },
                {
                    "surface_id": "capability-center",
                    "api_path": "/api/shared-intelligence/capability-center",
                    "source_tables": [
                        "capability_center_records",
                        "skill_invocations",
                        "workflow_invocations",
                        "agent_invocations",
                        "hardening_candidate_records",
                    ],
                },
                {
                    "surface_id": "scoped-agents",
                    "api_path": "/api/shared-intelligence/agents/registry",
                    "source_tables": [
                        "agent_registry_records",
                        "agent_context_scope_policies",
                        "workflow_agent_skill_mappings",
                        "agent_result_records",
                    ],
                },
                {
                    "surface_id": "github-repo-intake",
                    "api_path": "/api/shared-intelligence/github-repo-intake",
                    "source_tables": [
                        "github_repo_evaluations",
                        "github_repo_license_findings",
                        "github_repo_security_findings",
                        "github_repo_dependency_findings",
                    ],
                },
                {
                    "surface_id": "platform-hardening",
                    "api_path": "/api/shared-intelligence/platform-hardening",
                    "source_tables": [
                        "skill_evaluation_runs",
                        "policy_decision_records",
                        "connector_ingestion_runs",
                        "privacy_redaction_export_records",
                        "local_watch_schedule_records",
                        "team_rollup_records",
                        "installer_distribution_checks",
                        "demo_case_study_packets",
                    ],
                },
                {
                    "surface_id": "prd-authority-lifecycle",
                    "api_path": "/api/shared-intelligence/prd-authority",
                    "source_tables": [
                        "project_intake_records",
                        "project_intake_questions",
                        "project_assumption_records",
                        "prd_version_records",
                        "project_milestone_records",
                        "project_work_order_authority_records",
                        "project_change_order_records",
                        "prd_route_reconciliation_records",
                    ],
                },
            ],
            "source_tables": [
                "reg_projects",
                "validation_results",
                "findings",
                "learning_event_records",
                "hardening_candidate_records",
                "adapter_authority_profiles",
                "model_provider_profiles",
                "shared_context_packets",
                "adapter_result_records",
                "capability_route_records",
                "ai_adapter_accounting_profiles",
                "ai_usage_operational_records",
                "token_usage_records",
                "task_attribution_records",
                "career_profiles",
                "career_applications",
                "career_scorecards",
                "capability_center_records",
                "agent_registry_records",
                "github_repo_evaluations",
                "skill_evaluation_runs",
                "policy_decision_records",
                "connector_ingestion_runs",
                "privacy_redaction_export_records",
                "local_watch_schedule_records",
                "team_rollup_records",
                "installer_distribution_checks",
                "demo_case_study_packets",
                "project_intake_records",
                "prd_version_records",
                "project_milestone_records",
                "project_change_order_records",
                "prd_route_reconciliation_records",
            ],
            "empty_state": "Shared-intelligence routes are available; individual surfaces report their own empty states.",
        }
    )


@router.get("/analytics-only")
async def get_analytics_only_status() -> dict[str, Any]:
    """Return analytics-only profile and ingestion contract status."""

    return _with_connection(analytics_only_profile_status)


@router.get("/module-contracts")
async def get_module_contracts() -> dict[str, Any]:
    """Return major module boundary contracts without runtime execution."""

    return _dashboard_response(module_contracts())


@router.get("/expert-workflows")
async def get_expert_workflow_catalog(
    project_id: str | None = Query(default="dream-studio"),
) -> dict[str, Any]:
    """Return expert workflow definitions, overlap decisions, and rubrics."""

    return _dashboard_response(expert_workflow_catalog(project_id=project_id))


@router.get("/career-ops")
async def get_career_ops_status() -> dict[str, Any]:
    """Return private opt-in Career Ops status and dashboard summary."""

    return _with_connection(career_ops_dashboard_summary)


@router.get("/capability-center")
async def get_capability_center(
    project_id: str | None = Query(default="dream-studio"),
) -> dict[str, Any]:
    """Return Capability Center skills/workflows/agents/controls/evaluations sections."""

    repo_root = Path(__file__).resolve().parents[3]
    return _with_connection(
        lambda conn: capability_center_summary(
            conn,
            project_id=project_id,
            repo_root=repo_root,
        )
    )


@router.get("/agents/registry")
async def get_scoped_agent_registry() -> dict[str, Any]:
    """Return scoped agent declarations without authorizing execution."""

    return _with_connection(scoped_agent_registry)


@router.get("/agents/context-packet")
async def preview_scoped_agent_context_packet(
    agent_id: str = Query(default="implementation_worker"),
    task_summary: str = Query(default="Scoped Dream Studio task"),
    project_id: str | None = Query(default="dream-studio"),
    requested_data_classes: str | None = Query(default=None),
    career_scope_approved: bool = Query(default=False),
) -> dict[str, Any]:
    """Preview a scoped worker context packet without executing an agent."""

    data_classes = _split_query_list(requested_data_classes)
    return _with_connection(
        lambda conn: scoped_context_packet(
            conn,
            agent_id=agent_id,
            task_summary=task_summary,
            project_id=project_id,
            requested_data_classes=data_classes,
            career_scope_approved=career_scope_approved,
        )
    )


@router.get("/github-repo-intake")
async def get_github_repo_intake() -> dict[str, Any]:
    """Return GitHub repo intake workflow and persisted evaluation summary."""

    return _with_connection(github_repo_intake_dashboard_summary)


@router.get("/platform-hardening")
async def get_platform_hardening() -> dict[str, Any]:
    """Return platform-hardening status across eval, policy, privacy, install, and demo systems."""

    return _with_connection(platform_hardening_summary)


@router.get("/platform-hardening/skill-evaluations")
async def get_skill_evaluation_harness() -> dict[str, Any]:
    """Return skill/workflow evaluation harness status and contracts."""

    return _with_connection(skill_evaluation_harness_status)


@router.get("/platform-hardening/policy-decision")
async def preview_policy_decision(
    actor: str = Query(default="operator"),
    action: str = Query(default="read_only_action"),
    target: str | None = Query(default=None),
    approved: bool = Query(default=False),
) -> dict[str, Any]:
    """Preview a policy decision without persisting or authorizing execution."""

    return _dashboard_response(
        {
            "model_name": "dream_studio_policy_decision_preview",
            **evaluate_policy_decision(
                actor=actor,
                action=action,
                target=target,
                scope={},
                approved=approved,
            ),
        }
    )


@router.get("/platform-hardening/connectors")
async def get_connector_ingestion_framework() -> dict[str, Any]:
    """Return engineering connector ingestion contracts."""

    return _with_connection(connector_ingestion_framework_status)


@router.get("/platform-hardening/privacy")
async def get_privacy_redaction_status() -> dict[str, Any]:
    """Return privacy, redaction, and public-export boundary status."""

    return _with_connection(privacy_redaction_status)


@router.get("/platform-hardening/watchers")
async def get_local_watch_scheduler_status() -> dict[str, Any]:
    """Return opt-in local watch/scheduled validation declarations."""

    return _with_connection(local_watch_scheduler_status)


@router.get("/platform-hardening/team-rollup")
async def get_team_pilot_rollup_status() -> dict[str, Any]:
    """Return sanitized team-pilot rollup status."""

    return _with_connection(team_pilot_rollup_status)


@router.get("/platform-hardening/installer")
async def get_installer_distribution_status() -> dict[str, Any]:
    """Return installer/distribution hardening status."""

    return _with_connection(installer_distribution_status)


@router.get("/platform-hardening/demo")
async def get_demo_case_study_system_status() -> dict[str, Any]:
    """Return sanitized demo/case-study system status."""

    return _with_connection(demo_case_study_system_status)


@router.get("/prd-authority")
async def get_prd_authority_lifecycle(
    project_id: str | None = Query(default="dream-studio"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Return PRD intake, lifecycle, change-order, milestone, and route authority."""

    return _with_connection(
        lambda conn: project_prd_authority_summary(
            conn,
            project_id=project_id,
            limit=limit,
        )
    )


@router.get("/adapter-router")
async def get_adapter_router_status(
    project_id: str | None = Query(default="dream-studio"),
) -> dict[str, Any]:
    """Return installed adapter/router state without authorizing execution."""

    repo_root = Path(__file__).resolve().parents[3]
    return _with_connection(
        lambda conn: adapter_router_status(
            conn,
            source_root=repo_root,
            project_id=project_id,
        )
    )


@router.get("/security-lifecycle")
async def get_security_lifecycle_status(
    project_id: str | None = Query(default="dream-studio"),
    lifecycle_event: str = Query(default="code_change"),
    changed_files: str | None = Query(default=None),
) -> dict[str, Any]:
    """Preview the security-by-default lifecycle gate without executing scans."""

    repo_root = Path(__file__).resolve().parents[3]
    files = _split_query_list(changed_files)
    return _with_connection(
        lambda conn: build_security_lifecycle_gate(
            conn=conn,
            repo_root=repo_root,
            project_id=project_id or "dream-studio",
            lifecycle_event=lifecycle_event,
            changed_files=files,
        )
    )


@router.get("/production-readiness")
async def get_production_readiness_status(
    project_id: str | None = Query(default="dream-studio"),
    lifecycle_event: str = Query(default="code_change"),
    changed_files: str | None = Query(default=None),
    persisted_summary: bool = Query(default=False),
) -> dict[str, Any]:
    """Preview or read production readiness without executing checks."""

    if persisted_summary:
        return _with_connection(
            lambda conn: production_readiness_dashboard_summary(
                conn,
                project_id=project_id or "dream-studio",
            )
        )
    repo_root = Path(__file__).resolve().parents[3]
    files = _split_query_list(changed_files)
    return build_secure_production_readiness_gate(
        repo_root=repo_root,
        project_id=project_id or "dream-studio",
        lifecycle_event=lifecycle_event,
        changed_files=files,
        persist=False,
    )


@router.get("/production-readiness/controls")
async def get_production_readiness_controls() -> dict[str, Any]:
    """Return the reusable production readiness control catalog."""

    repo_root = Path(__file__).resolve().parents[3]
    return production_readiness_control_catalog(repo_root=repo_root)


@router.get("/learning-dashboard")
async def get_learning_dashboard(project_id: str | None = Query(default=None)) -> dict[str, Any]:
    """Return learning, hardening, skill-health, and feedback dashboard sections."""

    return _with_connection(
        lambda conn: learning_hardening_dashboard_view(conn, project_id=project_id)
    )


@router.get("/adapters/projections")
async def get_adapter_projection_report(
    project_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return adapter config projections without writing adapter config files."""

    return _with_connection(
        lambda conn: adapter_config_projection_report(conn, project_id=project_id)
    )


@router.get("/adapters/staleness")
async def get_adapter_staleness_report(
    project_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return adapter projection staleness using the repo root as config root."""

    repo_root = Path(__file__).resolve().parents[3]
    return _with_connection(
        lambda conn: adapter_staleness_report(
            conn,
            config_root=repo_root,
            project_id=project_id,
        )
    )


@router.get("/context-packets/{adapter_id}")
async def preview_context_packet(
    adapter_id: str,
    project_id: str | None = Query(default=None),
    milestone_id: str | None = Query(default=None),
    task_id: str | None = Query(default=None),
    packet_type: str = Query(default="resume"),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Preview an adapter context packet without persisting it."""

    packet_id = "dry-run-" + "-".join(
        item for item in (adapter_id, project_id or "global", packet_type) if item
    )
    return _with_connection(
        lambda conn: generate_shared_context_packet(
            conn,
            packet_id=packet_id,
            adapter_id=adapter_id,
            packet_type=packet_type,
            project_id=project_id,
            milestone_id=milestone_id,
            task_id=task_id,
            limit=limit,
            persist=False,
        )
    )


@router.get("/capability-routes")
async def get_capability_routes(
    project_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Return recorded capability-route recommendations."""

    return _with_connection(
        lambda conn: capability_route_summary(conn, project_id=project_id, limit=limit)
    )


@router.get("/capability-routes/recommendation")
async def preview_capability_route(
    task_class: str = Query(default="code"),
    required_capabilities: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    risk_level: str = Query(default="medium"),
    cost_sensitivity: str = Query(default="medium"),
    min_context_tokens: int | None = Query(default=None, ge=1),
) -> dict[str, Any]:
    """Preview a capability route without persisting or authorizing execution."""

    capabilities = [
        item.strip() for item in (required_capabilities or "").split(",") if item.strip()
    ]
    route_id = f"dry-run-{task_class}-{project_id or 'global'}"
    return _with_connection(
        lambda conn: recommend_capability_route(
            conn,
            capability_route_id=route_id,
            task_class=task_class,
            required_capabilities=capabilities,
            project_id=project_id,
            risk_level=risk_level,
            cost_sensitivity=cost_sensitivity,
            min_context_tokens=min_context_tokens,
            persist=False,
        )
    )


@router.get("/model-providers")
async def get_model_provider_summary() -> dict[str, Any]:
    """Return model/provider registry summary from recorded SQLite facts."""

    return _with_connection(model_provider_registry_summary)


@router.get("/model-providers/capability-matrix")
async def get_model_provider_capability_matrix(
    required_capabilities: str | None = Query(default=None),
    min_context_tokens: int | None = Query(default=None, ge=1),
    provider: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return recorded model/provider profiles matching requested capabilities."""

    capabilities = [
        item.strip() for item in (required_capabilities or "").split(",") if item.strip()
    ]
    return _with_connection(
        lambda conn: model_provider_capability_matrix(
            conn,
            required_capabilities=capabilities,
            min_context_tokens=min_context_tokens,
            provider=provider,
        )
    )


@router.get("/ai-usage-accounting")
async def get_ai_usage_accounting(
    project_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return honest AI adapter usage and operational value telemetry."""

    return _with_connection(
        lambda conn: adapter_usage_accounting_summary(conn, project_id=project_id)
    )


@router.get("/task-attribution")
async def get_task_attribution(
    project_id: str | None = Query(default=None),
    work_order_id: str | None = Query(default=None),
    adapter_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Return AI/adapter task attribution and execution outcome drilldowns."""

    return _with_connection(
        lambda conn: task_attribution_summary(
            conn,
            project_id=project_id,
            work_order_id=work_order_id,
            adapter_id=adapter_id,
            limit=limit,
        )
    )


@router.get("/task-attribution/work-orders/{work_order_id}")
async def get_work_order_task_attribution(
    work_order_id: str,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Return Work Order-specific adapter/skill/workflow attribution."""

    return _with_connection(
        lambda conn: work_order_task_attribution(conn, work_order_id, limit=limit)
    )


@router.get("/contract-atlas")
async def get_contract_atlas(
    project_id: str | None = Query(default=None),
    export_scope: str = Query(default="private", pattern="^(private|public)$"),
) -> dict[str, Any]:
    """Return the private-by-default Contract Atlas derived read model."""

    repo_root = Path(__file__).resolve().parents[3]
    return _with_connection(
        lambda conn: build_contract_atlas(
            conn,
            repo_root=repo_root,
            project_id=project_id,
            export_scope=export_scope,
        )
    )


@router.get("/contract-atlas/maturity-ledger")
async def get_contract_atlas_maturity_ledger(
    project_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return the current evidence-backed maturity ledger."""

    return _dashboard_response(maturity_ledger(project_id=project_id))


@router.get("/contract-atlas/docs-drift")
async def get_contract_atlas_docs_drift(
    changed_files: str | None = Query(default=None),
    reviewed_no_change_domains: str | None = Query(default=None),
) -> dict[str, Any]:
    """Preview contract/docs drift status for a comma-separated changed-file list."""

    files = _split_query_list(changed_files)
    reviewed = _split_query_list(reviewed_no_change_domains)
    return _dashboard_response(change_impact_report(files, reviewed_no_change_domains=reviewed))


@router.get("/contract-atlas/freshness")
async def get_contract_atlas_freshness(
    project_id: str | None = Query(default="dream-studio"),
    changed_files: str | None = Query(default=None),
    reviewed_no_change_domains: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return Contract Atlas lifecycle freshness without writing exports."""

    repo_root = Path(__file__).resolve().parents[3]
    files = _split_query_list(changed_files)
    reviewed = _split_query_list(reviewed_no_change_domains)
    return _with_connection(
        lambda conn: build_contract_atlas_freshness_manifest(
            conn,
            repo_root=repo_root,
            project_id=project_id or "dream-studio",
            changed_files=files,
            reviewed_no_change_domains=reviewed,
        )
    )


def _with_connection(func: Any) -> dict[str, Any]:
    try:
        with closing(get_connection(read_only=True)) as conn:
            payload = func(conn)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _dashboard_response(payload)


def _dashboard_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "dashboard_consumable": True,
        "execution_authorized": False,
        "policy_mutation_authorized": False,
        "authority_note": (
            "Shared-intelligence API routes expose derived views over SQLite authority; "
            "they do not write adapter configs, mutate routing policy, or authorize execution."
        ),
    }


def _split_query_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    normalized = raw.replace(";", ",").replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]
