"""
Default adapter for unknown model types.

Fallback adapter that accepts any input and passes through as payload.
Logs warnings for unrecognized model types.
"""

import logging
from typing import Any

from interfaces.adapters.base import BaseAdapter
from interfaces.adapters.models import CanonicalEvent, TraceContext

logger = logging.getLogger(__name__)


class DefaultAdapter(BaseAdapter):
    """
    Fallback adapter for unknown model types.

    Use when no model-specific adapter is available. Accepts any input,
    logs a warning, and wraps the raw input in a generic CanonicalEvent.

    This adapter ensures the system degrades gracefully when encountering
    unknown model types, rather than failing hard.

    Architecture constraints:
    - Overhead must be <10ms
    - No external API calls
    - Synchronous normalization only
    """

    def normalize(self, raw_output: Any) -> CanonicalEvent:
        """
        Pass-through normalization for unknown model outputs.

        Accepts any input type and wraps it in a CanonicalEvent.
        Logs a warning that an unrecognized model type is being used.

        Args:
            raw_output: Any model output (no type restrictions).

        Returns:
            CanonicalEvent with raw_output stored in payload.
        """
        # Log warning about unknown model type
        model_type = type(raw_output).__name__
        logger.warning(
            f"DefaultAdapter invoked for unknown model type: {model_type}. "
            "Consider implementing a model-specific adapter for better normalization."
        )

        # Serialize raw_output for payload (handle non-dict types)
        if isinstance(raw_output, dict):
            payload_data = raw_output.copy()
        else:
            # Wrap non-dict types in a container
            payload_data = {
                "raw_output": str(raw_output),
                "raw_type": model_type,
            }

        # Build generic canonical event
        event = CanonicalEvent(
            event_type="ai.completion.unknown",
            entity_type="unknown_model",
            entity_id=f"default-{hash(str(raw_output)) % 10**8}",  # Deterministic ID
            severity="info",
            payload=payload_data,
            trace=TraceContext(),  # Empty trace — caller can populate
            metadata={
                "adapter": "default",
                "adapter_version": "0.1.0",
                "original_type": model_type,
                "warning": "Unrecognized model type — using fallback adapter",
            },
        )

        # Validate before returning
        self.validate(event)

        logger.debug(f"DefaultAdapter normalized event {event.event_id} for type {model_type}")

        return event
