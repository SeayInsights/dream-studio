"""Reconcile legacy backup canonical_events into current authority tables.

The legacy canonical event stream is useful as historical evidence, but it is
not restored as active authority. This module profiles it read-only, builds an
idempotent import plan, and imports only high-confidence mapped events into the
current telemetry spine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SOURCE_TABLE = "canonical_events"
IMPORT_MAP_TABLE = "legacy_canonical_event_import_map"
HIGH_CONFIDENCE = 0.9


@dataclass(frozen=True)
class LegacyEvent:
    event_id: str
    event_type: str
    timestamp: str
    trace: dict[str, Any]
    severity: str
    payload: dict[str, Any]
    actor: dict[str, Any] | None
    confidence_score: float | None
    source_type: str | None
    created_at: str
    raw_trace: str
    raw_payload: str
    raw_actor: str | None


@dataclass(frozen=True)
class ImportPlanEntry:
    legacy_event_id: str
    source_table: str
    event_type: str
    taxonomy: str
    target_table: str | None
    target_record_id: str | None
    import_status: str
    confidence: float
    payload_hash: str
    reason: str
    source_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...] = ()

    @property
    def import_map_id(self) -> str:
        material = "|".join(
            [
                self.legacy_event_id,
                self.source_table,
                self.target_table or "",
                self.target_record_id or "",
            ]
        )
        return "legacy-canonical-map-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def backup_db_path(backup_home: Path) -> Path:
    return Path(backup_home) / "state" / "studio.db"


def _readonly_uri(path: Path) -> str:
    return f"file:{Path(path).resolve().as_posix()}?mode=ro"


def connect_backup_readonly(backup_home_or_db: Path) -> sqlite3.Connection:
    """Open the backup database read-only."""

    path = Path(backup_home_or_db)
    if path.is_dir():
        path = backup_db_path(path)
    conn = sqlite3.connect(_readonly_uri(path), uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def connect_active(active_home_or_db: Path) -> sqlite3.Connection:
    path = Path(active_home_or_db)
    if path.is_dir():
        path = path / "state" / "studio.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_json(value: str | None) -> Any:
    if value in (None, ""):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"__unparsed__": value}


def _coerce_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _payload_hash(raw_payload: str, raw_trace: str, raw_actor: str | None) -> str:
    material = json.dumps(
        {"payload": raw_payload, "trace": raw_trace, "actor": raw_actor},
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _stable_suffix(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _source_ref(event: LegacyEvent) -> str:
    return f"backup:{SOURCE_TABLE}:{event.event_id}"


def _event_name(event_type: str) -> str:
    return event_type.replace(".", " ").replace("_", " ").title()


def _actor_fields(event: LegacyEvent) -> dict[str, str | None]:
    actor = event.actor or {}
    return {
        "actor_type": actor.get("actor_type") or actor.get("type"),
        "actor_id": actor.get("actor_id") or actor.get("id"),
    }


def _project_id(event: LegacyEvent) -> str | None:
    context = event.payload.get("context")
    if not isinstance(context, dict):
        context = {}
    return (
        event.trace.get("project_id")
        or event.payload.get("project_id")
        or context.get("project_id")
    )


def _process_run_id(event: LegacyEvent) -> str | None:
    if event.trace.get("workflow_id"):
        return f"legacy-workflow-{event.trace['workflow_id']}"
    if event.payload.get("workflow_id"):
        return f"legacy-workflow-{event.payload['workflow_id']}"
    if event.payload.get("scan_id"):
        return f"legacy-security-scan-{event.payload['scan_id']}"
    if event.payload.get("session_id"):
        return f"legacy-session-{event.payload['session_id']}"
    execution_id = event.trace.get("execution_id")
    if execution_id:
        return f"legacy-execution-{execution_id}"
    return None


def _event_metadata(event: LegacyEvent, *, taxonomy: str, reason: str) -> dict[str, Any]:
    return {
        "legacy_event_type": event.event_type,
        "legacy_trace": event.trace,
        "legacy_payload": event.payload,
        "legacy_actor": event.actor,
        "legacy_created_at": event.created_at,
        "legacy_source_type": event.source_type,
        "legacy_confidence_score": event.confidence_score,
        "reconciliation_taxonomy": taxonomy,
        "reconciliation_reason": reason,
    }


def iter_legacy_events(conn: sqlite3.Connection) -> Iterable[LegacyEvent]:
    rows = conn.execute("""
        SELECT event_id, event_type, timestamp, trace, severity, payload, actor,
               confidence_score, source_type, created_at
        FROM canonical_events
        ORDER BY timestamp, event_id
        """)
    for row in rows:
        yield LegacyEvent(
            event_id=str(row["event_id"]),
            event_type=str(row["event_type"]),
            timestamp=str(row["timestamp"]),
            trace=_coerce_dict(_parse_json(row["trace"])),
            severity=str(row["severity"]),
            payload=_coerce_dict(_parse_json(row["payload"])),
            actor=(
                _coerce_dict(_parse_json(row["actor"])) if row["actor"] not in (None, "") else None
            ),
            confidence_score=row["confidence_score"],
            source_type=row["source_type"],
            created_at=str(row["created_at"]),
            raw_trace=str(row["trace"]),
            raw_payload=str(row["payload"]),
            raw_actor=row["actor"],
        )


def profile_canonical_events(backup_conn: sqlite3.Connection) -> dict[str, Any]:
    columns = [dict(row) for row in backup_conn.execute(f"PRAGMA table_info({SOURCE_TABLE})")]
    total = int(backup_conn.execute(f"SELECT COUNT(*) FROM {SOURCE_TABLE}").fetchone()[0])
    event_types = [{"event_type": row[0], "count": row[1]} for row in backup_conn.execute(f"""
            SELECT event_type, COUNT(*) AS count
            FROM {SOURCE_TABLE}
            GROUP BY event_type
            ORDER BY count DESC, event_type
            """)]
    bounds = backup_conn.execute(
        f"SELECT MIN(timestamp), MAX(timestamp), MIN(created_at), MAX(created_at) FROM {SOURCE_TABLE}"
    ).fetchone()
    return {
        "source_table": SOURCE_TABLE,
        "read_only": True,
        "row_count": total,
        "columns": columns,
        "event_type_count": len(event_types),
        "event_types": event_types,
        "timestamp_min": bounds[0],
        "timestamp_max": bounds[1],
        "created_at_min": bounds[2],
        "created_at_max": bounds[3],
    }


def ensure_import_map_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS legacy_canonical_event_import_map (
            import_map_id TEXT PRIMARY KEY,
            legacy_event_id TEXT NOT NULL,
            source_table TEXT NOT NULL DEFAULT 'canonical_events',
            event_type TEXT NOT NULL,
            taxonomy TEXT NOT NULL,
            target_table TEXT,
            target_record_id TEXT,
            import_status TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0,
            payload_hash TEXT NOT NULL,
            reason TEXT NOT NULL,
            source_refs_json TEXT NOT NULL DEFAULT '[]',
            evidence_refs_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_legacy_event_import_map_target
        ON legacy_canonical_event_import_map(
            legacy_event_id,
            source_table,
            COALESCE(target_table, ''),
            COALESCE(target_record_id, '')
        )
        """)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _record_exists(conn: sqlite3.Connection, table: str, id_column: str, record_id: str) -> bool:
    if not _table_exists(conn, table):
        return False
    row = conn.execute(
        f"SELECT 1 FROM {table} WHERE {id_column} = ? LIMIT 1",
        (record_id,),
    ).fetchone()
    return row is not None


