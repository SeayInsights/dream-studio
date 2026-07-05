"""LegacyBridge — dual-write bridge for skill execution events.

This module is the active write path for skill execution events. It is imported by:
- control/skills/router.py (skill dispatch)
- control/skills/metrics.py (per-invocation metrics)
- control/skills/loader.py (skill loading)

Provides backward-compatible writes to legacy activity_log while emitting
canonical events to EventStore (strangler pattern).

Retirement of this bridge requires migrating skill execution event emission
directly to the spool pipeline; that migration is not yet scoped.
"""

from datetime import datetime, UTC
from uuid import uuid4

from core.event_store.event_store import EventStore


class LegacyBridge:
    """
    Bridge between legacy activity_log writes and canonical EventStore.

    All writes go through dual-write:
    1. Write to legacy schema (backward compatibility)
    2. Emit canonical event (future-proof)
    """

    def __init__(self, event_store: EventStore):
        """
        Initialize legacy bridge.

        Args:
            event_store: EventStore instance for canonical events
        """
        self.event_store = event_store

    def emit_from_legacy(
        self,
        activity_type: str,
        stream_id: str,
        stream_type: str,
        event_data: dict | None = None,
        prd_id: str | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
        workflow_run_key: str | None = None,
        skill_id: str | None = None,
        status: str = "completed",
        severity: str = "info",
    ) -> bool:
        """
        Emit canonical event from legacy write.

        Maps legacy activity_log write to canonical event format.

        Args:
            activity_type: Legacy activity type (e.g., 'workflow_node')
            stream_id: Legacy stream ID
            stream_type: Legacy stream type (e.g., 'workflow')
            event_data: Legacy event data dict
            prd_id: Optional PRD ID
            task_id: Optional task ID
            session_id: Optional session ID
            workflow_run_key: Optional workflow run key
            skill_id: Optional skill ID
            status: Event status
            severity: Event severity

        Returns:
            True if event emitted successfully
        """
        # Map legacy activity_type to canonical event_type
        event_type = self._map_activity_to_event_type(activity_type, status)

        # Build trace context from legacy IDs
        trace = {}
        if prd_id:
            trace["prd_id"] = prd_id
        if task_id:
            trace["task_id"] = task_id
        if session_id:
            trace["session_id"] = session_id
        if workflow_run_key:
            trace["workflow_id"] = workflow_run_key
        if skill_id:
            trace["skill_id"] = skill_id

        # Ensure trace has at least one ID (required by schema)
        if not trace:
            # Use stream_id as execution_id if no other IDs present
            trace["execution_id"] = stream_id

        # Map legacy severity to canonical severity
        severity_map = {
            "info": "low",
            "warning": "medium",
            "error": "high",
            "critical": "critical",
            # Also handle canonical values if passed directly
            "low": "low",
            "medium": "medium",
            "high": "high",
        }
        canonical_severity = severity_map.get(severity, "medium")  # Default to medium if unknown

        # Build canonical event
        canonical_event = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "trace": trace,
            "severity": canonical_severity,
            "payload": {
                "stream_id": stream_id,
                "stream_type": stream_type,
                "legacy_activity_type": activity_type,
                "legacy_severity": severity,  # Preserve original for debugging
                "status": status,
                **(event_data or {}),
            },
        }

        # Emit to canonical event store
        return self.event_store.write_event(canonical_event)

    def _map_activity_to_event_type(self, activity_type: str, status: str) -> str:
        """
        Map legacy activity_type to canonical domain.entity.action format.

        Maps to EXISTING taxonomy event types only.

        Args:
            activity_type: Legacy activity type
            status: Event status

        Returns:
            Canonical event_type (guaranteed to be in taxonomy)
        """
        # Map known legacy types to EXISTING taxonomy events
        type_map = {
            "workflow_node": "workflow.execution.completed",
            "workflow_run": "workflow.execution.completed",
            "research_completed": "research.source.fetched",  # Closest match
            "lesson_captured": "ingestion.event.normalized",  # Closest match
            "session_started": "execution.started",
            "session_ended": "execution.completed",
            "handoff_saved": "execution.completed",
            "prd_created": "prd.created",
            "prd_updated": "prd.updated",
            "task_created": "task.created",
            "task_updated": "task.updated",
            "hook_execution": "execution.completed",
            "skill_execution": "skill.execution.completed",
            "token_logged": "usage.tokens.input",  # Closest match
        }

        # Try exact match first
        if activity_type in type_map:
            return type_map[activity_type]

        # Fallback based on status
        if "workflow" in activity_type:
            if status == "failed":
                return "workflow.execution.failed"
            if status == "started" or status == "pending" or status == "in_progress":
                return "workflow.execution.started"
            return "workflow.execution.completed"

        if "skill" in activity_type:
            if status == "failed":
                return "skill.execution.failed"
            if status == "started" or status == "pending" or status == "in_progress":
                return "skill.execution.started"
            return "skill.execution.completed"

        if "task" in activity_type:
            if status == "completed" or status == "done":
                return "task.completed"
            return "task.updated"

        if "prd" in activity_type:
            return "prd.updated"

        # Ultimate fallback: generic execution event
        if status == "failed":
            return "execution.failed"
        if status == "started" or status == "pending" or status == "in_progress":
            return "execution.started"
        return "execution.completed"

    def _infer_domain(self, activity_type: str) -> str:
        """Infer domain from activity_type."""
        if "workflow" in activity_type or "session" in activity_type or "hook" in activity_type:
            return "execution"
        if "research" in activity_type:
            return "research"
        if "prd" in activity_type:
            return "prd"
        if "task" in activity_type:
            return "task"
        if "lesson" in activity_type:
            return "ingestion"
        if "token" in activity_type:
            return "telemetry"
        if "security" in activity_type:
            return "security"
        return "unknown"

    def _extract_entity(self, activity_type: str) -> str:
        """Extract entity from activity_type."""
        # Split on underscore and take first non-status word
        parts = activity_type.split("_")
        for part in parts:
            if part not in ["started", "completed", "failed", "updated"]:
                return part
        return "unknown"
