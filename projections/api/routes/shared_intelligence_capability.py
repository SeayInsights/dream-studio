"""Shared-intelligence status, module contracts, expert workflows, capability
center, scoped agents, and GitHub repo intake routes.

WO-GF-API-ROUTES: split out of shared_intelligence.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Query

from core.analytics_ingestion import analytics_only_profile_status
from core.module_contracts import module_contracts
from core.shared_intelligence.capability_center import capability_center_summary
from core.shared_intelligence.expert_workflows import expert_workflow_catalog
from core.shared_intelligence.github_repo_intake import github_repo_intake_workflow
from core.shared_intelligence.scoped_agents import scoped_agent_registry, scoped_context_packet

from .shared_intelligence_router import router
from .shared_intelligence_shared import _dashboard_response, _split_query_list, _with_connection


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
                    "surface_id": "capability-center",
                    "api_path": "/api/shared-intelligence/capability-center",
                    "source_tables": [
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
                        # skill_evaluation_runs: dropped migration 131
                        # policy_decision_records: dropped migration 133
                        # connector_ingestion_runs: dropped migration 131
                        # privacy_redaction_export_records, local_watch_schedule_records,
                        # team_rollup_records, installer_distribution_checks,
                        # demo_case_study_packets: dropped migration 128
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
    """Return GitHub repo intake workflow definition.

    github_repo_evaluations and github_repo_adoption_decisions dropped migration 131;
    evaluation dashboard summary removed.
    """

    return github_repo_intake_workflow()
