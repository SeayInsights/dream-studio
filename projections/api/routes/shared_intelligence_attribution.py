"""Task attribution and Contract Atlas routes.

WO-GF-API-ROUTES: split out of shared_intelligence.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Query

from core.shared_intelligence.contract_atlas import build_contract_atlas
from core.shared_intelligence.contract_atlas_lifecycle import (
    build_contract_atlas_freshness_manifest,
)
from core.shared_intelligence.contract_registry import change_impact_report
from core.shared_intelligence.maturity_ledger import maturity_ledger
from core.shared_intelligence.task_attribution import (
    task_attribution_summary,
    work_order_task_attribution,
)

from .shared_intelligence_router import router
from .shared_intelligence_shared import _dashboard_response, _split_query_list, _with_connection


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
