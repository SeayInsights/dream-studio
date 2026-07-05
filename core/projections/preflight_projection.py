"""PreflightProjection — folds preflight_events spine into business_work_order_preflights.

Reads from preflight_events directly (not from business_canonical_events) because
preflight events are a local domain spine, not routed through the spool pipeline.

Registration:
    ProjectionRunner.register_spine(PreflightProjection())

The runner calls fold_spine() on each cycle instead of the standard canonical dispatch.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, UTC

logger = logging.getLogger(__name__)

_SPINE_TABLE = "preflight_events"
_READ_MODEL = "business_work_order_preflights"


class PreflightProjection:
    """Folds the preflight_events spine into business_work_order_preflights.

    One row per finding (keyed on the preflight.created event_id).
    Current status is taken from the latest preflight.status_changed event
    whose parent_event_id matches the finding_id.
    """

    name = "preflight_projection"

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        # Migration 107 owns the DDL.
        pass

    def fold_spine(self, conn: sqlite3.Connection) -> int:
        """Rebuild business_work_order_preflights from preflight_events.

        Idempotent: upserts on finding_id (the preflight.created event_id).
        Returns the number of rows upserted.
        """
        try:
            findings = conn.execute(
                f"SELECT * FROM {_SPINE_TABLE} WHERE event_kind = 'preflight.created' ORDER BY created_at ASC"
            ).fetchall()
        except sqlite3.OperationalError:
            logger.debug("preflight_events not available yet — fold_spine skipped")
            return 0

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        upserted = 0
        for row in findings:
            finding_id = row[0]  # event_id

            # Latest status change for this finding
            status_row = conn.execute(
                f"SELECT status, event_id FROM {_SPINE_TABLE}"
                f" WHERE parent_event_id = ? AND event_kind = 'preflight.status_changed'"
                f" ORDER BY created_at DESC LIMIT 1",
                (finding_id,),
            ).fetchone()

            current_status = status_row[0] if status_row else "open"
            last_status_event_id = status_row[1] if status_row else None

            conn.execute(
                f"""
                INSERT INTO {_READ_MODEL} (
                    finding_id, work_order_id, correlation_id, finding_type,
                    source, severity, summary, body, author_type,
                    status, last_status_event_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(finding_id) DO UPDATE SET
                    status              = excluded.status,
                    last_status_event_id = excluded.last_status_event_id,
                    updated_at          = excluded.updated_at
                """,
                (
                    finding_id,
                    row[2],  # work_order_id
                    row[3],  # correlation_id
                    row[5],  # finding_type
                    row[6],  # source
                    row[7],  # severity
                    row[8],  # summary
                    row[9],  # body
                    row[10],  # author_type
                    current_status,
                    last_status_event_id,
                    row[12],  # created_at
                    now,
                ),
            )
            upserted += 1

        return upserted
