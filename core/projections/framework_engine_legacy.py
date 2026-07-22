"""ProjectionEngine legacy mixin — health/inspection + pre-v2 backward-compat paths.

WO-GF-PROJECTION-ENGINE: split from ``core/projections/framework.py``. Methods
extracted verbatim onto ``_ProjectionEngineLegacyMixin``; ``ProjectionEngine``
(in framework_engine.py) composes this alongside the dispatch/retry/rebuild
mixins.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, UTC
from typing import Any

from core.config.database import get_connection, transaction

from .framework_events import _build_type_filter, _legacy_row_to_event
from .framework_projection import Projection
from .framework_shared import ProjectionCheckpoint, ProjectionResult, logger


class _ProjectionEngineLegacyMixin:
    # ── Health / inspection ───────────────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        """Return projection health status (includes both v2 and legacy projections)."""
        status: dict[str, Any] = {"projections": {}}
        with get_connection(read_only=True) as conn:
            # Count events across all three canonical tables.
            for tbl in ("business_canonical_events", "ai_canonical_events", "canonical_events"):
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                    status[f"total_{tbl}"] = count
                except sqlite3.OperationalError:
                    status[f"total_{tbl}"] = 0

            for name, proj in self._projections.items():
                ps_row = conn.execute(
                    "SELECT * FROM projection_state WHERE projection_name = ?", (name,)
                ).fetchone()
                dead = conn.execute(
                    "SELECT COUNT(*) FROM projection_dead_letter WHERE projection_name = ? AND status='active'",
                    (name,),
                ).fetchone()[0]
                pending_retries = conn.execute(
                    "SELECT COUNT(*) FROM projection_retry_queue WHERE projection_name = ?",
                    (name,),
                ).fetchone()[0]
                status["projections"][name] = {
                    "source_canonical": proj.source_canonical,
                    "consumed_event_types": proj.consumed_event_types,
                    "target_tables": proj.target_tables,
                    "last_processed_business": ps_row[1] if ps_row else None,
                    "last_processed_ai": ps_row[2] if ps_row else None,
                    "last_run_at": ps_row[3] if ps_row else None,
                    "events_processed_total": ps_row[4] if ps_row else 0,
                    "events_failed_total": ps_row[5] if ps_row else 0,
                    "active_dead_letters": dead,
                    "pending_retries": pending_retries,
                    "healthy": ps_row is not None and dead == 0,
                }
        return status

    # ── Legacy / backward-compat methods ─────────────────────────────────────

    def apply_incremental(self, projection_name: str | None = None) -> list[ProjectionResult]:
        """Legacy incremental dispatch: reads from canonical_events.

        Kept for pre-v2 consumers.py projections.  V2 projections should use
        run_cycle() instead, which reads from the dual canonical tables.
        """
        targets = (
            [self._projections[projection_name]]
            if projection_name and projection_name in self._projections
            else list(self._projections.values())
        )
        results = []
        for proj in targets:
            results.append(self._apply_one_legacy(proj))
        return results

    def _apply_one_legacy(self, proj: Projection) -> ProjectionResult:
        """Legacy incremental dispatch reading from canonical_events."""
        import time

        start = time.monotonic()
        checkpoint = self.get_checkpoint(proj.name)
        last_ts = checkpoint.last_timestamp if checkpoint else "1970-01-01T00:00:00Z"

        type_clause, type_params = _build_type_filter(proj.event_types)
        query = f"""
            SELECT event_id, event_type, timestamp, trace, severity,
                   payload, actor, confidence_score, source_type
            FROM canonical_events
            WHERE timestamp > ? AND {type_clause}
            ORDER BY timestamp ASC
        """
        params = [last_ts] + type_params

        events_processed = 0
        rows_written = 0
        errors: list[str] = []
        last_event_id = ""
        last_timestamp = last_ts

        with transaction() as conn:
            cursor = conn.execute(query, params)
            for row in cursor:
                event = _legacy_row_to_event(row)
                try:
                    written = proj.handle(event, conn)
                    rows_written += written
                    events_processed += 1
                    last_event_id = event["event_id"]
                    last_timestamp = event["timestamp"]
                except Exception as exc:
                    errors.append(f"{event['event_id']}: {exc}")
                    logger.warning(
                        "Projection %s error on %s: %s", proj.name, event["event_id"], exc
                    )

            if events_processed > 0:
                self._save_checkpoint(
                    conn, proj.name, last_event_id, last_timestamp, events_processed
                )

        elapsed = (time.monotonic() - start) * 1000
        return ProjectionResult(
            projection_name=proj.name,
            events_processed=events_processed,
            rows_written=rows_written,
            errors=errors,
            duration_ms=elapsed,
        )

    def apply_since(self, cursor: str | None = None) -> list[ProjectionResult]:
        """Alias for apply_incremental (legacy API)."""
        return self.apply_incremental()

    def get_checkpoint(self, name: str) -> ProjectionCheckpoint | None:
        """Return legacy ProjectionCheckpoint for a projection (backward compat)."""
        with get_connection(read_only=True) as conn:
            row = conn.execute(
                "SELECT * FROM projection_checkpoints WHERE projection_name = ?", (name,)
            ).fetchone()
            if not row:
                return None
            return ProjectionCheckpoint(
                projection_name=row[0],
                last_event_id=row[1],
                last_timestamp=row[2],
                events_processed=row[3],
                last_rebuilt=row[4],
            )

    def _save_checkpoint(
        self,
        conn: sqlite3.Connection,
        name: str,
        last_event_id: str,
        last_timestamp: str,
        events_processed: int,
        rebuilt: bool = False,
    ) -> None:
        """Write legacy projection_checkpoints row (backward compat)."""
        now = datetime.now(UTC).isoformat()
        conn.execute(
            """
            INSERT INTO projection_checkpoints
                (projection_name, last_event_id, last_timestamp, events_processed, last_rebuilt)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(projection_name) DO UPDATE SET
                last_event_id = excluded.last_event_id,
                last_timestamp = excluded.last_timestamp,
                events_processed = projection_checkpoints.events_processed + excluded.events_processed,
                last_rebuilt = CASE WHEN ? THEN ? ELSE projection_checkpoints.last_rebuilt END
            """,
            (name, last_event_id, last_timestamp, events_processed, 1 if rebuilt else 0, now),
        )

    # ── Meta table initialization ─────────────────────────────────────────────

    def _ensure_meta_tables(self) -> None:
        """Create legacy projection_checkpoints if it doesn't exist.

        The v2 tables (projection_state, projection_dead_letter,
        projection_retry_queue) are owned by migration 068 and are not
        created here.  This only ensures backward compat for pre-v2 code
        that checks projection_checkpoints directly.
        """
        with transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projection_checkpoints (
                    projection_name TEXT PRIMARY KEY,
                    last_event_id TEXT NOT NULL,
                    last_timestamp TEXT NOT NULL,
                    events_processed INTEGER NOT NULL DEFAULT 0,
                    last_rebuilt TEXT
                )
            """)
