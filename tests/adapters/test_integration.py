"""
Integration tests for adapter layer.

Tests the full adapter stack:
- EventNormalizer registry
- ClaudeAdapter normalization
- CanonicalEvent validation
- SQLite serialization readiness
"""

from __future__ import annotations

import json

import pytest

from interfaces.adapters import ClaudeAdapter, EventNormalizer
from interfaces.adapters.models import CanonicalEvent, TraceContext


@pytest.fixture
def normalizer() -> EventNormalizer:
    """Create EventNormalizer with ClaudeAdapter registered."""
    normalizer = EventNormalizer()
    normalizer.register_adapter("claude", ClaudeAdapter())
    return normalizer


def test_end_to_end_normalization(normalizer: EventNormalizer):
    """Test full normalization pipeline from raw output to validated event."""
    raw_output = {
        "id": "msg_e2e",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "End-to-end test"}],
        "model": "claude-sonnet-4.5",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 5, "output_tokens": 3},
    }

    # Normalize via registry
    event = normalizer.normalize(raw_output, model_type="claude")

    # Verify event structure
    assert isinstance(event, CanonicalEvent)
    assert event.event_type == "claude.message.completed"
    assert event.entity_id == "msg_e2e"

    # Verify validation passes
    event.validate()  # Should not raise

    # Verify SQLite-ready serialization
    event_dict = event.to_dict()
    json_str = json.dumps(event_dict)  # Should not raise
    assert len(json_str) > 0


def test_normalizer_with_trace_context(normalizer: EventNormalizer):
    """Test that trace context can be added after normalization."""
    raw_output = {
        "id": "msg_trace",
        "type": "message",
        "content": [{"type": "text", "text": "With trace"}],
        "stop_reason": "end_turn",
    }

    event = normalizer.normalize(raw_output, model_type="claude")

    # Add trace context
    event.trace = TraceContext(
        project_id="dream-studio",
        task_id="TC-003",
        session_id="session_123",
    )

    # Verify trace is serialized
    event_dict = event.to_dict()
    assert event_dict["trace"]["project_id"] == "dream-studio"
    assert event_dict["trace"]["task_id"] == "TC-003"


def test_normalizer_fallback_to_default(normalizer: EventNormalizer):
    """Test that unknown model types fall back to DefaultAdapter."""
    raw_output = {"some": "data"}

    # Use unregistered model type
    event = normalizer.normalize(raw_output, model_type="unknown_model")

    # Should use DefaultAdapter (not raise)
    assert event.event_type == "model.output.unknown"
    assert event.metadata["adapter"] == "default"
    assert event.metadata["reason"] == "unknown_model_type"


def test_claude_adapter_is_registered(normalizer: EventNormalizer):
    """Test that ClaudeAdapter is properly registered."""
    assert normalizer.is_registered("claude")
    assert "claude" in normalizer.get_registered_models()


def test_multiple_normalizations_independent(normalizer: EventNormalizer):
    """Test that multiple normalizations don't interfere with each other."""
    output1 = {
        "id": "msg_1",
        "type": "message",
        "content": [{"type": "text", "text": "First"}],
        "stop_reason": "end_turn",
    }
    output2 = {
        "id": "msg_2",
        "type": "message",
        "content": [{"type": "text", "text": "Second"}],
        "stop_reason": "tool_use",
    }

    event1 = normalizer.normalize(output1, model_type="claude")
    event2 = normalizer.normalize(output2, model_type="claude")

    # Events should be independent
    assert event1.entity_id == "msg_1"
    assert event2.entity_id == "msg_2"
    assert event1.event_type == "claude.message.completed"
    assert event2.event_type == "claude.tool_use.invoked"
    assert event1.event_id != event2.event_id  # Different UUIDs
