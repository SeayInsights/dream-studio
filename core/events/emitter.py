"""Event emitter helpers for business logic.

Simplifies event emission by auto-generating required fields like event_id, timestamp, etc.
Business logic only needs to provide event_type and payload.

Created: 2026-05-07 (Phase 1 Wave 1 - EventStore Migration)
Updated: 2026-05-07 (Phase 1 - Added criticality system for safe event handling)
Updated: 2026-05-09 (Phase 4E - Advisory event type validation)
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4
import logging

# Import criticality system
from core.events.criticality import EventCriticality, get_criticality
from core.events.errors import EventEmissionError
from core.events.event_type_advisory import validate_event_type_advisory

logger = logging.getLogger(__name__)

# Conditional import - will create EventStore instance lazily to avoid circular imports
_event_store = None


def _get_event_store():
    """Lazy-load EventStore to avoid circular imports."""
    global _event_store

    if _event_store is None:
        from core.event_store.event_store import EventStore
        from core.validation.event_validator import EventValidator
        from core.config import paths

        # CRITICAL FIX: Use same database path as studio_db.py
        # Was: Path(".dream-studio/studio.db") → wrong path, separate DB
        # Now: paths.state_dir() / "studio.db" → correct absolute path
        db_path = paths.state_dir() / "studio.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Load validator with taxonomy and schema
        taxonomy_path = "docs/canonical/event_taxonomy_v1.json"
        schema_path = "docs/canonical/canonical_event_v1_schema.json"

        try:
            validator = EventValidator(taxonomy_path, schema_path)
        except FileNotFoundError as e:
            raise RuntimeError(
                f"EventStore unavailable: Missing validation files. "
                f"Expected files: {taxonomy_path}, {schema_path}. "
                f"Original error: {e}"
            ) from e

        _event_store = EventStore(str(db_path), validator)

    return _event_store


def emit_event(
    event_type: str,
    payload: Dict[str, Any],
    severity: str = "info",
    actor: Optional[Dict[str, Any]] = None,
    source_type: Optional[str] = None,
    confidence_score: Optional[float] = None,
    trace: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Emit a business event to EventStore.

    Automatically generates event_id, timestamp, and trace (if not provided).
    Validates and persists event via EventStore.

    Args:
        event_type: Event type (use constants from core.events.types.EventType)
        payload: Event payload (business data)
        severity: Event severity ('info', 'warning', 'high', 'critical')
        actor: Optional actor information (who/what triggered this)
        source_type: Optional source type identifier
        confidence_score: Optional confidence score (0.0-1.0)
        trace: Optional trace information (defaults to empty dict)

    Returns:
        event_id if event was written successfully, None if validation failed

    Example:
        from core.events.emitter import emit_event
        from core.events.types import EventType

        success = emit_event(
            event_type=EventType.REPO_ANALYZED,
            payload={
                "repo_url": "https://github.com/example/repo",
                "repo_id": 123,
                "patterns_count": 5,
                "building_blocks_count": 10,
                "stack": "nextjs"
            },
            severity="info"
        )
    """
    # Advisory: check event type against canonical taxonomy (warn-only)
    advisory = validate_event_type_advisory(event_type)
    if not advisory.is_registered:
        logger.warning("Advisory: %s", advisory.message)

    # Build canonical event
    event = {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace": trace or {},
        "severity": severity,
        "payload": payload,
    }

    # Add optional fields
    if actor is not None:
        event["actor"] = actor

    if source_type is not None:
        event["source_type"] = source_type

    if confidence_score is not None:
        event["confidence_score"] = confidence_score

    # Determine criticality (auto-detect from event type)
    criticality = get_criticality(event_type)

    # Get EventStore and write event
    store = _get_event_store()
    success = store.write_event(event)

    # Handle failure based on criticality
    if not success:
        if criticality == EventCriticality.CRITICAL:
            # CRITICAL events MUST succeed - get error details and raise exception
            error_detail = _get_last_validation_error()
            raise EventEmissionError(
                f"Critical event '{event_type}' failed to persist: {error_detail}"
            )
        elif criticality == EventCriticality.IMPORTANT:
            # IMPORTANT events log error but don't block
            logger.error(
                f"Important event '{event_type}' failed to persist. "
                f"Check validation_failures table for details."
            )
        else:
            # OPTIONAL events just log debug
            logger.debug(f"Optional event '{event_type}' failed to persist")
        return None

    return event["event_id"]


def _get_last_validation_error() -> str:
    """
    Get the most recent validation failure message from database.

    Returns:
        str: Error message from validation_failures table
    """
    try:
        from core.config.database import get_connection

        with get_connection(read_only=True) as conn:
            cursor = conn.execute(
                "SELECT errors FROM validation_failures " "ORDER BY attempted_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return row[0] if row else "Unknown validation error"
    except Exception as e:
        return f"Could not retrieve error details: {e}"
