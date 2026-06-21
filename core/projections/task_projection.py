"""Task projection — derives business_tasks from business_canonical_events.

Modeled on WorkOrderProjection (Phase 18.1.5). Implements the task state
machine: pending → complete, or → deleted.

Phase 18.2.3 — builds TaskProjection alongside MilestoneProjection to
complete the business-table event-sourcing layer for tasks.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict

from core.projections.framework import Projection, RetryPolicy

logger = logging.getLogger(__name__)

_TABLE = "business_tasks"
_SKELETON_TITLE = "(pending)"


class TaskProjection(Projection):
    """Materializes business_tasks from business_canonical_events.

    Handles the full task lifecycle:
      task.created   → INSERT row with status='pending'
      task.completed → status='complete', set updated_at
      task.deleted   → status='deleted', set updated_at

    Out-of-order tolerance:
      Any event arriving before its task.created event is handled by
      inserting a skeleton row first so the update is never silently dropped.
      The skeleton uses a placeholder title that is backfilled when
      task.created arrives.
    """

    name = "task_projection"
    consumed_event_types = [
        "task.created",
        "task.completed",
        "task.deleted",
    ]
    source_canonical = "business"
    target_tables = [_TABLE]
    retry_policy = RetryPolicy(max_retries=3, base_delay_seconds=1.0)

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        # Migration 072 owns the business_tasks DDL additions.
        pass

    def handle(self, event: Dict[str, Any], conn: sqlite3.Connection) -> int:
        """Apply one canonical event to business_tasks.

        Returns 1 for every successfully applied event, 0 if skipped.
        """
        if self.is_already_processed(event["event_id"], _TABLE, conn):
            return 0

        payload = event.get("payload") or {}
        event_type = event["event_type"]
        event_id = event["event_id"]
        ts = event["event_timestamp"]
        now = datetime.now(timezone.utc).isoformat()

        # task_id is denormalized onto the canonical row; fall back to trace.
        task_id = event.get("task_id") or (event.get("trace") or {}).get("task_id")
        if not task_id:
            logger.warning(
                "TaskProjection: event %s (%s) has no task_id — skipping",
                event_id,
                event_type,
            )
            return 0

        work_order_id = event.get("work_order_id") or (event.get("trace") or {}).get(
            "work_order_id"
        )
        project_id = event.get("project_id") or (event.get("trace") or {}).get("project_id")

        if event_type == "task.created":
            return self._handle_created(
                conn, task_id, work_order_id, project_id, payload, event_id, ts, now
            )
        self._ensure_skeleton(conn, task_id, work_order_id, project_id, now)

        if event_type == "task.completed":
            return self._handle_completed(conn, task_id, event_id, now)
        if event_type == "task.deleted":
            return self._handle_deleted(conn, task_id, event_id, now)

        logger.warning("TaskProjection: unhandled event_type '%s' for %s", event_type, task_id)
        return 0

    # ── Event handlers ────────────────────────────────────────────────────────

    def _handle_created(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        work_order_id: str | None,
        project_id: str | None,
        payload: dict,
        event_id: str,
        ts: str,
        now: str,
    ) -> int:
        """INSERT OR IGNORE so a duplicate created event is a no-op."""
        row = {
            "task_id": task_id,
            "work_order_id": work_order_id,
            "project_id": project_id,
            "title": payload.get("title") or _SKELETON_TITLE,
            "description": payload.get("description"),
            "acceptance_criteria": payload.get("acceptance_criteria"),
            "status": "pending",
            "created_at": ts,
            "updated_at": now,
            "source_event_id": event_id,
            "last_event_id": event_id,
        }
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_TABLE}
                (task_id, work_order_id, project_id, title, description,
                 acceptance_criteria, status,
                 created_at, updated_at, source_event_id, last_event_id)
            VALUES
                (:task_id, :work_order_id, :project_id, :title, :description,
                 :acceptance_criteria, :status,
                 :created_at, :updated_at, :source_event_id, :last_event_id)
            """,
            row,
        )
        # Backfill fields the skeleton row may have lacked.
        conn.execute(
            f"""
            UPDATE {_TABLE}
            SET work_order_id       = COALESCE(work_order_id, :work_order_id),
                project_id          = COALESCE(project_id, :project_id),
                title               = CASE WHEN title = :skeleton THEN :title ELSE
                                           COALESCE(title, :title) END,
                description         = COALESCE(description, :description),
                acceptance_criteria = COALESCE(acceptance_criteria, :acceptance_criteria),
                created_at          = COALESCE(created_at, :created_at),
                source_event_id     = COALESCE(source_event_id, :source_event_id),
                updated_at          = :updated_at
            WHERE task_id = :task_id
            """,
            {**row, "skeleton": _SKELETON_TITLE},
        )
        return 1

    def _handle_completed(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        event_id: str,
        now: str,
    ) -> int:
        # safe_upsert cannot be used here: business_tasks has strict NOT NULL
        # constraints (work_order_id, project_id, title) that SQLite evaluates
        # during the INSERT phase of ON CONFLICT DO UPDATE even when the row
        # exists. Use a plain UPDATE instead; _ensure_skeleton guarantees the
        # row exists before this runs.
        conn.execute(
            f"UPDATE {_TABLE}"
            " SET status = 'complete', updated_at = ?, last_event_id = ?"
            " WHERE task_id = ?",
            (now, event_id, task_id),
        )
        return 1

    def _handle_deleted(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        event_id: str,
        now: str,
    ) -> int:
        conn.execute(
            f"UPDATE {_TABLE}"
            " SET status = 'deleted', updated_at = ?, last_event_id = ?"
            " WHERE task_id = ?",
            (now, event_id, task_id),
        )
        return 1

    # ── Out-of-order helper ───────────────────────────────────────────────────

    def _ensure_skeleton(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        work_order_id: str | None,
        project_id: str | None,
        now: str,
    ) -> None:
        """INSERT OR IGNORE a minimal row so subsequent UPSERTs never fail.

        business_tasks.title is NOT NULL, so the skeleton uses a placeholder
        that task.created will backfill when it arrives.
        """
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_TABLE}
                (task_id, work_order_id, project_id, title, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (task_id, work_order_id, project_id, _SKELETON_TITLE, now, now),
        )
