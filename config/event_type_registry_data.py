from __future__ import annotations

from .event_type_registry_entries_ai import _AI_ENTRIES
from .event_type_registry_entries_business import _BUSINESS_ENTRIES
from .event_type_registry_entries_other import _OTHER_ENTRIES
from .event_type_registry_shared import RegistryEntry

_ENTRIES: tuple[RegistryEntry, ...] = _BUSINESS_ENTRIES + _AI_ENTRIES + _OTHER_ENTRIES

# Primary lookup dict: event_type string → RegistryEntry
_REGISTRY: dict[str, RegistryEntry] = {e.event_type: e for e in _ENTRIES}