def _base_entry(
    event: LegacyEvent,
    *,
    taxonomy: str,
    target_table: str | None,
    target_record_id: str | None,
    status: str,
    confidence: float,
    reason: str,
) -> ImportPlanEntry:
    return ImportPlanEntry(
        legacy_event_id=event.event_id,
        source_table=SOURCE_TABLE,
        event_type=event.event_type,
        taxonomy=taxonomy,
        target_table=target_table,
        target_record_id=target_record_id,
        import_status=status,
        confidence=confidence,
        payload_hash=_payload_hash(event.raw_payload, event.raw_trace, event.raw_actor),
        reason=reason,
        source_refs=(_source_ref(event),),
    )


def _target_status(
    active_conn: sqlite3.Connection,
    table: str,
    id_column: str,
    record_id: str,
) -> str:
    return (
        "skipped_duplicate"
        if _record_exists(active_conn, table, id_column, record_id)
        else "pending_import"
    )


def _status_reason(status: str, import_reason: str) -> str:
    if status == "skipped_duplicate":
        return "Target record already exists in current authority."
    return import_reason


def _int_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _float_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _provider_from_model(model: str | None) -> str | None:
    if not model:
        return None
    normalized = model.lower()
    if "claude" in normalized or "anthropic" in normalized:
        return "anthropic"
    if "gpt" in normalized or "openai" in normalized:
        return "openai"
    if "gemini" in normalized or "google" in normalized:
        return "google"
    return None


def _map_execution_event(
    active_conn: sqlite3.Connection,
    event: LegacyEvent,
    *,
    taxonomy: str,
    reason: str,
    confidence: float = HIGH_CONFIDENCE,
) -> ImportPlanEntry:
    target_id = f"legacy-canonical-event-{_stable_suffix(event.event_id)}"
    status = _target_status(active_conn, "execution_events", "event_id", target_id)
    return _base_entry(
        event,
        taxonomy=taxonomy,
        target_table="execution_events",
        target_record_id=target_id,
        status=status,
        confidence=confidence,
        reason=_status_reason(status, reason),
    )


def _map_skill_event(active_conn: sqlite3.Connection, event: LegacyEvent) -> list[ImportPlanEntry]:
    if event.event_type == "raw.migrated.raw_skill_telemetry" and event.payload.get("id"):
        invocation_id = f"legacy-raw-skill-{event.payload['id']}"
        reason = "Raw skill telemetry has stable id, skill name, timestamp, and status."
    else:
        invocation_id = f"legacy-canonical-skill-{_stable_suffix(event.event_id)}"
        reason = "Skill execution event has a clear skill identifier and status."
    status = _target_status(active_conn, "skill_invocations", "invocation_id", invocation_id)
    return [
        _map_execution_event(
            active_conn,
            event,
            taxonomy="skill_invocation",
            reason="Execution event preserves the source-refed legacy skill event.",
        ),
        _base_entry(
            event,
            taxonomy="skill_invocation",
            target_table="skill_invocations",
            target_record_id=invocation_id,
            status=status,
            confidence=HIGH_CONFIDENCE,
            reason=_status_reason(status, reason),
        ),
    ]


