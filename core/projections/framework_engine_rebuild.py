"""ProjectionEngine rebuild mixin — full rebuild from canonical events.

WO-GF-PROJECTION-ENGINE: split from ``core/projections/framework.py``. Methods
extracted verbatim onto ``_ProjectionEngineRebuildMixin``; ``ProjectionEngine``
(in framework_engine.py) composes this alongside the dispatch/retry/legacy
mixins. Cross-mixin calls (``self._advance_cursor``, ``self._save_checkpoint``)
are resolved at runtime via the composed class — no import between mixins.
"""

from __future__ import annotations

import sqlite3

from core.config.database import get_connection, transaction

from .framework_events import _build_type_filter, _legacy_row_to_event, _row_to_event
from .framework_shared import ProjectionResult, _TABLE_FOR_SOURCE, logger


class _ProjectionEngineRebuildMixin:
    # ── Full rebuild ──────────────────────────────────────────────────────────

    def rebuild(self, projection_name: str) -> ProjectionResult:
        """Full rebuild: pre_rebuild() + replay all matching canonical events.

        For v2 projections: reads from dual canonical tables per source_canonical.
        For legacy projections: falls back to reading canonical_events.
        """
        if projection_name not in self._projections:
            raise KeyError(f"Projection '{projection_name}' is not registered")

        proj = self._projections[projection_name]

        import time

        start = time.monotonic()
        events_processed = 0
        rows_written = 0
        errors: list[str] = []

        # Detect v2 vs legacy projection.
        is_v2 = bool(proj.source_canonical) and bool(proj.consumed_event_types)

        if is_v2 and proj.source_canonical in ("business", "ai", "both"):
            # V2 rebuild: truncate target tables with FK enforcement off so
            # child tables referencing the projection target don't block DELETE.
            # PRAGMA foreign_keys cannot be changed inside a transaction, so
            # we use a raw connection here (separate from the replay transactions).
            _raw = sqlite3.connect(self.db_path, timeout=30.0)
            try:
                _raw.execute("PRAGMA foreign_keys = OFF")
                proj.pre_rebuild(_raw)
                _raw.commit()
            finally:
                _raw.close()

            sources = (
                ["business", "ai"] if proj.source_canonical == "both" else [proj.source_canonical]
            )
            for source in sources:
                table = _TABLE_FOR_SOURCE[source]
                type_clause, type_params = _build_type_filter(proj.consumed_event_types)
                query = f"""
                    SELECT *
                    FROM {table}
                    WHERE {type_clause}
                    ORDER BY event_timestamp ASC
                """
                with get_connection(read_only=True) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(query, type_params).fetchall()

                last_event_id: str | None = None
                for row in rows:
                    event = _row_to_event(row, source)
                    try:
                        with transaction() as conn:
                            written = proj.handle(event, conn)
                        rows_written += written
                        events_processed += 1
                        last_event_id = event["event_id"]
                    except Exception as exc:
                        errors.append(f"{event['event_id']}: {exc}")
                        logger.warning(
                            "Projection '%s' rebuild error on %s: %s",
                            proj.name,
                            event["event_id"],
                            exc,
                        )

                if last_event_id:
                    cursor_col = (
                        "last_processed_business_event_id"
                        if source == "business"
                        else "last_processed_ai_event_id"
                    )
                    self._advance_cursor(proj.name, cursor_col, last_event_id)

        else:
            # Legacy rebuild: read from canonical_events.
            type_clause, type_params = _build_type_filter(proj.event_types)
            last_event_id = ""
            last_timestamp = "1970-01-01T00:00:00Z"

            with transaction() as conn:
                proj.pre_rebuild(conn)
                cursor = conn.execute(
                    f"SELECT * FROM canonical_events WHERE {type_clause} ORDER BY timestamp ASC",
                    type_params,
                )
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

                if events_processed > 0:
                    self._save_checkpoint(
                        conn,
                        proj.name,
                        last_event_id,
                        last_timestamp,
                        events_processed,
                        rebuilt=True,
                    )

        elapsed = (time.monotonic() - start) * 1000
        return ProjectionResult(
            projection_name=proj.name,
            events_processed=events_processed,
            rows_written=rows_written,
            errors=errors,
            duration_ms=elapsed,
        )

    def rebuild_all(self) -> list[ProjectionResult]:
        """Rebuild every registered projection."""
        results = []
        for name in self._projections:
            results.append(self.rebuild(name))
        return results
