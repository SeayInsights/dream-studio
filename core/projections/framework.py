"""Projection framework v2 — derives materialized L3 state from dual canonical events.

Phase 18.1.5: Rewrites the projection engine to read from business_canonical_events
and ai_canonical_events (the v2 dual canonical layer from Phase 18.1.2) instead of
the legacy canonical_events table.

Architecture:
  - Projection ABC: code-first Python classes with imperative handle() logic.
  - ProjectionRegistry: tracks registered projections; validates event_type declarations
    against the event type registry.
  - ProjectionEngine: cursor-based incremental dispatch — reads dual canonical tables,
    routes events by source_canonical declaration, retries on transient failure
    (exponential backoff), and dead-letters after max_retries exceeded.

Dead-letter pattern:
  Transient failures → projection_retry_queue (scheduled retry with backoff).
  Exhausted retries  → projection_dead_letter (status='active', operator resolves).
  The engine continues processing subsequent events after dead-lettering; one bad
  event does not block a projection's progress.

Backward compatibility:
  ProjectionCheckpoint, ProjectionResult, and projection_checkpoints DDL are all
  preserved so existing consumers.py projections keep working. The old Projection
  ABC interface (name, event_types, setup_tables, handle, pre_rebuild) is kept as
  properties/methods on the new base class; consumers.py is migrated in Phase 18.2.

Usage (new v2 projection):
    from core.projections.framework import Projection, ProjectionEngine, RetryPolicy

    class WorkOrderProjection(Projection):
        name = "work_order_projection"
        consumed_event_types = ["work_order.created", "work_order.started", "work_order.%"]
        source_canonical = "business"
        target_tables = ["business_work_orders"]
        retry_policy = RetryPolicy(max_retries=5, base_delay_seconds=2.0)

        def setup_tables(self, conn):
            pass  # migration 069 owns the DDL

        def handle(self, event, conn):
            # idempotency built in via is_already_processed()
            ...
            return 1

        def rebuild_from_canonical(self):
            # framework default: pre_rebuild() + replay via handle()
            super().rebuild_from_canonical()

Usage (engine):
    engine = ProjectionEngine()
    engine.register(WorkOrderProjection())
    engine.run_cycle()          # process pending retries + new events
    engine.rebuild("work_order_projection")
"""

import json
import logging
import sqlite3
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from config.event_type_registry import all_entries, is_registered
from core.config.database import get_connection, transaction
from core.config.paths import state_dir

logger = logging.getLogger(__name__)

# ── Canonical source literals ─────────────────────────────────────────────────

CanonicalSource = Literal["business", "ai", "both"]

_TABLE_FOR_SOURCE: Dict[str, str] = {
    "business": "business_canonical_events",
    "ai": "ai_canonical_events",
}


# ── RetryPolicy ───────────────────────────────────────────────────────────────


@dataclass
class RetryPolicy:
    """Exponential backoff retry configuration for a projection.

    Default schedule: 1 s → 2 s → 4 s (3 retries, then dead-letter).
    Override per projection class to tune for expected failure profiles.
    """

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    backoff_factor: float = 2.0  # delay = base * backoff_factor^attempt

    def delay_for(self, attempt: int) -> float:
        """Return delay in seconds for the given attempt number (0-indexed)."""
        return self.base_delay_seconds * (self.backoff_factor**attempt)

    def next_retry_at(self, attempt: int) -> str:
        """Return ISO-format UTC timestamp for the next retry."""
        delay = self.delay_for(attempt)
        ts = datetime.now(timezone.utc) + timedelta(seconds=delay)
        return ts.isoformat()


# ── Backward-compat dataclasses ───────────────────────────────────────────────


@dataclass
class ProjectionCheckpoint:
    """Legacy checkpoint record — kept for backward compat with pre-v2 code."""

    projection_name: str
    last_event_id: str
    last_timestamp: str
    events_processed: int
    last_rebuilt: str


@dataclass
class ProjectionResult:
    """Summary of a single projection run (batch of events)."""

    projection_name: str
    events_processed: int
    rows_written: int
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0


# ── Projection ABC ────────────────────────────────────────────────────────────


