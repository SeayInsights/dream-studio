"""
Unit tests for EventNormalizer.

Tests cover:
- Adapter registration (valid, invalid, duplicate)
- Normalization routing (registered, unregistered)
- DefaultAdapter fallback behavior
- Validation enforcement
- Registry query methods
"""

import pytest
from typing import Any

from interfaces.adapters.base import BaseAdapter
from interfaces.adapters.models import CanonicalEvent
from interfaces.adapters.normalizer import EventNormalizer, DefaultAdapter


class MockAdapter(BaseAdapter):
    """Mock adapter for testing."""

    def normalize(self, raw_output: Any) -> CanonicalEvent:
        """Return a canonical event with mock data."""
        return CanonicalEvent(
            event_type="mock.event",
            entity_type="mock_entity",
            entity_id="mock-123",
            severity="info",
            payload={"raw": raw_output},
            metadata={"source": "mock_adapter"},
        )


class InvalidAdapter:
    """Invalid adapter (does not inherit from BaseAdapter)."""

    def normalize(self, raw_output: Any) -> CanonicalEvent:
        return CanonicalEvent(event_type="invalid", entity_type="invalid", entity_id="invalid")


def test_normalizer_initialization():
    """EventNormalizer initializes with empty registry."""
    normalizer = EventNormalizer()
    assert normalizer.get_registered_models() == []
    assert isinstance(normalizer._default_adapter, DefaultAdapter)


def test_register_adapter_valid():
    """Can register valid adapter."""
    normalizer = EventNormalizer()
    adapter = MockAdapter()

    normalizer.register_adapter("mock", adapter)

    assert normalizer.is_registered("mock")
    assert normalizer.get_registered_models() == ["mock"]


def test_register_adapter_multiple():
    """Can register multiple adapters."""
    normalizer = EventNormalizer()
    adapter1 = MockAdapter()
    adapter2 = MockAdapter()

    normalizer.register_adapter("mock1", adapter1)
    normalizer.register_adapter("mock2", adapter2)

    assert normalizer.is_registered("mock1")
    assert normalizer.is_registered("mock2")
    assert set(normalizer.get_registered_models()) == {"mock1", "mock2"}


def test_register_adapter_empty_model_type():
    """Raises ValueError if model_type is empty."""
    normalizer = EventNormalizer()
    adapter = MockAdapter()

    with pytest.raises(ValueError, match="model_type cannot be empty"):
        normalizer.register_adapter("", adapter)


def test_register_adapter_invalid_type():
    """Raises ValueError if adapter is not BaseAdapter instance."""
    normalizer = EventNormalizer()
    invalid_adapter = InvalidAdapter()

    with pytest.raises(ValueError, match="adapter must be an instance of BaseAdapter"):
        normalizer.register_adapter("invalid", invalid_adapter)


def test_normalize_registered_adapter():
    """Normalize routes to registered adapter."""
    normalizer = EventNormalizer()
    adapter = MockAdapter()
    normalizer.register_adapter("mock", adapter)

    raw_output = {"test": "data"}
    event = normalizer.normalize(raw_output, model_type="mock")

    assert event.event_type == "mock.event"
    assert event.entity_type == "mock_entity"
    assert event.entity_id == "mock-123"
    assert event.payload["raw"] == raw_output
    assert event.metadata["source"] == "mock_adapter"
    assert event.metadata["adapter"] == "mock"
    assert "normalized_at" in event.metadata


def test_normalize_unregistered_adapter():
    """Normalize falls back to DefaultAdapter for unregistered model_type."""
    normalizer = EventNormalizer()

    raw_output = {"test": "data"}
    event = normalizer.normalize(raw_output, model_type="unknown")

    assert event.event_type == "model.output.unknown"
    assert event.entity_type == "model_output"
    assert event.entity_id == "unknown"
    assert event.payload["raw_output"] == raw_output
    assert event.metadata["adapter"] == "default"
    assert event.metadata["reason"] == "unknown_model_type"
    assert "normalized_at" in event.metadata


def test_normalize_validates_event():
    """Normalize calls validate() on canonical event."""

    class InvalidEventAdapter(BaseAdapter):
        """Adapter that produces invalid event (missing event_type)."""

        def normalize(self, raw_output: Any) -> CanonicalEvent:
            return CanonicalEvent(
                event_type="",  # Invalid: empty event_type
                entity_type="test",
                entity_id="test",
            )

    normalizer = EventNormalizer()
    normalizer.register_adapter("invalid", InvalidEventAdapter())

    with pytest.raises(ValueError, match="event_type is required"):
        normalizer.normalize({"test": "data"}, model_type="invalid")


def test_is_registered():
    """is_registered returns correct boolean."""
    normalizer = EventNormalizer()
    adapter = MockAdapter()

    assert not normalizer.is_registered("mock")

    normalizer.register_adapter("mock", adapter)

    assert normalizer.is_registered("mock")
    assert not normalizer.is_registered("other")


def test_get_registered_models_empty():
    """get_registered_models returns empty list when no adapters registered."""
    normalizer = EventNormalizer()
    assert normalizer.get_registered_models() == []


def test_default_adapter_normalize():
    """DefaultAdapter creates valid canonical event."""
    adapter = DefaultAdapter()
    raw_output = {"test": "data", "count": 42}

    event = adapter.normalize(raw_output)

    assert event.event_type == "model.output.unknown"
    assert event.entity_type == "model_output"
    assert event.entity_id == "unknown"
    assert event.severity == "info"
    assert event.payload["raw_output"] == raw_output
    assert event.metadata["adapter"] == "default"
    assert event.metadata["reason"] == "unknown_model_type"

    # Should not raise
    event.validate()


def test_normalize_adds_metadata_only_if_missing():
    """Normalize does not overwrite existing adapter/normalized_at metadata."""

    class PreMetadataAdapter(BaseAdapter):
        """Adapter that pre-populates metadata."""

        def normalize(self, raw_output: Any) -> CanonicalEvent:
            return CanonicalEvent(
                event_type="test.event",
                entity_type="test",
                entity_id="test-123",
                metadata={
                    "adapter": "custom_adapter_name",
                    "normalized_at": "2026-01-01T00:00:00Z",
                },
            )

    normalizer = EventNormalizer()
    normalizer.register_adapter("pre_metadata", PreMetadataAdapter())

    event = normalizer.normalize({"test": "data"}, model_type="pre_metadata")

    # Should preserve existing metadata
    assert event.metadata["adapter"] == "custom_adapter_name"
    assert event.metadata["normalized_at"] == "2026-01-01T00:00:00Z"


def test_normalize_thread_safety():
    """Normalize has no mutable shared state (basic smoke test)."""
    normalizer = EventNormalizer()
    adapter = MockAdapter()
    normalizer.register_adapter("mock", adapter)

    # Simulate concurrent normalization (sequential but different outputs)
    event1 = normalizer.normalize({"id": 1}, model_type="mock")
    event2 = normalizer.normalize({"id": 2}, model_type="mock")

    # Events should be independent
    assert event1.payload["raw"]["id"] == 1
    assert event2.payload["raw"]["id"] == 2
    assert event1.event_id != event2.event_id
