"""Emit-only creators for the findings event spine (AD-6 / WO-Y).

record_finding() and set_finding_status() write to the security_events spine
only (AD-6: no direct row write to read-model tables). findings_current_status
(the projection that used to fold this spine into a "current status" table)
was dropped in migration 140 (WO dff23cb0) — see core/findings/current_status.py
for the read-time derivation that replaced it.

Both functions also emit canonical events for cross-system observability (fail-open).
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _get_conn(db_path: Path | None) -> tuple[sqlite3.Connection, bool]:
    if db_path is not None:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn, True
    try:
        from core.config.database import get_connection

        return get_connection(), False
    except Exception:
        from core.event_store.studio_db import _connect as _studio_connect
        from core.config.paths import state_dir

        conn = _studio_connect(state_dir() / "studio.db")
        return conn, True


def record_finding(
    *,
    project_id: str | None = None,
    work_order_id: str | None = None,
    severity: str,
    title: str,
    body: str | None = None,
    file_path: str | None = None,
    line_number: int | None = None,
    scanner_type: str | None = None,
    cwe_id: str | None = None,
    owasp_category: str | None = None,
    cve_id: str | None = None,
    vuln_class: str | None = None,
    exploitability: str | None = None,
    correlation_id: str | None = None,
    db_path: Path | None = None,
) -> str:
    """Insert a finding.recorded event into security_events.

    Returns the generated finding_id (UUID). Current status is derived at read
    time from security_events (see core/findings/current_status.py) — there is
    no separate projection to update.

    Also emits a finding.recorded canonical event (fail-open, for observability).
    """
    finding_id = str(uuid.uuid4())
    now = _now()

    conn, owned = _get_conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO security_events (
                event_id, parent_event_id, event_kind, correlation_id,
                project_id, work_order_id, scanner_type,
                cwe_id, owasp_category, cve_id,
                file_path, line_number, vuln_class, exploitability,
                severity, title, body, created_at
            ) VALUES (?, ?, 'finding.recorded', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding_id,
                None,
                correlation_id,
                project_id,
                work_order_id,
                scanner_type,
                cwe_id,
                owasp_category,
                cve_id,
                file_path,
                line_number,
                vuln_class,
                exploitability,
                severity,
                title,
                body,
                now,
            ),
        )
        if owned:
            conn.commit()
    finally:
        if owned:
            conn.close()

    # Canonical event emission — fail-open (observability only).
    try:
        from canonical.events.envelope import CanonicalEventEnvelope
        from canonical.events.types import EventType
        from emitters.shared.spool_writer import write_envelopes

        payload: dict[str, Any] = {
            "finding_id": finding_id,
            "severity": severity,
            "title": title,
        }
        if project_id is not None:
            payload["project_id"] = project_id
        if file_path is not None:
            payload["file_path"] = file_path
        if scanner_type is not None:
            payload["scanner_type"] = scanner_type

        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=EventType.FINDING_RECORDED.value,
                    session_id=None,
                    payload=payload,
                    confidence="high",
                    project_id=project_id,
                    correlation_id=correlation_id,
                )
            ]
        )
    except Exception:
        pass

    return finding_id


def set_finding_status(
    finding_id: str,
    new_status: str,
    *,
    project_id: str | None = None,
    reason: str | None = None,
    correlation_id: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Insert a finding.status_changed event into security_events.

    Current status is derived at read time from security_events (see
    core/findings/current_status.py) — the next read picks this up immediately.

    new_status: open | mitigated | false_positive | accepted | resolved
    """
    event_id = str(uuid.uuid4())
    now = _now()

    conn, owned = _get_conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO security_events (
                event_id, parent_event_id, event_kind, correlation_id,
                project_id, body, created_at
            ) VALUES (?, ?, 'finding.status_changed', ?, ?, ?, ?)
            """,
            (
                event_id,
                finding_id,
                correlation_id,
                project_id,
                new_status if reason is None else f"{new_status}: {reason}",
                now,
            ),
        )
        if owned:
            conn.commit()
    finally:
        if owned:
            conn.close()

    # Canonical event emission — fail-open.
    try:
        from canonical.events.envelope import CanonicalEventEnvelope
        from canonical.events.types import EventType
        from emitters.shared.spool_writer import write_envelopes

        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=EventType.FINDING_STATUS_CHANGED.value,
                    session_id=None,
                    payload={
                        "finding_id": finding_id,
                        "new_status": new_status,
                        **({"reason": reason} if reason else {}),
                        **({"project_id": project_id} if project_id else {}),
                    },
                    confidence="high",
                    project_id=project_id,
                    correlation_id=correlation_id,
                )
            ]
        )
    except Exception:
        pass