class Projection(ABC):
    """Base class for all Dream Studio projections (v2-compatible).

    Class attributes (define on each concrete projection):
        name (str):
            Unique projection identifier used as the primary key in
            projection_state.  Example: "work_order_projection".

        consumed_event_types (List[str]):
            Event types this projection subscribes to.  Supports '%' suffix
            wildcards (LIKE semantics).
            Example: ["work_order.created", "work_order.started"]
            Example: ["workflow.%"]  — all workflow events

        source_canonical (str):
            Which canonical table(s) to read from.
            "business" | "ai" | "both"
            Determines which column in projection_state tracks the cursor.

        target_tables (List[str]):
            L3 tables this projection writes to.  Used for registry metadata
            and for the default rebuild_from_canonical() implementation which
            calls pre_rebuild() before replaying.

        retry_policy (RetryPolicy):
            Configures exponential backoff for transient handle() failures.
            Defaults to RetryPolicy() (3 retries, 1 s base, 2× backoff).

    Backward-compat shim:
        event_types property — alias for consumed_event_types (consumers.py uses it).
    """

    # ── Class-level declarations (override in subclasses) ─────────────────────

    name: str = ""
    consumed_event_types: List[str] = field(default_factory=list)
    source_canonical: CanonicalSource = "business"
    target_tables: List[str] = field(default_factory=list)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)

    # ── Backward-compat: property alias for event_types ───────────────────────

    @property
    def event_types(self) -> List[str]:
        """Alias for consumed_event_types — preserved for consumers.py compat."""
        return self.consumed_event_types

    # ── Abstract interface (every projection must implement) ──────────────────

    @abstractmethod
    def setup_tables(self, conn: sqlite3.Connection) -> None:
        """Create target tables if they don't exist.

        Called once at registration time.  Should be idempotent (CREATE TABLE
        IF NOT EXISTS).  Projections that delegate DDL to migrations may
        implement this as a no-op.
        """
        ...

    @abstractmethod
    def handle(self, event: Dict[str, Any], conn: sqlite3.Connection) -> int:
        """Process a single canonical event and write to target table(s).

        Contract:
          - MUST be idempotent: calling handle() twice with the same event_id
            must produce the same final state (use is_already_processed or
            INSERT OR IGNORE / ON CONFLICT).
          - MUST handle out-of-order events gracefully.
          - Returns the number of rows written (used for result metrics).
          - Raises on unrecoverable error; raises on transient error (the
            engine will retry per retry_policy before dead-lettering).

        The event dict format (see _row_to_event):
            event_id (str)
            event_type (str)
            event_timestamp (str)  — ISO-8601
            trace (dict)           — parsed from JSON
            payload (dict)         — parsed from JSON
            correlation_id (str | None)
            project_id (str | None)
            work_order_id (str | None)
            _source ("business" | "ai")
        """
        ...

    # ── Optional hooks (override if needed) ───────────────────────────────────

    def pre_rebuild(self, conn: sqlite3.Connection) -> None:
        """Called before a full rebuild — truncate target tables.

        Default: DELETE FROM each table in target_tables.
        Override if you need a different truncation strategy or need to
        preserve certain rows across a rebuild.
        """
        for table in self.target_tables:
            try:
                conn.execute(f"DELETE FROM {table}")
                logger.debug("pre_rebuild: cleared %s for %s", table, self.name)
            except sqlite3.OperationalError as exc:
                logger.warning("pre_rebuild: could not clear %s: %s", table, exc)

    def rebuild_from_canonical(self) -> None:
        """Full rebuild: clear target tables and replay all canonical events.

        Default implementation:
          1. Calls pre_rebuild() inside a transaction to truncate target tables.
          2. Queries the relevant canonical table(s) for all matching events
             (ordered by event_timestamp ASC for deterministic replay).
          3. Calls handle() for each event.
          4. Resets the projection_state cursor to the last replayed event.

        Override this method for projections that need custom rebuild logic
        (e.g., reading from non-canonical sources, joining multiple tables).
        """
        engine = ProjectionEngine()
        engine.register_without_setup(self)
        engine.rebuild(self.name)

    # ── Helper methods provided by the framework ──────────────────────────────

    def is_already_processed(
        self, event_id: str, target_table: str, conn: sqlite3.Connection
    ) -> bool:
        """Idempotency check: returns True if event_id was already applied.

        Checks whether the event_id appears as source_event_id OR last_event_id
        in the target_table row.  Override if your table uses different column
        names for event provenance.

        Usage in handle():
            if self.is_already_processed(event["event_id"], "business_work_orders", conn):
                return 0
        """
        try:
            row = conn.execute(
                f"""
                SELECT 1 FROM {target_table}
                WHERE source_event_id = ? OR last_event_id = ?
                LIMIT 1
                """,
                (event_id, event_id),
            ).fetchone()
            return row is not None
        except sqlite3.OperationalError:
            # Table may not yet have these columns; treat as not processed.
            return False

    def safe_upsert(
        self,
        conn: sqlite3.Connection,
        table: str,
        row: Dict[str, Any],
        conflict_key: str,
    ) -> int:
        """INSERT ... ON CONFLICT(conflict_key) DO UPDATE SET for all other columns.

        Returns 1 always (the upserted row count).

        Usage:
            self.safe_upsert(conn, "business_work_orders", {
                "work_order_id": wo_id,
                "status": "in_progress",
                "started_at": ts,
                "last_event_id": event["event_id"],
                "last_updated_at": datetime.now(timezone.utc).isoformat(),
            }, conflict_key="work_order_id")
        """
        columns = list(row.keys())
        placeholders = ", ".join("?" * len(columns))
        col_list = ", ".join(columns)
        update_set = ", ".join(f"{c} = excluded.{c}" for c in columns if c != conflict_key)
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict_key}) DO UPDATE SET {update_set}"
        )
        conn.execute(sql, list(row.values()))
        return 1