def _map_workflow_event(
    active_conn: sqlite3.Connection, event: LegacyEvent
) -> list[ImportPlanEntry]:
    workflow_id = event.payload.get("workflow_id") or event.trace.get("workflow_id")
    if not workflow_id:
        return [
            _base_entry(
                event,
                taxonomy="workflow_invocation",
                target_table=None,
                target_record_id=None,
                status="manual_review_required",
                confidence=0.4,
                reason="Workflow event lacks a workflow_id needed for current authority mapping.",
            )
        ]
    invocation_id = f"legacy-canonical-workflow-{_stable_suffix(event.event_id)}"
    status = _target_status(active_conn, "workflow_invocations", "invocation_id", invocation_id)
    return [
        _map_execution_event(
            active_conn,
            event,
            taxonomy="workflow_invocation",
            reason="Execution event preserves source-refed legacy workflow lifecycle evidence.",
        ),
        _base_entry(
            event,
            taxonomy="workflow_invocation",
            target_table="workflow_invocations",
            target_record_id=invocation_id,
            status=status,
            confidence=HIGH_CONFIDENCE,
            reason=_status_reason(status, "Workflow event has workflow_id and lifecycle status."),
        ),
    ]


def _hook_target_id(event: LegacyEvent) -> str:
    original_id = event.trace.get("original_id") or event.payload.get("activity_id")
    if original_id:
        return f"legacy-hook-execution-{original_id}"
    return f"legacy-canonical-hook-{_stable_suffix(event.event_id)}"


def _map_hook_event(active_conn: sqlite3.Connection, event: LegacyEvent) -> list[ImportPlanEntry]:
    target_id = _hook_target_id(event)
    status = _target_status(active_conn, "hook_invocations", "invocation_id", target_id)
    return [
        _map_execution_event(
            active_conn,
            event,
            taxonomy="hook_invocation",
            reason="Execution event preserves source-refed legacy hook evidence.",
        ),
        _base_entry(
            event,
            taxonomy="hook_invocation",
            target_table="hook_invocations",
            target_record_id=target_id,
            status=status,
            confidence=HIGH_CONFIDENCE,
            reason=_status_reason(status, "Hook event has hook name/type and status."),
        ),
    ]


def _map_security_scan_event(
    active_conn: sqlite3.Connection, event: LegacyEvent
) -> list[ImportPlanEntry]:
    if not event.payload.get("scan_id"):
        return [
            _base_entry(
                event,
                taxonomy="security_scan",
                target_table=None,
                target_record_id=None,
                status="manual_review_required",
                confidence=0.5,
                reason="Security scan event lacks scan_id.",
            )
        ]
    return [
        _map_execution_event(
            active_conn,
            event,
            taxonomy="security_scan",
            reason="Security scan lifecycle event has stable scan_id and status payload.",
        )
    ]


def _map_security_finding_event(
    active_conn: sqlite3.Connection, event: LegacyEvent
) -> list[ImportPlanEntry]:
    finding_id = event.payload.get("finding_id")
    if not finding_id:
        return [
            _base_entry(
                event,
                taxonomy="security_finding",
                target_table=None,
                target_record_id=None,
                status="manual_review_required",
                confidence=0.4,
                reason="Security finding event lacks finding_id.",
            )
        ]
    if _record_exists(active_conn, "security_findings", "finding_id", str(finding_id)):
        return [
            _base_entry(
                event,
                taxonomy="security_finding",
                target_table="security_findings",
                target_record_id=str(finding_id),
                status="skipped_duplicate",
                confidence=HIGH_CONFIDENCE,
                reason="Finding already exists in current security_findings authority.",
            )
        ]
    return [
        _base_entry(
            event,
            taxonomy="security_finding",
            target_table="security_findings",
            target_record_id=str(finding_id),
            status="manual_review_required",
            confidence=0.6,
            reason="Finding event lacks file/line/description details required for safe finding import.",
        )
    ]


def _map_token_usage_event(
    active_conn: sqlite3.Connection, event: LegacyEvent
) -> list[ImportPlanEntry]:
    input_tokens = _int_value(event.payload.get("input_tokens"))
    output_tokens = _int_value(event.payload.get("output_tokens"))
    cached_tokens = _int_value(event.payload.get("cached_tokens")) or 0
    total_tokens = _int_value(event.payload.get("total_tokens"))
    model = event.payload.get("model")
    recorded_at = event.payload.get("recorded_at") or event.timestamp
    if input_tokens is None or output_tokens is None or not model or not recorded_at:
        return _single_classification(
            event,
            taxonomy="token_usage",
            status="manual_review_required",
            confidence=0.45,
            reason="Token usage event lacks nonnegative token counts, model, or timestamp required for safe import.",
        )
    computed_total = input_tokens + output_tokens + cached_tokens
    if total_tokens is not None and total_tokens != computed_total:
        return _single_classification(
            event,
            taxonomy="token_usage",
            status="manual_review_required",
            confidence=0.55,
            reason="Token usage total does not match input, output, and cached token counts.",
        )
    if event.event_type.startswith("raw.migrated.raw_token_usage") and event.payload.get("id"):
        target_id = f"legacy-raw-token-{event.payload['id']}"
        reason = (
            "Raw token usage has stable legacy id, token counts, model, and timestamp; "
            "cost was not present in the legacy source."
        )
    elif event.event_type == "telemetry.token_usage" and event.payload.get("session_id"):
        target_id = f"legacy-canonical-token-{_stable_suffix(event.event_id)}"
        reason = "Telemetry token usage has session id, token counts, model, and timestamp."
    else:
        return _single_classification(
            event,
            taxonomy="token_usage",
            status="manual_review_required",
            confidence=0.55,
            reason="Token usage event lacks stable raw id or session context needed for deduplication.",
        )
    status = _target_status(active_conn, "token_usage_records", "token_usage_id", target_id)
    return [
        _base_entry(
            event,
            taxonomy="token_usage",
            target_table="token_usage_records",
            target_record_id=target_id,
            status=status,
            confidence=HIGH_CONFIDENCE,
            reason=_status_reason(status, reason),
        )
    ]


