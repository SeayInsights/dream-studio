"""Manual-review lineage cleanup planning helpers.

The functions here are deliberately non-mutating. They classify legacy lineage
sources, prove whether current authority records preserve references, and
return purge eligibility for approved cleanup tooling to execute separately.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from typing import Any

DEFAULT_QUARANTINED_PROJECT_IDS: tuple[str, ...] = (
    ".temp",
    "a",
    "b",
    "my-project",
    "p1",
    "p2",
    "proj-1",
    "test-proj",
    "test_idempotent_handoff0",
    "test_main_writes_on_activity0",
    "tmpm_x_7sef",
)


def raw_skill_telemetry_status(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return migration/reference status for raw_skill_telemetry."""

    if not _exists(conn, "raw_skill_telemetry"):
        return {
            "source_table": "raw_skill_telemetry",
            "classification": "empty_by_design",
            "source_rows": 0,
            "mapped_rows": 0,
            "unmapped_source_ids": [],
            "correction_rows": 0,
            "purge_ready": True,
        }

    source_ids = _ids(conn, "raw_skill_telemetry", "id")
    mapped_ids: set[int] = set()
    if _exists(conn, "skill_invocations") and "metadata_json" in _columns(
        conn, "skill_invocations"
    ):
        for row in conn.execute("""
            SELECT metadata_json
            FROM skill_invocations
            WHERE purpose = 'legacy raw_skill_telemetry backfill'
            """):
            try:
                metadata = json.loads(row[0] or "{}")
            except json.JSONDecodeError:
                continue
            if metadata.get("source_table") != "raw_skill_telemetry":
                continue
            source_id = metadata.get("source_id")
            if isinstance(source_id, int):
                mapped_ids.add(source_id)
            elif isinstance(source_id, str) and source_id.isdigit():
                mapped_ids.add(int(source_id))

    correction_rows = _count(conn, "cor_skill_corrections")
    unmapped = sorted(source_ids - mapped_ids)
    if unmapped:
        classification = "not_migrated_manual_review"
    elif correction_rows:
        classification = "requires_correction_migration_first"
    else:
        classification = "migrated_then_purge_source"

    return {
        "source_table": "raw_skill_telemetry",
        "target_table": "skill_invocations",
        "classification": classification,
        "source_rows": len(source_ids),
        "mapped_rows": len(source_ids & mapped_ids),
        "unmapped_source_ids": unmapped,
        "correction_rows": correction_rows,
        "purge_ready": classification == "migrated_then_purge_source",
        "reference_basis": "skill_invocations.metadata_json.source_table/source_id",
    }


