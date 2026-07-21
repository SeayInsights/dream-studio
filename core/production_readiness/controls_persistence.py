"""SQLite authority persistence for production-readiness assessments.

WO-GF-READINESS-INSIGHTS: split from ``core/production_readiness/controls.py``.
No logic changes — extracted verbatim.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .controls_shared import _stable_id, _table_exists


def record_production_readiness_assessment(
    conn: sqlite3.Connection,
    gate: dict[str, Any],
) -> bool:
    """Persist a gate result to SQLite authority using an injected connection.

    Returns False (no-op) if production_readiness_assessment_runs has been retired (migration 112+).
    """
    if not _table_exists(conn, "production_readiness_assessment_runs"):
        return False

    assessment_id = gate["assessment_id"]
    created_at = gate["created_at"]
    conn.execute(
        """
        INSERT OR REPLACE INTO production_readiness_assessment_runs(
            assessment_id, project_id, workflow_id, lifecycle_event, status,
            confidence, full_review_required, release_readiness_effect,
            health_score_json, readiness_score_json, missing_evidence_json,
            blocking_factors_json, source_refs_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            assessment_id,
            gate["project_id"],
            gate["workflow_id"],
            gate["lifecycle_event"],
            gate["release_readiness"]["status"],
            gate["project_readiness_score"]["confidence"],
            int(gate["full_review_required"]),
            gate["release_readiness"]["release_readiness_effect"],
            _json(gate["project_health_score"]),
            _json(gate["project_readiness_score"]),
            _json(gate["project_readiness_score"]["missing_evidence"]),
            _json(gate["project_readiness_score"]["blocking_factors"]),
            _json(["core/production_readiness/controls.py"]),
            created_at,
        ),
    )
    for result in gate["control_results"]:
        conn.execute(
            """
            INSERT OR REPLACE INTO production_readiness_control_results(
                result_id, assessment_id, project_id, control_id, control_family,
                name, skill_owner, workflow_owner, applicability, status,
                severity, blocking, score_impact, evidence_refs_json,
                source_refs_json, file_path, line, remediation_work_order,
                reason_not_applicable, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["result_id"],
                assessment_id,
                gate["project_id"],
                result["control_id"],
                result["control_family"],
                result["name"],
                result["skill_owner"],
                result["workflow_owner"],
                result["applicability"],
                result["status"],
                result["severity"],
                int(result["blocking"]),
                result["score_impact"],
                _json(result["evidence_refs"]),
                _json(result["source_refs"]),
                result.get("file_path"),
                result.get("line"),
                result.get("remediation_work_order"),
                result.get("reason_not_applicable"),
                created_at,
            ),
        )
    for finding in gate["findings"]:
        conn.execute(
            """
            INSERT OR REPLACE INTO production_readiness_findings(
                finding_id, project_id, assessment_id, control_id, control_family,
                skill_owner, workflow_owner, applicability, status, severity,
                blocking, score_impact, evidence_refs_json, source_refs_json,
                file_path, line, remediation_work_order, reason_not_applicable, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding["finding_id"],
                gate["project_id"],
                assessment_id,
                finding["control_id"],
                finding["control_family"],
                finding["skill_owner"],
                finding["workflow_owner"],
                finding["applicability"],
                finding["status"],
                finding["severity"],
                int(finding["blocking"]),
                finding["score_impact"],
                _json(finding["evidence_refs"]),
                _json(finding["source_refs"]),
                finding.get("file_path"),
                finding.get("line"),
                finding.get("remediation_work_order"),
                finding.get("reason_not_applicable"),
                created_at,
            ),
        )
    for work_order in gate["remediation_work_orders"]:
        conn.execute(
            """
            INSERT OR REPLACE INTO production_readiness_remediation_work_orders(
                remediation_work_order_id, project_id, assessment_id, control_id,
                finding_id, status, recommended_phase_type, objective,
                evidence_refs_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                work_order["remediation_work_order_id"],
                gate["project_id"],
                assessment_id,
                work_order["control_id"],
                work_order.get("finding_id"),
                work_order["status"],
                work_order["recommended_phase_type"],
                work_order["objective"],
                _json(work_order["evidence_refs"]),
                created_at,
            ),
        )
    for mapping in gate["overlap_matrix"]:
        mapping_id = _stable_id(
            "pr-map",
            mapping["existing_skill_control_name"],
            mapping["proposed_canonical_owner"],
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO production_readiness_skill_control_mappings(
                mapping_id, control_id, control_family, existing_skill_or_check,
                proposed_canonical_owner, overlap_reason, decision, evidence_json,
                validation_requirement, rollback_or_supersession_plan,
                dashboard_project_health_impact, contract_atlas_impact, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mapping_id,
                mapping["proposed_canonical_owner"],
                mapping["proposed_canonical_owner"],
                mapping["existing_skill_control_name"],
                mapping["proposed_canonical_owner"],
                mapping["overlap_reason"],
                mapping["decision"],
                _json(mapping["evidence"]),
                mapping["validation_requirement"],
                mapping["rollback_supersession_plan"],
                mapping["dashboard_project_health_impact"],
                mapping["contract_atlas_impact"],
                created_at,
            ),
        )
    _record_scorecards(conn, gate, created_at)
    # _record_compliance_flags removed — compliance_review_flags dropped in migration 133.
    conn.commit()
    return True


def _record_scorecards(conn: sqlite3.Connection, gate: dict[str, Any], created_at: str) -> None:
    # release_readiness_records dropped in migration 133 (persist=False dead gate — no
    # production caller ever passes persist=True). Only writes to project_readiness_scorecards
    # and project_health_scorecards remain; release_readiness_records write removed.
    if not _table_exists(conn, "project_readiness_scorecards"):
        return
    for table, prefix, score_key, score_column in (
        (
            "project_readiness_scorecards",
            "readiness-scorecard",
            "project_readiness_score",
            "readiness_score",
        ),
        ("project_health_scorecards", "health-scorecard", "project_health_score", "health_score"),
    ):
        score = gate[score_key]
        conn.execute(
            f"""
            INSERT OR REPLACE INTO {table}(
                scorecard_id, project_id, assessment_id, {score_column},
                confidence, status, missing_evidence_json,
                blocking_factors_json, evidence_refs_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _stable_id(prefix, gate["assessment_id"]),
                gate["project_id"],
                gate["assessment_id"],
                score["score"],
                score["confidence"],
                score["status"],
                _json(score["missing_evidence"]),
                _json(score["blocking_factors"]),
                _json([]),
                created_at,
            ),
        )
    # release_readiness_records write removed — table dropped migration 133.


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)
