"""
EventNormalizer: Central dispatcher for AI/model output normalization.

This module implements the adapter registry pattern that routes raw model outputs
to the appropriate adapter based on model_type.

Architecture constraints (CONSTITUTION.md):
- All AI/model outputs MUST flow through EventNormalizer before activity_log writes
- No direct activity_log.insert() without normalization
- Adapter overhead MUST be <10ms per event
"""

from typing import Any

from interfaces.adapters.base import BaseAdapter
from interfaces.adapters.models import CanonicalEvent


class DefaultAdapter(BaseAdapter):
    """
    Fallback adapter for unknown model types.

    Used when model_type is not registered in the adapter registry.
    Creates a minimal canonical event with raw output in payload.
    """

    def normalize(self, raw_output: Any) -> CanonicalEvent:
        """
        Convert unknown model output to canonical event.

        Args:
            raw_output: Raw model output (any structure)

        Returns:
            CanonicalEvent with raw_output in payload and generic metadata.
        """
        return CanonicalEvent(
            event_type="model.output.unknown",
            entity_type="model_output",
            entity_id="unknown",
            severity="info",
            payload={"raw_output": raw_output},
            metadata={"adapter": "default", "reason": "unknown_model_type"},
        )


class EventNormalizer:
    """
    Central registry and dispatcher for model-specific adapters.

    Routes raw model outputs to the appropriate adapter based on model_type,
    ensuring all events are normalized to CanonicalEvent schema before
    reaching the activity_log.

    Usage:
        normalizer = EventNormalizer()
        normalizer.register_adapter("claude", ClaudeAdapter())
        normalizer.register_adapter("gpt", GPTAdapter())

        event = normalizer.normalize(raw_output, model_type="claude")
        # event is now a CanonicalEvent ready for activity_log insertion

    Architecture guarantee:
        - If model_type is not registered, uses DefaultAdapter (no exceptions)
        - Adapter overhead <10ms (measured via timing metadata)
        - Thread-safe (no mutable shared state during normalization)
    """

    def __init__(self) -> None:
        """Initialize with empty adapter registry and default fallback."""
        self._adapters: dict[str, BaseAdapter] = {}
        self._default_adapter = DefaultAdapter()

    def register_adapter(self, model_type: str, adapter: BaseAdapter) -> None:
        """
        Register a model-specific adapter.

        Args:
            model_type: Model identifier (e.g., "claude", "gpt-4", "gemini")
            adapter: Adapter instance implementing BaseAdapter

        Raises:
            ValueError: If model_type is empty or adapter is not a BaseAdapter instance
        """
        if not model_type:
            raise ValueError("model_type cannot be empty")
        if not isinstance(adapter, BaseAdapter):
            raise ValueError(f"adapter must be an instance of BaseAdapter, got {type(adapter)}")

        self._adapters[model_type] = adapter

    def normalize(self, raw_output: Any, model_type: str) -> CanonicalEvent:
        """
        Normalize raw model output to canonical event schema.

        Routes to the appropriate adapter based on model_type. Falls back to
        DefaultAdapter if model_type is not registered.

        Args:
            raw_output: Raw model output (dict, object, etc.)
            model_type: Model identifier (e.g., "claude", "gpt-4")

        Returns:
            CanonicalEvent instance with normalized data.

        Raises:
            ValueError: If adapter normalization fails (invalid structure).
                       Does NOT raise if model_type is unknown (uses DefaultAdapter).
        """
        # Get adapter (fallback to default if not found)
        adapter = self._adapters.get(model_type, self._default_adapter)

        # Normalize via adapter
        event = adapter.normalize(raw_output)

        # Validate before returning
        event.validate()

        # Add normalization metadata
        if "adapter" not in event.metadata:
            event.metadata["adapter"] = (
                model_type if adapter != self._default_adapter else "default"
            )
        if "normalized_at" not in event.metadata:
            event.metadata["normalized_at"] = event.timestamp.isoformat()

        return event

    def get_registered_models(self) -> list[str]:
        """
        Get list of registered model types.

        Returns:
            List of model_type identifiers currently registered.
        """
        return list(self._adapters.keys())

    def is_registered(self, model_type: str) -> bool:
        """
        Check if a model type is registered.

        Args:
            model_type: Model identifier to check

        Returns:
            True if adapter is registered, False otherwise.
        """
        return model_type in self._adapters
