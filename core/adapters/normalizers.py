"""Adapter classes for the legacy normalization layer.

Moved from interfaces/adapters/ (Slice 4 retirement).
All imports updated to core.adapters.models.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from core.adapters.models import CanonicalEvent, SeverityLevel, TraceContext

logger = logging.getLogger(__name__)


# ── BaseAdapter ──────────────────────────────────────────────────────────────


class BaseAdapter(ABC):
    """Abstract base class for model-specific event adapters.

    Architecture constraint (CONSTITUTION.md):
    - Adapter overhead MUST be <10ms per event
    - No external API calls (synchronous normalization only)
    - No database writes (only in-memory transformation)
    """

    @abstractmethod
    def normalize(self, raw_output: Any) -> CanonicalEvent:
        """Convert model-specific output to canonical event."""
        pass

    def validate(self, event: CanonicalEvent) -> None:
        """Validate canonical event structure."""
        event.validate()


# ── ClaudeAdapter ─────────────────────────────────────────────────────────────


class ClaudeAdapter(BaseAdapter):
    """Adapter for Claude API responses.

    Normalizes Claude message/completion outputs to CanonicalEvent schema.
    """

    ADAPTER_VERSION = "1.0"

    SEVERITY_MAP: dict[str, SeverityLevel] = {
        "end_turn": "info",
        "max_tokens": "low",
        "stop_sequence": "info",
        "tool_use": "info",
        "error": "high",
        "rate_limit": "medium",
        "overloaded": "medium",
        "invalid_request": "high",
    }

    def normalize(self, raw_output: Any) -> CanonicalEvent:
        if raw_output is None:
            raise ValueError("raw_output cannot be None")

        if hasattr(raw_output, "model_dump"):
            data = raw_output.model_dump()
        elif hasattr(raw_output, "dict"):
            data = raw_output.dict()
        elif hasattr(raw_output, "__dict__"):
            data = vars(raw_output)
        elif isinstance(raw_output, dict):
            data = raw_output
        else:
            raise ValueError(
                f"Cannot normalize raw_output of type {type(raw_output)}. "
                "Expected dict or object with dict() / model_dump() / __dict__."
            )

        return CanonicalEvent(
            event_type=self._extract_event_type(data),
            entity_type=self._extract_entity_type(data),
            entity_id=self._extract_entity_id(data),
            severity=self._extract_severity(data),
            payload=self._build_payload(data),
            metadata=self._build_metadata(data),
        )

    def _extract_event_type(self, data: dict[str, Any]) -> str:
        if "error" in data:
            error_type = data.get("error", {}).get("type", "unknown")
            return f"claude.error.{error_type}"
        msg_type = data.get("type", "message")
        stop_reason = data.get("stop_reason", "unknown")
        if stop_reason == "tool_use":
            return "claude.tool_use.invoked"
        elif msg_type == "message":
            return "claude.message.completed"
        else:
            return f"claude.{msg_type}.completed"

    def _extract_entity_type(self, data: dict[str, Any]) -> str:
        if "error" in data:
            return "claude_error"
        elif data.get("stop_reason") == "tool_use":
            return "claude_tool_call"
        else:
            return "claude_message"

    def _extract_entity_id(self, data: dict[str, Any]) -> str:
        return data.get("id") or data.get("request_id", "unknown")

    def _extract_severity(self, data: dict[str, Any]) -> SeverityLevel:
        if "error" in data:
            error_type = data.get("error", {}).get("type", "error")
            return self.SEVERITY_MAP.get(error_type, "high")
        stop_reason = data.get("stop_reason", "end_turn")
        return self.SEVERITY_MAP.get(stop_reason, "info")

    def _build_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "claude_response": data,
            "content": data.get("content", []),
            "role": data.get("role"),
            "model": data.get("model"),
            "stop_reason": data.get("stop_reason"),
            "usage": data.get("usage", {}),
        }

    def _build_metadata(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "adapter": "claude",
            "adapter_version": self.ADAPTER_VERSION,
            "model": data.get("model"),
            "api_version": data.get("api_version"),
        }


# ── DefaultAdapter ────────────────────────────────────────────────────────────


class DefaultAdapter(BaseAdapter):
    """Fallback adapter for unknown model types.

    Accepts any input, logs a warning, and wraps the raw input in a generic
    CanonicalEvent. Ensures graceful degradation for unknown model types.
    """

    def normalize(self, raw_output: Any) -> CanonicalEvent:
        model_type = type(raw_output).__name__
        logger.warning(
            f"DefaultAdapter invoked for unknown model type: {model_type}. "
            "Consider implementing a model-specific adapter for better normalization."
        )

        if isinstance(raw_output, dict):
            payload_data = raw_output.copy()
        else:
            payload_data = {
                "raw_output": str(raw_output),
                "raw_type": model_type,
            }

        event = CanonicalEvent(
            event_type="ai.completion.unknown",
            entity_type="unknown_model",
            entity_id=f"default-{hash(str(raw_output)) % 10**8}",
            severity="info",
            payload=payload_data,
            trace=TraceContext(),
            metadata={
                "adapter": "default",
                "adapter_version": "0.1.0",
                "original_type": model_type,
                "warning": "Unrecognized model type — using fallback adapter",
            },
        )

        self.validate(event)
        logger.debug(f"DefaultAdapter normalized event {event.event_id} for type {model_type}")
        return event


# ── GPTAdapter ────────────────────────────────────────────────────────────────


class GPTAdapter(BaseAdapter):
    """Adapter for OpenAI GPT API responses (proof-of-concept)."""

    def normalize(self, raw_output: Any) -> CanonicalEvent:
        if not isinstance(raw_output, dict):
            raise ValueError(f"GPTAdapter expects dict input, got {type(raw_output).__name__}")

        completion_id = raw_output.get("id", "")
        model = raw_output.get("model", "unknown-gpt-model")
        created_timestamp = raw_output.get("created")

        choices = raw_output.get("choices", [])
        first_choice = choices[0] if choices else {}
        message_content = first_choice.get("message", {}).get("content", "")

        event = CanonicalEvent(
            event_type="ai.completion.created",
            entity_type="gpt_completion",
            entity_id=completion_id,
            severity="info",
            payload={
                "model": model,
                "content": message_content,
                "raw_response": raw_output,
            },
            trace=TraceContext(),
            metadata={
                "adapter": "gpt",
                "adapter_version": "0.1.0-poc",
                "openai_created": created_timestamp,
            },
        )

        self.validate(event)
        logger.debug(f"GPTAdapter normalized event {event.event_id} for model {model}")
        return event


# ── EventNormalizer ───────────────────────────────────────────────────────────


class EventNormalizer:
    """Central registry and dispatcher for model-specific adapters.

    Routes raw model outputs to the appropriate adapter based on model_type.
    Falls back to DefaultAdapter for unregistered model types.

    Architecture guarantee:
    - If model_type is not registered, uses DefaultAdapter (no exceptions)
    - Adapter overhead <10ms (measured via timing metadata)
    - Thread-safe (no mutable shared state during normalization)
    """

    def __init__(self) -> None:
        self._adapters: dict[str, BaseAdapter] = {}
        self._default_adapter = DefaultAdapter()

    def register_adapter(self, model_type: str, adapter: BaseAdapter) -> None:
        if not model_type:
            raise ValueError("model_type cannot be empty")
        if not isinstance(adapter, BaseAdapter):
            raise ValueError(f"adapter must be an instance of BaseAdapter, got {type(adapter)}")
        self._adapters[model_type] = adapter

    def normalize(self, raw_output: Any, model_type: str) -> CanonicalEvent:
        adapter = self._adapters.get(model_type, self._default_adapter)
        event = adapter.normalize(raw_output)
        event.validate()

        if "adapter" not in event.metadata:
            event.metadata["adapter"] = (
                model_type if adapter != self._default_adapter else "default"
            )
        if "normalized_at" not in event.metadata:
            event.metadata["normalized_at"] = event.timestamp.isoformat()

        return event

    def get_registered_models(self) -> list[str]:
        return list(self._adapters.keys())

    def is_registered(self, model_type: str) -> bool:
        return model_type in self._adapters
