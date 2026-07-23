"""WO-GF-TELEMETRY-SPLIT: read_models security findings rollups.

Extracted verbatim from core/telemetry/read_models.py (see read_models.py
facade). _security_rollup, _security_remediation_intelligence,
_security_status_counts, _security_attribution.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL

from .read_models_shared import ScopeFilter, _rows, _where_scope_project_only


def _security_rollup(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> list[dict[str, Any]]:
    # findings retired in migration 112 (WO-Y); findings_current_status dropped
    # migration 140 (WO dff23cb0) — derive from security_events.
    where, params = _where_scope_project_only(scope)
    try:
        return _rows(
            conn,
            f"""
            SELECT
                COALESCE(project_id, 'unknown') AS project_id,
                COALESCE(file_path, 'unknown') AS file_path,
                line_number AS start_line,
                NULL AS end_line,
                severity,
                current_status AS status,
                COUNT(*) AS finding_count
            FROM ({FINDINGS_CURRENT_STATUS_SQL})
            {where}
            GROUP BY project_id, file_path, line_number, severity, current_status
            ORDER BY finding_count DESC, severity DESC, file_path
            """,
            params,
        )
    except Exception:
        return []


def _security_remediation_intelligence(
    conn: sqlite3.Connection,
    scope: ScopeFilter | None = None,
) -> dict[str, Any]:
    # findings retired in migration 112 (WO-Y); findings_current_status dropped
    # migration 140 (WO dff23cb0) — derive from security_events.
    # Use fcs.project_id to avoid "ambiguous column name" in the LEFT JOIN.
    if scope and scope.project_id:
        fcs_where = "WHERE fcs.project_id = ?"
        params: tuple[Any, ...] = (scope.project_id,)
    else:
        fcs_where = ""
        params = ()
    try:
        findings = _rows(
            conn,
            f"""
            SELECT
                fcs.finding_id,
                COALESCE(fcs.project_id, 'unknown') AS project_id,
                'unknown' AS milestone_id,
                'unknown' AS task_id,
                'unknown' AS process_run_id,
                'unknown' AS scan_id,
                fcs.severity,
                COALESCE(se.vuln_class, 'unknown') AS category,
                COALESCE(se.vuln_class, 'unknown') AS rule_id,
                COALESCE(fcs.file_path, 'unknown') AS file_path,
                fcs.line_number AS start_line,
                NULL AS end_line,
                fcs.current_status AS status,
                NULL AS recommendation,
                'unknown' AS agent_id,
                'unknown' AS skill_id,
                'unknown' AS workflow_id,
                'unknown' AS hook_id,
                NULL AS evidence_refs_json,
                fcs.created_at,
                fcs.updated_at
            FROM ({FINDINGS_CURRENT_STATUS_SQL}) fcs
            LEFT JOIN security_events se ON se.event_id = fcs.finding_id
            {fcs_where}
            ORDER BY
                CASE fcs.severity
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END,
            status,
            file_path,
            start_line
            """,
            params,
        )
    except Exception:
        findings = []
    remediation_candidates = [
        {
            **finding,
            "candidate_type": "security_remediation_work_order_candidate",
            "requires_future_approval": True,
            "execution_authorized": False,
            "remediation_basis": "open_security_finding",
        }
        for finding in findings
        if finding["status"] in {"open", "unresolved"}
        and finding["severity"] in {"critical", "high", "medium"}
    ]
    false_positive_candidates = [
        finding
        for finding in findings
        if finding["status"] in {"false_positive", "false-positive", "dismissed"}
    ]
    resolved_findings = [
        finding for finding in findings if finding["status"] in {"resolved", "fixed", "closed"}
    ]

    return {
        "findings": findings,
        "status_counts": _security_status_counts(conn, scope),
        "attribution": _security_attribution(conn, scope),
        "remediation_candidates": remediation_candidates,
        "false_positive_candidates": false_positive_candidates,
        "resolved_findings": resolved_findings,
        "remediation_policy": {
            "execution_authorized": False,
            "requires_future_work_order": True,
            "requires_human_approval": True,
            "db_record_deletion_allowed": False,
            "dashboard_ready": True,
            "derived_view": True,
            "primary_authority": False,
        },
        "empty_state": "No security findings for the selected scope.",
    }


def _security_status_counts(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> list[dict[str, Any]]:
    # findings retired in migration 112 (WO-Y); findings_current_status dropped
    # migration 140 (WO dff23cb0) — derive from security_events.
    where, params = _where_scope_project_only(scope)
    try:
        return _rows(
            conn,
            f"""
            SELECT
                COALESCE(project_id, 'unknown') AS project_id,
                severity,
                current_status AS status,
                COUNT(*) AS finding_count
            FROM ({FINDINGS_CURRENT_STATUS_SQL})
            {where}
            GROUP BY project_id, severity, current_status
            ORDER BY finding_count DESC, severity, current_status
            """,
            params,
        )
    except Exception:
        return []


def _security_attribution(
    conn: sqlite3.Connection, scope: ScopeFilter | None = None
) -> list[dict[str, Any]]:
    # findings retired in migration 112 (WO-Y); attribution columns not on spine.
    # findings_current_status dropped migration 140 (WO dff23cb0) — derive from
    # security_events. Return project/severity/status summary only; agent
    # attribution is empty.
    where, params = _where_scope_project_only(scope)
    try:
        return _rows(
            conn,
            f"""
            SELECT
                COALESCE(project_id, 'unknown') AS project_id,
                'unknown' AS agent_id,
                'unknown' AS skill_id,
                'unknown' AS workflow_id,
                'unknown' AS hook_id,
                severity,
                current_status AS status,
                COUNT(*) AS finding_count
            FROM ({FINDINGS_CURRENT_STATUS_SQL})
            {where}
            GROUP BY project_id, severity, current_status
            ORDER BY finding_count DESC, severity DESC
            """,
            params,
        )
    except Exception:
        return []
