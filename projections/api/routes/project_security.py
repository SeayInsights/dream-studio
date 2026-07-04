"""Project security findings endpoint."""

import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException

from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL, security_spine_present
from projections.api.routes.sqlite_schema import object_exists
from projections.api.lib.project_helpers import (
    get_db_connection,
    _empty_project_source_status,
)
from projections.api.lib.security_helpers import _security_aliases

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{project_id}/security")
async def get_project_security(project_id: str) -> Dict[str, Any]:
    """
    Get security findings for a specific project.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # findings_current_status dropped migration 140 (WO dff23cb0) — derived
        # from security_events at read time (core/findings/current_status.py).
        # security_events (not findings_current_status) has always been the
        # real presence gate: the two were created by the same migration-111
        # DDL statement and security_events always carried project_id.
        if security_spine_present(conn):
            aliases = _security_aliases(project_id)
            placeholders = ",".join("?" for _ in aliases)
            rows = cursor.execute(
                f"""
                SELECT
                    fcs.finding_id,
                    fcs.project_id,
                    se.vuln_class AS rule_id,
                    fcs.severity,
                    fcs.title,
                    fcs.file_path,
                    fcs.line_number AS start_line,
                    fcs.current_status AS status,
                    fcs.scanner_type,
                    fcs.created_at
                FROM ({FINDINGS_CURRENT_STATUS_SQL}) fcs
                LEFT JOIN security_events se ON se.event_id = fcs.finding_id
                WHERE fcs.project_id IN ({placeholders})
                  AND fcs.current_status NOT IN ('resolved', 'mitigated', 'false_positive')
                ORDER BY
                    CASE lower(fcs.severity)
                        WHEN 'critical' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3
                        ELSE 4
                    END,
                    fcs.created_at DESC
                """,
                aliases,
            ).fetchall()
            findings = [
                {
                    "id": row["finding_id"],
                    "source_project_id": row["project_id"],
                    "project_id": project_id,
                    "title": row["title"] or "security finding",
                    "rule_id": row["rule_id"],
                    "severity": str(row["severity"] or "unknown").lower(),
                    "description": row["title"],
                    "file_path": row["file_path"],
                    "line": row["start_line"],
                    "location": (
                        f"{row['file_path']}:{row['start_line']}" if row["file_path"] else "Unknown"
                    ),
                    "status": row["status"],
                    "scanner_type": row["scanner_type"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
            return {
                "project_id": project_id,
                "findings": findings,
                "count": len(findings),
                "alias_policy": {
                    "aliases": aliases,
                    "reason": "Security findings derived from the security_events spine (WO-Y / AD-10; WO dff23cb0).",
                },
                "source_status": {
                    "classification": "fresh",
                    "reason": "Project security detail is derived from the security_events spine at read time.",
                    "source_tables": ["security_events"],
                    "derived_view": True,
                    "primary_authority": False,
                },
            }

        if not object_exists(conn, "pi_violations"):
            return {
                "project_id": project_id,
                "findings": [],
                "count": 0,
                "source_status": _empty_project_source_status(
                    ["pi_violations"],
                    reason="Project security detail table is not present in this DB snapshot.",
                ),
            }

        query = """
        SELECT
            violation_id,
            violation_type,
            severity,
            description,
            files,
            lines,
            status,
            detected_at
        FROM pi_violations
        WHERE project_id = ? AND status != 'resolved'
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                ELSE 4
            END,
            detected_at DESC
        """

        rows = cursor.execute(query, (project_id,)).fetchall()
        findings = []

        for row in rows:
            findings.append(
                {
                    "id": row["violation_id"],
                    "title": row["violation_type"],
                    "severity": row["severity"],
                    "description": row["description"],
                    "location": f"{row['files']}:{row['lines']}" if row["files"] else "Unknown",
                    "status": row["status"],
                    "created_at": row["detected_at"],
                }
            )

        return {"project_id": project_id, "findings": findings, "count": len(findings)}

    except Exception as e:
        logger.error(f"Error getting project security: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
