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

        canonical_events is primarily declared by migration 083.
        This block is an idempotent fallback (IF NOT EXISTS) for environments
        where the migration runner has not yet run (e.g. direct EventStore instantiation
        in isolation). The column list matches migration 083's authoritative schema.
        """
        with self._transaction() as conn:
            # Canonical event stream — mirror of migration 083 DDL.
            # Migration 083 is the authoritative declaration; this is a runtime fallback.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    trace JSON NOT NULL DEFAULT '{}',
                    severity TEXT NOT NULL DEFAULT 'info',
                    payload JSON NOT NULL DEFAULT '{}',
                    actor JSON,
                    confidence_score REAL,
                    source_type TEXT,
                    raw_prompt_retained INTEGER NOT NULL DEFAULT 0,
                    raw_tool_output_retained INTEGER NOT NULL DEFAULT 0,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    invocation_mode TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS validation_failures (
                    failure_id TEXT PRIMARY KEY,
                    event_id TEXT,
                    event_type TEXT,
                    errors JSON NOT NULL,
                    attempted_event JSON NOT NULL,
                    attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_canonical_events_event_type
                ON canonical_events(event_type)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_canonical_events_timestamp
                ON canonical_events(timestamp)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_validation_failures_event_type
                ON validation_failures(event_type)
            """)

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

        # Event is valid - persist to canonical_events (NEW architecture)
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO canonical_events (
                    event_id, event_type, timestamp, trace, severity, payload,
                    actor, confidence_score, source_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    event["event_id"],
                    event["event_type"],
                    event["timestamp"],
                    json.dumps(event["trace"]),
                    event["severity"],
                    json.dumps(event["payload"]),
                    json.dumps(event.get("actor")) if event.get("actor") else None,
                    event.get("confidence_score"),
                    event.get("source_type"),
                ),
            )

        return True

    def _log_validation_failure(self, event: Dict, result: ValidationResult):
        """
        Log validation failure to validation_failures table.

        Args:
            event: Invalid event
            result: ValidationResult with errors
        """
        failure_id = str(uuid4())
        event_id = event.get("event_id", "MISSING")
        event_type = event.get("event_type", "UNKNOWN")

        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO validation_failures (
                    failure_id, event_id, event_type, errors, attempted_event
                )
                VALUES (?, ?, ?, ?, ?)
            """,
                (failure_id, event_id, event_type, json.dumps(result.errors), json.dumps(event)),
            )

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
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO canonical_events (
                    event_id, event_type, timestamp, trace, severity, payload
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    failure_event["event_id"],
                    failure_event["event_type"],
                    failure_event["timestamp"],
                    json.dumps(failure_event["trace"]),
                    failure_event["severity"],
                    json.dumps(failure_event["payload"]),
                ),
            )

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

        Args:
            limit: Maximum number of failures to return

        Returns:
            List of validation failure records
        """
        cursor = self.db.execute(
            """
            SELECT * FROM validation_failures
            ORDER BY attempted_at DESC
            LIMIT ?
        """,
            (limit,),
        )

        rows = cursor.fetchall()

        failures = []
        for row in rows:
            failures.append(
                {
                    "failure_id": row["failure_id"],
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "errors": json.loads(row["errors"]),
                    "attempted_event": json.loads(row["attempted_event"]),
                    "attempted_at": row["attempted_at"],
                }
            )

        return failures

    def close(self):
        """Close database connection."""
        self.db.close()
