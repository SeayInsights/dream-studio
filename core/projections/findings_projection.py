"""FindingsProjection — folds security_events spine into findings_current_status.

Reads from security_events directly (local spine, not business_canonical_events)
because findings are domain-local; the canonical event emission in mutations.py
is for cross-system observability only.

Registration:
    ProjectionRunner.register_spine(FindingsProjection())

The runner calls fold_spine(conn) on each cycle after canonical projections.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_SPINE_TABLE = "security_events"
_READ_MODEL = "findings_current_status"


class FindingsProjection:
    """Folds the security_events spine into findings_current_status.

    One row per finding (keyed on the finding.recorded event_id).
    Current status is derived from the latest finding.status_changed
    or finding.resolved event whose parent_event_id matches the finding_id.
    """

    name = "findings_projection"

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        # Migration 111 owns the DDL for both security_events and findings_current_status.
        pass

    def fold_spine(self, conn: sqlite3.Connection) -> int:
        """Upsert findings_current_status from security_events.

        Idempotent: upserts on finding_id (the finding.recorded event_id).
        Returns the number of rows upserted.
        """
        try:
            recordings = conn.execute(
                f"SELECT event_id, project_id, work_order_id, severity, title,"
                f"       file_path, line_number, scanner_type, created_at"
                f" FROM {_SPINE_TABLE}"
                f" WHERE event_kind = 'finding.recorded'"
                f" ORDER BY created_at ASC"
            ).fetchall()
        except sqlite3.OperationalError:
            logger.debug("security_events not available yet — fold_spine skipped")
            return 0

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        upserted = 0

        for row in recordings:
            finding_id = row[0]

            # Latest status change for this finding (status_changed or resolved)
            status_row = conn.execute(
                f"SELECT body, event_id FROM {_SPINE_TABLE}"
                f" WHERE parent_event_id = ?"
                f"   AND event_kind IN ('finding.status_changed', 'finding.resolved')"
                f" ORDER BY created_at DESC LIMIT 1",
                (finding_id,),
            ).fetchone()

            # body on status_changed is "new_status" or "new_status: reason"
            raw_body = status_row[0] if status_row else None
            current_status = raw_body.split(":")[0].strip() if raw_body else "open"
            last_status_event_id = status_row[1] if status_row else None

            try:
                conn.execute(
                    f"""
                    INSERT INTO {_READ_MODEL} (
                        finding_id, project_id, work_order_id,
                        severity, title, file_path, line_number, scanner_type,
                        current_status, last_status_event_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(finding_id) DO UPDATE SET
                        current_status       = excluded.current_status,
                        last_status_event_id = excluded.last_status_event_id,
                        updated_at           = excluded.updated_at
                    """,
                    (
                        finding_id,
                        row[1],  # project_id
                        row[2],  # work_order_id
                        row[3],  # severity
                        row[4],  # title
                        row[5],  # file_path
                        row[6],  # line_number
                        row[7],  # scanner_type
                        current_status,
                        last_status_event_id,
                        row[8],  # created_at (from spine)
                        now,
                    ),
                )
                upserted += 1
            except sqlite3.Error as exc:
                logger.warning("FindingsProjection: upsert failed for %s: %s", finding_id, exc)

        return upserted


def fold_findings(conn: sqlite3.Connection | None = None) -> int:
    """Convenience: fold findings_current_status from security_events.

    Acquires a connection if none provided. Returns the number of rows upserted.
    """
    if conn is not None:
        return FindingsProjection().fold_spine(conn)

    try:
        from core.config.database import get_connection

        with get_connection() as _conn:
            result = FindingsProjection().fold_spine(_conn)
            return result
    except Exception as exc:
        logger.debug("fold_findings: failed: %s", exc)
        return 0
