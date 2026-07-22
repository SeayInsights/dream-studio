"""Security findings listing endpoints: all findings, SARIF, CVE, and manual
review views.

WO-GF-API-ROUTES: split out of security.py.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query

from core.config.database import get_connection
from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL
from projections.api.routes.sqlite_schema import object_exists, table_columns

from .security_router import router
from .security_shared import _security_empty, _security_fallback_findings


@router.get("/security/findings")
async def list_all_findings(
    severity: str | None = Query(
        None, description="Filter by severity (critical, high, medium, low, info)"
    ),
    status: str | None = Query(None, description="Filter by status (varies by source)"),
    since: str | None = Query(None, description="Filter by date (YYYY-MM-DD format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
) -> dict[str, Any]:
    """
    List all security findings across all 4 source types.

    Returns unified JSON array with type field indicating source (sarif, cve, manual_review, hook_check).
    Sorted by most recent first.

    Uses the current compatible security authority tables unless the optional
    summary view is complete enough to preserve project attribution.
    """
    conn = get_connection()

    try:
        required_view_columns = {
            "source_type",
            "finding_id",
            "project_id",
            "tool",
            "severity",
            "file_path",
            "line_number",
            "message",
            "status",
            "created_at",
        }
        filters = {"severity": severity, "status": status, "since": since, "limit": limit}
        if not required_view_columns.issubset(table_columns(conn, "vw_security_summary")):
            findings = _security_fallback_findings(
                conn,
                severity=severity,
                status=status,
                since=since,
                limit=limit,
            )
            payload = (
                _security_empty(filters)
                if not findings
                else {
                    "findings": findings,
                    "count": len(findings),
                    "filters": filters,
                }
            )
            payload["source_status"] = {
                "classification": "fresh" if findings else "empty by design",
                "reason": "Dashboard security findings are read from current compatible security finding tables because the optional summary view does not expose the full dashboard contract.",
                # findings_current_status dropped migration 140 (WO dff23cb0) —
                # derived from security_events at read time, not a schema object.
                "source_tables": [
                    name
                    for name in ("security_events", "vw_security_summary")
                    if object_exists(conn, name)
                ],
                "retired_view_columns_missing": sorted(
                    required_view_columns - table_columns(conn, "vw_security_summary")
                ),
                "derived_view": True,
                "primary_authority": False,
            }
            return payload

        # Query pre-computed view (replaces 4 separate table queries + Python aggregation)
        query = "SELECT * FROM vw_security_summary WHERE 1=1"
        params = []

        if severity:
            query += " AND severity = ?"
            params.append(severity)

        if status:
            query += " AND status = ?"
            params.append(status)

        if since:
            query += " AND created_at >= ?"
            params.append(since)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        # Convert to JSON (view returns unified schema)
        findings = []
        for row in rows:
            row_keys = set(row.keys())
            findings.append(
                {
                    "type": row["source_type"],
                    "id": row["finding_id"],
                    "project_id": row["project_id"] if "project_id" in row_keys else None,
                    "tool": row["tool"],
                    "severity": row["severity"],
                    "file_path": row["file_path"],
                    "line_number": row["line_number"],
                    "message": row["message"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                }
            )

        return {
            "findings": findings,
            "count": len(findings),
            "filters": {"severity": severity, "status": status, "since": since, "limit": limit},
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.get("/security/sarif")
async def list_sarif_findings(
    scan_tool: str | None = Query(
        None, description="Filter by scan tool (semgrep, bandit, trivy, etc.)"
    ),
    status: str | None = Query(
        None, description="Filter by status (open, mitigated, false_positive, accepted)"
    ),
    severity: str | None = Query(
        None, description="Filter by severity (critical, high, medium, low, info)"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
) -> dict[str, Any]:
    """
    List SARIF findings only.

    Returns findings from SARIF-compliant security scanners.
    """
    conn = get_connection()

    try:
        # sec_sarif_findings retired in migration 112 (WO-Y). Read from security_events spine.
        if not object_exists(conn, "security_events"):
            return {
                "findings": [],
                "count": 0,
                "filters": {
                    "scan_tool": scan_tool,
                    "status": status,
                    "severity": severity,
                    "limit": limit,
                },
                "source_status": {
                    "classification": "empty by design",
                    "reason": "security_events spine not yet present.",
                },
            }

        # findings_current_status dropped migration 140 (WO dff23cb0) — derive
        # from security_events at read time (core/findings/current_status.py).
        query = (
            "SELECT se.event_id AS sarif_finding_id, se.scanner_type AS scan_tool,"
            "       se.vuln_class AS rule_id, se.severity, se.file_path, se.line_number,"
            "       se.title AS message, se.cwe_id, se.created_at,"
            "       COALESCE(fcs.current_status, 'open') AS status"
            " FROM security_events se"
            f" LEFT JOIN ({FINDINGS_CURRENT_STATUS_SQL}) fcs ON fcs.finding_id = se.event_id"
            " WHERE se.event_kind = 'finding.recorded'"
        )
        params: list = []

        if scan_tool:
            query += " AND se.scanner_type = ?"
            params.append(scan_tool)

        if status:
            query += " AND COALESCE(fcs.current_status, 'open') = ?"
            params.append(status)

        if severity:
            query += " AND se.severity = ?"
            params.append(severity)

        query += " ORDER BY se.created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        findings = []
        for row in rows:
            findings.append(
                {
                    "sarif_finding_id": row["sarif_finding_id"],
                    "scan_tool": row["scan_tool"],
                    "rule_id": row["rule_id"],
                    "severity": row["severity"],
                    "file_path": row["file_path"],
                    "line_number": row["line_number"],
                    "message": row["message"],
                    "cwe_ids": [row["cwe_id"]] if row["cwe_id"] else None,
                    "status": row["status"],
                    "created_at": row["created_at"],
                }
            )

        return {
            "findings": findings,
            "count": len(findings),
            "filters": {
                "scan_tool": scan_tool,
                "status": status,
                "severity": severity,
                "limit": limit,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.get("/security/cve")
async def list_cve_matches(
    package_name: str | None = Query(None, description="Filter by package name"),
    status: str | None = Query(
        None, description="Filter by status (vulnerable, patched, mitigated)"
    ),
    severity: str | None = Query(
        None, description="Filter by severity (critical, high, medium, low)"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
) -> dict[str, Any]:
    """
    List CVE matches only.

    Returns CVE matches from dependency scanners (npm audit, pip-audit, Trivy, etc.).
    """
    conn = get_connection()

    try:
        # sec_cve_matches retired in migration 112 (WO-Y). CVE findings now route through
        # the security_events spine via record_finding(cve_id=...). Filtered reads pending
        # a dedicated CVE spine query (forward work). Return empty for now.
        return {
            "findings": [],
            "count": 0,
            "filters": {
                "package_name": package_name,
                "status": status,
                "severity": severity,
                "limit": limit,
            },
            "source_status": {
                "classification": "empty by design",
                "reason": "sec_cve_matches retired in migration 112. CVE findings now live on the security_events spine.",
                "derived_view": True,
                "primary_authority": False,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.get("/security/reviews")
async def list_manual_reviews(
    reviewer: str | None = Query(None, description="Filter by reviewer name"),
    review_type: str | None = Query(
        None,
        description="Filter by review type (code_review, architecture_review, security_review)",
    ),
    status: str | None = Query(None, description="Filter by status (draft, published, closed)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
) -> dict[str, Any]:
    """
    List manual reviews only.

    Returns manual security/code/architecture reviews.
    """
    conn = get_connection()

    try:
        # sec_manual_reviews retired in migration 112 (WO-Y). Manual review findings
        # route through the security_events spine. Return empty for now.
        return {
            "reviews": [],
            "count": 0,
            "filters": {
                "reviewer": reviewer,
                "review_type": review_type,
                "status": status,
                "limit": limit,
            },
            "source_status": {
                "classification": "empty by design",
                "reason": "sec_manual_reviews retired in migration 112. Manual reviews now live on the security_events spine.",
                "derived_view": True,
                "primary_authority": False,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()
