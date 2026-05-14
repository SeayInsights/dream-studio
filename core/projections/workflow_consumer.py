"""Event consumer for workflow metrics projection.

Listens to workflow events from EventStore and updates workflow_metrics projection.
Run as background process or on-demand via CLI.

Created: 2026-05-08
"""

import logging
from typing import Optional

from core.config.database import get_connection
from core.event_store.event_store import EventStore
from core.projections.workflow_metrics import WorkflowMetricsProjection
from core.validation.event_validator import EventValidator
from core.config import paths

logger = logging.getLogger(__name__)


class WorkflowEventConsumer:
    """Event consumer for workflow metrics projection."""

    def __init__(self):
        """Initialize consumer with EventStore and projection."""
        # Initialize EventStore
        db_path = paths.state_dir() / "studio.db"
        taxonomy_path = "docs/canonical/event_taxonomy_v1.json"
        schema_path = "docs/canonical/canonical_event_v1_schema.json"

        validator = EventValidator(taxonomy_path, schema_path)
        self.event_store = EventStore(str(db_path), validator)

        # Initialize projection
        self.projection = WorkflowMetricsProjection()

        # Track last consumed event ID
        self.last_event_id: Optional[str] = None

    def consume_all_events(self):
        """Consume all workflow events from EventStore and update projection.

        This is a full rebuild of the projection from event history.
        """
        logger.info("Starting full workflow metrics projection rebuild")

        # Query all workflow events
        workflow_event_types = [
            "workflow.execution.started",
            "workflow.execution.completed",
            "workflow.execution.failed",
            "workflow.phase.completed",
        ]

        for event_type in workflow_event_types:
            events = self._query_events(event_type)
            logger.info(f"Processing {len(events)} events of type {event_type}")

            for event in events:
                self._process_event(event)

        logger.info("Workflow metrics projection rebuild complete")

    def consume_new_events(self):
        """Consume only new events since last consumption.

        Used for incremental updates in background process.
        """
        # Load last consumed event ID from state
        self._load_last_event_id()

        workflow_event_types = [
            "workflow.execution.started",
            "workflow.execution.completed",
            "workflow.execution.failed",
            "workflow.phase.completed",
        ]

        new_events_count = 0
        for event_type in workflow_event_types:
            events = self._query_events(event_type, after_event_id=self.last_event_id)

            for event in events:
                self._process_event(event)
                new_events_count += 1
                self.last_event_id = event["event_id"]

        if new_events_count > 0:
            logger.info(f"Processed {new_events_count} new workflow events")
            self._save_last_event_id()

    def _query_events(self, event_type: str, after_event_id: Optional[str] = None):
        """Query events from EventStore.

        Args:
            event_type: Event type to query
            after_event_id: Optional cursor for incremental consumption

        Returns:
            List of event dicts
        """
        with get_connection(read_only=True) as conn:
            if after_event_id:
                # Incremental: get events after last consumed
                cursor = conn.execute(
                    """SELECT * FROM canonical_events
                       WHERE event_type = ? AND event_id > ?
                       ORDER BY timestamp ASC""",
                    (event_type, after_event_id),
                )
            else:
                # Full rebuild: get all events
                cursor = conn.execute(
                    """SELECT * FROM canonical_events
                       WHERE event_type = ?
                       ORDER BY timestamp ASC""",
                    (event_type,),
                )

            rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def _process_event(self, event: dict):
        """Route event to appropriate projection handler.

        Args:
            event: Canonical event dict
        """
        event_type = event["event_type"]

        # Parse payload JSON string back to dict
        import json

        if isinstance(event["payload"], str):
            event["payload"] = json.loads(event["payload"])

        # Route to handler
        handlers = {
            "workflow.execution.started": self.projection.consume_workflow_started,
            "workflow.execution.completed": self.projection.consume_workflow_completed,
            "workflow.execution.failed": self.projection.consume_workflow_failed,
            "workflow.phase.completed": self.projection.consume_workflow_phase_completed,
        }

        handler = handlers.get(event_type)
        if handler:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error processing event {event['event_id']}: {e}")

    def _load_last_event_id(self):
        """Load last consumed event ID from consumer state table."""
        with get_connection() as conn:
            # Create consumer state table if not exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS consumer_state (
                    consumer_name TEXT PRIMARY KEY,
                    last_event_id TEXT,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            row = conn.execute(
                "SELECT last_event_id FROM consumer_state WHERE consumer_name = 'workflow_metrics'",
            ).fetchone()

            if row:
                self.last_event_id = row[0]

    def _save_last_event_id(self):
        """Save last consumed event ID to consumer state table."""
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO consumer_state (consumer_name, last_event_id, last_updated)
                   VALUES ('workflow_metrics', ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(consumer_name) DO UPDATE SET
                       last_event_id = excluded.last_event_id,
                       last_updated = CURRENT_TIMESTAMP""",
                (self.last_event_id,),
            )


def main():
    """CLI entry point for workflow event consumer."""
    import sys

    logging.basicConfig(level=logging.INFO)

    consumer = WorkflowEventConsumer()

    if len(sys.argv) > 1 and sys.argv[1] == "rebuild":
        # Full rebuild
        consumer.consume_all_events()
    else:
        # Incremental consumption
        consumer.consume_new_events()


if __name__ == "__main__":
    main()