def _single_classification(
    event: LegacyEvent,
    *,
    taxonomy: str,
    status: str,
    confidence: float,
    reason: str,
) -> list[ImportPlanEntry]:
    return [
        _base_entry(
            event,
            taxonomy=taxonomy,
            target_table=None,
            target_record_id=None,
            status=status,
            confidence=confidence,
            reason=reason,
        )
    ]


def map_event(active_conn: sqlite3.Connection, event: LegacyEvent) -> list[ImportPlanEntry]:
    event_type = event.event_type
    if event_type in {
        "raw.migrated.raw_skill_telemetry",
        "skill.execution.completed",
        "telemetry.skill_execution",
    }:
        return _map_skill_event(active_conn, event)
    if event_type in {
        "workflow.execution.started",
        "workflow.execution.completed",
        "workflow.phase.completed",
    }:
        return _map_workflow_event(active_conn, event)
    if event_type.startswith("hook.execution."):
        return _map_hook_event(active_conn, event)
    if event_type.startswith("security.scan."):
        return _map_security_scan_event(active_conn, event)
    if event_type == "security.finding.detected":
        return _map_security_finding_event(active_conn, event)
    if event_type == "system.activity.hook_execution":
        return _single_classification(
            event,
            taxonomy="hook_invocation",
            status="superseded_by_current_authority",
            confidence=0.8,
            reason="Legacy activity hook rows are superseded by hook_invocations imported from hook execution records.",
        )
    if event_type == "event.validation.failed":
        return _single_classification(
            event,
            taxonomy="validation_failure",
            status="retention_only",
            confidence=0.75,
            reason="High-volume legacy validator noise is preserved in backup; current dashboard does not require active import.",
        )
    if event_type.startswith("project."):
        return _single_classification(
            event,
            taxonomy="project_authority",
            status="superseded_by_current_authority",
            confidence=0.8,
            reason="Project authority was rehydrated into current registry/authority tables.",
        )
    if (
        event_type.startswith("raw.migrated.raw_token_usage")
        or event_type == "telemetry.token_usage"
    ):
        return _map_token_usage_event(active_conn, event)
    if event_type.startswith("raw.migrated."):
        return _single_classification(
            event,
            taxonomy="raw_legacy_migration",
            status="retention_only",
            confidence=0.7,
            reason="Raw legacy table event is retained in backup unless mapped by a specific high-confidence rule.",
        )
    if event_type.startswith("ingestion."):
        return _single_classification(
            event,
            taxonomy="ingestion_trace",
            status="retention_only",
            confidence=0.7,
            reason="Legacy ingestion trace is historical pipeline evidence, not current operational authority.",
        )
    if event_type.startswith("system.activity."):
        return _single_classification(
            event,
            taxonomy="activity_log",
            status="retention_only",
            confidence=0.65,
            reason="Legacy activity-log projection lacks enough current-table semantics for safe import.",
        )
    return _single_classification(
        event,
        taxonomy="unknown",
        status="manual_review_required",
        confidence=0.0,
        reason="No current high-confidence mapping rule exists for this event type.",
    )


def build_import_plan(
    backup_conn: sqlite3.Connection, active_conn: sqlite3.Connection
) -> list[ImportPlanEntry]:
    entries: list[ImportPlanEntry] = []
    for event in iter_legacy_events(backup_conn):
        entries.extend(map_event(active_conn, event))
    return entries


def summarize_plan(
    profile: Mapping[str, Any], entries: Sequence[ImportPlanEntry]
) -> dict[str, Any]:
    by_status = Counter(entry.import_status for entry in entries)
    by_taxonomy = Counter(entry.taxonomy for entry in entries)
    by_event_type = Counter(entry.event_type for entry in entries)
    target_counts = Counter(
        entry.target_table
        for entry in entries
        if entry.target_table and entry.import_status == "pending_import"
    )
    source_events_with_import = {
        entry.legacy_event_id
        for entry in entries
        if entry.import_status == "pending_import" and entry.confidence >= HIGH_CONFIDENCE
    }
    manual_review_events = {
        entry.legacy_event_id
        for entry in entries
        if entry.import_status == "manual_review_required"
    }
    duplicate_events = {
        entry.legacy_event_id for entry in entries if entry.import_status == "skipped_duplicate"
    }
    return {
        "profile": dict(profile),
        "entry_count": len(entries),
        "source_event_count": profile.get("row_count"),
        "source_events_with_high_confidence_import": len(source_events_with_import),
        "pending_import_entries": by_status.get("pending_import", 0),
        "skipped_duplicate_events": len(duplicate_events),
        "manual_review_events": len(manual_review_events),
        "status_counts": dict(sorted(by_status.items())),
        "taxonomy_counts": dict(sorted(by_taxonomy.items())),
        "event_type_counts_in_plan": dict(sorted(by_event_type.items())),
        "pending_target_counts": dict(sorted(target_counts.items())),
        "canonical_events_active_authority": False,
    }


