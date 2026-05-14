"""
Unit tests for GPTAdapter (OpenAI GPT integration).

Tests proof-of-concept implementation for future GPT integration.
"""

import pytest
from interfaces.adapters.gpt_adapter import GPTAdapter
from interfaces.adapters.models import CanonicalEvent


class TestGPTAdapter:
    """Test suite for GPTAdapter."""

    def setup_method(self):
        """Initialize adapter before each test."""
        self.adapter = GPTAdapter()

    def test_normalize_valid_openai_response(self):
        """Test normalizing a valid OpenAI chat completion response."""
        raw_output = {
            "id": "chatcmpl-abc123",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "gpt-4",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "This is a test response from GPT-4.",
                    },
                    "finish_reason": "stop",
                    "index": 0,
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            },
        }

        event = self.adapter.normalize(raw_output)

        # Verify CanonicalEvent structure
        assert isinstance(event, CanonicalEvent)
        assert event.event_type == "ai.completion.created"
        assert event.entity_type == "gpt_completion"
        assert event.entity_id == "chatcmpl-abc123"
        assert event.severity == "info"

        # Verify payload content
        assert event.payload["model"] == "gpt-4"
        assert event.payload["content"] == "This is a test response from GPT-4."
        assert "raw_response" in event.payload

        # Verify metadata
        assert event.metadata["adapter"] == "gpt"
        assert "adapter_version" in event.metadata
        assert event.metadata["openai_created"] == 1234567890

    def test_normalize_minimal_response(self):
        """Test normalizing a minimal response with missing optional fields."""
        raw_output = {
            "id": "chatcmpl-xyz789",
            "choices": [],
        }

        event = self.adapter.normalize(raw_output)

        assert event.event_id  # Auto-generated
        assert event.entity_id == "chatcmpl-xyz789"
        assert event.payload["model"] == "unknown-gpt-model"
        assert event.payload["content"] == ""

    def test_normalize_non_dict_input(self):
        """Test that non-dict input raises ValueError."""
        with pytest.raises(ValueError, match="GPTAdapter expects dict input"):
            self.adapter.normalize("not a dict")

        with pytest.raises(ValueError, match="GPTAdapter expects dict input"):
            self.adapter.normalize(["list", "input"])

    def test_normalize_empty_dict(self):
        """Test normalizing an empty dict (edge case)."""
        raw_output = {}

        event = self.adapter.normalize(raw_output)

        # Should create valid event with defaults
        assert event.event_type == "ai.completion.created"
        assert event.entity_id == ""
        assert event.payload["model"] == "unknown-gpt-model"
        assert event.payload["content"] == ""

    def test_normalize_multiple_choices(self):
        """Test that only the first choice is extracted (POC simplification)."""
        raw_output = {
            "id": "chatcmpl-multi",
            "model": "gpt-3.5-turbo",
            "choices": [
                {"message": {"content": "First choice"}},
                {"message": {"content": "Second choice"}},
            ],
        }

        event = self.adapter.normalize(raw_output)

        # Only first choice should be in content
        assert event.payload["content"] == "First choice"

    def test_event_validation(self):
        """Test that adapter validates events before returning."""
        # Valid input should pass validation
        valid_output = {
            "id": "chatcmpl-valid",
            "model": "gpt-4",
            "choices": [{"message": {"content": "Valid"}}],
        }

        event = self.adapter.normalize(valid_output)
        # Should not raise (validation passed)
        event.validate()

    def test_trace_context_initialization(self):
        """Test that trace context is initialized (empty by default)."""
        raw_output = {"id": "chatcmpl-trace"}

        event = self.adapter.normalize(raw_output)

        assert event.trace is not None
        assert event.trace.project_id is None
        assert event.trace.task_id is None
        assert event.trace.session_id is None

    def test_payload_stores_full_response(self):
        """Test that full raw response is stored in payload for debugging."""
        raw_output = {
            "id": "chatcmpl-debug",
            "model": "gpt-4",
            "custom_field": "custom_value",
        }

        event = self.adapter.normalize(raw_output)

        # Full response should be preserved
        assert event.payload["raw_response"] == raw_output
        assert event.payload["raw_response"]["custom_field"] == "custom_value"