# ── ProjectionRegistry ────────────────────────────────────────────────────────


class ProjectionRegistry:
    """Tracks registered projections and validates event type declarations.

    The registry validates that each projection's consumed_event_types entries
    match at least one entry in the event type registry.  Unknown event types
    (no wildcard, not in registry) emit a WARNING — they are not rejected,
    because the registry is comprehensive but not exhaustive.
    """

    def __init__(self) -> None:
        self._projections: Dict[str, Projection] = {}
        # Build a set of known event_types from the event type registry for
        # validation (wildcard check uses LIKE semantics against prefixes).
        self._known_types: frozenset[str] = frozenset(e.event_type for e in all_entries())

    def register(self, projection: Projection) -> None:
        """Register a projection and validate its event type declarations."""
        if not projection.name:
            raise ValueError(f"Projection {type(projection).__name__} must define a non-empty name")
        self._validate_event_types(projection)
        self._projections[projection.name] = projection
        logger.info(
            "ProjectionRegistry: registered '%s' (source=%s, types=%s)",
            projection.name,
            projection.source_canonical,
            projection.consumed_event_types,
        )

    def _validate_event_types(self, projection: Projection) -> None:
        """Warn if any declared event type is not in the event type registry."""
        for et in projection.consumed_event_types:
            if "%" in et:
                # Wildcard — skip validation (matches a family of event types).
                continue
            if not is_registered(et):
                logger.warning(
                    "ProjectionRegistry: '%s' declares event_type '%s' which is not "
                    "in the event type registry.  Add it to config/event_type_registry.py "
                    "if this is a new canonical event type.",
                    projection.name,
                    et,
                )

    def get_projections_for_event_type(self, event_type: str, source: str) -> List[Projection]:
        """Return all projections that consume the given event_type from the given source.

        Matching rules:
          - exact match:    event_type == consumed_event_type
          - wildcard match: consumed_event_type ends with '%' and event_type
                            starts with the prefix before '%'
          - source filter:  projection.source_canonical must be source or "both"
        """
        result = []
        for proj in self._projections.values():
            if not _source_matches(proj.source_canonical, source):
                continue
            for pattern in proj.consumed_event_types:
                if _event_type_matches(event_type, pattern):
                    result.append(proj)
                    break
        return result

    def all_projections(self) -> List[Projection]:
        """Return all registered projections."""
        return list(self._projections.values())

    def projected_tables(self) -> frozenset:
        """Return the set of all target tables across registered projections."""
        tables: set = set()
        for proj in self._projections.values():
            tables.update(proj.target_tables)
        return frozenset(tables)

    def get(self, name: str) -> Optional[Projection]:
        """Return projection by name or None."""
        return self._projections.get(name)

    def summary(self) -> Dict[str, Any]:
        """Return summary dict for `ds projection list`."""
        return {
            "count": len(self._projections),
            "projections": [
                {
                    "name": p.name,
                    "source_canonical": p.source_canonical,
                    "consumed_event_types": p.consumed_event_types,
                    "target_tables": p.target_tables,
                    "retry_policy": {
                        "max_retries": p.retry_policy.max_retries,
                        "base_delay_seconds": p.retry_policy.base_delay_seconds,
                        "backoff_factor": p.retry_policy.backoff_factor,
                    },
                }
                for p in self._projections.values()
            ],
        }


