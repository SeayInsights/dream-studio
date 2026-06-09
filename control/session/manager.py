"""Session management utilities for session-end hook."""

import sys
from pathlib import Path

from canonical.events.envelope import CanonicalEventEnvelope
from canonical.events.types import EventType as CanonicalEventType
from emitters.shared.spool_writer import write_envelopes

# Ensure project root is in path for event store imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from core.event_store.legacy_bridge import LegacyBridge
    from core.event_store.event_store import EventStore
    from core.validation.event_validator import EventValidator

    _BRIDGE_AVAILABLE = True
except ImportError:
    _BRIDGE_AVAILABLE = False

from core.event_store.studio_db import _db_path
from core.config.database import transaction


def _get_bridge():
    """Lazy init bridge for event emission."""
    if not _BRIDGE_AVAILABLE:
        return None

    try:
        repo_root = Path(__file__).resolve().parents[2]
        docs_dir = repo_root / "docs" / "canonical"

        if not docs_dir.exists():
            return None

        taxonomy_path = str(docs_dir / "event_taxonomy_v1.json")
        schema_path = str(docs_dir / "canonical_event_v1_schema.json")

        if not Path(taxonomy_path).exists() or not Path(schema_path).exists():
            return None

        validator = EventValidator(taxonomy_path, schema_path)
        event_store = EventStore(
            db_path=str(_db_path()), validator=validator, emit_validation_failures=True
        )
        return LegacyBridge(event_store)
    except Exception:
        return None


def validate_session_research(session_id: str) -> None:
    """Validate all research from session based on outcome.

    Session success heuristic:
        1. Check raw_sessions.outcome if available ('success' = successful)
        2. Fallback: check task completion ratio (completed >= 0)
        3. Default: assume successful (optimistic MVP approach)

    Trust score adjustments (via trigger):
        - Validated: trust_score += 0.1
        - Rejected: trust_score -= 0.2
    """
    try:
        with transaction() as conn:
            cursor = conn.cursor()
            is_successful = True  # Default optimistic

            # Check if raw_sessions has an outcome
            outcome_row = cursor.execute(
                "SELECT outcome FROM raw_sessions WHERE session_id = ? LIMIT 1", (session_id,)
            ).fetchone()
            if outcome_row and outcome_row[0]:
                is_successful = outcome_row[0].lower() == "success"
            else:
                # Fallback: check task completion
                task_stats = cursor.execute(
                    "SELECT tasks_completed FROM raw_sessions WHERE session_id = ? LIMIT 1",
                    (session_id,),
                ).fetchone()
                if task_stats and task_stats[0] is not None:
                    is_successful = task_stats[0] > 0

            # Get pending research
            pending_research = cursor.execute(
                "SELECT research_id, source_url, trust_score FROM raw_research WHERE session_id = ? AND validation_status = 'pending'",
                (session_id,),
            ).fetchall()

            if not pending_research:
                return

            new_status = "validated" if is_successful else "rejected"
            validated_count = len(pending_research)
            for row in pending_research:
                research_id, current_trust = row[0], row[2] or 0.5
                new_trust = (
                    min(current_trust + 0.1, 1.0)
                    if is_successful
                    else max(current_trust - 0.2, 0.0)
                )

                # Phase 1 Wave 1.5 → Slice 3: Emit event via spool pipeline
                _env = CanonicalEventEnvelope(
                    event_type=CanonicalEventType.RESEARCH_VALIDATED.value,
                    session_id=session_id,
                    payload={
                        "research_id": research_id,
                        "validation_status": new_status,
                        "trust_score": new_trust,
                        "validated_by": session_id,
                        "session_id": session_id,
                    },
                    severity="info",
                    confidence="exact",
                    project_id=None,
                )
                write_envelopes([_env])

                cursor.execute(
                    "UPDATE raw_research SET validation_status = ?, trust_score = ?, validated_by = ?, validated_at = datetime('now') WHERE research_id = ?",
                    (new_status, new_trust, session_id, research_id),
                )

            # DUAL-WRITE: Emit canonical event after validation
            try:
                bridge = _get_bridge()
                if bridge:
                    bridge.emit_from_legacy(
                        activity_type="execution.completed",
                        stream_id=f"session-{session_id}",
                        stream_type="session",
                        event_data={
                            "session_id": session_id,
                            "validated_count": validated_count,
                            "outcome": outcome_row[0] if outcome_row else "inferred_success",
                            "operation": "validate_session_research",
                        },
                        session_id=session_id,
                        status="completed",
                    )
            except Exception:
                pass  # Never fail on event emission

    except Exception:
        pass  # Don't break session cleanup on validation errors
