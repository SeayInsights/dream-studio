"""
Event store module for Dream Studio.

Provides append-only event ledger with mandatory validation gate.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from core.validation.event_validator import EventValidator, ValidationResult


class EventStore:
    """
    Append-only event store with validation gateway.

    Design principles:
    - Events are immutable (no updates, only appends)
    - Validation is mandatory (invalid events NEVER persisted)
    - Validation failures are logged (for debugging)
    - Event store is the single source of truth
    """

    def __init__(
        self,
        db_path: str,
        validator: EventValidator,
        emit_validation_failures: bool = True,
        shared_connection: sqlite3.Connection = None,
    ):
        """
        Initialize event store.

        Args:
            db_path: Path to SQLite database
            validator: EventValidator instance
            emit_validation_failures: If True, emit event.validation.failed events
            shared_connection: Optional shared connection (for testing)
        """
        self.db_path = db_path
        self.validator = validator
        self.emit_validation_failures = emit_validation_failures
        self._shared_connection = shared_connection

        # Use shared connection if provided (for testing with temp DB)
        if shared_connection is not None:
            self.db = shared_connection
            self.db.row_factory = sqlite3.Row
        else:
            self.db = self._connect()
            self.db.row_factory = sqlite3.Row

        self._init_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.OperationalError:
            pass
        return conn

    @contextmanager
    def _transaction(self):
        if self._shared_connection is not None:
            try:
                yield self._shared_connection
                self._shared_connection.commit()
            except Exception:
                self._shared_connection.rollback()
                raise
            return

        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self):
        """Initialize database tables if they don't exist.

        WO-M: canonical_events is retired (now a compat VIEW via migration 102).
        This method only creates validation_failures, which EventStore still owns.
        Dual-canonical tables are created on demand by _write_to_dual_canonical.
        """
        # validation_failures was dropped in migration 129 (WO-READMODELS-DUCKDB).
        # The DuckDB events_fact validation_failures VIEW replaces this projection table.
        # No tables created here; dual-canonical tables are created on demand by
        # _write_to_dual_canonical, and the migration system owns all other tables.

    def write_event(self, event: Dict) -> bool:
        """
        Write event to store (with mandatory validation).

        Args:
            event: Event dictionary to write

        Returns:
            True if event written successfully, False if validation failed
        """
        # CRITICAL: Validate BEFORE persisting
        result = self.validator.validate(event)

        if not result.is_valid:
            # Log validation failure
            self._log_validation_failure(event, result)

            # Optionally emit validation.failed event (recursive guard)
            if (
                self.emit_validation_failures
                and event.get("event_type") != "event.validation.failed"
            ):
                self._emit_validation_failure_event(event, result)

            # DO NOT PERSIST invalid events
            return False

        # Event is valid — write to dual-canonical authority tables (WO-M: canonical_events retired)
        from spool.ingestor import _write_to_dual_canonical

        _write_to_dual_canonical(event, Path(self.db_path))
        return True

    def _log_validation_failure(self, event: Dict, result: ValidationResult):
        """Log validation failure.

        The SQLite validation_failures projection table was dropped in migration 129
        (WO-READMODELS-DUCKDB). Validation failures are now surfaced via the
        event.validation.failed canonical event (emitted by _emit_validation_failure_event)
        which the DuckDB events_fact pipeline projects into the validation_failures VIEW.
        This method is retained as a no-op to preserve the call site; the canonical
        event emission path is the sole writer going forward.
        """

    def _emit_validation_failure_event(self, event: Dict, result: ValidationResult):
        """
        Emit event.validation.failed event (for monitoring).

        Args:
            event: Invalid event
            result: ValidationResult with errors
        """
        failure_event = {
            "event_id": str(uuid4()),
            "event_type": "event.validation.failed",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "trace": event.get("trace", {}),
            "severity": "high",
            "payload": {
                "invalid_event_type": event.get("event_type", "UNKNOWN"),
                "errors": result.errors,
            },
        }

        # Recursion guard: Don't validate validation failures
        from spool.ingestor import _write_to_dual_canonical

        _write_to_dual_canonical(failure_event, Path(self.db_path))

    def query_events(
        self,
        event_type: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        trace_filter: Optional[Dict] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Query events from canonical_events.

        Args:
            event_type: Filter by event type (supports wildcards with %)
            start_time: Filter by start timestamp (ISO-8601)
            end_time: Filter by end timestamp (ISO-8601)
            trace_filter: Filter by trace fields (e.g., {'project_id': 'proj_123'})
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries
        """
        query = "SELECT * FROM canonical_events WHERE 1=1"
        params = []

        if event_type:
            query += " AND event_type LIKE ?"
            params.append(event_type)

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)

        if trace_filter:
            for key, value in trace_filter.items():
                query += f" AND json_extract(trace, '$.{key}') = ?"
                params.append(value)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = self.db.execute(query, params)
        rows = cursor.fetchall()

        events = []
        for row in rows:
            event = {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "timestamp": row["timestamp"],
                "trace": json.loads(row["trace"]),
                "severity": row["severity"],
                "payload": json.loads(row["payload"]),
            }

            if row["actor"]:
                event["actor"] = json.loads(row["actor"])
            if row["confidence_score"] is not None:
                event["confidence_score"] = row["confidence_score"]
            if row["source_type"]:
                event["source_type"] = row["source_type"]

            events.append(event)

        return events

    def get_validation_failures(self, limit: int = 100) -> List[Dict]:
        """
        Get recent validation failures (for debugging).

        Stubbed out: the SQLite validation_failures table was dropped in migration 129
        (WO-READMODELS-DUCKDB). Validation failures are now served by the DuckDB
        validation_failures VIEW in aggregate_metrics.db (events_fact pipeline).
        Use connect_analytics(read_only=True) and SELECT from validation_failures
        in DuckDB for live data.

        Returns:
            Empty list (SQLite table no longer exists)
        """
        return []

    def close(self):
        """Close database connection."""
        self.db.close()
