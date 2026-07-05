"""Design brief projection — derives business_design_briefs from business_canonical_events.

Modeled on TaskProjection / MilestoneProjection (Phase 18.2.3). Implements the
brief state machine: draft → (field updates) → locked.

Phase 18.2.4 — first event-sourcing coverage for design briefs.

Events handled:
  design_brief.created → INSERT row with project_id, status='draft'
  design_brief.updated → UPDATE one field (validated against _UPDATABLE_FIELDS)
  design_brief.locked  → UPDATE status='locked'

Out-of-order tolerance:
  Any event arriving before its design_brief.created is handled by inserting a
  skeleton row so the update is never silently dropped. Skeleton uses project_id
  from the event trace (populated by writers).
"""

import logging
import sqlite3
from datetime import datetime, UTC
from typing import Any

from core.projections.framework import Projection, RetryPolicy

logger = logging.getLogger(__name__)

_TABLE = "business_design_briefs"

# Safe allowlist for field-update events. Only these columns may be written by
# design_brief.updated. The f-string update is safe because field is validated
# against this frozenset before reaching the SQL layer.
_UPDATABLE_FIELDS: frozenset[str] = frozenset(
    ["purpose", "audience", "tone", "design_system", "font_pairing", "brand_tokens", "raw_output"]
)


class DesignBriefProjection(Projection):
    """Materializes business_design_briefs from business_canonical_events.

    Handles the full brief lifecycle:
      design_brief.created → INSERT row with status='draft'
      design_brief.updated → UPDATE one field on a draft brief
      design_brief.locked  → status='locked', set updated_at

    Out-of-order tolerance:
      Any event arriving before its design_brief.created event is handled by
      inserting a skeleton row first so the update is never silently dropped.
      business_design_briefs.project_id is NOT NULL, so the skeleton requires
      project_id from the event trace — writers populate it for all event types.
    """

    name = "design_brief_projection"
    consumed_event_types = [
        "design_brief.created",
        "design_brief.updated",
        "design_brief.locked",
        "design_brief.deleted",
    ]
    source_canonical = "business"
    target_tables = [_TABLE]
    retry_policy = RetryPolicy(max_retries=3, base_delay_seconds=1.0)

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        # Migration 074 owns the business_design_briefs DDL additions.
        pass

    def handle(self, event: dict[str, Any], conn: sqlite3.Connection) -> int:
        """Apply one canonical event to business_design_briefs.

        Returns 1 for every successfully applied event, 0 if skipped.
        """
        if self.is_already_processed(event["event_id"], _TABLE, conn):
            return 0

        payload = event.get("payload") or {}
        event_type = event["event_type"]
        event_id = event["event_id"]
        ts = event["event_timestamp"]
        now = datetime.now(UTC).isoformat()

        brief_id = (event.get("trace") or {}).get("brief_id") or payload.get("brief_id")
        if not brief_id:
            logger.warning(
                "DesignBriefProjection: event %s (%s) has no brief_id — skipping",
                event_id,
                event_type,
            )
            return 0

        project_id = (event.get("trace") or {}).get("project_id") or payload.get("project_id")

        if event_type == "design_brief.created":
            return self._handle_created(conn, brief_id, project_id, payload, event_id, ts, now)
        self._ensure_skeleton(conn, brief_id, project_id, now)

        if event_type == "design_brief.updated":
            return self._handle_updated(conn, brief_id, payload, event_id, now)
        if event_type == "design_brief.locked":
            return self._handle_locked(conn, brief_id, event_id, now)
        if event_type == "design_brief.deleted":
            return self._handle_deleted(conn, brief_id, event_id, now)

        logger.warning(
            "DesignBriefProjection: unhandled event_type '%s' for %s", event_type, brief_id
        )
        return 0

    # ── Event handlers ────────────────────────────────────────────────────────

    def _handle_created(
        self,
        conn: sqlite3.Connection,
        brief_id: str,
        project_id: str | None,
        payload: dict,
        event_id: str,
        ts: str,
        now: str,
    ) -> int:
        """INSERT OR IGNORE so a duplicate created event is a no-op."""
        row = {
            "brief_id": brief_id,
            "project_id": project_id,
            "status": payload.get("status") or "draft",
            "created_at": ts,
            "updated_at": now,
            "source_event_id": event_id,
            "last_event_id": event_id,
        }
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_TABLE}
                (brief_id, project_id, status, created_at, updated_at,
                 source_event_id, last_event_id)
            VALUES
                (:brief_id, :project_id, :status, :created_at, :updated_at,
                 :source_event_id, :last_event_id)
            """,
            row,
        )
        # Backfill sparse fields written by an out-of-order skeleton.
        conn.execute(
            f"""
            UPDATE {_TABLE}
            SET project_id      = COALESCE(project_id, :project_id),
                created_at      = COALESCE(created_at, :created_at),
                source_event_id = COALESCE(source_event_id, :source_event_id),
                updated_at      = :updated_at
            WHERE brief_id = :brief_id
            """,
            row,
        )
        return 1

    def _handle_updated(
        self,
        conn: sqlite3.Connection,
        brief_id: str,
        payload: dict,
        event_id: str,
        now: str,
    ) -> int:
        field = payload.get("field")
        new_value = payload.get("new_value")
        if field not in _UPDATABLE_FIELDS:
            logger.warning(
                "DesignBriefProjection: design_brief.updated has invalid field '%s' for %s — skipping",
                field,
                brief_id,
            )
            return 0
        # field is validated against _UPDATABLE_FIELDS — safe to use in f-string.
        conn.execute(
            f"UPDATE {_TABLE}"
            f" SET {field} = ?, updated_at = ?, last_event_id = ?"
            f" WHERE brief_id = ?",
            (new_value, now, event_id, brief_id),
        )
        return 1

    def _handle_locked(
        self,
        conn: sqlite3.Connection,
        brief_id: str,
        event_id: str,
        now: str,
    ) -> int:
        # safe_upsert cannot be used: business_design_briefs.project_id is NOT NULL.
        # _ensure_skeleton guarantees the row exists before this runs.
        conn.execute(
            f"UPDATE {_TABLE}"
            " SET status = 'locked', updated_at = ?, last_event_id = ?"
            " WHERE brief_id = ?",
            (now, event_id, brief_id),
        )
        return 1

    def _handle_deleted(
        self,
        conn: sqlite3.Connection,
        brief_id: str,
        event_id: str,
        now: str,
    ) -> int:
        conn.execute(
            f"UPDATE {_TABLE}"
            " SET status = 'deleted', updated_at = ?, last_event_id = ?"
            " WHERE brief_id = ?",
            (now, event_id, brief_id),
        )
        return 1

    # ── Out-of-order helper ───────────────────────────────────────────────────

    def _ensure_skeleton(
        self,
        conn: sqlite3.Connection,
        brief_id: str,
        project_id: str | None,
        now: str,
    ) -> None:
        """INSERT OR IGNORE a minimal row so subsequent updates never fail.

        business_design_briefs.project_id is NOT NULL, so the skeleton requires
        a project_id. Writers populate it in the event trace for all event types.
        If project_id is None (unexpected), this is a no-op and the subsequent
        UPDATE will hit 0 rows — the event is silently skipped rather than
        corrupting with a NULL FK.
        """
        if project_id is None:
            logger.warning(
                "DesignBriefProjection: cannot create skeleton for %s — project_id missing",
                brief_id,
            )
            return
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_TABLE}
                (brief_id, project_id, status, created_at, updated_at)
            VALUES (?, ?, 'draft', ?, ?)
            """,
            (brief_id, project_id, now, now),
        )
