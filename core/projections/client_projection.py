"""Client projection — derives business_clients from business_canonical_events.

Client Layer (Attribution Coherence Phase 2). Mirrors ProjectProjection's state machine, but
business_clients (migration 155) carries no source_event_id/last_event_id columns, so idempotency
rests on INSERT OR IGNORE (client.created) + an idempotent status UPDATE (client.archived) plus the
projection cursor — is_already_processed degrades to False here (missing columns), which is safe.

Events handled:
  client.created  → INSERT OR IGNORE row (status='active')
  client.archived → UPDATE status='archived'

The three seed clients (SeayInsights/Fulcrum/Hypershift) are reference data inserted by migration
155 itself, not by events; a client.created for a seed id is a harmless INSERT OR IGNORE no-op.
"""

import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

from core.projections.framework import Projection, RetryPolicy

logger = logging.getLogger(__name__)

_TABLE = "business_clients"


class ClientProjection(Projection):
    """Materializes business_clients from business_canonical_events."""

    name = "client_projection"
    consumed_event_types = [
        "client.created",
        "client.archived",
    ]
    source_canonical = "business"
    target_tables = [_TABLE]
    retry_policy = RetryPolicy(max_retries=3, base_delay_seconds=1.0)

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        # Migration 155 owns the business_clients DDL.
        pass

    def handle(self, event: dict[str, Any], conn: sqlite3.Connection) -> int:
        payload = event.get("payload") or {}
        event_type = event["event_type"]
        now = datetime.now(UTC).isoformat()
        ts = event.get("event_timestamp") or now

        client_id = payload.get("client_id") or event.get("project_id")
        if not client_id:
            logger.warning(
                "ClientProjection: event %s (%s) has no client_id — skipping",
                event.get("event_id"),
                event_type,
            )
            return 0

        if event_type == "client.created":
            conn.execute(
                f"""
                INSERT OR IGNORE INTO {_TABLE}
                    (client_id, name, description, status, created_at, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?)
                """,
                (
                    client_id,
                    payload.get("name") or "",
                    payload.get("description") or "",
                    ts,
                    now,
                ),
            )
            return 1
        if event_type == "client.archived":
            conn.execute(
                f"UPDATE {_TABLE} SET status = 'archived', updated_at = ? WHERE client_id = ?",
                (now, client_id),
            )
            return 1

        logger.warning("ClientProjection: unhandled event_type '%s'", event_type)
        return 0
