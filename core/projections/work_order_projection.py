"""Work order projection — derives business_work_orders from business_canonical_events.

This is the first v2-compliant projection and serves as the template for all
future projections.  It implements the work order state machine: created →
in_progress ↔ blocked → closed.

Phase 18.1.5 — ProjectionEngine reads from business_canonical_events; this
class contains only the state-machine logic, not any engine plumbing.
"""

import logging
import sqlite3
from datetime import datetime, UTC
from typing import Any

from core.projections.framework import Projection, RetryPolicy

logger = logging.getLogger(__name__)

_TABLE = "business_work_orders"


class WorkOrderProjection(Projection):
    """Materializes business_work_orders from business_canonical_events.

    Handles the full work order lifecycle:
      work_order.created   → INSERT row with status='created'
      work_order.started   → status='in_progress', set started_at
      work_order.blocked   → status='blocked', set blocked_at + block_reason
      work_order.unblocked → status='in_progress', clear block_reason
      work_order.closed    → status='closed', set closed_at

    Out-of-order tolerance:
      Any event arriving before its work_order.created event is handled by
      inserting a skeleton row first so the update is never silently dropped.
    """

    name = "work_order_projection"
    consumed_event_types = [
        "work_order.created",
        "work_order.started",
        "work_order.blocked",
        "work_order.unblocked",
        "work_order.closed",
        "work_order.deleted",
    ]
    source_canonical = "business"
    target_tables = [_TABLE]
    retry_policy = RetryPolicy(max_retries=3, base_delay_seconds=1.0)

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        # Migration 069 owns the business_work_orders DDL.
        pass

    def handle(self, event: dict[str, Any], conn: sqlite3.Connection) -> int:
        """Apply one canonical event to business_work_orders.

        Returns 1 for every successfully applied event, 0 if skipped (idempotent
        duplicate or unresolvable payload).
        """
        # Idempotency: skip events we have already applied to this table.
        if self.is_already_processed(event["event_id"], _TABLE, conn):
            return 0

        payload = event.get("payload") or {}
        event_type = event["event_type"]
        event_id = event["event_id"]
        ts = event["event_timestamp"]
        now = datetime.now(UTC).isoformat()

        # work_order_id is denormalized onto the canonical row; fall back to
        # the payload for events emitted before the denormalization was added.
        work_order_id = event.get("work_order_id") or payload.get("work_order_id")
        if not work_order_id:
            logger.warning(
                "WorkOrderProjection: event %s (%s) has no work_order_id — skipping",
                event_id,
                event_type,
            )
            return 0

        project_id = event.get("project_id") or payload.get("project_id")
        milestone_id = event.get("milestone_id") or payload.get("milestone_id")

        if event_type == "work_order.created":
            return self._handle_created(
                conn, work_order_id, project_id, milestone_id, payload, event_id, ts, now
            )
        # For every non-created event, ensure the row exists first.
        # A closed or blocked event can legitimately arrive before created
        # when events are ingested out of chronological order.
        self._ensure_skeleton(conn, work_order_id, project_id, now)

        if event_type == "work_order.started":
            return self._handle_started(conn, work_order_id, event_id, ts, now)
        if event_type == "work_order.blocked":
            return self._handle_blocked(conn, work_order_id, payload, event_id, ts, now)
        if event_type == "work_order.unblocked":
            return self._handle_unblocked(conn, work_order_id, event_id, ts, now)
        if event_type == "work_order.closed":
            return self._handle_closed(conn, work_order_id, event_id, ts, now)
        if event_type == "work_order.deleted":
            return self._handle_deleted(conn, work_order_id, event_id, now)

        # Declared in consumed_event_types but not handled — defensive fallback.
        logger.warning(
            "WorkOrderProjection: unhandled event_type '%s' for %s", event_type, work_order_id
        )
        return 0

    # ── Event handlers ────────────────────────────────────────────────────────

    def _handle_created(
        self,
        conn: sqlite3.Connection,
        work_order_id: str,
        project_id: str | None,
        milestone_id: str | None,
        payload: dict,
        event_id: str,
        ts: str,
        now: str,
    ) -> int:
        """INSERT OR IGNORE so a duplicate created event is a no-op."""
        row = {
            "work_order_id": work_order_id,
            "project_id": project_id,
            "milestone_id": milestone_id,
            "title": payload.get("title"),
            "work_order_type": payload.get("type"),
            "status": "created",
            "created_at": ts,
            "source_event_id": event_id,
            "last_event_id": event_id,
            "last_updated_at": now,
            "originating_symptom": payload.get("originating_symptom"),
        }
        # INSERT OR IGNORE preserves an existing skeleton row written by an
        # out-of-order event while still recording source_event_id on a
        # genuinely new row.  We then patch the fields the skeleton lacked.
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_TABLE}
                (work_order_id, project_id, milestone_id, title, work_order_type,
                 status, created_at, source_event_id, last_event_id, last_updated_at,
                 originating_symptom)
            VALUES
                (:work_order_id, :project_id, :milestone_id, :title, :work_order_type,
                 :status, :created_at, :source_event_id, :last_event_id, :last_updated_at,
                 :originating_symptom)
            """,
            row,
        )
        # If the row already existed (skeleton from out-of-order event), fill
        # in the fields that only the created event carries.  work_order_type is
        # patched via COALESCE so a skeleton row that arrived without a type is
        # backfilled from the created event — the WorkOrderProjection type-drop fix.
        conn.execute(
            f"""
            UPDATE {_TABLE}
            SET project_id           = COALESCE(project_id, :project_id),
                milestone_id         = COALESCE(milestone_id, :milestone_id),
                title                = COALESCE(title, :title),
                work_order_type      = COALESCE(work_order_type, :work_order_type),
                created_at           = COALESCE(created_at, :created_at),
                source_event_id      = COALESCE(source_event_id, :source_event_id),
                originating_symptom  = COALESCE(originating_symptom, :originating_symptom),
                last_updated_at      = :last_updated_at
            WHERE work_order_id = :work_order_id
            """,
            row,
        )
        return 1

    def _handle_started(
        self,
        conn: sqlite3.Connection,
        work_order_id: str,
        event_id: str,
        ts: str,
        now: str,
    ) -> int:
        return self.safe_upsert(
            conn,
            _TABLE,
            {
                "work_order_id": work_order_id,
                "status": "in_progress",
                "started_at": ts,
                "last_event_id": event_id,
                "last_updated_at": now,
            },
            conflict_key="work_order_id",
        )

    def _handle_blocked(
        self,
        conn: sqlite3.Connection,
        work_order_id: str,
        payload: dict,
        event_id: str,
        ts: str,
        now: str,
    ) -> int:
        block_reason = payload.get("reason") or payload.get("block_reason")
        return self.safe_upsert(
            conn,
            _TABLE,
            {
                "work_order_id": work_order_id,
                "status": "blocked",
                "blocked_at": ts,
                "block_reason": block_reason,
                "last_event_id": event_id,
                "last_updated_at": now,
            },
            conflict_key="work_order_id",
        )

    def _handle_unblocked(
        self,
        conn: sqlite3.Connection,
        work_order_id: str,
        event_id: str,
        ts: str,
        now: str,
    ) -> int:
        return self.safe_upsert(
            conn,
            _TABLE,
            {
                "work_order_id": work_order_id,
                "status": "in_progress",
                "unblocked_at": ts,
                "block_reason": None,
                "last_event_id": event_id,
                "last_updated_at": now,
            },
            conflict_key="work_order_id",
        )

    def _handle_closed(
        self,
        conn: sqlite3.Connection,
        work_order_id: str,
        event_id: str,
        ts: str,
        now: str,
    ) -> int:
        return self.safe_upsert(
            conn,
            _TABLE,
            {
                "work_order_id": work_order_id,
                "status": "closed",
                "closed_at": ts,
                "last_event_id": event_id,
                "last_updated_at": now,
            },
            conflict_key="work_order_id",
        )

    def _handle_deleted(
        self,
        conn: sqlite3.Connection,
        work_order_id: str,
        event_id: str,
        now: str,
    ) -> int:
        return self.safe_upsert(
            conn,
            _TABLE,
            {
                "work_order_id": work_order_id,
                "status": "deleted",
                "last_event_id": event_id,
                "last_updated_at": now,
            },
            conflict_key="work_order_id",
        )

    # ── Out-of-order helper ───────────────────────────────────────────────────

    def _ensure_skeleton(
        self,
        conn: sqlite3.Connection,
        work_order_id: str,
        project_id: str | None,
        now: str,
    ) -> None:
        """INSERT OR IGNORE a minimal row so subsequent UPSERTs never fail.

        This fires only when a non-created event arrives before work_order.created.
        The skeleton's sparse fields will be backfilled when created arrives.
        """
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_TABLE}
                (work_order_id, project_id, status, last_updated_at)
            VALUES (?, ?, 'created', ?)
            """,
            (work_order_id, project_id, now),
        )
