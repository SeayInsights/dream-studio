"""Advisory event type validation.

Checks event types against the canonical event taxonomy (event_taxonomy_v1.json).
Advisory only: warns on unregistered types but never blocks emission.

Derives from the same taxonomy used by EventValidator.
Does NOT create a separate event type authority.

Created: 2026-05-09 (Phase 4E - EventType Advisory Validation)
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_TAXONOMY_PATH = Path("docs/canonical/event_taxonomy_v1.json")

_cached_event_types: frozenset[str] | None = None


@dataclass(frozen=True)
class AdvisoryResult:
    """Result of advisory event type validation."""

    is_registered: bool
    event_type: str
    message: str | None = None


def get_registered_event_types(
    taxonomy_path: Path | None = None,
) -> frozenset[str]:
    """Load canonical event types from event_taxonomy_v1.json.

    Returns the same set of types that EventValidator uses for hard validation.
    Result is cached after first load.
    """
    global _cached_event_types

    if _cached_event_types is not None:
        return _cached_event_types

    path = taxonomy_path or _TAXONOMY_PATH

    try:
        with open(path) as f:
            taxonomy = json.load(f)
    except FileNotFoundError:
        logger.warning(
            "Event taxonomy not found at %s. " "Advisory event type validation disabled.",
            path,
        )
        _cached_event_types = frozenset()
        return _cached_event_types

    types: set[str] = set()
    for event_types in taxonomy.get("allowed_event_types", {}).values():
        types.update(event_types)

    _cached_event_types = frozenset(types)
    return _cached_event_types


def validate_event_type_advisory(
    event_type: str,
    taxonomy_path: Path | None = None,
) -> AdvisoryResult:
    """Check if an event type is registered in the canonical taxonomy.

    Advisory only: never blocks emission, only reports registration status.
    Derives from the same event_taxonomy_v1.json used by EventValidator.
    """
    registered_types = get_registered_event_types(taxonomy_path)

    if not registered_types:
        return AdvisoryResult(
            is_registered=True,
            event_type=event_type,
            message="Advisory validation disabled (taxonomy not loaded)",
        )

    if event_type in registered_types:
        return AdvisoryResult(is_registered=True, event_type=event_type)

    return AdvisoryResult(
        is_registered=False,
        event_type=event_type,
        message=(
            f"Event type '{event_type}' is not registered in the canonical "
            f"event taxonomy. This event may fail EventStore validation."
        ),
    )


def reset_cache() -> None:
    """Reset the cached event types. For testing only."""
    global _cached_event_types
    _cached_event_types = None
