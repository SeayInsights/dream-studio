"""Project details endpoint (health + readiness, separated).

WO-GF-API-ROUTES: split out of project_detail.py.
"""

from __future__ import annotations

import logging
from typing import Any

from core.production_readiness import production_readiness_dashboard_summary
from core.shared_intelligence.task_attribution import project_recent_attributed_work
from projections.api.lib.project_helpers import (
    get_db_connection,
    _module_runtime_fit,
    _recent_validation_state,
    _attention_detail_items,
    _finding_summary,
    _collect_evidence_refs,
    _project_detail_known_gaps,
    _project_detail_next_action,
)

from .project_detail_health import get_project_health
from .project_detail_router import router

logger = logging.getLogger(__name__)


@router.get("/{project_id}/details")
async def get_project_details(project_id: str) -> dict[str, Any]:
    """Return project detail view data with health and readiness separated."""

    health_payload = await get_project_health(project_id)
    conn = get_db_connection()
    try:
        production_readiness = production_readiness_dashboard_summary(conn, project_id=project_id)
        security_controls = health_payload["project"]["security_lifecycle_status"]
        from projections.api.routes.project_artifacts import get_project_dependencies

        dependency_graph = await get_project_dependencies(project_id, limit=200)
        # Phase 18.2 compliance: filesystem scan removed from critical popup path.
        # Stack framework data comes from business_projects.stack_json (L3, instant).
        # Detailed filesystem scan deferred — will surface via on-demand endpoint in a
        # future WO with proper event emission and L3 write-back.
        repo_stack = {
            "classification": "deferred",
            "reason": (
                "Detailed filesystem scan not on popup critical path. "
                "Framework data from business_projects.stack_json."
            ),
            "source_refs": [],
            "inferred_dependency_edges": [],
            "inferred_dependency_count": 0,
            "derived_view": True,
            "primary_authority": False,
        }
        # Use L3 stack evidence (from business_projects) for module_runtime_fit
        # instead of the filesystem-derived repo_stack.
        module_fit = _module_runtime_fit(
            health_payload["project"],
            health_payload["project"].get("stack_evidence") or repo_stack,
            dependency_graph,
        )
        validation_state = _recent_validation_state(conn, project_id)
        attention_detail = _attention_detail_items(conn, project_id)
        attributed_work = project_recent_attributed_work(conn, project_id, limit=10)
        prd_lifecycle = {"data_status": "retired", "model_name": "prd_cluster_retired_wo_f"}
        return {
            "project_id": project_id,
            "derived_view": True,
            "primary_authority": False,
            "project_identity": {
                "project_id": project_id,
                "project_name": health_payload["project"].get("project_name"),
                "project_path": health_payload["project"].get("project_path"),
                "project_authority_status": health_payload["project"].get(
                    "project_authority_status"
                ),
                "authority_source": health_payload["project"].get("authority_source"),
            },
            "prd_status": health_payload["project"].get("prd_status"),
            "prd_summary": (health_payload["project"].get("prd_status") or {})
            .get("authority", {})
            .get("summary"),
            "prd_lifecycle_authority": prd_lifecycle.get("data_status", "retired"),
            "prd_version": prd_lifecycle.get("prd_version"),
            "prd_confidence": prd_lifecycle.get("prd_confidence"),
            "in_flight_formalization_status": prd_lifecycle.get("in_flight_formalization_status"),
            "pending_prd_questions": prd_lifecycle.get("pending_prd_questions", []),
            "prd_assumptions": prd_lifecycle.get("prd_assumptions", []),
            "current_milestones": prd_lifecycle.get("current_milestones", []),
            "active_work_orders": prd_lifecycle.get("active_work_orders", []),
            "change_order_history": prd_lifecycle.get("change_order_history", []),
            "pending_change_orders": prd_lifecycle.get("pending_change_orders", []),
            "route_reconciliation_status": prd_lifecycle.get("route_reconciliation_status"),
            "planned_vs_actual_route_summary": prd_lifecycle.get("planned_vs_actual_route_summary"),
            "health_score": health_payload["health"],
            "readiness_score": production_readiness["readiness_score"],
            "readiness_control_coverage": production_readiness["control_summary"],
            "enterprise_security_controls": security_controls["applicability_summary"],
            "enterprise_security_control_status": {
                "controls": security_controls.get("applicability", []),
                "summary": security_controls["applicability_summary"],
                "source_framework": security_controls["source_framework"],
                "manual_review_required": security_controls["applicability_summary"].get(
                    "manual_review_required", 0
                ),
                "unknown": security_controls["applicability_summary"].get("unknown", 0),
                "derived_view": True,
                "primary_authority": False,
            },
            "production_readiness_controls": production_readiness["controls"],
            "findings_by_severity_status": _finding_summary(
                production_readiness["findings"],
                health_payload.get("project", {})
                .get("security_package_status", {})
                .get("open_findings", 0),
            ),
            "not_applicable_controls": [
                item
                for item in production_readiness["controls"]
                if item.get("status") == "not_applicable"
            ],
            "manual_review_controls": [
                item
                for item in production_readiness["controls"]
                if item.get("status") == "manual_review"
            ],
            "remediation_work_orders": production_readiness["remediation_work_orders"],
            "evidence_refs": _collect_evidence_refs(production_readiness["controls"]),
            "release_blockers": [
                item for item in production_readiness["controls"] if item.get("blocking")
            ],
            "compliance_legal_review_flags": production_readiness["compliance_review_flags"],
            "stack_status": health_payload["project"].get("stack_evidence"),
            "stack_evidence": {
                "registry_stack": health_payload["project"].get("stack_evidence"),
                "repo_scan": repo_stack,
                "source_refs": sorted(
                    set(
                        (repo_stack.get("source_refs") or [])
                        + (
                            health_payload["project"]
                            .get("stack_evidence", {})
                            .get("config_files", [])
                        )
                    )
                ),
                "secret_contents_read": False,
                "repo_mutation_authorized": False,
                "derived_view": True,
                "primary_authority": False,
            },
            "confirmed_dependencies": {
                "nodes": dependency_graph.get("nodes", []),
                "edges": dependency_graph.get("edges", []),
                "node_count": dependency_graph.get("node_count", 0),
                "edge_count": dependency_graph.get("edge_count", 0),
                "rendered_by_default": True,
                "source_status": dependency_graph.get("source_status"),
                "knowledge_graph_status": dependency_graph.get("knowledge_graph_status"),
            },
            "inferred_or_unverified_dependencies": {
                "edges": dependency_graph.get("inferred_edges", [])
                + repo_stack.get("inferred_dependency_edges", []),
                "edge_count": dependency_graph.get("inferred_edge_count", 0)
                + repo_stack.get("inferred_dependency_count", 0),
                "rendered_by_default": False,
                "reason": "Manifest-derived or unverified dependencies are labeled separately and hidden from the default confirmed graph.",
            },
            "dependency_drilldown": {
                "project_to_stack_component": "/api/v1/projects/{project_id}/details",
                "stack_component_to_dependency": "/api/v1/projects/{project_id}/dependencies",
                "dependency_to_evidence": "edge.source_refs and node.evidence_refs",
                "confirmed_edges_only_by_default": True,
            },
            "dependency_status": health_payload["project"].get("dependency_source_status"),
            "module_runtime_profile_fit": module_fit,
            "security_status": health_payload["project"].get("security_package_status"),
            "validation_state": {
                "summary": health_payload["project"].get("telemetry_status"),
                "recent": validation_state,
            },
            "recent_attributed_work": attributed_work,
            "work_order_status": health_payload["project"].get("work_order_status"),
            "attention_items": attention_detail,
            "known_gaps": _project_detail_known_gaps(health_payload, production_readiness),
            "current_next_action": _project_detail_next_action(
                health_payload, production_readiness
            ),
            "source_status": {
                "classification": (
                    "fresh" if production_readiness.get("assessment_id") else "empty by design"
                ),
                "source_tables": production_readiness.get("source_tables", []),
                "derived_view": True,
                "primary_authority": False,
            },
        }
    finally:
        conn.close()
