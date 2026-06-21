"""Project projection — derives business_projects from business_canonical_events.

Modeled on MilestoneProjection / DesignBriefProjection (Phase 18.2.3/18.2.4).
Implements the project state machine:
  created → active ↔ paused → deleted (soft)

Phase 18.2.5 — event-sourcing coverage for project lifecycle.

Events handled:
  project.created     → INSERT row with status='active'
  project.activated   → UPDATE status='active'
  project.deactivated → UPDATE status='paused'
  project.deleted     → UPDATE status='deleted' (soft delete)

Out-of-order tolerance:
  Any non-created event arriving before project.created inserts a skeleton row
  so the update is never silently dropped.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict

from core.projections.framework import Projection, RetryPolicy

logger = logging.getLogger(__name__)

_TABLE = "business_projects"


class ProjectProjection(Projection):
    """Materializes business_projects from business_canonical_events.

    State machine:
      project.created     → INSERT OR IGNORE (status='active')
      project.activated   → status='active'
      project.deactivated → status='paused'
      project.deleted     → status='deleted'  (soft delete — row stays queryable)
    """

    name = "project_projection"
    consumed_event_types = [
        "project.created",
        "project.activated",
        "project.deactivated",
        "project.deleted",
    ]
    source_canonical = "business"
    target_tables = [_TABLE]
    retry_policy = RetryPolicy(max_retries=3, base_delay_seconds=1.0)

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        # Migration 076 owns the business_projects DDL additions.
        pass

    def handle(self, event: Dict[str, Any], conn: sqlite3.Connection) -> int:
        """Apply one canonical event to business_projects.

        Returns 1 for a successfully applied event, 0 if skipped.
        """
        if self.is_already_processed(event["event_id"], _TABLE, conn):
            return 0

        payload = event.get("payload") or {}
        event_type = event["event_type"]
        event_id = event["event_id"]
        ts = event["event_timestamp"]
        now = datetime.now(timezone.utc).isoformat()

        project_id = (
            event.get("project_id")
            or (event.get("trace") or {}).get("project_id")
            or payload.get("project_id")
        )
        if not project_id:
            logger.warning(
                "ProjectProjection: event %s (%s) has no project_id — skipping",
                event_id,
                event_type,
            )
            return 0

        if event_type == "project.created":
            return self._handle_created(conn, project_id, payload, event_id, ts, now)
        self._ensure_skeleton(conn, project_id, now)

        if event_type == "project.activated":
            return self._handle_activated(conn, project_id, event_id, now)
        if event_type == "project.deactivated":
            return self._handle_deactivated(conn, project_id, event_id, now)
        if event_type == "project.deleted":
            return self._handle_deleted(conn, project_id, event_id, now)

        logger.warning(
            "ProjectProjection: unhandled event_type '%s' for %s", event_type, project_id
        )
        return 0

    # ── Event handlers ────────────────────────────────────────────────────────

    def _handle_created(
        self,
        conn: sqlite3.Connection,
        project_id: str,
        payload: dict,
        event_id: str,
        ts: str,
        now: str,
    ) -> int:
        """INSERT OR IGNORE so a duplicate created event is a no-op."""
        row = {
            "project_id": project_id,
            "name": payload.get("name") or "",
            "description": payload.get("description") or "",
            "status": payload.get("status") or "active",
            "created_at": ts,
            "updated_at": now,
            "source_event_id": event_id,
            "last_event_id": event_id,
        }
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_TABLE}
                (project_id, name, description, status, created_at, updated_at,
                 source_event_id, last_event_id)
            VALUES
                (:project_id, :name, :description, :status, :created_at, :updated_at,
                 :source_event_id, :last_event_id)
            """,
            row,
        )
        # Backfill sparse fields if a skeleton row already existed.
        conn.execute(
            f"""
            UPDATE {_TABLE}
            SET name            = COALESCE(NULLIF(name, ''), :name),
                description     = COALESCE(NULLIF(description, ''), :description),
                created_at      = COALESCE(created_at, :created_at),
                source_event_id = COALESCE(source_event_id, :source_event_id),
                updated_at      = :updated_at
            WHERE project_id = :project_id
            """,
            row,
        )
        return 1

    def _handle_activated(
        self,
        conn: sqlite3.Connection,
        project_id: str,
        event_id: str,
        now: str,
    ) -> int:
        conn.execute(
            f"UPDATE {_TABLE}"
            " SET status = 'active', updated_at = ?, last_event_id = ?"
            " WHERE project_id = ?",
            (now, event_id, project_id),
        )
        return 1

    def _handle_deactivated(
        self,
        conn: sqlite3.Connection,
        project_id: str,
        event_id: str,
        now: str,
    ) -> int:
        conn.execute(
            f"UPDATE {_TABLE}"
            " SET status = 'paused', updated_at = ?, last_event_id = ?"
            " WHERE project_id = ?",
            (now, event_id, project_id),
        )
        return 1

    def _handle_deleted(
        self,
        conn: sqlite3.Connection,
        project_id: str,
        event_id: str,
        now: str,
    ) -> int:
        conn.execute(
            f"UPDATE {_TABLE}"
            " SET status = 'deleted', updated_at = ?, last_event_id = ?"
            " WHERE project_id = ?",
            (now, event_id, project_id),
        )
        return 1

    # ── Out-of-order helper ───────────────────────────────────────────────────

    def _ensure_skeleton(
        self,
        conn: sqlite3.Connection,
        project_id: str,
        now: str,
    ) -> None:
        """INSERT OR IGNORE a minimal row so subsequent updates never fail."""
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_TABLE}
                (project_id, name, status, created_at, updated_at)
            VALUES (?, '', 'active', ?, ?)
            """,
            (project_id, now, now),
        )