# ── Matching helpers ──────────────────────────────────────────────────────────


def _event_type_matches(event_type: str, pattern: str) -> bool:
    """Return True if event_type matches pattern (supports trailing '%' wildcard)."""
    if pattern.endswith("%"):
        return event_type.startswith(pattern[:-1])
    return event_type == pattern


def _source_matches(projection_source: CanonicalSource, event_source: str) -> bool:
    """Return True if the projection should receive events from this source."""
    if projection_source == "both":
        return True
    return projection_source == event_source


def _build_type_filter(event_types: List[str]) -> tuple[str, list]:
    """Build a SQL WHERE clause fragment for event type matching.

    Returns (clause, params) where clause is something like:
        "(event_type LIKE ? OR event_type = ? OR event_type LIKE ?)"
    and params are the corresponding values.
    """
    clauses = []
    params: list = []
    for et in event_types:
        if "%" in et:
            clauses.append("event_type LIKE ?")
        else:
            clauses.append("event_type = ?")
        params.append(et)
    return "(" + " OR ".join(clauses) + ")", params


# ── Row → event dict conversion ───────────────────────────────────────────────


def _row_to_event(row: sqlite3.Row, source: str) -> Dict[str, Any]:
    """Convert a sqlite3.Row from a canonical table to a normalized event dict.

    Works with both business_canonical_events and ai_canonical_events.
    The _source key indicates which canonical the event came from.
    """
    event: Dict[str, Any] = {
        "event_id": row["event_id"],
        "event_type": row["event_type"],
        "event_timestamp": row["event_timestamp"],
        "trace": _parse_json(row["trace"]),
        "payload": _parse_json(row["payload"]),
        "correlation_id": row["correlation_id"] if "correlation_id" in row.keys() else None,
        "_source": source,
    }
    # Denormalized SDLC context — present on business_canonical_events.
    for col in ("project_id", "milestone_id", "work_order_id", "task_id"):
        if col in row.keys():
            event[col] = row[col]
    # Denormalized AI execution context — present on ai_canonical_events.
    for col in ("session_id", "skill_id", "workflow_id", "agent_id", "hook_id", "model_id"):
        if col in row.keys():
            event[col] = row[col]
    return event


