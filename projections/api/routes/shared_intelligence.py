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

from core.config.database import get_connection
from core.shared_intelligence.adapter_config_projection import (
    adapter_config_projection_report,
)
from core.shared_intelligence.adapter_staleness import adapter_staleness_report
from core.shared_intelligence.capability_routing import (
    capability_route_summary,
    recommend_capability_route,
)
from core.shared_intelligence.contract_atlas import build_contract_atlas
from core.shared_intelligence.contract_registry import change_impact_report
from core.shared_intelligence.context_packets import generate_shared_context_packet
from core.shared_intelligence.dashboard_views import learning_hardening_dashboard_view
from core.shared_intelligence.maturity_ledger import maturity_ledger
from core.shared_intelligence.model_registry import (
    model_provider_capability_matrix,
    model_provider_registry_summary,
)

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
                    "surface_id": "contract-atlas",
                    "api_path": "/api/shared-intelligence/contract-atlas",
                    "source_tables": [
                        "adapter_authority_profiles",
                        "telemetry_module_registry",
                        "execution_events",
                    ],
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
            ],
            "source_tables": [
                "learning_event_records",
                "hardening_candidate_records",
                "adapter_authority_profiles",
                "model_provider_profiles",
                "shared_context_packets",
                "adapter_result_records",
                "capability_route_records",
            ],
            "empty_state": "Shared-intelligence routes are available; individual surfaces report their own empty states.",
        }
    )


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