def _entry_to_row(entry: ImportPlanEntry, status: str | None = None) -> dict[str, Any]:
    return {
        "import_map_id": entry.import_map_id,
        "legacy_event_id": entry.legacy_event_id,
        "source_table": entry.source_table,
        "event_type": entry.event_type,
        "taxonomy": entry.taxonomy,
        "target_table": entry.target_table,
        "target_record_id": entry.target_record_id,
        "import_status": status or entry.import_status,
        "confidence": entry.confidence,
        "payload_hash": entry.payload_hash,
        "reason": entry.reason,
        "source_refs_json": json.dumps(list(entry.source_refs), sort_keys=True),
        "evidence_refs_json": json.dumps(list(entry.evidence_refs), sort_keys=True),
    }


def upsert_import_map_entry(
    active_conn: sqlite3.Connection, entry: ImportPlanEntry, *, status: str | None = None
) -> None:
    row = _entry_to_row(entry, status)
    active_conn.execute(
        """
        INSERT INTO legacy_canonical_event_import_map (
            import_map_id, legacy_event_id, source_table, event_type, taxonomy,
            target_table, target_record_id, import_status, confidence, payload_hash,
            reason, source_refs_json, evidence_refs_json
        ) VALUES (
            :import_map_id, :legacy_event_id, :source_table, :event_type, :taxonomy,
            :target_table, :target_record_id, :import_status, :confidence, :payload_hash,
            :reason, :source_refs_json, :evidence_refs_json
        )
        ON CONFLICT(import_map_id) DO UPDATE SET
            import_status = CASE
                WHEN legacy_canonical_event_import_map.import_status = 'imported'
                  AND excluded.import_status = 'skipped_duplicate'
                THEN legacy_canonical_event_import_map.import_status
                ELSE excluded.import_status
            END,
            confidence = excluded.confidence,
            payload_hash = excluded.payload_hash,
            reason = excluded.reason,
            source_refs_json = excluded.source_refs_json,
            evidence_refs_json = excluded.evidence_refs_json,
            updated_at = datetime('now')
        """,
        row,
    )


def supersede_resolved_token_manual_entries(active_conn: sqlite3.Connection) -> int:
    """Mark old token manual-review ledger rows resolved by token_usage_records imports."""

    if not _table_exists(active_conn, IMPORT_MAP_TABLE):
        return 0
    result = active_conn.execute(f"""
        UPDATE {IMPORT_MAP_TABLE}
        SET import_status = 'superseded_by_current_authority',
            reason = 'Resolved by source-ref-safe token_usage_records reconciliation.',
            updated_at = datetime('now')
        WHERE taxonomy = 'token_usage'
          AND target_table IS NULL
          AND import_status = 'manual_review_required'
          AND EXISTS (
              SELECT 1
              FROM {IMPORT_MAP_TABLE} AS imported
              WHERE imported.legacy_event_id = {IMPORT_MAP_TABLE}.legacy_event_id
                AND imported.taxonomy = 'token_usage'
                AND imported.target_table = 'token_usage_records'
                AND imported.import_status IN ('imported', 'skipped_duplicate')
          )
        """)
    return int(result.rowcount or 0)


def _insert_execution_event(
    active_conn: sqlite3.Connection,
    event: LegacyEvent,
    entry: ImportPlanEntry,
) -> None:
    actor = _actor_fields(event)
    active_conn.execute(
        """
        INSERT INTO execution_events (
            event_id, event_type, event_name, project_id, milestone_id, task_id,
            process_run_id, parent_event_id, actor_type, actor_id, agent_id,
            skill_id, workflow_id, hook_id, tool_id, model_id, adapter_id,
            source_refs_json, evidence_refs_json, metadata_json, outcome_status,
            created_at
        ) VALUES (
            :event_id, :event_type, :event_name, :project_id, NULL, NULL,
            :process_run_id, NULL, :actor_type, :actor_id, NULL,
            :skill_id, :workflow_id, :hook_id, NULL, :model_id, NULL,
            :source_refs_json, :evidence_refs_json, :metadata_json, :outcome_status,
            :created_at
        )
        """,
        {
            "event_id": entry.target_record_id,
            "event_type": event.event_type,
            "event_name": _event_name(event.event_type),
            "project_id": _project_id(event),
            "process_run_id": _process_run_id(event),
            "actor_type": actor["actor_type"],
            "actor_id": actor["actor_id"],
            "skill_id": event.payload.get("skill_id") or event.payload.get("skill_name"),
            "workflow_id": event.payload.get("workflow_id") or event.trace.get("workflow_id"),
            "hook_id": event.payload.get("hook_name") or event.payload.get("stream_id"),
            "model_id": event.payload.get("model"),
            "source_refs_json": json.dumps(list(entry.source_refs), sort_keys=True),
            "evidence_refs_json": json.dumps(list(entry.evidence_refs), sort_keys=True),
            "metadata_json": json.dumps(
                _event_metadata(event, taxonomy=entry.taxonomy, reason=entry.reason),
                sort_keys=True,
            ),
            "outcome_status": (
                event.payload.get("status")
                or event.payload.get("validation_result")
                or ("failed" if event.event_type.endswith(".failed") else "recorded")
            ),
            "created_at": event.timestamp,
        },
    )


