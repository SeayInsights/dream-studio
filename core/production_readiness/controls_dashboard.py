"""SQLite read model for the production-readiness dashboard summary.

WO-GF-READINESS-INSIGHTS: split from ``core/production_readiness/controls.py``.
No logic changes — extracted verbatim.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from typing import Any

from .controls_shared import _table_exists


def production_readiness_dashboard_summary(
    conn: sqlite3.Connection,
    *,
    project_id: str,
) -> dict[str, Any]:
    """Read the latest SQLite-backed production readiness summary for a project."""

    # WO-SCHEMALEAN: the normalized production_readiness_* tables were dropped in
    # migration 112; `ds analytics-ingest` now writes the readiness_events spine
    # (assessment.started + control_result.recorded events). This reader was
    # repointed to it — the summary is reconstructed from the latest assessment
    # event plus its child control events for the project.
    if not _table_exists(conn, "readiness_events"):
        return _empty_summary(project_id, ["readiness_events"])
    latest = conn.execute(
        """
        SELECT event_id, body, created_at FROM readiness_events
        WHERE project_id = ? AND event_kind = 'assessment.started'
        ORDER BY created_at DESC, event_id DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    if latest is None:
        return _empty_summary(project_id, [])
    assessment_id = latest["event_id"]
    body = json.loads(latest["body"] or "{}")
    status = body.get("status") or "partial"
    confidence = body.get("confidence") or "medium"
    missing_evidence = body.get("missing_evidence") or []
    blocking_factors = body.get("blocking_factors") or []
    controls = []
    for row in conn.execute(
        """
        SELECT control_id, result, body FROM readiness_events
        WHERE parent_event_id = ? AND event_kind = 'control_result.recorded'
        ORDER BY control_id
        """,
        (assessment_id,),
    ).fetchall():
        cbody = json.loads(row["body"] or "{}")
        controls.append(
            {
                "control_id": row["control_id"],
                "status": row["result"],
                "control_family": cbody.get("control_family"),
                "severity": cbody.get("severity"),
                "applicability": cbody.get("applicability"),
            }
        )
    summary = Counter(control["status"] for control in controls)

    def _score_dict(raw: Any) -> dict[str, Any]:
        # readiness_events stores the health/readiness score as whatever the
        # analytics payload provided (a scalar in practice); wrap a scalar into
        # the dashboard's expected {score,status,confidence,...} shape.
        if isinstance(raw, dict):
            return raw
        return {
            "score": raw,
            "status": status,
            "confidence": confidence,
            "missing_evidence": missing_evidence,
            "blocking_factors": blocking_factors,
        }

    return {
        "model_name": "production_readiness_dashboard_summary",
        "project_id": project_id,
        "assessment_id": assessment_id,
        "derived_view": True,
        "primary_authority": False,
        "source_tables": ["readiness_events"],
        "readiness_score": _score_dict(body.get("readiness_score")),
        "health_score": _score_dict(body.get("health_score")),
        "release_readiness_effect": body.get("release_readiness_effect"),
        "status": status,
        "confidence": confidence,
        "control_summary": {
            "total": len(controls),
            "pass": summary["pass"],
            "warn": summary["warn"],
            "fail": summary["fail"],
            "not_applicable": summary["not_applicable"],
            "manual_review": summary["manual_review"],
            "unknown": summary["unknown"],
        },
        "controls": controls,
        # The retired normalized findings / remediation / compliance tables are not
        # part of the readiness_events spine; blocking_factors + missing_evidence on
        # the score dicts carry the equivalent signal. Honestly empty, not fabricated.
        "findings": [],
        "remediation_work_orders": [],
        "compliance_review_flags": [],
        "empty_state": None,
    }


def _decode_json_fields(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    for key in list(decoded):
        if key.endswith("_json") and isinstance(decoded[key], str):
            decoded[key[:-5]] = json.loads(decoded[key])
    return decoded


def _empty_summary(project_id: str, missing: list[str]) -> dict[str, Any]:
    return {
        "model_name": "production_readiness_dashboard_summary",
        "project_id": project_id,
        "derived_view": True,
        "primary_authority": False,
        "status": "unavailable",
        "readiness_score": {
            "score": None,
            "status": "unavailable",
            "confidence": "none",
            "reason": "No SQLite-backed production readiness assessment exists for this project.",
            "missing_evidence": ["production readiness assessment"],
            "blocking_factors": [],
        },
        "health_score": {
            "score": None,
            "status": "unavailable",
            "confidence": "none",
            "reason": "No SQLite-backed production readiness assessment exists for this project.",
            "missing_evidence": ["production readiness assessment"],
            "blocking_factors": [],
        },
        "control_summary": {},
        "controls": [],
        "findings": [],
        "remediation_work_orders": [],
        "compliance_review_flags": [],
        "source_status": {
            "classification": "empty by design" if not missing else "missing schema",
            "missing": missing,
            "derived_view": True,
            "primary_authority": False,
        },
    }
