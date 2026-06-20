"""Security helpers for project intelligence routes."""

import sqlite3
from typing import Any

from projections.api.routes.sqlite_schema import object_exists, table_columns


def _security_alias_expr(project_ref: str) -> str:
    return (
        f"project_id IN ({project_ref}, "
        f"'project_' || replace({project_ref}, '-', '_'), "
        f"replace({project_ref}, '_', '-'))"
    )


def _security_aliases(project_id: str) -> list[str]:
    aliases = [
        project_id,
        f"project_{project_id.replace('-', '_')}",
        project_id.replace("_", "-"),
    ]
    return list(dict.fromkeys(alias for alias in aliases if alias))


def _security_assignment_summary(
    conn: sqlite3.Connection,
    visible_projects: list[dict[str, Any]],
) -> dict[str, Any]:
    if not object_exists(conn, "findings_current_status"):
        return {
            "classification": "unavailable",
            "unassigned_legacy_finding_count": 0,
            "unassigned_project_ids": [],
            "source_tables": [],
        }
    if "project_id" not in table_columns(conn, "findings_current_status"):
        return {
            "classification": "unavailable",
            "reason": "findings_current_status has no project_id column in this schema snapshot.",
            "mapped_project_alias_count": 0,
            "unassigned_legacy_finding_count": 0,
            "unassigned_project_ids": [],
            "source_tables": ["findings_current_status"],
            "derived_view": True,
            "primary_authority": False,
        }
    aliases: set[str] = set()
    for project in visible_projects:
        aliases.update(_security_aliases(str(project.get("project_id") or "")))
    rows = conn.execute("""
        SELECT COALESCE(project_id, '<null>') AS project_id, COUNT(*) AS count
        FROM findings_current_status
        GROUP BY COALESCE(project_id, '<null>')
        ORDER BY count DESC
        """).fetchall()
    unassigned = [
        {"project_id": row["project_id"], "count": row["count"]}
        for row in rows
        if row["project_id"] not in aliases
    ]
    return {
        "classification": "fresh",
        "mapped_project_alias_count": len(aliases),
        "unassigned_legacy_finding_count": sum(item["count"] for item in unassigned),
        "unassigned_project_ids": unassigned,
        "unassigned_policy": "manual_review_required_or_retention_only; not shown in normal project cards until mapped",
        "source_tables": ["findings_current_status"],
        "derived_view": True,
        "primary_authority": False,
    }
