"""Projection ABC — base class for all Dream Studio projections (v2-compatible).

WO-GF-PROJECTION-ENGINE: split from ``core/projections/framework.py``.

CYCLE NOTE: ``rebuild_from_canonical()`` constructs a ``ProjectionEngine`` (a
runtime dependency), while ``ProjectionEngine.register()`` type-hints
``Projection``. To keep the DAG acyclic at import time, ``framework_engine.py``
imports ``Projection`` at module scope (one-directional), and this module's
``rebuild_from_canonical()`` imports ``ProjectionEngine`` lazily, function-local.
This lazy import is introduced by the split and MUST stay lazy — a top-level
import here would create an import cycle with ``framework_engine.py``.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import field
from typing import Any

from .framework_shared import CanonicalSource, RetryPolicy, logger


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
    consumed_event_types: list[str] = field(default_factory=list)
    source_canonical: CanonicalSource = "business"
    target_tables: list[str] = field(default_factory=list)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)

    # ── Backward-compat: property alias for event_types ───────────────────────

    @property
    def event_types(self) -> list[str]:
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
    def handle(self, event: dict[str, Any], conn: sqlite3.Connection) -> int:
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
        from .framework_engine import ProjectionEngine

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
        row: dict[str, Any],
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
