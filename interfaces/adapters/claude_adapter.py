"""
ClaudeAdapter: Normalizes Claude API responses to CanonicalEvent format.

This adapter handles Claude-specific output structures (messages, completions,
tool calls) and preserves all Claude-specific fields in the payload for
downstream analysis.

Architecture constraints (CONSTITUTION.md):
- Adapter overhead MUST be <10ms per event
- No external API calls (synchronous normalization only)
- Preserves all Claude fields (backward compatible)
"""

from typing import Any

from interfaces.adapters.base import BaseAdapter
from interfaces.adapters.models import CanonicalEvent, SeverityLevel


class ClaudeAdapter(BaseAdapter):
    """
    Adapter for Claude API responses.

    Normalizes Claude message/completion outputs to CanonicalEvent schema.
    Preserves all Claude-specific metadata for backward compatibility and
    downstream analytics.

    Supported Claude output types:
    - Message completions (chat/completion API)
    - Tool use events
    - Streaming chunks (aggregated)
    - Error responses

    Example input (Claude message):
        {
            "id": "msg_123",
            "type": "message",
            "role": "assistant",
            "content": [...],
            "model": "claude-sonnet-4.5",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 100, "output_tokens": 200}
        }

    Example output (CanonicalEvent):
        CanonicalEvent(
            event_type="claude.message.completed",
            entity_type="claude_message",
            entity_id="msg_123",
            severity="info",
            payload={...full Claude response...},
            metadata={"model": "claude-sonnet-4.5", "adapter_version": "1.0"}
        )
    """

    ADAPTER_VERSION = "1.0"

    # Severity mapping for Claude stop_reasons and error types
    SEVERITY_MAP = {
        # Normal completions
        "end_turn": "info",
        "max_tokens": "low",
        "stop_sequence": "info",
        # Tool use
        "tool_use": "info",
        # Errors (if present in error field)
        "error": "high",
        "rate_limit": "medium",
        "overloaded": "medium",
        "invalid_request": "high",
    }

    def normalize(self, raw_output: Any) -> CanonicalEvent:
        """
        Convert Claude API output to canonical event.

        Args:
            raw_output: Raw Claude API response (dict or compatible object)

        Returns:
            CanonicalEvent with normalized data.

        Raises:
            ValueError: If raw_output is None or missing required fields.
        """
        if raw_output is None:
            raise ValueError("raw_output cannot be None")

        # Convert to dict if needed (handles dataclass, pydantic models, etc.)
        if hasattr(raw_output, "model_dump"):  # Pydantic v2
            data = raw_output.model_dump()
        elif hasattr(raw_output, "dict"):  # Pydantic v1
            data = raw_output.dict()
        elif hasattr(raw_output, "__dict__"):  # Dataclass or plain object
            data = vars(raw_output)
        elif isinstance(raw_output, dict):
            data = raw_output
        else:
            raise ValueError(
                f"Cannot normalize raw_output of type {type(raw_output)}. "
                "Expected dict or object with dict() / model_dump() / __dict__."
            )

        # Extract core event fields
        event_type = self._extract_event_type(data)
        entity_type = self._extract_entity_type(data)
        entity_id = self._extract_entity_id(data)
        severity = self._extract_severity(data)

        # Preserve ALL Claude fields in payload
        payload = self._build_payload(data)

        # Build metadata with Claude version/model info
        metadata = self._build_metadata(data)

        return CanonicalEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            severity=severity,
            payload=payload,
            metadata=metadata,
        )

    def _extract_event_type(self, data: dict[str, Any]) -> str:
        """
        Derive event_type from Claude response structure.

        Event type format: "claude.{type}.{status}"
        Examples:
        - "claude.message.completed"
        - "claude.tool_use.invoked"
        - "claude.error.rate_limit"
        """
        # Handle error responses
        if "error" in data:
            error_type = data.get("error", {}).get("type", "unknown")
            return f"claude.error.{error_type}"

        # Handle message completions
        msg_type = data.get("type", "message")
        stop_reason = data.get("stop_reason", "unknown")

        if stop_reason == "tool_use":
            return "claude.tool_use.invoked"
        elif msg_type == "message":
            return "claude.message.completed"
        else:
            return f"claude.{msg_type}.completed"

    def _extract_entity_type(self, data: dict[str, Any]) -> str:
        """
        Extract entity type from Claude response.

        Maps to canonical entity types:
        - claude_message (standard completions)
        - claude_tool_call (tool use)
        - claude_error (error responses)
        """
        if "error" in data:
            return "claude_error"
        elif data.get("stop_reason") == "tool_use":
            return "claude_tool_call"
        else:
            return "claude_message"

    def _extract_entity_id(self, data: dict[str, Any]) -> str:
        """
        Extract unique identifier from Claude response.

        Tries (in order):
        1. id field (message ID)
        2. request_id (for errors)
        3. "unknown" fallback
        """
        return data.get("id") or data.get("request_id", "unknown")

    def _extract_severity(self, data: dict[str, Any]) -> SeverityLevel:
        """
        Map Claude stop_reason or error type to severity level.

        Severity levels:
        - info: Normal completions, tool use
        - low: Max tokens reached (potentially incomplete)
        - medium: Rate limits, service overload
        - high: Errors, invalid requests
        - critical: (reserved for security/compliance events)
        """
        # Error responses get higher severity
        if "error" in data:
            error_type = data.get("error", {}).get("type", "error")
            return self.SEVERITY_MAP.get(error_type, "high")

        # Map stop_reason to severity
        stop_reason = data.get("stop_reason", "end_turn")
        return self.SEVERITY_MAP.get(stop_reason, "info")

    def _build_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Preserve all Claude fields in payload.

        Stores the complete Claude response for:
        - Backward compatibility (existing analytics queries)
        - Debugging (full context available)
        - Future analytics (new fields automatically available)

        Warning: Does NOT filter sensitive data. Caller must ensure
                 no API keys, credentials, or PII in raw_output.
        """
        return {
            "claude_response": data,
            # Extract commonly-used fields to top level for convenience
            "content": data.get("content", []),
            "role": data.get("role"),
            "model": data.get("model"),
            "stop_reason": data.get("stop_reason"),
            "usage": data.get("usage", {}),
        }

    def _build_metadata(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Build adapter metadata with Claude version/model info.

        Metadata fields:
        - adapter: "claude"
        - adapter_version: "1.0"
        - model: Claude model ID (e.g., "claude-sonnet-4.5")
        - api_version: Claude API version (if present)
        """
        return {
            "adapter": "claude",
            "adapter_version": self.ADAPTER_VERSION,
            "model": data.get("model"),
            "api_version": data.get("api_version"),
        }
