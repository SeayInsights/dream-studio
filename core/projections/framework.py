"""Projection framework — derives materialized state from canonical events.

A projection reads events from canonical_events, transforms them, and writes
to a target table. Projections are idempotent: rebuilding from scratch produces
the same result as incremental application.

Usage:
    from core.projections.framework import ProjectionEngine

    engine = ProjectionEngine()
    engine.register(WorkflowProjection())
    engine.register(SkillRoutingProjection())
    engine.rebuild_all()       # full rebuild from event stream
    engine.apply_since(cursor) # incremental from last checkpoint
"""

import json
import logging
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from core.config.database import get_connection, transaction
from core.config.paths import state_dir

logger = logging.getLogger(__name__)


@dataclass
class ProjectionCheckpoint:
    projection_name: str
    last_event_id: str
    last_timestamp: str
    events_processed: int
    last_rebuilt: str


@dataclass
class ProjectionResult:
    projection_name: str
    events_processed: int
    rows_written: int
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0


class Projection(ABC):
    """Base class for event projections.

    Subclasses define:
    - name: unique projection identifier
    - event_types: which events this projection consumes
    - setup_tables(): DDL to create target tables
    - handle(event): transform one event into target writes
    - rebuild(): optional full-rebuild logic
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def event_types(self) -> List[str]:
        """Event types this projection subscribes to. Use '%' for wildcards."""
        ...

    @abstractmethod
    def setup_tables(self, conn: sqlite3.Connection) -> None:
        """Create target tables if they don't exist."""
        ...

    @abstractmethod
    def handle(self, event: Dict[str, Any], conn: sqlite3.Connection) -> int:
        """Process one event. Returns number of rows written."""
        ...

    def pre_rebuild(self, conn: sqlite3.Connection) -> None:
        """Called before rebuild — truncate target tables."""
        pass


class ProjectionEngine:
    """Runs projections against the canonical event stream."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(state_dir() / "studio.db")
        self._projections: Dict[str, Projection] = {}
        self._ensure_meta_tables()

    def _ensure_meta_tables(self) -> None:
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

    def register(self, projection: Projection) -> None:
        with transaction() as conn:
            projection.setup_tables(conn)
        self._projections[projection.name] = projection
        logger.info(f"Registered projection: {projection.name}")

    def get_checkpoint(self, name: str) -> Optional[ProjectionCheckpoint]:
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
        now = datetime.now(timezone.utc).isoformat()
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

    def apply_incremental(self, projection_name: Optional[str] = None) -> List[ProjectionResult]:
        """Apply new events since last checkpoint."""
        targets = (
            [self._projections[projection_name]]
            if projection_name and projection_name in self._projections
            else list(self._projections.values())
        )
        results = []
        for proj in targets:
            results.append(self._apply_one(proj))
        return results

    def _apply_one(self, proj: Projection) -> ProjectionResult:
        import time

        start = time.monotonic()
        checkpoint = self.get_checkpoint(proj.name)
        last_ts = checkpoint.last_timestamp if checkpoint else "1970-01-01T00:00:00Z"

        type_clauses = []
        params: list = []
        for et in proj.event_types:
            if "%" in et:
                type_clauses.append("event_type LIKE ?")
            else:
                type_clauses.append("event_type = ?")
            params.append(et)

        type_filter = "(" + " OR ".join(type_clauses) + ")"

        query = f"""
            SELECT event_id, event_type, timestamp, trace, severity,
                   payload, actor, confidence_score, source_type
            FROM canonical_events
            WHERE timestamp > ? AND {type_filter}
            ORDER BY timestamp ASC
        """
        params.insert(0, last_ts)

        events_processed = 0
        rows_written = 0
        errors: List[str] = []
        last_event_id = ""
        last_timestamp = last_ts

        with transaction() as conn:
            cursor = conn.execute(query, params)
            for row in cursor:
                event = self._row_to_event(row)
                try:
                    written = proj.handle(event, conn)
                    rows_written += written
                    events_processed += 1
                    last_event_id = event["event_id"]
                    last_timestamp = event["timestamp"]
                except Exception as e:
                    errors.append(f"{event['event_id']}: {e}")
                    logger.warning(f"Projection {proj.name} error on {event['event_id']}: {e}")

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

    def rebuild(self, projection_name: str) -> ProjectionResult:
        """Full rebuild: truncate target, replay all events."""
        proj = self._projections[projection_name]
        import time

        start = time.monotonic()

        type_clauses = []
        params: list = []
        for et in proj.event_types:
            if "%" in et:
                type_clauses.append("event_type LIKE ?")
            else:
                type_clauses.append("event_type = ?")
            params.append(et)
        type_filter = "(" + " OR ".join(type_clauses) + ")"

        events_processed = 0
        rows_written = 0
        errors: List[str] = []
        last_event_id = ""
        last_timestamp = "1970-01-01T00:00:00Z"

        with transaction() as conn:
            proj.pre_rebuild(conn)

            cursor = conn.execute(
                f"SELECT * FROM canonical_events WHERE {type_filter} ORDER BY timestamp ASC",
                params,
            )
            for row in cursor:
                event = self._row_to_event(row)
                try:
                    written = proj.handle(event, conn)
                    rows_written += written
                    events_processed += 1
                    last_event_id = event["event_id"]
                    last_timestamp = event["timestamp"]
                except Exception as e:
                    errors.append(f"{event['event_id']}: {e}")

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

    def rebuild_all(self) -> List[ProjectionResult]:
        results = []
        for name in self._projections:
            results.append(self.rebuild(name))
        return results

    def health(self) -> Dict[str, Any]:
        """Return projection health status."""
        status: Dict[str, Any] = {"projections": {}}
        with get_connection(read_only=True) as conn:
            total_events = conn.execute("SELECT COUNT(*) FROM canonical_events").fetchone()[0]
            status["total_events"] = total_events

            for name, proj in self._projections.items():
                cp = self.get_checkpoint(name)
                status["projections"][name] = {
                    "event_types": proj.event_types,
                    "last_processed": cp.last_timestamp if cp else None,
                    "events_processed": cp.events_processed if cp else 0,
                    "last_rebuilt": cp.last_rebuilt if cp else None,
                    "healthy": cp is not None,
                }
        return status

    @staticmethod
    def _row_to_event(row) -> Dict[str, Any]:
        event = {
            "event_id": row[0] if isinstance(row, tuple) else row["event_id"],
            "event_type": row[1] if isinstance(row, tuple) else row["event_type"],
            "timestamp": row[2] if isinstance(row, tuple) else row["timestamp"],
            "trace": json.loads(row[3] if isinstance(row, tuple) else row["trace"]),
            "severity": row[4] if isinstance(row, tuple) else row["severity"],
            "payload": json.loads(row[5] if isinstance(row, tuple) else row["payload"]),
        }
        actor = row[6] if isinstance(row, tuple) else row["actor"]
        if actor:
            event["actor"] = json.loads(actor) if isinstance(actor, str) else actor
        cs = row[7] if isinstance(row, tuple) else row["confidence_score"]
        if cs is not None:
            event["confidence_score"] = cs
        st = row[8] if isinstance(row, tuple) else row["source_type"]
        if st:
            event["source_type"] = st
        return event