def _insert_skill_invocation(
    active_conn: sqlite3.Connection,
    event: LegacyEvent,
    entry: ImportPlanEntry,
    execution_event_id: str | None,
) -> None:
    skill_id = (
        event.payload.get("skill_id")
        or event.payload.get("skill_name")
        or event.payload.get("stream_id")
        or "unknown"
    )
    success = event.payload.get("success")
    status = event.payload.get("status") or ("completed" if success in (1, True) else "failed")
    active_conn.execute(
        """
        INSERT INTO skill_invocations (
            invocation_id, project_id, milestone_id, task_id, process_run_id,
            event_id, skill_id, status, purpose, metadata_json, created_at
        ) VALUES (
            :invocation_id, :project_id, NULL, NULL, :process_run_id,
            :event_id, :skill_id, :status, :purpose, :metadata_json, :created_at
        )
        """,
        {
            "invocation_id": entry.target_record_id,
            "project_id": _project_id(event),
            "process_run_id": _process_run_id(event),
            "event_id": execution_event_id,
            "skill_id": skill_id,
            "status": status,
            "purpose": "legacy canonical event reconciliation",
            "metadata_json": json.dumps(
                {
                    "source_refs": list(entry.source_refs),
                    "legacy_payload": event.payload,
                    "legacy_trace": event.trace,
                    "reconciliation_reason": entry.reason,
                },
                sort_keys=True,
            ),
            "created_at": event.payload.get("invoked_at") or event.timestamp,
        },
    )


def _insert_workflow_invocation(
    active_conn: sqlite3.Connection,
    event: LegacyEvent,
    entry: ImportPlanEntry,
    execution_event_id: str | None,
) -> None:
    workflow_id = event.payload.get("workflow_id") or event.trace.get("workflow_id") or "unknown"
    status = event.payload.get("status")
    if not status:
        status = "completed" if event.event_type.endswith(".completed") else "started"
    active_conn.execute(
        """
        INSERT INTO workflow_invocations (
            invocation_id, project_id, milestone_id, task_id, process_run_id,
            event_id, workflow_id, status, purpose, metadata_json, created_at
        ) VALUES (
            :invocation_id, :project_id, NULL, NULL, :process_run_id,
            :event_id, :workflow_id, :status, :purpose, :metadata_json, :created_at
        )
        """,
        {
            "invocation_id": entry.target_record_id,
            "project_id": _project_id(event),
            "process_run_id": _process_run_id(event),
            "event_id": execution_event_id,
            "workflow_id": workflow_id,
            "status": status,
            "purpose": "legacy canonical event reconciliation",
            "metadata_json": json.dumps(
                {
                    "source_refs": list(entry.source_refs),
                    "legacy_payload": event.payload,
                    "legacy_trace": event.trace,
                    "reconciliation_reason": entry.reason,
                },
                sort_keys=True,
            ),
            "created_at": event.timestamp,
        },
    )


def _insert_hook_invocation(
    active_conn: sqlite3.Connection,
    event: LegacyEvent,
    entry: ImportPlanEntry,
    execution_event_id: str | None,
) -> None:
    status = event.payload.get("status") or "completed"
    hook_id = event.payload.get("hook_name") or event.payload.get("stream_id") or "unknown"
    active_conn.execute(
        """
        INSERT INTO hook_invocations (
            invocation_id, project_id, milestone_id, task_id, process_run_id,
            event_id, hook_id, status, prevented_risky_action, purpose,
            metadata_json, created_at
        ) VALUES (
            :invocation_id, :project_id, NULL, NULL, :process_run_id,
            :event_id, :hook_id, :status, 0, :purpose, :metadata_json, :created_at
        )
        """,
        {
            "invocation_id": entry.target_record_id,
            "project_id": _project_id(event),
            "process_run_id": _process_run_id(event),
            "event_id": execution_event_id,
            "hook_id": hook_id,
            "status": status,
            "purpose": "legacy canonical event reconciliation",
            "metadata_json": json.dumps(
                {
                    "source_refs": list(entry.source_refs),
                    "legacy_payload": event.payload,
                    "legacy_trace": event.trace,
                    "reconciliation_reason": entry.reason,
                },
                sort_keys=True,
            ),
            "created_at": event.timestamp,
        },
    )


def _insert_token_usage(
    active_conn: sqlite3.Connection,
    event: LegacyEvent,
    entry: ImportPlanEntry,
) -> None:
    input_tokens = _int_value(event.payload.get("input_tokens")) or 0
    output_tokens = _int_value(event.payload.get("output_tokens")) or 0
    cached_tokens = _int_value(event.payload.get("cached_tokens")) or 0
    total_tokens = _int_value(event.payload.get("total_tokens"))
    if total_tokens is None:
        total_tokens = input_tokens + output_tokens + cached_tokens
    estimated_cost = _float_value(event.payload.get("cost_usd"))
    active_conn.execute(
        """
        INSERT INTO token_usage_records (
            token_usage_id, project_id, milestone_id, task_id, process_run_id,
            agent_id, skill_id, workflow_id, hook_id, model_id, provider,
            input_tokens, output_tokens, cached_tokens, total_tokens,
            estimated_cost, purpose, source_refs_json, evidence_refs_json,
            created_at
        ) VALUES (
            :token_usage_id, :project_id, NULL, NULL, :process_run_id,
            NULL, :skill_id, NULL, NULL, :model_id, :provider,
            :input_tokens, :output_tokens, :cached_tokens, :total_tokens,
            :estimated_cost, :purpose, :source_refs_json, :evidence_refs_json,
            :created_at
        )
        """,
        {
            "token_usage_id": entry.target_record_id,
            "project_id": _project_id(event),
            "process_run_id": _process_run_id(event),
            "skill_id": event.payload.get("skill_id") or event.payload.get("skill_name"),
            "model_id": event.payload.get("model"),
            "provider": _provider_from_model(event.payload.get("model")),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "total_tokens": total_tokens,
            "estimated_cost": estimated_cost if estimated_cost is not None else 0,
            "purpose": (
                "legacy canonical event reconciliation"
                if estimated_cost is not None
                else "legacy canonical event reconciliation; cost unavailable in source"
            ),
            "source_refs_json": json.dumps(list(entry.source_refs), sort_keys=True),
            "evidence_refs_json": json.dumps(list(entry.evidence_refs), sort_keys=True),
            "created_at": event.payload.get("recorded_at") or event.timestamp,
        },
    )


