"""Legacy adapter layer — moved from interfaces/adapters/ (Slice 4 retirement)."""

from core.adapters.models import CanonicalEvent, SeverityLevel
from core.adapters.normalizers import (
    BaseAdapter,
    ClaudeAdapter,
    DefaultAdapter,
    EventNormalizer,
    GPTAdapter,
)

__all__ = [
    "BaseAdapter",
    "CanonicalEvent",
    "ClaudeAdapter",
    "DefaultAdapter",
    "EventNormalizer",
    "GPTAdapter",
    "SeverityLevel",
]
