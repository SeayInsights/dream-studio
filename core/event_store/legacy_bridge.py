# DEPRECATED: Superseded by the spool pipeline (spool/ + emitters/).
# Retained for backward compatibility during Slice 1-2 transition.
# Scheduled for deletion in Slice 2 after test suite green.
"""
Legacy bridge for dual-write migration.

Provides backward-compatible writes to legacy activity_log
while emitting canonical events to EventStore.

This is a strangler pattern migration - old code continues to work
while new canonical event stream is built in parallel.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Optional
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
        event_data: Optional[Dict] = None,
        prd_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        workflow_run_key: Optional[str] = None,
        skill_id: Optional[str] = None,
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
            elif status == "started" or status == "pending" or status == "in_progress":
                return "workflow.execution.started"
            else:
                return "workflow.execution.completed"

        if "skill" in activity_type:
            if status == "failed":
                return "skill.execution.failed"
            elif status == "started" or status == "pending" or status == "in_progress":
                return "skill.execution.started"
            else:
                return "skill.execution.completed"

        if "task" in activity_type:
            if status == "completed" or status == "done":
                return "task.completed"
            else:
                return "task.updated"

        if "prd" in activity_type:
            return "prd.updated"

        # Ultimate fallback: generic execution event
        if status == "failed":
            return "execution.failed"
        elif status == "started" or status == "pending" or status == "in_progress":
            return "execution.started"
        else:
            return "execution.completed"

    def _infer_domain(self, activity_type: str) -> str:
        """Infer domain from activity_type."""
        if "workflow" in activity_type or "session" in activity_type or "hook" in activity_type:
            return "execution"
        elif "research" in activity_type:
            return "research"
        elif "prd" in activity_type:
            return "prd"
        elif "task" in activity_type:
            return "task"
        elif "lesson" in activity_type:
            return "ingestion"
        elif "token" in activity_type:
            return "telemetry"
        elif "security" in activity_type:
            return "security"
        else:
            return "unknown"

    def _extract_entity(self, activity_type: str) -> str:
        """Extract entity from activity_type."""
        # Split on underscore and take first non-status word
        parts = activity_type.split("_")
        for part in parts:
            if part not in ["started", "completed", "failed", "updated"]:
                return part
        return "unknown"
