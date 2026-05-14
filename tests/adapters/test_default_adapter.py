"""
Unit tests for DefaultAdapter (fallback for unknown model types).

Tests pass-through normalization and warning behavior.
"""

import logging

import pytest
from interfaces.adapters.default_adapter import DefaultAdapter
from interfaces.adapters.models import CanonicalEvent


class TestDefaultAdapter:
    """Test suite for DefaultAdapter."""

    def setup_method(self):
        """Initialize adapter before each test."""
        self.adapter = DefaultAdapter()

    def test_normalize_dict_input(self):
        """Test normalizing a dict input (most common case)."""
        raw_output = {
            "model": "unknown-model",
            "content": "Test content",
            "metadata": {"foo": "bar"},
        }

        event = self.adapter.normalize(raw_output)

        # Verify CanonicalEvent structure
        assert isinstance(event, CanonicalEvent)
        assert event.event_type == "ai.completion.unknown"
        assert event.entity_type == "unknown_model"
        assert event.severity == "info"

        # Payload should contain copy of input
        assert event.payload["model"] == "unknown-model"
        assert event.payload["content"] == "Test content"
        assert event.payload["metadata"]["foo"] == "bar"

        # Verify metadata
        assert event.metadata["adapter"] == "default"
        assert event.metadata["original_type"] == "dict"
        assert "warning" in event.metadata

    def test_normalize_string_input(self):
        """Test normalizing a non-dict input (string)."""
        raw_output = "This is a plain string response"

        event = self.adapter.normalize(raw_output)

        # Should wrap in container
        assert event.payload["raw_output"] == raw_output
        assert event.payload["raw_type"] == "str"
        assert event.metadata["original_type"] == "str"

    def test_normalize_list_input(self):
        """Test normalizing a list input."""
        raw_output = ["item1", "item2", "item3"]

        event = self.adapter.normalize(raw_output)

        assert event.payload["raw_output"] == str(raw_output)
        assert event.payload["raw_type"] == "list"

    def test_normalize_int_input(self):
        """Test normalizing a primitive type (int)."""
        raw_output = 42

        event = self.adapter.normalize(raw_output)

        assert event.payload["raw_output"] == "42"
        assert event.payload["raw_type"] == "int"

    def test_normalize_none_input(self):
        """Test normalizing None input."""
        raw_output = None

        event = self.adapter.normalize(raw_output)

        assert event.payload["raw_output"] == "None"
        assert event.payload["raw_type"] == "NoneType"

    def test_entity_id_generation(self):
        """Test that entity_id is deterministic based on input."""
        raw_output = {"test": "data"}

        event1 = self.adapter.normalize(raw_output)
        event2 = self.adapter.normalize(raw_output)

        # Same input should produce same entity_id (deterministic hash)
        assert event1.entity_id == event2.entity_id
        assert event1.entity_id.startswith("default-")

    def test_entity_id_unique_for_different_inputs(self):
        """Test that different inputs produce different entity_ids."""
        event1 = self.adapter.normalize({"input": "A"})
        event2 = self.adapter.normalize({"input": "B"})

        assert event1.entity_id != event2.entity_id

    def test_warning_logged(self, caplog):
        """Test that adapter logs warning when invoked."""
        with caplog.at_level(logging.WARNING):
            self.adapter.normalize({"test": "data"})

        # Check that warning was logged
        assert len(caplog.records) >= 1
        warning_record = next((r for r in caplog.records if r.levelname == "WARNING"), None)
        assert warning_record is not None
        assert "DefaultAdapter invoked" in warning_record.message
        assert "unknown model type" in warning_record.message

    def test_event_validation(self):
        """Test that adapter validates events before returning."""
        raw_output = {"valid": "input"}

        event = self.adapter.normalize(raw_output)

        # Should not raise (validation passed)
        event.validate()

    def test_trace_context_initialization(self):
        """Test that trace context is initialized (empty by default)."""
        raw_output = {"test": "data"}

        event = self.adapter.normalize(raw_output)

        assert event.trace is not None
        assert event.trace.project_id is None
        assert event.trace.task_id is None

    def test_payload_preserves_dict_structure(self):
        """Test that dict inputs preserve their structure in payload."""
        raw_output = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "string": "test",
        }

        event = self.adapter.normalize(raw_output)

        # Structure should be preserved
        assert event.payload["nested"]["key"] == "value"
        assert event.payload["list"] == [1, 2, 3]
        assert event.payload["string"] == "test"

    def test_empty_dict_input(self):
        """Test normalizing an empty dict."""
        raw_output = {}

        event = self.adapter.normalize(raw_output)

        assert event.payload == {}
        assert event.metadata["original_type"] == "dict"

    def test_complex_object_input(self):
        """Test normalizing a custom object."""

        class CustomClass:
            def __str__(self):
                return "CustomClass instance"

        raw_output = CustomClass()

        event = self.adapter.normalize(raw_output)

        assert "CustomClass instance" in event.payload["raw_output"]
        assert event.payload["raw_type"] == "CustomClass"
