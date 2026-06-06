"""Security findings API routes for vulnerability tracking dashboard"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
import tempfile
import json

from core.config.database import get_connection
from projections.api.routes.sqlite_schema import has_columns, object_exists, table_columns
from projections.parsers.sarif_parser import parse_sarif_file

router = APIRouter()


# ── Dismiss endpoint (Phase 19.2) ─────────────────────────────────────────


class DismissRequest(BaseModel):
    reason: str


@router.post("/findings/{finding_id}/dismiss")
async def dismiss_finding(finding_id: str, body: DismissRequest) -> Dict[str, Any]:
    """Mark a finding as dismissed by the operator.

    Sets findings.dismissed_at and findings.dismissed_reason.
    These columns feed the dismissed_finding friction signal detector.
    Idempotent: dismissing an already-dismissed finding updates reason + timestamp.
    """
    with get_connection() as conn:
        if not has_columns(conn, "findings", ["dismissed_at", "dismissed_reason"]):
            raise HTTPException(
                status_code=503,
                detail="Migration 096 not applied — dismissed_at column missing",
            )
        row = conn.execute(
            "SELECT finding_id FROM findings WHERE finding_id = ?", (finding_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Finding {finding_id!r} not found")

        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute(
            "UPDATE findings SET dismissed_at = ?, dismissed_reason = ? WHERE finding_id = ?",
            (now, body.reason, finding_id),
        )
        conn.commit()

    return {
        "finding_id": finding_id,
        "dismissed_at": now,
        "dismissed_reason": body.reason,
        "status": "dismissed",
    }


def _security_empty(filters: dict[str, Any]) -> Dict[str, Any]:
    return {
        "findings": [],
        "count": 0,
        "filters": filters,
        "source_status": {
            "classification": "empty by design",
            "reason": "No compatible security finding source tables are available.",
            "derived_view": True,
            "primary_authority": False,
        },
    }


def _security_fallback_findings(
    conn,
    *,
    severity: Optional[str],
    status: Optional[str],
    since: Optional[str],
    limit: int,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    security_columns = table_columns(conn, "findings")
    if has_columns(
        conn,
        "findings",
        [
            "finding_id",
            "severity",
            "file_path",
            "start_line",
            "description",
            "status",
            "created_at",
        ],
    ):
        project_id_expr = "project_id" if "project_id" in security_columns else "NULL as project_id"
        tool_sources = [column for column in ("scan_id", "category") if column in security_columns]
        tool_expr = (
            f"COALESCE({', '.join(tool_sources)}, 'telemetry_security')"
            if tool_sources
            else "'telemetry_security'"
        )
        query = """
            SELECT
                finding_id,
                {project_id_expr},
                {tool_expr} as tool,
                severity,
                file_path,
                start_line as line_number,
                description as message,
                status,
                created_at
            FROM findings
            WHERE 1=1
        """.format(project_id_expr=project_id_expr, tool_expr=tool_expr)
        params: list[Any] = []
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
        for row in conn.execute(query, params).fetchall():
            findings.append(
                {
                    "type": "telemetry_security",
                    "id": row["finding_id"],
                    "project_id": row["project_id"],
                    "tool": row["tool"],
                    "severity": row["severity"],
                    "file_path": row["file_path"],
                    "line_number": row["line_number"],
                    "message": row["message"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                }
            )

    remaining = max(limit - len(findings), 0)
    sarif_columns = table_columns(conn, "sec_sarif_findings")
    if remaining and has_columns(
        conn,
        "sec_sarif_findings",
        [
            "sarif_finding_id",
            "scan_tool",
            "severity",
            "file_path",
            "line_number",
            "message",
            "status",
            "created_at",
        ],
    ):
        project_id_expr = "project_id" if "project_id" in sarif_columns else "NULL as project_id"
        query = """
            SELECT
                sarif_finding_id,
                {project_id_expr},
                scan_tool,
                severity,
                file_path,
                line_number,
                message,
                status,
                created_at
            FROM sec_sarif_findings
            WHERE 1=1
        """.format(project_id_expr=project_id_expr)
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
        params.append(remaining)
        for row in conn.execute(query, params).fetchall():
            findings.append(
                {
                    "type": "sarif",
                    "id": row["sarif_finding_id"],
                    "project_id": row["project_id"],
                    "tool": row["scan_tool"],
                    "severity": row["severity"],
                    "file_path": row["file_path"],
                    "line_number": row["line_number"],
                    "message": row["message"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                }
            )

    return sorted(findings, key=lambda item: item.get("created_at") or "", reverse=True)[:limit]


def _count_group(conn, table: str, column: str, cutoff: str) -> dict[str, int]:
    if not has_columns(conn, table, [column, "created_at"]):
        return {}
    rows = conn.execute(
        f"SELECT {column} as key, COUNT(*) as count FROM {table} WHERE created_at >= ? GROUP BY {column}",
        (cutoff,),
    ).fetchall()
    return {str(row["key"]): int(row["count"]) for row in rows if row["key"] is not None}


def _count_since(conn, table: str, cutoff: str) -> int:
    if not has_columns(conn, table, ["created_at"]):
        return 0
    return int(
        conn.execute(
            f"SELECT COUNT(*) as count FROM {table} WHERE created_at >= ?", (cutoff,)
        ).fetchone()["count"]
        or 0
    )


@router.get("/security/findings")
async def list_all_findings(
    severity: Optional[str] = Query(
        None, description="Filter by severity (critical, high, medium, low, info)"
    ),
    status: Optional[str] = Query(None, description="Filter by status (varies by source)"),
    since: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
) -> Dict[str, Any]:
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
                "source_tables": [
                    name
                    for name in ("findings", "sec_sarif_findings", "vw_security_summary")
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
    scan_tool: Optional[str] = Query(
        None, description="Filter by scan tool (semgrep, bandit, trivy, etc.)"
    ),
    status: Optional[str] = Query(
        None, description="Filter by status (open, mitigated, false_positive, accepted)"
    ),
    severity: Optional[str] = Query(
        None, description="Filter by severity (critical, high, medium, low, info)"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
) -> Dict[str, Any]:
    """
    List SARIF findings only.

    Returns findings from SARIF-compliant security scanners.
    """
    conn = get_connection()

    try:
        query = """
            SELECT
                sarif_finding_id,
                activity_id,
                scan_tool,
                rule_id,
                rule_name,
                severity,
                file_path,
                line_number,
                message,
                cwe_ids,
                cvss_score,
                status,
                mitigated_at,
                mitigation_task_id,
                created_at
            FROM sec_sarif_findings
            WHERE 1=1
        """
        params = []

        if scan_tool:
            query += " AND scan_tool = ?"
            params.append(scan_tool)

        if status:
            query += " AND status = ?"
            params.append(status)

        if severity:
            query += " AND severity = ?"
            params.append(severity)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        findings = []
        for row in rows:
            findings.append(
                {
                    "sarif_finding_id": row["sarif_finding_id"],
                    "activity_id": row["activity_id"],
                    "scan_tool": row["scan_tool"],
                    "rule_id": row["rule_id"],
                    "rule_name": row["rule_name"],
                    "severity": row["severity"],
                    "file_path": row["file_path"],
                    "line_number": row["line_number"],
                    "message": row["message"],
                    "cwe_ids": json.loads(row["cwe_ids"]) if row["cwe_ids"] else None,
                    "cvss_score": row["cvss_score"],
                    "status": row["status"],
                    "mitigated_at": row["mitigated_at"],
                    "mitigation_task_id": row["mitigation_task_id"],
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
    package_name: Optional[str] = Query(None, description="Filter by package name"),
    status: Optional[str] = Query(
        None, description="Filter by status (vulnerable, patched, mitigated)"
    ),
    severity: Optional[str] = Query(
        None, description="Filter by severity (critical, high, medium, low)"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
) -> Dict[str, Any]:
    """
    List CVE matches only.

    Returns CVE matches from dependency scanners (npm audit, pip-audit, Trivy, etc.).
    """
    conn = get_connection()

    try:
        query = """
            SELECT
                cve_match_id,
                activity_id,
                cve_id,
                package_name,
                package_version,
                severity,
                cvss_score,
                description,
                fixed_version,
                status,
                patched_at,
                created_at
            FROM sec_cve_matches
            WHERE 1=1
        """
        params = []

        if package_name:
            query += " AND package_name = ?"
            params.append(package_name)

        if status:
            query += " AND status = ?"
            params.append(status)

        if severity:
            query += " AND severity = ?"
            params.append(severity)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        findings = []
        for row in rows:
            findings.append(
                {
                    "cve_match_id": row["cve_match_id"],
                    "activity_id": row["activity_id"],
                    "cve_id": row["cve_id"],
                    "package_name": row["package_name"],
                    "package_version": row["package_version"],
                    "severity": row["severity"],
                    "cvss_score": row["cvss_score"],
                    "description": row["description"],
                    "fixed_version": row["fixed_version"],
                    "status": row["status"],
                    "patched_at": row["patched_at"],
                    "created_at": row["created_at"],
                }
            )

        return {
            "findings": findings,
            "count": len(findings),
            "filters": {
                "package_name": package_name,
                "status": status,
                "severity": severity,
                "limit": limit,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.get("/security/reviews")
async def list_manual_reviews(
    reviewer: Optional[str] = Query(None, description="Filter by reviewer name"),
    review_type: Optional[str] = Query(
        None,
        description="Filter by review type (code_review, architecture_review, security_review)",
    ),
    status: Optional[str] = Query(None, description="Filter by status (draft, published, closed)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
) -> Dict[str, Any]:
    """
    List manual reviews only.

    Returns manual security/code/architecture reviews.
    """
    conn = get_connection()

    try:
        query = """
            SELECT
                review_id,
                activity_id,
                reviewer,
                review_type,
                findings,
                risk_level,
                recommendations,
                status,
                created_at
            FROM sec_manual_reviews
            WHERE 1=1
        """
        params = []

        if reviewer:
            query += " AND reviewer = ?"
            params.append(reviewer)

        if review_type:
            query += " AND review_type = ?"
            params.append(review_type)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        reviews = []
        for row in rows:
            reviews.append(
                {
                    "review_id": row["review_id"],
                    "activity_id": row["activity_id"],
                    "reviewer": row["reviewer"],
                    "review_type": row["review_type"],
                    "findings": row["findings"],
                    "risk_level": row["risk_level"],
                    "recommendations": row["recommendations"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                }
            )

        return {
            "reviews": reviews,
            "count": len(reviews),
            "filters": {
                "reviewer": reviewer,
                "review_type": review_type,
                "status": status,
                "limit": limit,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.get("/security/stats")
async def get_security_stats(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze")
) -> Dict[str, Any]:
    """
    Get aggregate statistics for security findings.

    Returns:
    - findings_by_severity: {critical: N, high: N, medium: N, low: N, info: N}
    - findings_by_source: {sarif: N, cve: N, manual_review: N, hook_check: N}
    - findings_by_status: {open: N, mitigated: N, false_positive: N, ...}
    - trend_last_N_days: [{date: '2026-05-01', count: 5}, ...]
    """
    conn = get_connection()

    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        findings_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for table, column in (
            ("findings", "severity"),
            ("sec_sarif_findings", "severity"),
            ("sec_cve_matches", "severity"),
            ("sec_manual_reviews", "risk_level"),
        ):
            for sev, count in _count_group(conn, table, column, cutoff).items():
                if sev in findings_by_severity:
                    findings_by_severity[sev] += count

        # Count by source
        findings_by_source = {
            "telemetry_security": _count_since(conn, "findings", cutoff),
            "sarif": _count_since(conn, "sec_sarif_findings", cutoff),
            "cve": _count_since(conn, "sec_cve_matches", cutoff),
            "manual_review": _count_since(conn, "sec_manual_reviews", cutoff),
            "hook_check": _count_since(conn, "sec_hook_checks", cutoff),
        }

        # Count by status (combining different status fields)
        findings_by_status = {}
        for table in (
            "findings",
            "sec_sarif_findings",
            "sec_cve_matches",
            "sec_manual_reviews",
        ):
            for item_status, count in _count_group(conn, table, "status", cutoff).items():
                findings_by_status[item_status] = findings_by_status.get(item_status, 0) + count

        # Trend over last N days
        trend_data = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=days - i - 1)).strftime("%Y-%m-%d")
            next_date = (datetime.now() - timedelta(days=days - i - 2)).strftime("%Y-%m-%d")

            def daily(table: str) -> int:
                if not has_columns(conn, table, ["created_at"]):
                    return 0
                return int(
                    conn.execute(
                        f"SELECT COUNT(*) as count FROM {table} WHERE created_at >= ? AND created_at < ?",
                        (date, next_date),
                    ).fetchone()["count"]
                    or 0
                )

            sarif_daily = daily("sec_sarif_findings")
            cve_daily = daily("sec_cve_matches")
            review_daily = daily("sec_manual_reviews")
            hook_daily = daily("sec_hook_checks")
            telemetry_daily = daily("findings")

            total_daily = sarif_daily + cve_daily + review_daily + hook_daily + telemetry_daily

            trend_data.append({"date": date, "count": total_daily})

        source_tables = [
            name
            for name in (
                "findings",
                "sec_sarif_findings",
                "sec_cve_matches",
                "sec_manual_reviews",
                "sec_hook_checks",
            )
            if object_exists(conn, name)
        ]

        return {
            "findings_by_severity": findings_by_severity,
            "findings_by_source": findings_by_source,
            "findings_by_status": findings_by_status,
            "trend_last_30_days": trend_data,
            "days_analyzed": days,
            "source_status": {
                "classification": "fresh" if source_tables else "empty by design",
                "reason": (
                    "Security stats aggregate current compatible security authority tables."
                    if source_tables
                    else "No current security authority tables are present in this DB snapshot."
                ),
                "source_tables": source_tables,
                "derived_view": True,
                "primary_authority": False,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.post("/security/sarif/import")
async def import_sarif_file(
    file: UploadFile = File(..., description="SARIF file to import")
) -> Dict[str, Any]:
    """
    Upload SARIF file for parsing and import.

    Accepts multipart/form-data file upload, saves to temp location,
    and calls parse_sarif_file() to process the results.

    Returns {imported: count, skipped: count, errors: []}
    """
    # Validate file extension
    if not file.filename or (
        not file.filename.endswith(".sarif") and not file.filename.endswith(".json")
    ):
        raise HTTPException(
            status_code=400, detail="Invalid file type. Expected .sarif or .json file."
        )

    try:
        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".sarif", delete=False) as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name

        imported = parse_sarif_file(tmp_path)
        result = {"imported": imported, "skipped": 0, "errors": []}

        # Clean up temp file
        import os

        os.unlink(tmp_path)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")
