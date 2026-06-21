"""Milestone projection — derives business_milestones from business_canonical_events.

Modeled on WorkOrderProjection (Phase 18.1.5). Implements the milestone state
machine: pending → active → complete, or → deleted.

Phase 18.2.3 — builds MilestoneProjection alongside TaskProjection to
complete the business-table event-sourcing layer for milestones.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict

from core.projections.framework import Projection, RetryPolicy

logger = logging.getLogger(__name__)

_TABLE = "business_milestones"


class MilestoneProjection(Projection):
    """Materializes business_milestones from business_canonical_events.

    Handles the milestone lifecycle:
      milestone.created   → INSERT row with status='pending'
      milestone.completed → status='complete', set updated_at
      milestone.deleted   → status='deleted', set updated_at

    Out-of-order tolerance:
      Any event arriving before its milestone.created event is handled by
      inserting a skeleton row first so the update is never silently dropped.
    """

    name = "milestone_projection"
    consumed_event_types = [
        "milestone.created",
        "milestone.completed",
        "milestone.deleted",
    ]
    source_canonical = "business"
    target_tables = [_TABLE]
    retry_policy = RetryPolicy(max_retries=3, base_delay_seconds=1.0)

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        # Migration 073 owns the business_milestones DDL additions.
        pass

    def handle(self, event: Dict[str, Any], conn: sqlite3.Connection) -> int:
        """Apply one canonical event to business_milestones.

        Returns 1 for every successfully applied event, 0 if skipped.
        """
        if self.is_already_processed(event["event_id"], _TABLE, conn):
            return 0

        payload = event.get("payload") or {}
        event_type = event["event_type"]
        event_id = event["event_id"]
        ts = event["event_timestamp"]
        now = datetime.now(timezone.utc).isoformat()

        # milestone_id is denormalized onto the canonical row; fall back to trace.
        milestone_id = event.get("milestone_id") or (event.get("trace") or {}).get("milestone_id")
        if not milestone_id:
            logger.warning(
                "MilestoneProjection: event %s (%s) has no milestone_id — skipping",
                event_id,
                event_type,
            )
            return 0

        project_id = event.get("project_id") or (event.get("trace") or {}).get("project_id")

        if event_type == "milestone.created":
            return self._handle_created(conn, milestone_id, project_id, payload, event_id, ts, now)
        self._ensure_skeleton(conn, milestone_id, project_id, now)

        if event_type == "milestone.completed":
            return self._handle_completed(conn, milestone_id, event_id, now)
        if event_type == "milestone.deleted":
            return self._handle_deleted(conn, milestone_id, event_id, now)

        logger.warning(
            "MilestoneProjection: unhandled event_type '%s' for %s",
            event_type,
            milestone_id,
        )
        return 0

    # ── Event handlers ────────────────────────────────────────────────────────

    def _handle_created(
        self,
        conn: sqlite3.Connection,
        milestone_id: str,
        project_id: str | None,
        payload: dict,
        event_id: str,
        ts: str,
        now: str,
    ) -> int:
        """INSERT OR IGNORE so a duplicate created event is a no-op."""
        row = {
            "milestone_id": milestone_id,
            "project_id": project_id,
            "title": payload.get("title") or "(pending)",
            "description": payload.get("description"),
            "status": payload.get("status") or "pending",
            "order_index": payload.get("order_index") or 0,
            "created_at": ts,
            "updated_at": now,
            "source_event_id": event_id,
            "last_event_id": event_id,
        }
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_TABLE}
                (milestone_id, project_id, title, description, status, order_index,
                 created_at, updated_at, source_event_id, last_event_id)
            VALUES
                (:milestone_id, :project_id, :title, :description, :status, :order_index,
                 :created_at, :updated_at, :source_event_id, :last_event_id)
            """,
            row,
        )
        # Backfill sparse fields written by an out-of-order skeleton.
        conn.execute(
            f"""
            UPDATE {_TABLE}
            SET project_id      = COALESCE(project_id, :project_id),
                title           = COALESCE(CASE WHEN title = '(pending)' THEN :title ELSE NULL END, title, :title),
                description     = COALESCE(description, :description),
                created_at      = COALESCE(created_at, :created_at),
                source_event_id = COALESCE(source_event_id, :source_event_id),
                updated_at      = :updated_at
            WHERE milestone_id = :milestone_id
            """,
            row,
        )
        return 1

    def _handle_completed(
        self,
        conn: sqlite3.Connection,
        milestone_id: str,
        event_id: str,
        now: str,
    ) -> int:
        # safe_upsert cannot be used here: business_milestones has strict NOT NULL
        # constraints (project_id, title) that SQLite evaluates during the INSERT
        # phase of ON CONFLICT DO UPDATE even when the row exists. Use a plain
        # UPDATE instead; _ensure_skeleton guarantees the row exists before this runs.
        conn.execute(
            f"UPDATE {_TABLE}"
            " SET status = 'complete', updated_at = ?, last_event_id = ?"
            " WHERE milestone_id = ?",
            (now, event_id, milestone_id),
        )
        return 1

    def _handle_deleted(
        self,
        conn: sqlite3.Connection,
        milestone_id: str,
        event_id: str,
        now: str,
    ) -> int:
        conn.execute(
            f"UPDATE {_TABLE}"
            " SET status = 'deleted', updated_at = ?, last_event_id = ?"
            " WHERE milestone_id = ?",
            (now, event_id, milestone_id),
        )
        return 1

    # ── Out-of-order helper ───────────────────────────────────────────────────

    def _ensure_skeleton(
        self,
        conn: sqlite3.Connection,
        milestone_id: str,
        project_id: str | None,
        now: str,
    ) -> None:
        """INSERT OR IGNORE a minimal row so subsequent UPSERTs never fail."""
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_TABLE}
                (milestone_id, project_id, title, status, created_at, updated_at)
            VALUES (?, ?, '(pending)', 'pending', ?, ?)
            """,
            (milestone_id, project_id, now, now),
        )