def correction_lineage_status(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return migration/reference status for cor_skill_corrections."""

    source_rows = _count(conn, "cor_skill_corrections")
    if source_rows == 0:
        return {
            "source_table": "cor_skill_corrections",
            "target_table": "learning_event_records",
            "classification": "empty_by_design",
            "source_rows": 0,
            "mapped_rows": 0,
            "unmapped_source_ids": [],
            "purge_ready": True,
        }

    mapped_ids: set[int] = set()
    if _exists(conn, "learning_event_records"):
        for row in conn.execute("""
            SELECT source_refs_json, metadata_json
            FROM learning_event_records
            WHERE event_class = 'operator_correction'
            """):
            refs = _loads(row[0], [])
            metadata = _loads(row[1], {})
            for ref in refs:
                prefix = "sqlite:cor_skill_corrections:"
                if isinstance(ref, str) and ref.startswith(prefix) and ref[len(prefix) :].isdigit():
                    mapped_ids.add(int(ref[len(prefix) :]))
            legacy_id = metadata.get("legacy_correction_id")
            if isinstance(legacy_id, int):
                mapped_ids.add(legacy_id)
            elif isinstance(legacy_id, str) and legacy_id.isdigit():
                mapped_ids.add(int(legacy_id))

    source_ids = _ids(conn, "cor_skill_corrections", "id")
    unmapped = sorted(source_ids - mapped_ids)
    classification = (
        "migrated_then_purge_source" if not unmapped else "migrate_to_learning_events_first"
    )
    return {
        "source_table": "cor_skill_corrections",
        "target_table": "learning_event_records",
        "classification": classification,
        "source_rows": source_rows,
        "mapped_rows": len(source_ids & mapped_ids),
        "unmapped_source_ids": unmapped,
        "purge_ready": classification == "migrated_then_purge_source",
        "reference_basis": "learning_event_records.source_refs_json or metadata_json.legacy_correction_id",
    }


def correction_learning_event_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Build canonical learning event rows from legacy correction records."""

    if not _exists(conn, "cor_skill_corrections"):
        return []

    rows = conn.execute("""
        SELECT
            c.id AS correction_id,
            c.telemetry_id,
            c.corrected_success,
            c.reason,
            c.corrected_at,
            t.skill_name,
            t.invoked_at,
            t.success AS original_success,
            t.project_id,
            t.session_id,
            t.event_id
        FROM cor_skill_corrections c
        LEFT JOIN raw_skill_telemetry t ON t.id = c.telemetry_id
        ORDER BY c.id
        """).fetchall()

    events: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        correction_id = int(item["correction_id"])
        telemetry_id = item.get("telemetry_id")
        skill_id = item.get("skill_name") or "unknown_skill"
        reason = (item.get("reason") or "").strip()
        reason_present = bool(reason)
        summary_reason = reason if reason_present else "no correction reason supplied"
        event_id = f"legacy-skill-correction-{correction_id}"
        invocation_ref = (
            f"sqlite:skill_invocations:legacy-raw-skill-{telemetry_id}" if telemetry_id else None
        )
        source_refs = [
            f"sqlite:cor_skill_corrections:{correction_id}",
        ]
        if telemetry_id is not None:
            source_refs.append(f"sqlite:raw_skill_telemetry:{telemetry_id}")
        if invocation_ref is not None:
            source_refs.append(invocation_ref)

        events.append(
            {
                "learning_event_id": event_id,
                "project_id": item.get("project_id") or "dream-studio",
                "milestone_id": "manual_review_lineage_purge_resolution",
                "task_id": "legacy-skill-correction-lineage",
                "process_run_id": "manual-review-lineage-cleanup",
                "component_type": "skill",
                "component_id": skill_id,
                "event_class": "operator_correction",
                "severity": "warning" if reason_present else "info",
                "summary": f"Legacy skill correction migrated for {skill_id}: {summary_reason}.",
                "observed_pattern": reason or "Legacy correction row did not include a reason.",
                "root_cause": reason or "Legacy correction records allowed blank reason values.",
                "remediation_hint": (
                    "Review repeated skill correction reasons for hardening candidates."
                    if reason_present
                    else "Require future skill corrections to capture a non-empty reason."
                ),
                "recurrence_key": f"skill_correction:{skill_id}:{_slug(reason or 'blank_reason')}",
                "promotion_status": "candidate" if reason_present else "observed",
                "source_refs": source_refs,
                "evidence_refs": [
                    "evidence/manual_review_lineage_reference_proof.yaml",
                    "evidence/manual_review_lineage_live_purge_evidence.yaml",
                ],
                "metadata": {
                    "legacy_correction_id": correction_id,
                    "legacy_telemetry_id": telemetry_id,
                    "corrected_success": item.get("corrected_success"),
                    "original_success": item.get("original_success"),
                    "legacy_invoked_at": item.get("invoked_at"),
                    "legacy_corrected_at": item.get("corrected_at"),
                    "legacy_session_id_present": bool(item.get("session_id")),
                    "legacy_event_id_present": bool(item.get("event_id")),
                    "reason_present": reason_present,
                    "source_tables": ["cor_skill_corrections", "raw_skill_telemetry"],
                },
                "created_at": item.get("corrected_at"),
            }
        )
    return events


def correction_hardening_candidates(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return hardening candidates for repeated non-empty correction patterns."""

    grouped: Counter[tuple[str, str]] = Counter()
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        metadata = event.get("metadata", {})
        if not metadata.get("reason_present"):
            continue
        key = (event["component_id"], event["recurrence_key"])
        grouped[key] += 1
        by_key[key] = event

    candidates: list[dict[str, Any]] = []
    for (component_id, recurrence_key), count in sorted(grouped.items()):
        if count < 3:
            continue
        event = by_key[(component_id, recurrence_key)]
        candidate_id = (
            f"legacy-skill-correction-hardening-{_slug(component_id)}-{_slug(recurrence_key)}"
        )
        candidates.append(
            {
                "candidate_id": candidate_id[:160],
                "learning_event_id": event["learning_event_id"],
                "component_type": "skill",
                "component_id": component_id,
                "current_version": None,
                "proposed_version": None,
                "hardening_type": "recurring_operator_correction",
                "status": "candidate",
                "validation_plan": [
                    "Confirm current skill behavior no longer repeats the migrated correction pattern.",
                    "Add a focused skill/workflow test before promotion if the pattern recurs.",
                ],
                "recurrence_check": {
                    "recurrence_key": recurrence_key,
                    "legacy_occurrences": count,
                    "source": "learning_event_records",
                },
                "rollback_plan": "Remove candidate row only; migrated learning events preserve source lineage.",
                "source_refs": [f"sqlite:learning_event_records:{event['learning_event_id']}"],
                "evidence_refs": ["evidence/manual_review_lineage_reference_proof.yaml"],
            }
        )
    return candidates


def quarantined_project_lineage_status(
    conn: sqlite3.Connection,
    project_ids: tuple[str, ...] = DEFAULT_QUARANTINED_PROJECT_IDS,
) -> dict[str, Any]:
    """Classify quarantined/temp project dependents without reading content."""

    project_rows = _project_rows(conn, project_ids)
    dependent_counts = {
        "ds_documents": _project_count(conn, "ds_documents", project_ids),
        "raw_approaches": _project_count(conn, "raw_approaches", project_ids),
        # reg_projects deleted in migration 084; no longer a dependent table
    }
    active_reference_counts = project_reference_counts(conn, project_ids)
    blocking_refs = {
        table: count
        for table, count in active_reference_counts.items()
        if not table.startswith("_backup_")
        and table not in {"ds_documents", "raw_approaches", "reg_projects"}
    }
    unsafe_projects = [
        row["project_id"]
        for row in project_rows
        if int(row.get("is_temp") or 0) != 1
        or str(row.get("status") or "").lower() not in {"inactive", "quarantined"}
    ]
    purge_ready = not unsafe_projects and not blocking_refs
    classification = "obsolete_purge" if purge_ready else "not_migrated_manual_review"
    return {
        "source": "quarantined_project_dependents",
        "classification": classification,
        "project_ids": [row["project_id"] for row in project_rows],
        "dependent_counts": dependent_counts,
        "active_reference_counts": active_reference_counts,
        "blocking_reference_counts": blocking_refs,
        "unsafe_projects": unsafe_projects,
        "purge_ready": purge_ready,
        "content_inspected": False,
        "classification_basis": "project status/is_temp/path metadata plus project_id reference scan",
    }


def project_reference_counts(
    conn: sqlite3.Connection,
    project_ids: tuple[str, ...] = DEFAULT_QUARANTINED_PROJECT_IDS,
) -> dict[str, int]:
    """Return tables with project_id references to the candidate project ids."""

    if not project_ids:
        return {}
    placeholders = ",".join("?" for _ in project_ids)
    counts: dict[str, int] = {}
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"):
        table = str(row[0])
        if "project_id" not in _columns(conn, table):
            continue
        try:
            count = int(
                conn.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE project_id IN ({placeholders})',
                    project_ids,
                ).fetchone()[0]
                or 0
            )
        except sqlite3.Error:
            continue
        if count:
            counts[table] = count
    return counts


def manual_review_lineage_plan(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return a consolidated non-mutating lineage cleanup plan."""

    raw_skill = raw_skill_telemetry_status(conn)
    corrections = correction_lineage_status(conn)
    projects = quarantined_project_lineage_status(conn)
    return {
        "model_name": "manual_review_lineage_cleanup_plan",
        "derived_view": True,
        "primary_authority": False,
        "execution_authorized": False,
        "sources": [raw_skill, corrections, projects],
        "all_purge_ready": all(
            item.get("purge_ready") for item in (raw_skill, corrections, projects)
        ),
    }


def _project_rows(conn: sqlite3.Connection, project_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    # reg_projects deleted in migration 084; use business_projects.
    if not _exists(conn, "business_projects") or not project_ids:
        return []
    placeholders = ",".join("?" for _ in project_ids)
    columns = _columns(conn, "business_projects")
    select_columns = [
        _select_column(columns, "project_id"),
        _select_column(columns, "project_path"),
        "name AS project_name",
        "NULL AS project_source",
        "0 AS is_temp",
        _select_column(columns, "status"),
        "NULL AS deactivation_reason",
    ]
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT {", ".join(select_columns)}
            FROM business_projects
            WHERE project_id IN ({placeholders})
            ORDER BY project_id
            """,
            project_ids,
        ).fetchall()
    ]


def _project_count(conn: sqlite3.Connection, table: str, project_ids: tuple[str, ...]) -> int:
    if not _exists(conn, table) or "project_id" not in _columns(conn, table) or not project_ids:
        return 0
    placeholders = ",".join("?" for _ in project_ids)
    return int(
        conn.execute(
            f'SELECT COUNT(*) FROM "{table}" WHERE project_id IN ({placeholders})',
            project_ids,
        ).fetchone()[0]
        or 0
    )


def _ids(conn: sqlite3.Connection, table: str, column: str) -> set[int]:
    if not _exists(conn, table):
        return set()
    return {int(row[0]) for row in conn.execute(f'SELECT "{column}" FROM "{table}"')}


def _count(conn: sqlite3.Connection, table: str) -> int:
    if not _exists(conn, table):
        return 0
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] or 0)


def _exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = ? AND type IN ('table', 'view')",
            (name,),
        ).fetchone()
        is not None
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "blank"


def _select_column(columns: set[str], name: str) -> str:
    if name in columns:
        return f'"{name}"'
    return f"NULL AS {name}"
