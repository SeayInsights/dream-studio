"""ProjectionEngine retry mixin — retry queue and dead-letter handling.

WO-GF-PROJECTION-ENGINE: split from ``core/projections/framework.py``. Methods
extracted verbatim onto ``_ProjectionEngineRetryMixin``; ``ProjectionEngine``
(in framework_engine.py) composes this alongside the dispatch/rebuild/legacy
mixins. Cross-mixin calls (``self._advance_cursor``) are resolved at runtime
via the composed class — no import between mixins.
"""

from __future__ import annotations

import sqlite3
import traceback
from datetime import datetime, UTC
from typing import Any

from core.config.database import get_connection, transaction

from .framework_events import _row_to_event
from .framework_projection import Projection
from .framework_shared import _TABLE_FOR_SOURCE, logger


class _ProjectionEngineRetryMixin:
    # ── Retry / dead-letter ───────────────────────────────────────────────────

    def _schedule_retry(
        self,
        proj: Projection,
        event: dict[str, Any],
        source: str,
        error_message: str,
        error_traceback: str,
    ) -> None:
        """Queue the event for retry or dead-letter if max_retries exceeded."""
        event_id = event["event_id"]

        # Check current retry count across retry queue + dead letter.
        with get_connection(read_only=True) as conn:
            rq_row = conn.execute(
                """
                SELECT retry_count FROM projection_retry_queue
                WHERE event_id = ? AND projection_name = ?
                ORDER BY id DESC LIMIT 1
                """,
                (event_id, proj.name),
            ).fetchone()
        current_retries = rq_row[0] if rq_row else 0
        next_attempt = current_retries + 1

        if next_attempt > proj.retry_policy.max_retries:
            # Exhausted — move to dead letter.
            logger.error(
                "Projection '%s': event %s exhausted %d retries → dead-letter",
                proj.name,
                event_id,
                proj.retry_policy.max_retries,
            )
            self._dead_letter(
                proj.name, event_id, source, error_message, error_traceback, current_retries
            )
            # Remove from retry queue if present.
            with transaction() as conn:
                conn.execute(
                    "DELETE FROM projection_retry_queue WHERE event_id = ? AND projection_name = ?",
                    (event_id, proj.name),
                )
        else:
            next_at = proj.retry_policy.next_retry_at(current_retries)
            logger.info(
                "Projection '%s': scheduling retry %d/%d for %s at %s",
                proj.name,
                next_attempt,
                proj.retry_policy.max_retries,
                event_id,
                next_at,
            )
            with transaction() as conn:
                # Upsert retry queue entry (update if already present).
                conn.execute(
                    """
                    INSERT INTO projection_retry_queue
                        (event_id, event_source, projection_name, next_retry_at, retry_count)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    (event_id, source, proj.name, next_at, next_attempt),
                )

    def _dead_letter(
        self,
        projection_name: str,
        event_id: str,
        event_source: str,
        error_message: str,
        error_traceback: str,
        retry_count: int,
    ) -> None:
        """Write an entry to projection_dead_letter."""
        now = datetime.now(UTC).isoformat()
        with transaction() as conn:
            conn.execute(
                """
                INSERT INTO projection_dead_letter
                    (event_id, event_source, projection_name, error_message,
                     error_traceback, failed_at, retry_count, last_retry_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    event_id,
                    event_source,
                    projection_name,
                    error_message,
                    error_traceback,
                    now,
                    retry_count,
                    now,
                ),
            )

    def _process_retries(self, proj: Projection) -> None:
        """Process all due retry entries for this projection."""
        now = datetime.now(UTC).isoformat()

        with get_connection(read_only=True) as conn:
            due = conn.execute(
                """
                SELECT id, event_id, event_source, retry_count
                FROM projection_retry_queue
                WHERE projection_name = ? AND next_retry_at <= ?
                ORDER BY next_retry_at ASC
                """,
                (proj.name, now),
            ).fetchall()

        for row in due:
            retry_id, event_id, event_source, retry_count = row
            table = _TABLE_FOR_SOURCE[event_source]

            # Fetch the original event from the canonical table.
            with get_connection(read_only=True) as conn:
                conn.row_factory = sqlite3.Row
                event_row = conn.execute(
                    f"SELECT * FROM {table} WHERE event_id = ?", (event_id,)
                ).fetchone()

            if event_row is None:
                logger.warning(
                    "Projection '%s': retry event %s not found in %s — removing from queue",
                    proj.name,
                    event_id,
                    table,
                )
                with transaction() as conn:
                    conn.execute("DELETE FROM projection_retry_queue WHERE id = ?", (retry_id,))
                continue

            event = _row_to_event(event_row, event_source)
            try:
                with transaction() as conn:
                    proj.handle(event, conn)

                # Success — remove from retry queue and advance cursor.
                with transaction() as conn:
                    conn.execute("DELETE FROM projection_retry_queue WHERE id = ?", (retry_id,))
                cursor_col = (
                    "last_processed_business_event_id"
                    if event_source == "business"
                    else "last_processed_ai_event_id"
                )
                self._advance_cursor(proj.name, cursor_col, event_id)
                logger.info(
                    "Projection '%s': retry succeeded for event %s",
                    proj.name,
                    event_id,
                )
            except Exception as exc:
                err_msg = str(exc)
                err_tb = traceback.format_exc()
                next_attempt = retry_count + 1
                if next_attempt > proj.retry_policy.max_retries:
                    logger.error(
                        "Projection '%s': retry exhausted for %s → dead-letter",
                        proj.name,
                        event_id,
                    )
                    self._dead_letter(
                        proj.name, event_id, event_source, err_msg, err_tb, retry_count
                    )
                    with transaction() as conn:
                        conn.execute(
                            "DELETE FROM projection_retry_queue WHERE id = ?",
                            (retry_id,),
                        )
                else:
                    next_at = proj.retry_policy.next_retry_at(next_attempt)
                    with transaction() as conn:
                        conn.execute(
                            """
                            UPDATE projection_retry_queue
                            SET retry_count = ?, next_retry_at = ?
                            WHERE id = ?
                            """,
                            (next_attempt, next_at, retry_id),
                        )
                    logger.warning(
                        "Projection '%s': retry %d/%d failed for %s — next at %s",
                        proj.name,
                        next_attempt,
                        proj.retry_policy.max_retries,
                        event_id,
                        next_at,
                    )
