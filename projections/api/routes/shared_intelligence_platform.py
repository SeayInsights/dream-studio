"""Platform-hardening, adapter-router, security-lifecycle, and production
readiness routes.

WO-GF-API-ROUTES: split out of shared_intelligence.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Query

from core.installed_runtime import adapter_router_status
from core.production_readiness import (
    build_secure_production_readiness_gate,
    production_readiness_control_catalog,
    production_readiness_dashboard_summary,
)
from core.security.lifecycle import build_security_lifecycle_gate
from core.shared_intelligence.platform_hardening import (
    connector_ingestion_framework_status,
    evaluate_policy_decision,
    platform_hardening_summary,
    skill_evaluation_harness_status,
    # demo_case_study_system_status, installer_distribution_status,
    # local_watch_scheduler_status, privacy_redaction_status,
    # team_pilot_rollup_status removed — backing tables dropped in migration 128.
)

from .shared_intelligence_router import router
from .shared_intelligence_shared import _dashboard_response, _split_query_list, _with_connection


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


# /platform-hardening/privacy, /watchers, /team-rollup, /installer, /demo
# endpoints removed — backing tables (privacy_redaction_export_records,
# local_watch_schedule_records, team_rollup_records, installer_distribution_checks,
# demo_case_study_packets) dropped in migration 128.


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
