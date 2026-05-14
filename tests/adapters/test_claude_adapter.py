"""
Unit tests for ClaudeAdapter.

Tests cover:
- Normal message completions
- Tool use events
- Error responses
- Edge cases (missing fields, malformed input)
- Backward compatibility (preserves all Claude fields)
- Performance (<10ms normalization)
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pytest

from interfaces.adapters.claude_adapter import ClaudeAdapter
from interfaces.adapters.models import CanonicalEvent

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def adapter() -> ClaudeAdapter:
    """Create ClaudeAdapter instance for testing."""
    return ClaudeAdapter()


@pytest.fixture
def sample_message() -> dict:
    """Sample Claude message completion response."""
    return {
        "id": "msg_abc123",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello, I'm Claude!"}],
        "model": "claude-sonnet-4.5",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


@pytest.fixture
def sample_tool_use() -> dict:
    """Sample Claude tool use response."""
    return {
        "id": "msg_tool456",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "tool_123",
                "name": "get_weather",
                "input": {"city": "San Francisco"},
            }
        ],
        "model": "claude-opus-4.5",
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 50, "output_tokens": 20},
    }


@pytest.fixture
def sample_error() -> dict:
    """Sample Claude error response."""
    return {
        "error": {
            "type": "rate_limit",
            "message": "Rate limit exceeded",
        },
        "request_id": "req_error789",
    }


# ============================================================================
# TESTS: Normal Message Completion
# ============================================================================


def test_normalize_basic_message(adapter: ClaudeAdapter, sample_message: dict):
    """Test normalization of standard message completion."""
    event = adapter.normalize(sample_message)

    # Verify event structure
    assert isinstance(event, CanonicalEvent)
    assert event.event_type == "claude.message.completed"
    assert event.entity_type == "claude_message"
    assert event.entity_id == "msg_abc123"
    assert event.severity == "info"

    # Verify payload preservation
    assert "claude_response" in event.payload
    assert event.payload["claude_response"] == sample_message
    assert event.payload["model"] == "claude-sonnet-4.5"
    assert event.payload["content"][0]["text"] == "Hello, I'm Claude!"

    # Verify metadata
    assert event.metadata["adapter"] == "claude"
    assert event.metadata["model"] == "claude-sonnet-4.5"
    assert event.metadata["adapter_version"] == "1.0"


def test_normalize_max_tokens(adapter: ClaudeAdapter):
    """Test severity mapping for max_tokens stop_reason."""
    data = {
        "id": "msg_max",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Incomplete..."}],
        "model": "claude-sonnet-4.5",
        "stop_reason": "max_tokens",
        "usage": {"input_tokens": 10, "output_tokens": 1000},
    }

    event = adapter.normalize(data)
    assert event.severity == "low"  # Potentially incomplete response
    assert event.event_type == "claude.message.completed"


# ============================================================================
# TESTS: Tool Use
# ============================================================================


def test_normalize_tool_use(adapter: ClaudeAdapter, sample_tool_use: dict):
    """Test normalization of tool use event."""
    event = adapter.normalize(sample_tool_use)

    assert event.event_type == "claude.tool_use.invoked"
    assert event.entity_type == "claude_tool_call"
    assert event.entity_id == "msg_tool456"
    assert event.severity == "info"

    # Verify tool details preserved
    assert event.payload["content"][0]["type"] == "tool_use"
    assert event.payload["content"][0]["name"] == "get_weather"


# ============================================================================
# TESTS: Error Responses
# ============================================================================


def test_normalize_rate_limit_error(adapter: ClaudeAdapter, sample_error: dict):
    """Test normalization of rate limit error."""
    event = adapter.normalize(sample_error)

    assert event.event_type == "claude.error.rate_limit"
    assert event.entity_type == "claude_error"
    assert event.entity_id == "req_error789"
    assert event.severity == "medium"

    # Verify error details preserved
    assert "error" in event.payload["claude_response"]
    assert event.payload["claude_response"]["error"]["type"] == "rate_limit"


def test_normalize_invalid_request_error(adapter: ClaudeAdapter):
    """Test severity mapping for invalid_request errors."""
    data = {
        "error": {
            "type": "invalid_request",
            "message": "Invalid parameter",
        },
        "request_id": "req_invalid",
    }

    event = adapter.normalize(data)
    assert event.severity == "high"  # Invalid requests are more severe
    assert event.event_type == "claude.error.invalid_request"


def test_normalize_generic_error(adapter: ClaudeAdapter):
    """Test handling of unknown error types."""
    data = {
        "error": {
            "type": "unknown_error_type",
            "message": "Something went wrong",
        },
        "request_id": "req_unknown",
    }

    event = adapter.normalize(data)
    assert event.event_type == "claude.error.unknown_error_type"
    assert event.severity == "high"  # Default to high for unknown errors


# ============================================================================
# TESTS: Edge Cases
# ============================================================================


def test_normalize_none_raises_error(adapter: ClaudeAdapter):
    """Test that None input raises ValueError."""
    with pytest.raises(ValueError, match="cannot be None"):
        adapter.normalize(None)


def test_normalize_invalid_type_raises_error(adapter: ClaudeAdapter):
    """Test that invalid types raise ValueError."""
    with pytest.raises(ValueError, match="Cannot normalize"):
        adapter.normalize("not a dict")


def test_normalize_missing_id_uses_fallback(adapter: ClaudeAdapter):
    """Test handling of missing id field."""
    data = {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "No ID"}],
        "stop_reason": "end_turn",
    }

    event = adapter.normalize(data)
    assert event.entity_id == "unknown"  # Fallback to "unknown"


def test_normalize_minimal_data(adapter: ClaudeAdapter):
    """Test normalization with minimal required fields."""
    data = {
        "type": "message",
    }

    event = adapter.normalize(data)
    assert event.event_type == "claude.message.completed"
    assert event.entity_type == "claude_message"
    assert event.entity_id == "unknown"
    assert event.severity == "info"


# ============================================================================
# TESTS: Backward Compatibility
# ============================================================================


def test_preserves_all_claude_fields(adapter: ClaudeAdapter):
    """Test that ALL Claude fields are preserved in payload."""
    data = {
        "id": "msg_full",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Full response"}],
        "model": "claude-sonnet-4.5",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        # Extra fields that might be added in future Claude versions
        "custom_field_1": "value1",
        "custom_field_2": {"nested": "value2"},
    }

    event = adapter.normalize(data)

    # ALL fields must be in payload
    assert event.payload["claude_response"] == data
    assert event.payload["claude_response"]["custom_field_1"] == "value1"
    assert event.payload["claude_response"]["custom_field_2"]["nested"] == "value2"


def test_supports_pydantic_v2_models(adapter: ClaudeAdapter):
    """Test normalization of Pydantic v2 models (via model_dump)."""

    class MockPydanticV2:
        """Mock Pydantic v2 model with model_dump method."""

        def model_dump(self):
            return {
                "id": "msg_pydantic",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "From Pydantic"}],
                "stop_reason": "end_turn",
            }

    mock_model = MockPydanticV2()
    event = adapter.normalize(mock_model)

    assert event.entity_id == "msg_pydantic"
    assert event.payload["content"][0]["text"] == "From Pydantic"


def test_supports_pydantic_v1_models(adapter: ClaudeAdapter):
    """Test normalization of Pydantic v1 models (via dict)."""

    class MockPydanticV1:
        """Mock Pydantic v1 model with dict method."""

        def dict(self):
            return {
                "id": "msg_pydantic_v1",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "From Pydantic v1"}],
                "stop_reason": "end_turn",
            }

    mock_model = MockPydanticV1()
    event = adapter.normalize(mock_model)

    assert event.entity_id == "msg_pydantic_v1"


def test_supports_dataclass_models(adapter: ClaudeAdapter):
    """Test normalization of dataclass objects."""

    @dataclass
    class ClaudeMessage:
        id: str
        type: str
        role: str
        content: list
        stop_reason: str

    msg = ClaudeMessage(
        id="msg_dataclass",
        type="message",
        role="assistant",
        content=[{"type": "text", "text": "From dataclass"}],
        stop_reason="end_turn",
    )

    event = adapter.normalize(msg)
    assert event.entity_id == "msg_dataclass"


# ============================================================================
# TESTS: Performance
# ============================================================================


def test_normalization_performance(adapter: ClaudeAdapter, sample_message: dict):
    """Test that normalization completes in <10ms (CONSTITUTION.md constraint)."""
    # Warm up (JIT compilation, caching, etc.)
    for _ in range(10):
        adapter.normalize(sample_message)

    # Measure 100 normalizations
    start = time.perf_counter()
    for _ in range(100):
        adapter.normalize(sample_message)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / 100) * 1000
    assert avg_ms < 10, f"Normalization took {avg_ms:.2f}ms (limit: 10ms)"


# ============================================================================
# TESTS: Validation
# ============================================================================


def test_normalized_event_validates(adapter: ClaudeAdapter, sample_message: dict):
    """Test that normalized events pass validation."""
    event = adapter.normalize(sample_message)

    # Should not raise
    event.validate()

    # Verify required fields are set
    assert event.event_id  # Auto-generated UUID
    assert event.event_type
    assert event.severity in {"info", "low", "medium", "high", "critical"}


def test_adapter_validate_method(adapter: ClaudeAdapter, sample_message: dict):
    """Test BaseAdapter.validate() method."""
    event = adapter.normalize(sample_message)

    # Should not raise (delegates to event.validate())
    adapter.validate(event)
