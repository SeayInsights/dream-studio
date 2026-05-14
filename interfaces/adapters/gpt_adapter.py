"""
GPT adapter for OpenAI API outputs.

Proof-of-concept implementation for future GPT integration.
Currently mocked for testing purposes.
"""

import logging
from typing import Any

from interfaces.adapters.base import BaseAdapter
from interfaces.adapters.models import CanonicalEvent, TraceContext

logger = logging.getLogger(__name__)


class GPTAdapter(BaseAdapter):
    """
    Adapter for OpenAI GPT API responses.

    Proof-of-concept implementation. Converts OpenAI-like response structures
    to CanonicalEvent format. This is NOT production-ready — external API
    integration requires async handling in the Control Plane.

    Expected input structure (OpenAI chat completion response):
    {
        "id": "chatcmpl-abc123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "gpt-4",
        "choices": [...],
        "usage": {...}
    }

    Architecture constraints:
    - Overhead must be <10ms
    - No external API calls (accepts pre-fetched responses only)
    - Synchronous normalization only
    """

    def normalize(self, raw_output: Any) -> CanonicalEvent:
        """
        Convert OpenAI GPT response to canonical event.

        Args:
            raw_output: Dict with OpenAI-like structure (chat completion response).

        Returns:
            CanonicalEvent with normalized GPT data.

        Raises:
            ValueError: If raw_output is not a dict or missing required fields.
        """
        if not isinstance(raw_output, dict):
            raise ValueError(f"GPTAdapter expects dict input, got {type(raw_output).__name__}")

        # Extract OpenAI-specific fields (with defaults for POC)
        completion_id = raw_output.get("id", "")
        model = raw_output.get("model", "unknown-gpt-model")
        created_timestamp = raw_output.get("created")

        # Extract first choice (POC simplification)
        choices = raw_output.get("choices", [])
        first_choice = choices[0] if choices else {}
        message_content = first_choice.get("message", {}).get("content", "")

        # Build canonical event
        event = CanonicalEvent(
            event_type="ai.completion.created",
            entity_type="gpt_completion",
            entity_id=completion_id,
            severity="info",
            payload={
                "model": model,
                "content": message_content,
                "raw_response": raw_output,  # Store full response for debugging
            },
            trace=TraceContext(),  # Empty trace — caller can populate
            metadata={
                "adapter": "gpt",
                "adapter_version": "0.1.0-poc",
                "openai_created": created_timestamp,
            },
        )

        # Validate before returning
        self.validate(event)

        logger.debug(f"GPTAdapter normalized event {event.event_id} for model {model}")

        return event
