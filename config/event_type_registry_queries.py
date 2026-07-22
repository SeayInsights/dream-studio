from __future__ import annotations

from .event_type_registry_data import _ENTRIES, _REGISTRY
from .event_type_registry_shared import RegistryEntry


def get_routes(event_type: str) -> tuple[str, ...]:
    """Return routing destinations for event_type.

    Unknown event_types default to ("business", "ai") — the safe over-record
    default. Callers should log a warning when this fallback fires.
    """
    entry = _REGISTRY.get(event_type)
    if entry is None:
        return ("business", "ai")
    return entry.routes_to


def is_registered(event_type: str) -> bool:
    """Return True if event_type has an explicit registry entry."""
    return event_type in _REGISTRY


def get_entry(event_type: str) -> RegistryEntry | None:
    """Return the RegistryEntry for event_type, or None if not registered."""
    return _REGISTRY.get(event_type)


def all_entries() -> tuple[RegistryEntry, ...]:
    """Return all registry entries (for inspection and tooling)."""
    return _ENTRIES