def _event_by_id(backup_conn: sqlite3.Connection, event_id: str) -> LegacyEvent:
    row = backup_conn.execute(
        """
        SELECT event_id, event_type, timestamp, trace, severity, payload, actor,
               confidence_score, source_type, created_at
        FROM canonical_events
        WHERE event_id = ?
        """,
        (event_id,),
    ).fetchone()
    if row is None:
        raise KeyError(event_id)
    return LegacyEvent(
        event_id=str(row["event_id"]),
        event_type=str(row["event_type"]),
        timestamp=str(row["timestamp"]),
        trace=_coerce_dict(_parse_json(row["trace"])),
        severity=str(row["severity"]),
        payload=_coerce_dict(_parse_json(row["payload"])),
        actor=_coerce_dict(_parse_json(row["actor"])) if row["actor"] not in (None, "") else None,
        confidence_score=row["confidence_score"],
        source_type=row["source_type"],
        created_at=str(row["created_at"]),
        raw_trace=str(row["trace"]),
        raw_payload=str(row["payload"]),
        raw_actor=row["actor"],
    )


def _execution_event_id_for(entries: Sequence[ImportPlanEntry], legacy_event_id: str) -> str | None:
    for entry in entries:
        if (
            entry.legacy_event_id == legacy_event_id
            and entry.target_table == "execution_events"
            and entry.import_status in {"pending_import", "skipped_duplicate"}
        ):
            return entry.target_record_id
    return None


def apply_import_plan(
    backup_conn: sqlite3.Connection,
    active_conn: sqlite3.Connection,
    entries: Sequence[ImportPlanEntry],
) -> dict[str, Any]:
    """Apply high-confidence pending entries and persist map entries for all rows."""

    ensure_import_map_table(active_conn)
    imported: Counter[str] = Counter()
    skipped: Counter[str] = Counter()
    errors: list[dict[str, str]] = []
    entries_by_event: dict[str, list[ImportPlanEntry]] = {}
    for entry in entries:
        entries_by_event.setdefault(entry.legacy_event_id, []).append(entry)

    with active_conn:
        for entry in entries:
            status = entry.import_status
            if entry.import_status != "pending_import" or entry.confidence < HIGH_CONFIDENCE:
                upsert_import_map_entry(active_conn, entry, status=status)
                skipped[status] += 1
                continue
            try:
                event = _event_by_id(backup_conn, entry.legacy_event_id)
                if entry.target_table == "execution_events":
                    if _record_exists(
                        active_conn, "execution_events", "event_id", entry.target_record_id or ""
                    ):
                        status = "skipped_duplicate"
                    else:
                        _insert_execution_event(active_conn, event, entry)
                        status = "imported"
                elif entry.target_table == "skill_invocations":
                    if _record_exists(
                        active_conn,
                        "skill_invocations",
                        "invocation_id",
                        entry.target_record_id or "",
                    ):
                        status = "skipped_duplicate"
                    else:
                        _insert_skill_invocation(
                            active_conn,
                            event,
                            entry,
                            _execution_event_id_for(
                                entries_by_event[event.event_id], event.event_id
                            ),
                        )
                        status = "imported"
                elif entry.target_table == "workflow_invocations":
                    if _record_exists(
                        active_conn,
                        "workflow_invocations",
                        "invocation_id",
                        entry.target_record_id or "",
                    ):
                        status = "skipped_duplicate"
                    else:
                        _insert_workflow_invocation(
                            active_conn,
                            event,
                            entry,
                            _execution_event_id_for(
                                entries_by_event[event.event_id], event.event_id
                            ),
                        )
                        status = "imported"
                elif entry.target_table == "hook_invocations":
                    if _record_exists(
                        active_conn,
                        "hook_invocations",
                        "invocation_id",
                        entry.target_record_id or "",
                    ):
                        status = "skipped_duplicate"
                    else:
                        _insert_hook_invocation(
                            active_conn,
                            event,
                            entry,
                            _execution_event_id_for(
                                entries_by_event[event.event_id], event.event_id
                            ),
                        )
                        status = "imported"
                elif entry.target_table == "token_usage_records":
                    if _record_exists(
                        active_conn,
                        "token_usage_records",
                        "token_usage_id",
                        entry.target_record_id or "",
                    ):
                        status = "skipped_duplicate"
                    else:
                        _insert_token_usage(active_conn, event, entry)
                        status = "imported"
                else:
                    status = "manual_review_required"
                upsert_import_map_entry(active_conn, entry, status=status)
                imported[entry.target_table or "none"] += 1 if status == "imported" else 0
                if status != "imported":
                    skipped[status] += 1
            except Exception as exc:  # pragma: no cover - defensive ledger path
                errors.append({"legacy_event_id": entry.legacy_event_id, "error": str(exc)})
                upsert_import_map_entry(active_conn, entry, status="error")
                skipped["error"] += 1
        superseded_token_manual_entries = supersede_resolved_token_manual_entries(active_conn)
    return {
        "imported_by_target": dict(sorted(imported.items())),
        "skipped_by_status": dict(sorted(skipped.items())),
        "superseded_token_manual_entries": superseded_token_manual_entries,
        "error_count": len(errors),
        "errors": errors,
    }


