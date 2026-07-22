"""ProjectionEngine dispatch mixin — v2 incremental dispatch + cursor management.

WO-GF-PROJECTION-ENGINE: split from ``core/projections/framework.py``. Methods
extracted verbatim onto ``_ProjectionEngineDispatchMixin``; ``ProjectionEngine``
(in framework_engine.py) composes this alongside the retry/rebuild/legacy
mixins. Cross-mixin calls (``self._schedule_retry`` etc.) are resolved at
runtime via the composed class — no import between mixins.
"""

from __future__ import annotations

import sqlite3
import traceback
from datetime import datetime, UTC

from core.config.database import get_connection, transaction

from .framework_events import _build_type_filter, _row_to_event
from .framework_projection import Projection
from .framework_shared import ProjectionResult, _TABLE_FOR_SOURCE, logger


class _ProjectionEngineDispatchMixin:
    # ── V2 incremental dispatch ───────────────────────────────────────────────

    def _apply_v2(self, proj: Projection) -> ProjectionResult:
        """Fetch new events for proj from dual canonical and dispatch to handle()."""
        import time

        start = time.monotonic()
        events_processed = 0
        rows_written = 0
        errors: list[str] = []

        # Determine which canonical table(s) to query.
        sources: list[str] = (
            ["business", "ai"] if proj.source_canonical == "both" else [proj.source_canonical]
        )

        for source in sources:
            table = _TABLE_FOR_SOURCE[source]
            cursor_col = (
                "last_processed_business_event_id"
                if source == "business"
                else "last_processed_ai_event_id"
            )
            last_ts = self._get_cursor_timestamp(proj.name, cursor_col, table)
            type_clause, type_params = _build_type_filter(proj.consumed_event_types)
            query = f"""
                SELECT *
                FROM {table}
                WHERE event_timestamp > ? AND {type_clause}
                ORDER BY event_timestamp ASC
            """
            params = [last_ts] + type_params

            with transaction() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(query, params).fetchall()

            for row in rows:
                event = _row_to_event(row, source)
                try:
                    with transaction() as conn:
                        written = proj.handle(event, conn)
                    rows_written += written
                    events_processed += 1
                    self._advance_cursor(proj.name, cursor_col, event["event_id"])
                    self._update_state_metrics(proj.name, events_processed=1)
                except Exception as exc:
                    err_msg = str(exc)
                    err_tb = traceback.format_exc()
                    errors.append(f"{event['event_id']}: {err_msg}")
                    logger.warning(
                        "Projection '%s' handle() failed for %s (%s): %s",
                        proj.name,
                        event["event_id"],
                        source,
                        err_msg,
                    )
                    self._schedule_retry(proj, event, source, err_msg, err_tb)
                    self._update_state_metrics(proj.name, events_failed=1)

                # Mirror to DuckDB analytics store (fail-open; never blocks SQLite path).
                if self._analytics_conn is not None:
                    try:
                        from core.projections.duckdb_projections import dispatch_to_duckdb

                        dispatch_to_duckdb(event, self._analytics_conn)
                    except Exception:
                        logger.debug(
                            "DuckDB dispatch failed for %s (non-fatal)", event.get("event_id")
                        )

        elapsed = (time.monotonic() - start) * 1000
        return ProjectionResult(
            projection_name=proj.name,
            events_processed=events_processed,
            rows_written=rows_written,
            errors=errors,
            duration_ms=elapsed,
        )

    # ── Cursor management ─────────────────────────────────────────────────────

    def _get_cursor_timestamp(self, projection_name: str, cursor_col: str, table: str) -> str:
        """Return the event_timestamp of the last processed event, or epoch."""
        with get_connection(read_only=True) as conn:
            row = conn.execute(
                f"SELECT {cursor_col} FROM projection_state WHERE projection_name = ?",
                (projection_name,),
            ).fetchone()
            last_event_id = row[0] if row else None

        if not last_event_id:
            return "1970-01-01T00:00:00+00:00"

        # Look up the timestamp for this event_id in the canonical table.
        with get_connection(read_only=True) as conn:
            ts_row = conn.execute(
                f"SELECT event_timestamp FROM {table} WHERE event_id = ?",
                (last_event_id,),
            ).fetchone()
            return ts_row[0] if ts_row else "1970-01-01T00:00:00+00:00"

    def _advance_cursor(self, projection_name: str, cursor_col: str, event_id: str) -> None:
        """Update the cursor in projection_state to the given event_id."""
        now = datetime.now(UTC).isoformat()
        with transaction() as conn:
            conn.execute(
                f"""
                UPDATE projection_state
                SET {cursor_col} = ?, last_run_at = ?
                WHERE projection_name = ?
                """,
                (event_id, now, projection_name),
            )

    def _update_state_metrics(
        self,
        projection_name: str,
        *,
        events_processed: int = 0,
        events_failed: int = 0,
    ) -> None:
        """Increment aggregate counters in projection_state."""
        with transaction() as conn:
            conn.execute(
                """
                UPDATE projection_state
                SET events_processed_total = events_processed_total + ?,
                    events_failed_total = events_failed_total + ?
                WHERE projection_name = ?
                """,
                (events_processed, events_failed, projection_name),
            )
