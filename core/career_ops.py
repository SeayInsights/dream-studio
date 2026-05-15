"""Private optional Career Ops authority and dashboard read model."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

CAREER_OPS_SCHEMA = "dream_studio.career_ops.v1"

CAREER_OPS_TABLES: tuple[str, ...] = (
    "career_profiles",
    "career_profile_fields",
    "career_role_targets",
    "career_resume_versions",
    "career_cover_letter_versions",
    "career_portfolio_artifacts",
    "career_case_studies",
    "career_job_opportunities",
    "career_applications",
    "career_application_events",
    "career_application_field_mappings",
    "career_browser_automation_runs",
    "career_interview_story_bank",
    "career_evidence_refs",
    "career_scorecards",
)

CAREER_SCORECARD_TYPES: tuple[str, ...] = (
    "target_role_readiness_score",
    "portfolio_readiness_score",
    "resume_evidence_strength",
    "interview_story_strength",
    "architecture_explanation_strength",
    "compensation_strategy_confidence",
    "public_demo_readiness",
    "consulting_offer_readiness",
    "application_readiness_score",
)

APPLICATION_AUTOMATION_BOUNDARIES: tuple[str, ...] = (
    "do_not_create_accounts",
    "do_not_bypass_captchas",
    "do_not_misrepresent_operator",
    "do_not_submit_without_explicit_approval_or_approved_policy",
    "pause_for_operator_review_on_ambiguous_questions",
    "store_sensitive_fields_only_in_approved_local_private_storage",
    "do_not_print_secrets_or_private_identifiers_unnecessarily",
    "record_filled_skipped_and_operator_input_required",
)

PUBLIC_EXPORT_EXCLUSIONS: tuple[str, ...] = (
    "career_profiles",
    "career_profile_fields",
    "career_resume_versions",
    "career_cover_letter_versions",
    "career_applications",
    "career_application_events",
    "career_application_field_mappings",
    "career_browser_automation_runs",
    "career_interview_story_bank",
    "career_scorecards",
)


def career_ops_status(
    conn: sqlite3.Connection, *, enabled_override: bool | None = None
) -> dict[str, Any]:
    """Return the optional/private Career Ops module status without writing."""

    missing = missing_career_ops_tables(conn)
    enabled = bool(enabled_override) if enabled_override is not None else _career_ops_enabled(conn)
    return {
        "schema": CAREER_OPS_SCHEMA,
        "model_name": "dream_studio_career_ops_status",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "db_write_authorized": False,
        "module_id": "career_ops",
        "enabled": enabled,
        "opt_in_required": True,
        "private_by_default": True,
        "schema_status": "available" if not missing else "schema_missing",
        "missing_tables": missing,
        "source_tables": list(CAREER_OPS_TABLES),
        "public_export_exclusions": list(PUBLIC_EXPORT_EXCLUSIONS),
        "application_automation_boundaries": list(APPLICATION_AUTOMATION_BOUNDARIES),
        "empty_state": "Career Ops is disabled until an operator enables the private local module.",
    }


def career_ops_dashboard_summary(
    conn: sqlite3.Connection, *, enabled_override: bool | None = None
) -> dict[str, Any]:
    """Build the private dashboard summary over Career Ops authority."""

    status = career_ops_status(conn, enabled_override=enabled_override)
    if status["schema_status"] != "available":
        return {
            **status,
            "model_name": "dream_studio_career_ops_dashboard_summary",
            "dashboard_private_module": True,
            "editable_when_enabled": False,
            "sections": {},
        }

    enabled = bool(status["enabled"])
    profiles = _rows(
        conn,
        """
        SELECT profile_id, owner_label, enabled, privacy_scope, profile_status,
               headline, summary, updated_at
        FROM career_profiles
        ORDER BY updated_at DESC
        """,
    )
    active_profile_ids = [row["profile_id"] for row in profiles if row["enabled"]]
    scorecards = _scorecard_summary(conn, active_profile_ids)
    applications = _application_summary(conn, active_profile_ids)
    profile_completeness = _profile_completeness(conn, active_profile_ids)
    return {
        **status,
        "model_name": "dream_studio_career_ops_dashboard_summary",
        "dashboard_private_module": True,
        "editable_when_enabled": enabled,
        "career_data_in_public_exports": False,
        "team_rollup_inclusion": False,
        "demo_packet_inclusion": "redacted_operator_approval_required",
        "profile_count": len(profiles),
        "active_profile_count": len(active_profile_ids),
        "sections": {
            "profile_completeness": profile_completeness,
            "target_role_strategy": _count_section(conn, "career_role_targets", active_profile_ids),
            "resume_variants": _count_section(conn, "career_resume_versions", active_profile_ids),
            "portfolio_readiness": _count_section(
                conn, "career_portfolio_artifacts", active_profile_ids
            ),
            "application_pipeline": applications,
            "interview_prep": _count_section(
                conn, "career_interview_story_bank", active_profile_ids
            ),
            "evidence_strength": _count_section(conn, "career_evidence_refs", active_profile_ids),
            "scorecards": scorecards,
        },
        "recommended_next_action": _recommended_next_action(enabled, profiles, scorecards),
    }


def record_career_profile(conn: sqlite3.Connection, **values: Any) -> None:
    """Persist an opt-in career profile through an injected connection."""

    require_career_ops_tables(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO career_profiles (
            profile_id, owner_label, enabled, privacy_scope, profile_status,
            headline, summary, source_refs_json, evidence_refs_json,
            metadata_json, updated_at
        ) VALUES (
            :profile_id, :owner_label, :enabled, :privacy_scope, :profile_status,
            :headline, :summary, :source_refs_json, :evidence_refs_json,
            :metadata_json, datetime('now')
        )
        """,
        {
            "profile_id": values["profile_id"],
            "owner_label": values.get("owner_label"),
            "enabled": 1 if values.get("enabled") else 0,
            "privacy_scope": values.get("privacy_scope", "private_local"),
            "profile_status": values.get("profile_status", "draft"),
            "headline": values.get("headline"),
            "summary": values.get("summary"),
            "source_refs_json": _json(values.get("source_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
            "metadata_json": _json(values.get("metadata"), {}),
        },
    )


def require_career_ops_tables(conn: sqlite3.Connection) -> None:
    missing = missing_career_ops_tables(conn)
    if missing:
        raise RuntimeError(f"career ops schema missing tables: {missing}")


def missing_career_ops_tables(conn: sqlite3.Connection) -> list[str]:
    placeholders = ",".join("?" for _ in CAREER_OPS_TABLES)
    rows = conn.execute(
        f"SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ({placeholders})",
        CAREER_OPS_TABLES,
    ).fetchall()
    found = {str(row[0]) for row in rows}
    return sorted(set(CAREER_OPS_TABLES) - found)


def _career_ops_enabled(conn: sqlite3.Connection) -> bool:
    if missing_career_ops_tables(conn):
        return False
    row = conn.execute("SELECT COUNT(*) FROM career_profiles WHERE enabled = 1").fetchone()
    return bool(row and row[0])


def _scorecard_summary(conn: sqlite3.Connection, profile_ids: Sequence[str]) -> dict[str, Any]:
    rows = _filtered_rows(conn, "career_scorecards", profile_ids, "updated_at DESC")
    by_type = {row["scorecard_type"]: row for row in rows}
    items: list[dict[str, Any]] = []
    for scorecard_type in CAREER_SCORECARD_TYPES:
        row = by_type.get(scorecard_type)
        if row:
            items.append(
                {
                    "scorecard_type": scorecard_type,
                    "status": row["status"],
                    "confidence": row["confidence"],
                    "score_value": row["score_value"],
                    "missing_evidence": _decode(row["missing_evidence_json"], []),
                    "evidence_refs": _decode(row["evidence_refs_json"], []),
                }
            )
        else:
            items.append(
                {
                    "scorecard_type": scorecard_type,
                    "status": "unavailable",
                    "confidence": "unknown",
                    "score_value": None,
                    "reason": "No evidence-backed scorecard has been recorded.",
                }
            )
    return {"count": len(rows), "items": items}


def _application_summary(conn: sqlite3.Connection, profile_ids: Sequence[str]) -> dict[str, Any]:
    rows = _filtered_rows(conn, "career_applications", profile_ids, "updated_at DESC")
    statuses = Counter(row["application_status"] for row in rows)
    submitted = [row for row in rows if row["submitted_at"]]
    return {
        "count": len(rows),
        "submitted_count": len(submitted),
        "status_counts": dict(sorted(statuses.items())),
        "items": [
            {
                "application_id": row["application_id"],
                "job_opportunity_id": row["job_opportunity_id"],
                "application_status": row["application_status"],
                "follow_up_at": row["follow_up_at"],
                "submission_policy": row["submission_policy"],
            }
            for row in rows[:25]
        ],
    }


def _profile_completeness(conn: sqlite3.Connection, profile_ids: Sequence[str]) -> dict[str, Any]:
    if not profile_ids:
        return {
            "status": "unavailable",
            "reason": "Career Ops has no enabled private profile.",
            "confidence": "unknown",
        }
    field_count = _filtered_count(conn, "career_profile_fields", profile_ids)
    evidence_count = _filtered_count(conn, "career_evidence_refs", profile_ids)
    status = "partial" if field_count else "unavailable"
    return {
        "status": status,
        "confidence": "medium" if evidence_count else "low",
        "field_count": field_count,
        "evidence_ref_count": evidence_count,
        "missing_evidence_behavior": "partial_or_unavailable_with_reason",
    }


def _recommended_next_action(
    enabled: bool, profiles: Sequence[Mapping[str, Any]], scorecards: Mapping[str, Any]
) -> str:
    if not enabled:
        return "Enable Career Ops explicitly before storing private career/application data."
    if not profiles:
        return "Create a private career profile before adding role targets or applications."
    unavailable = [
        item["scorecard_type"]
        for item in scorecards.get("items", [])
        if item.get("status") == "unavailable"
    ]
    if unavailable:
        return f"Record evidence-backed scorecards for: {', '.join(unavailable[:3])}."
    return "Review application pipeline and follow-up dates."


def _count_section(
    conn: sqlite3.Connection, table: str, profile_ids: Sequence[str]
) -> dict[str, Any]:
    count = _filtered_count(conn, table, profile_ids)
    return {
        "count": count,
        "status": "available" if count else "empty",
        "empty_state": f"No {table} records have been captured.",
    }


def _filtered_count(conn: sqlite3.Connection, table: str, profile_ids: Sequence[str]) -> int:
    if not profile_ids:
        return 0
    placeholders = ",".join("?" for _ in profile_ids)
    row = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE profile_id IN ({placeholders})",
        tuple(profile_ids),
    ).fetchone()
    return int(row[0] if row else 0)


def _filtered_rows(
    conn: sqlite3.Connection, table: str, profile_ids: Sequence[str], order_by: str
) -> list[dict[str, Any]]:
    if not profile_ids:
        return []
    placeholders = ",".join("?" for _ in profile_ids)
    return _rows(
        conn,
        f"SELECT * FROM {table} WHERE profile_id IN ({placeholders}) ORDER BY {order_by}",
        tuple(profile_ids),
    )


def _rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def _json(value: Any, default: Any) -> str:
    return json.dumps(default if value is None else value, sort_keys=True)


def _decode(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