def _parse_json(value: Any) -> Any:
    """Parse JSON string to dict/list, or return value as-is if already parsed."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return value or {}


# ── ProjectionEngine ──────────────────────────────────────────────────────────


class ProjectionEngine:
    """Runtime engine: reads dual canonical tables and dispatches to projections.

    Cursor pattern:
      Each projection has a row in projection_state with two cursor columns:
        last_processed_business_event_id  — last event_id consumed from business
        last_processed_ai_event_id        — last event_id consumed from ai
      Events with event_timestamp > the cursor timestamp are fetched and
      dispatched in event_timestamp ASC order (deterministic replay).

    Retry / dead-letter cycle (per run_cycle()):
      1. Process any due entries in projection_retry_queue.
      2. Fetch new events from canonical tables past the current cursor.
      3. Dispatch to matching projections.
      4. On success: advance cursor in projection_state.
      5. On failure: schedule retry in projection_retry_queue.
      6. On retry exhaustion: move to projection_dead_letter.

    Backward compat:
      The old canonical_events table is NOT read by new v2 code paths.
      Old consumers.py projections continue to work via apply_incremental()
      which reads canonical_events (unchanged from pre-v2).  projection_checkpoints
      table is kept and still written for legacy projections.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or str(state_dir() / "studio.db")
        self._registry = ProjectionRegistry()
        # Legacy dict for backward compat with apply_incremental / rebuild
        self._projections: Dict[str, Projection] = {}
        self._ensure_meta_tables()

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, projection: Projection) -> None:
        """Register a projection and call setup_tables() to initialize DDL."""
        with transaction() as conn:
            projection.setup_tables(conn)
        self._registry.register(projection)
        self._projections[projection.name] = projection
        self._ensure_projection_state(projection.name)
        logger.info("ProjectionEngine: registered '%s'", projection.name)

    def register_without_setup(self, projection: Projection) -> None:
        """Register without calling setup_tables() (used internally by rebuild)."""
        if projection.name not in self._projections:
            self._registry.register(projection)
            self._projections[projection.name] = projection
            self._ensure_projection_state(projection.name)

    def _ensure_projection_state(self, projection_name: str) -> None:
        """Insert a default projection_state row if one doesn't exist."""
        with transaction() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO projection_state (projection_name)
                VALUES (?)
                """,
                (projection_name,),
            )

    # ── Main cycle ────────────────────────────────────────────────────────────

    def run_cycle(self, projection_name: Optional[str] = None) -> List[ProjectionResult]:
        """Execute one full processing cycle: retries first, then new events.

        Args:
            projection_name: If provided, only process this projection.
                             Otherwise process all registered projections.

        Returns:
            List of ProjectionResult, one per projection processed.
        """
        targets: List[Projection] = (
            [self._projections[projection_name]]
            if projection_name and projection_name in self._projections
            else list(self._projections.values())
        )
        results = []
        for proj in targets:
            self._process_retries(proj)
            results.append(self._apply_v2(proj))
        return results

    # ── V2 incremental dispatch ───────────────────────────────────────────────

    def _apply_v2(self, proj: Projection) -> ProjectionResult:
        """Fetch new events for proj from dual canonical and dispatch to handle()."""
        import time

        start = time.monotonic()
        events_processed = 0
        rows_written = 0
        errors: List[str] = []

        # Determine which canonical table(s) to query.
        sources: List[str] = (
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
        now = datetime.now(timezone.utc).isoformat()
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

    # ── Retry / dead-letter ───────────────────────────────────────────────────

    def _schedule_retry(
        self,
        proj: Projection,
        event: Dict[str, Any],
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
        now = datetime.now(timezone.utc).isoformat()
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
        now = datetime.now(timezone.utc).isoformat()

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
        errors: List[str] = []

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

                last_event_id: Optional[str] = None
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

    def rebuild_all(self) -> List[ProjectionResult]:
        """Rebuild every registered projection."""
        results = []
        for name in self._projections:
            results.append(self.rebuild(name))
        return results

    # ── Health / inspection ───────────────────────────────────────────────────

    def health(self) -> Dict[str, Any]:
        """Return projection health status (includes both v2 and legacy projections)."""
        status: Dict[str, Any] = {"projections": {}}
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

    def apply_incremental(self, projection_name: Optional[str] = None) -> List[ProjectionResult]:
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
        errors: List[str] = []
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

    def apply_since(self, cursor: Optional[str] = None) -> List[ProjectionResult]:
        """Alias for apply_incremental (legacy API)."""
        return self.apply_incremental()

    def get_checkpoint(self, name: str) -> Optional[ProjectionCheckpoint]:
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


# ── Legacy canonical_events row format ────────────────────────────────────────


def _legacy_row_to_event(row: Any) -> Dict[str, Any]:
    """Convert a row from the legacy canonical_events table to an event dict.

    Preserved exactly as in pre-v2 for consumers.py backward compat.
    The _source key is set to "legacy" to distinguish from v2 events.
    """

    def _get(row: Any, idx: int, key: str) -> Any:
        return row[idx] if isinstance(row, tuple) else row[key]

    event: Dict[str, Any] = {
        "event_id": _get(row, 0, "event_id"),
        "event_type": _get(row, 1, "event_type"),
        "timestamp": _get(row, 2, "timestamp"),
        "trace": _parse_json(_get(row, 3, "trace")),
        "severity": _get(row, 4, "severity"),
        "payload": _parse_json(_get(row, 5, "payload")),
        "_source": "legacy",
    }
    actor = _get(row, 6, "actor") if len(row) > 6 else None
    if actor:
        event["actor"] = _parse_json(actor) if isinstance(actor, str) else actor
    cs = _get(row, 7, "confidence_score") if len(row) > 7 else None
    if cs is not None:
        event["confidence_score"] = cs
    st = _get(row, 8, "source_type") if len(row) > 8 else None
    if st:
        event["source_type"] = st
    return event
