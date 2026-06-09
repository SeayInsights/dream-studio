"""Security findings API routes for vulnerability tracking dashboard"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
import tempfile

from core.config.database import get_connection
from projections.api.routes.sqlite_schema import has_columns, object_exists, table_columns
from projections.parsers.sarif_parser import parse_sarif_file

router = APIRouter()


# ── Dismiss endpoint (Phase 19.2) ─────────────────────────────────────────


class DismissRequest(BaseModel):
    reason: str


@router.post("/findings/{finding_id}/dismiss")
async def dismiss_finding(finding_id: str, body: DismissRequest) -> Dict[str, Any]:
    """Mark a finding as dismissed (false_positive) on the security_events spine.

    Calls set_finding_status() to record a finding.status_changed event.
    Idempotent: dismissing an already-dismissed finding records a new status event.
    """
    from core.findings.mutations import set_finding_status

    with get_connection() as conn:
        if not object_exists(conn, "findings_current_status"):
            raise HTTPException(
                status_code=503,
                detail="findings_current_status not present — migration 111 not yet applied",
            )
        row = conn.execute(
            "SELECT finding_id FROM findings_current_status WHERE finding_id = ?", (finding_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Finding {finding_id!r} not found")

    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    set_finding_status(
        finding_id,
        "false_positive",
        project_id=None,
        reason=body.reason,
        correlation_id=None,
        db_path=None,
    )

    return {
        "finding_id": finding_id,
        "dismissed_at": now,
        "dismissed_reason": body.reason,
        "status": "false_positive",
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
    """Return findings from findings_current_status (spine read-model, WO-Y / AD-10).

    Falls back to empty list if the spine tables are not yet present.
    """
    findings: list[dict[str, Any]] = []

    if not has_columns(
        conn, "findings_current_status", ["finding_id", "severity", "current_status"]
    ):
        # Pre-migration install: spine not yet present; return empty (not an error).
        return findings

    query = (
        "SELECT fcs.finding_id, fcs.project_id, fcs.severity,"
        "       fcs.file_path, fcs.line_number,"
        "       COALESCE(se.title, '') AS message,"
        "       fcs.current_status AS status, fcs.scanner_type AS tool,"
        "       fcs.created_at"
        " FROM findings_current_status fcs"
        " LEFT JOIN security_events se ON se.event_id = fcs.finding_id"
        " WHERE 1=1"
    )
    params: list[Any] = []
    if severity:
        query += " AND fcs.severity = ?"
        params.append(severity)
    if status:
        query += " AND fcs.current_status = ?"
        params.append(status)
    if since:
        query += " AND fcs.created_at >= ?"
        params.append(since)
    query += " ORDER BY fcs.created_at DESC LIMIT ?"
    params.append(limit)

    try:
        for row in conn.execute(query, params).fetchall():
            findings.append(
                {
                    "type": "spine",
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
    except Exception:
        pass

    return findings


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
                    for name in (
                        "findings_current_status",
                        "security_events",
                        "vw_security_summary",
                    )
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

        query = (
            "SELECT se.event_id AS sarif_finding_id, se.scanner_type AS scan_tool,"
            "       se.vuln_class AS rule_id, se.severity, se.file_path, se.line_number,"
            "       se.title AS message, se.cwe_id, se.created_at,"
            "       COALESCE(fcs.current_status, 'open') AS status"
            " FROM security_events se"
            " LEFT JOIN findings_current_status fcs ON fcs.finding_id = se.event_id"
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

        # Aggregate from findings_current_status spine read-model (WO-Y / AD-10).
        findings_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for sev, count in _count_group(conn, "findings_current_status", "severity", cutoff).items():
            if sev in findings_by_severity:
                findings_by_severity[sev] += count

        # Count by source (scanner_type from security_events spine)
        findings_by_source: dict[str, int] = {}
        if object_exists(conn, "security_events"):
            rows = conn.execute(
                "SELECT COALESCE(scanner_type, 'unknown') AS src, COUNT(*) AS cnt"
                " FROM security_events"
                " WHERE event_kind = 'finding.recorded' AND created_at >= ?"
                " GROUP BY src",
                (cutoff,),
            ).fetchall()
            for row in rows:
                findings_by_source[row["src"]] = int(row["cnt"])

        # Count by status
        findings_by_status = {}
        for item_status, count in _count_group(
            conn, "findings_current_status", "current_status", cutoff
        ).items():
            findings_by_status[item_status] = findings_by_status.get(item_status, 0) + count

        # Trend over last N days — events recorded per day on the spine
        trend_data = []
        spine_ok = has_columns(conn, "security_events", ["created_at"])
        for i in range(days):
            date = (datetime.now() - timedelta(days=days - i - 1)).strftime("%Y-%m-%d")
            next_date = (datetime.now() - timedelta(days=days - i - 2)).strftime("%Y-%m-%d")
            if spine_ok:
                count = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM security_events"
                        " WHERE event_kind = 'finding.recorded'"
                        "   AND created_at >= ? AND created_at < ?",
                        (date, next_date),
                    ).fetchone()[0]
                    or 0
                )
            else:
                count = 0
            trend_data.append({"date": date, "count": count})

        source_tables = [
            name
            for name in ("findings_current_status", "security_events", "vw_security_summary")
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
                    "Security stats aggregate findings_current_status + security_events spine (WO-Y / AD-10)."
                    if source_tables
                    else "No security spine tables present in this DB snapshot."
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
