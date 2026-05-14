"""
Base adapter interface for AI/model output normalization.

All model-specific adapters (Claude, GPT, etc.) must inherit from BaseAdapter
and implement the normalize() method.
"""

from abc import ABC, abstractmethod
from typing import Any

from interfaces.adapters.models import CanonicalEvent


class BaseAdapter(ABC):
    """
    Abstract base class for model-specific event adapters.

    Adapters convert model-specific outputs (API responses, tool calls, etc.)
    into the canonical event schema used across all planes.

    Architecture constraint (CONSTITUTION.md):
    - Adapter overhead MUST be <10ms per event
    - No external API calls (synchronous normalization only)
    - No database writes (only in-memory transformation)

    Subclasses must implement:
        - normalize(raw_output) -> CanonicalEvent
    """

    @abstractmethod
    def normalize(self, raw_output: Any) -> CanonicalEvent:
        """
        Convert model-specific output to canonical event.

        Args:
            raw_output: Raw model output (dict, object, etc.)

        Returns:
            CanonicalEvent instance with normalized data.

        Raises:
            ValueError: If raw_output cannot be normalized (invalid structure).
        """
        pass

    def validate(self, event: CanonicalEvent) -> None:
        """
        Validate canonical event structure.

        Default implementation checks required fields.
        Subclasses can override for model-specific validation.

        Args:
            event: CanonicalEvent to validate

        Raises:
            ValueError: If validation fails.
        """
        event.validate()
