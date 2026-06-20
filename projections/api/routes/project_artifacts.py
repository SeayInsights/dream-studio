"""Project PRDs and dependencies endpoints."""

import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Query

from projections.api.routes.sqlite_schema import object_exists, table_columns
from projections.api.lib.project_helpers import (
    get_db_connection,
    _empty_project_source_status,
    _build_prd_authority_status,
    _project_row_for_authority,
    _component_index,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{project_id}/prds")
async def get_project_prds(project_id: str) -> Dict[str, Any]:
    """
    Get all PRDs associated with a specific project.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if not object_exists(conn, "prd_documents"):
            return {
                "project_id": project_id,
                "prds": [],
                "count": 0,
                "source_status": _empty_project_source_status(
                    ["prd_documents"],
                    reason="PRD documents table is not present in this DB snapshot.",
                ),
            }

        prd_columns = table_columns(conn, "prd_documents")
        file_path_expr = "file_path" if "file_path" in prd_columns else "NULL AS file_path"
        approved_at_expr = "approved_at" if "approved_at" in prd_columns else "NULL AS approved_at"
        completed_at_expr = (
            "completed_at" if "completed_at" in prd_columns else "NULL AS completed_at"
        )
        total_tasks_expr = "total_tasks" if "total_tasks" in prd_columns else "0 AS total_tasks"
        completed_tasks_expr = (
            "completed_tasks" if "completed_tasks" in prd_columns else "0 AS completed_tasks"
        )
        pct_complete_expr = (
            "ROUND(100.0 * completed_tasks / NULLIF(total_tasks, 0), 1) AS pct_complete"
            if {"completed_tasks", "total_tasks"}.issubset(prd_columns)
            else "NULL AS pct_complete"
        )

        query = f"""
        SELECT
            prd_id,
            title,
            status,
            {file_path_expr},
            created_at,
            {approved_at_expr},
            {completed_at_expr},
            {total_tasks_expr},
            {completed_tasks_expr},
            {pct_complete_expr}
        FROM prd_documents
        WHERE project_id = ?
        ORDER BY created_at DESC
        """

        rows = cursor.execute(query, (project_id,)).fetchall()
        prds = [dict(row) for row in rows]
        project = _project_row_for_authority(conn, project_id)
        if project:
            project.update(
                {
                    "prd_count": len(prds),
                    "latest_prd_status": prds[0].get("status") if prds else None,
                    "latest_prd_title": prds[0].get("title") if prds else None,
                    "latest_prd_file_path": prds[0].get("file_path") if prds else None,
                    "latest_prd_created_at": prds[0].get("created_at") if prds else None,
                }
            )
            prd_authority = _build_prd_authority_status(project)
        else:
            prd_authority = {
                "status": "manual_review_required",
                "reason": "Project authority row is missing for this PRD request.",
                "manual_review_flags": ["project_authority_missing"],
            }

        return {
            "project_id": project_id,
            "prds": prds,
            "count": len(prds),
            "prd_authority": prd_authority,
            "source_status": {
                "classification": "fresh" if prds else "honest_empty_state",
                "reason": (
                    "PRD records are linked to current project authority."
                    if prds
                    else "No PRD authority rows are linked; draft_generated/manual review status is exposed instead."
                ),
                "source_tables": ["prd_documents", "business_projects"],
                "derived_view": True,
                "primary_authority": False,
            },
        }

    except Exception as e:
        logger.error(f"Error getting project PRDs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{project_id}/dependencies")
async def get_project_dependencies(
    project_id: str, limit: int = Query(100, ge=1, le=500)
) -> Dict[str, Any]:
    """
    Get dependency graph for a specific project.
    Returns nodes and edges for visualization.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if not object_exists(conn, "pi_dependencies"):
            return {
                "project_id": project_id,
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "type_counts": {},
                "source_status": _empty_project_source_status(
                    ["pi_dependencies"],
                    reason="Project dependency table is not present in this DB snapshot.",
                ),
            }

        dependency_columns = table_columns(conn, "pi_dependencies")
        if not {"from_component", "to_component"}.issubset(dependency_columns):
            return {
                "project_id": project_id,
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "type_counts": {},
                "source_status": _empty_project_source_status(
                    ["pi_dependencies.from_component", "pi_dependencies.to_component"],
                    reason="Project dependency table exists but lacks the required endpoint columns.",
                ),
            }

        dependency_type_expr = (
            "dependency_type"
            if "dependency_type" in dependency_columns
            else "'confirmed' AS dependency_type"
        )
        strength_expr = "strength" if "strength" in dependency_columns else "1.0 AS strength"
        dependency_id_expr = (
            "dependency_id"
            if "dependency_id" in dependency_columns
            else "from_component || '->' || to_component AS dependency_id"
        )

        # Get dependencies
        deps_query = """
        SELECT
            {dependency_id_expr},
            from_component,
            to_component,
            {dependency_type_expr},
            {strength_expr}
        FROM pi_dependencies
        WHERE project_id = ?
        LIMIT ?
        """.format(
            dependency_id_expr=dependency_id_expr,
            dependency_type_expr=dependency_type_expr,
            strength_expr=strength_expr,
        )

        rows = cursor.execute(deps_query, (project_id, limit)).fetchall()
        components = _component_index(conn, project_id)

        # Build nodes and edges
        nodes = {}
        edges = []

        for row in rows:
            dependency_id = row["dependency_id"]
            from_comp = row["from_component"]
            to_comp = row["to_component"]
            dep_type = row["dependency_type"]
            strength = row["strength"] or 1.0

            # Extract simple names
            from_name = from_comp.split(":")[-1] if ":" in from_comp else from_comp
            to_name = to_comp.split(":")[-1] if ":" in to_comp else to_comp

            # Add nodes
            if from_comp not in nodes:
                nodes[from_comp] = {
                    "id": from_comp,
                    "name": components.get(from_comp, {}).get("name") or from_name,
                    "type": components.get(from_comp, {}).get("component_type") or "component",
                    "path": components.get(from_comp, {}).get("path"),
                    "evidence_refs": components.get(from_comp, {}).get("evidence_refs", []),
                    "confirmation_status": "confirmed",
                    "source_tables": ["pi_components", "pi_dependencies"],
                }
            if to_comp not in nodes:
                nodes[to_comp] = {
                    "id": to_comp,
                    "name": components.get(to_comp, {}).get("name") or to_name,
                    "type": components.get(to_comp, {}).get("component_type") or "component",
                    "path": components.get(to_comp, {}).get("path"),
                    "evidence_refs": components.get(to_comp, {}).get("evidence_refs", []),
                    "confirmation_status": "confirmed",
                    "source_tables": ["pi_components", "pi_dependencies"],
                }

            # Add edge
            edge_source_refs = []
            for component_id in (from_comp, to_comp):
                edge_source_refs.extend(components.get(component_id, {}).get("evidence_refs", []))
            edges.append(
                {
                    "id": dependency_id,
                    "from": from_comp,
                    "to": to_comp,
                    "type": dep_type,
                    "strength": strength,
                    "confirmation_status": "confirmed",
                    "rendered_by_default": True,
                    "source_tables": ["pi_dependencies"],
                    "source_refs": sorted(dict.fromkeys(edge_source_refs)),
                    "evidence_refs": sorted(dict.fromkeys(edge_source_refs)),
                }
            )

        # Group by dependency type
        type_counts = {}
        for edge in edges:
            t = edge["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "project_id": project_id,
            "nodes": list(nodes.values()),
            "edges": edges,
            "confirmed_edges": edges,
            "inferred_edges": [],
            "unverified_edges": [],
            "node_count": len(nodes),
            "edge_count": len(edges),
            "confirmed_edge_count": len(edges),
            "inferred_edge_count": 0,
            "unverified_edge_count": 0,
            "type_counts": type_counts,
            "knowledge_graph_status": {
                "classification": "confirmed" if edges else "unavailable",
                "reason": (
                    "Confirmed dependency edges are available from pi_dependencies."
                    if edges
                    else "No confirmed dependency edges exist; the dashboard must not draw placeholder graph nodes or inferred edges."
                ),
                "source_tables": ["pi_dependencies"],
                "placeholder_edges_rendered": False,
                "confirmed_edges_rendered_by_default": True,
                "inferred_edges_rendered_by_default": False,
                "derived_view": True,
                "primary_authority": False,
            },
            "source_status": {
                "classification": "fresh" if edges else "honest_empty_state",
                "source_tables": ["pi_dependencies"]
                + (["pi_components"] if object_exists(conn, "pi_components") else []),
                "derived_view": True,
                "primary_authority": False,
            },
            "drilldown": {
                "project": project_id,
                "node_to_component_evidence": "nodes[].evidence_refs",
                "edge_to_dependency_evidence": "edges[].source_refs",
                "confirmed_edges_only_by_default": True,
            },
        }

    except Exception as e:
        logger.error(f"Error getting project dependencies: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
