"""Task projection — derives business_tasks from business_canonical_events.

Modeled on WorkOrderProjection (Phase 18.1.5). Implements the task state
machine: pending → complete, or → deleted.

Phase 18.2.3 — builds TaskProjection alongside MilestoneProjection to
complete the business-table event-sourcing layer for tasks.
"""

import logging
import sqlite3
from datetime import datetime, UTC
from typing import Any

from core.projections.framework import Projection, RetryPolicy
from core.work_orders.task_status import (
    TASK_ABANDONED_STATUSES,
    TASK_DONE_STATUSES,
    creation_status,
    status_for,
)

logger = logging.getLogger(__name__)

_TABLE = "business_tasks"
_SKELETON_TITLE = "(pending)"


class TaskProjection(Projection):
    """Materializes business_tasks from business_canonical_events.

    Handles the full task lifecycle:
      task.created   → INSERT row with status='pending'
      task.started   → status='in_progress', set updated_at
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
        "task.started",
        "task.completed",
        "task.cancelled",
        "task.deleted",
        "task.ac_repointed",
    ]
    source_canonical = "business"
    target_tables = [_TABLE]
    retry_policy = RetryPolicy(max_retries=3, base_delay_seconds=1.0)

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        # Migration 072 owns the business_tasks DDL additions.
        pass

    def handle(self, event: dict[str, Any], conn: sqlite3.Connection) -> int:
        """Apply one canonical event to business_tasks.

        Returns 1 for every successfully applied event, 0 if skipped.
        """
        if self.is_already_processed(event["event_id"], _TABLE, conn):
            return 0

        payload = event.get("payload") or {}
        event_type = event["event_type"]
        event_id = event["event_id"]
        ts = event["event_timestamp"]
        now = datetime.now(UTC).isoformat()

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
        project_id = self._resolve_project_id(conn, project_id, work_order_id)

        if event_type == "task.created":
            return self._handle_created(
                conn, task_id, work_order_id, project_id, payload, event_id, ts, now
            )
        self._ensure_skeleton(conn, task_id, work_order_id, project_id, now)

        if event_type == "task.started":
            return self._handle_started(conn, task_id, event_id, now)
        if event_type == "task.completed":
            return self._handle_completed(conn, task_id, event_id, now)
        if event_type == "task.cancelled":
            return self._handle_cancelled(conn, task_id, event_id, now)
        if event_type == "task.deleted":
            return self._handle_deleted(conn, task_id, event_id, now)
        if event_type == "task.ac_repointed":
            return self._handle_ac_repointed(conn, task_id, payload, event_id, now)

        logger.warning("TaskProjection: unhandled event_type '%s' for %s", event_type, task_id)
        return 0

    def _handle_ac_repointed(
        self, conn: Any, task_id: str, payload: dict, event_id: str, now: str
    ) -> int:
        """Correct a task's acceptance criterion.

        The ONLY writer that overwrites ``acceptance_criteria``. Everywhere else the
        column is COALESCEd, which made it write-once: a one-character typo in a
        TEST-CHECK node id could not be fixed, the close gate correctly reported
        MISADDRESSED rather than passing it, and the only remaining escape was --force --
        bypassing every other gate to correct one string.

        Replay-safe because the event carries the value rather than a delta, so replaying
        the stream in order lands on the same final criterion.
        """
        new_ac = payload.get("acceptance_criteria")
        if not new_ac:
            return 0
        conn.execute(
            f"UPDATE {_TABLE} SET acceptance_criteria = ?, source_event_id = ?, updated_at = ?"
            " WHERE task_id = ?",
            (new_ac, event_id, now, task_id),
        )
        return 1

    # ── Project-key resolution ────────────────────────────────────────────────

    def _resolve_project_id(
        self,
        conn: sqlite3.Connection,
        project_id: str | None,
        work_order_id: str | None,
    ) -> str | None:
        """Map an event's project key onto a registered project, or leave it alone.

        business_tasks declares a FOREIGN KEY to business_projects and
        business_work_orders declares none, so the SAME unvalidated key is accepted
        at one door and rejected at the other: measured on the live authority,
        business_work_orders referenced 30 distinct project_ids against 8 real
        project rows, and every one of the 36 events stuck in this projection's
        dead-letter table failed on that constraint (issue #719).

        Two thirds of them (24) carry the literal slug ``dream-studio`` rather than a
        UUID -- the WO-ATTRIBUTION-NORMALIZE class, fixed for execution_events and
        never applied here. The remaining keys are resolved from the event's OWN work
        order, which already holds the correct project_id; nothing is invented.

        Resolution never fabricates: a key that resolves to nothing is returned
        UNCHANGED so the insert still fails and still dead-letters. An event whose
        project genuinely was never registered is unattributable, and silently
        reassigning it to some plausible project would be worse than leaving it stuck.
        """
        if not project_id:
            return project_id
        try:
            if conn.execute(
                "SELECT 1 FROM business_projects WHERE project_id = ? LIMIT 1",
                (project_id,),
            ).fetchone():
                return project_id

            from core.projects.attribution import resolve_project_uuid

            resolved = resolve_project_uuid(project_id, conn)
            if resolved:
                logger.info("TaskProjection: resolved project key %r to %s", project_id, resolved)
                return resolved

            if work_order_id:
                row = conn.execute(
                    "SELECT w.project_id FROM business_work_orders w"
                    " JOIN business_projects p ON w.project_id = p.project_id"
                    " WHERE w.work_order_id = ? LIMIT 1",
                    (work_order_id,),
                ).fetchone()
                if row and row[0]:
                    logger.info(
                        "TaskProjection: took project %s from work order %s for key %r",
                        row[0],
                        work_order_id,
                        project_id,
                    )
                    return row[0]
        except sqlite3.Error as exc:
            # A failed lookup must not decide attribution. Fall through unchanged and
            # let the insert fail honestly rather than guess.
            logger.warning("TaskProjection: project-key resolution failed: %s", exc)
        return project_id

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
            "status": creation_status(),
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

    def _handle_started(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        event_id: str,
        now: str,
    ) -> int:
        """Claim the task, unless it has already finished.

        THE ONLY BACKWARD TRANSITION IN THIS PROJECTION, which is why it is the only
        handler that reads the current status first. Every other event here moves a task
        toward a terminal state, so applying one twice or late is harmless. A late
        `task.started` is not: replayed after the completion it preceded, it would return
        a finished task to `in_progress` and the rebuild would disagree with the history
        it was built from. The guard is on the DONE and ABANDONED sets rather than on
        `!= 'complete'`, because cancelled and deleted are equally finished -- the same
        distinction WO 654a54d7 found the hard way on work orders.
        """
        terminal = TASK_DONE_STATUSES + TASK_ABANDONED_STATUSES
        placeholders = ",".join("?" * len(terminal))
        conn.execute(
            f"UPDATE {_TABLE}"
            " SET status = ?, updated_at = ?, last_event_id = ?"
            f" WHERE task_id = ? AND status NOT IN ({placeholders})",
            (status_for("task.started"), now, event_id, task_id, *terminal),
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
            " SET status = ?, updated_at = ?, last_event_id = ?"
            " WHERE task_id = ?",
            (status_for("task.completed"), now, event_id, task_id),
        )
        return 1

    def _handle_cancelled(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        event_id: str,
        now: str,
    ) -> int:
        """Abandoned, and still countable as abandoned rather than as open work.

        WO 20796691. `cancelled` is already declared a real state in
        TASK_ABANDONED_STATUSES, and 369 tasks held it -- written by the gap drain as a
        bare UPDATE with no emission, so a replay reverted every one of them to whatever
        their last handled event said. The vocabulary knew about this state; the event
        substrate did not.

        Kept separate from `deleted` on purpose: `is_open()` treats both as not-open, but
        a reader deciding whether work was abandoned or the row should never have existed
        needs the two to stay distinguishable.
        """
        conn.execute(
            f"UPDATE {_TABLE}"
            " SET status = ?, updated_at = ?, last_event_id = ?"
            " WHERE task_id = ?",
            (status_for("task.cancelled"), now, event_id, task_id),
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
            " SET status = ?, updated_at = ?, last_event_id = ?"
            " WHERE task_id = ?",
            (status_for("task.deleted"), now, event_id, task_id),
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
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, work_order_id, project_id, _SKELETON_TITLE, creation_status(), now, now),
        )