def validate_reconciliation(
    active_conn: sqlite3.Connection,
    *,
    expected_imported_min: int = 0,
) -> dict[str, Any]:
    tables = {
        row[0] for row in active_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    active_has_canonical_events = SOURCE_TABLE in tables
    map_count = 0
    missing_source_ref_count = 0
    imported_count = 0
    imported_token_rows_missing_source_refs = 0
    if IMPORT_MAP_TABLE in tables:
        map_count = active_conn.execute(f"SELECT COUNT(*) FROM {IMPORT_MAP_TABLE}").fetchone()[0]
        imported_count = active_conn.execute(
            f"SELECT COUNT(*) FROM {IMPORT_MAP_TABLE} WHERE import_status = 'imported'"
        ).fetchone()[0]
        missing_source_ref_count = active_conn.execute(f"""
            SELECT COUNT(*)
            FROM {IMPORT_MAP_TABLE}
            WHERE import_status = 'imported'
              AND source_refs_json NOT LIKE '%backup:canonical_events:%'
            """).fetchone()[0]
        if "token_usage_records" in tables:
            token_columns = {
                row[1] for row in active_conn.execute("PRAGMA table_info(token_usage_records)")
            }
            if "source_refs_json" in token_columns:
                imported_token_rows_missing_source_refs = active_conn.execute(f"""
                    SELECT COUNT(*)
                    FROM {IMPORT_MAP_TABLE} AS m
                    JOIN token_usage_records AS t
                      ON t.token_usage_id = m.target_record_id
                    WHERE m.import_status = 'imported'
                      AND m.target_table = 'token_usage_records'
                      AND t.source_refs_json NOT LIKE '%backup:canonical_events:%'
                    """).fetchone()[0]
    execution_missing_refs = active_conn.execute("""
        SELECT COUNT(*)
        FROM execution_events
        WHERE event_id LIKE 'legacy-canonical-event-%'
          AND source_refs_json NOT LIKE '%backup:canonical_events:%'
        """).fetchone()[0]
    quick_check = active_conn.execute("PRAGMA quick_check").fetchone()[0]
    errors = []
    if active_has_canonical_events:
        errors.append("active install must not recreate canonical_events")
    if missing_source_ref_count:
        errors.append("import map contains imported rows without backup source refs")
    if execution_missing_refs:
        errors.append("imported execution_events missing backup source refs")
    if imported_token_rows_missing_source_refs:
        errors.append("imported token_usage_records missing backup source refs")
    if imported_count < expected_imported_min:
        errors.append("imported row count below expected minimum")
    if quick_check != "ok":
        errors.append(f"sqlite quick_check failed: {quick_check}")
    return {
        "valid": not errors,
        "errors": errors,
        "quick_check": quick_check,
        "active_has_canonical_events": active_has_canonical_events,
        "import_map_rows": map_count,
        "imported_rows": imported_count,
        "missing_source_ref_count": missing_source_ref_count,
        "imported_execution_events_missing_source_refs": execution_missing_refs,
        "imported_token_usage_records_missing_source_refs": imported_token_rows_missing_source_refs,
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")


def run_reconciliation(
    *,
    backup_home: Path,
    active_home: Path,
    report_path: Path | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    backup_conn = connect_backup_readonly(backup_home)
    active_conn = connect_active(active_home)
    try:
        profile = profile_canonical_events(backup_conn)
        entries = build_import_plan(backup_conn, active_conn)
        summary = summarize_plan(profile, entries)
        result: dict[str, Any] = {
            "mode": "apply" if apply else "dry_run",
            "backup_home": str(backup_home),
            "active_home": str(active_home),
            "backup_read_only": True,
            "plan": summary,
        }
        if apply:
            result["apply_result"] = apply_import_plan(backup_conn, active_conn, entries)
            result["validation"] = validate_reconciliation(active_conn)
        else:
            result["validation"] = {
                "dry_run_only": True,
                "active_mutation_performed": False,
            }
        if report_path is not None:
            write_report(report_path, result)
        return result
    finally:
        backup_conn.close()
        active_conn.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-home", required=True, type=Path)
    parser.add_argument("--active-home", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    result = run_reconciliation(
        backup_home=args.backup_home,
        active_home=args.active_home,
        report_path=args.report,
        apply=args.apply,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("validation", {}).get("valid", True) else 1


__all__ = [
    "HIGH_CONFIDENCE",
    "IMPORT_MAP_TABLE",
    "ImportPlanEntry",
    "LegacyEvent",
    "apply_import_plan",
    "build_import_plan",
    "connect_active",
    "connect_backup_readonly",
    "ensure_import_map_table",
    "main",
    "profile_canonical_events",
    "run_reconciliation",
    "summarize_plan",
    "validate_reconciliation",
]
