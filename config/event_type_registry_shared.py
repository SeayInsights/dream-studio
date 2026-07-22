from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RegistryEntry:
    event_type: str
    routes_to: tuple[str, ...]  # subset of {"business", "ai"}; () = raw only
    granularity_level: str  # "meaningful-unit" | "mechanical-detail"
    description: str
    # Keys that MUST be present in the payload dict for this event type.
    # Enforces the additive-only schema evolution policy. Empty = no enforcement.
    # Populated for event types consumed by at least one projection.
    payload_required_keys: frozenset = field(default_factory=frozenset, compare=False, hash=False)


_BUSINESS: tuple[str, ...] = ("business",)
_AI: tuple[str, ...] = ("ai",)
_BOTH: tuple[str, ...] = ("business", "ai")
_RAW_ONLY: tuple[str, ...] = ()
