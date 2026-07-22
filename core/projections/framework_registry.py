"""ProjectionRegistry — tracks registered projections and validates event types.

WO-GF-PROJECTION-ENGINE: split from ``core/projections/framework.py``.
"""

from __future__ import annotations

from typing import Any

from config.event_type_registry import all_entries, is_registered

from .framework_projection import Projection
from .framework_shared import CanonicalSource, logger


class ProjectionRegistry:
    """Tracks registered projections and validates event type declarations.

    The registry validates that each projection's consumed_event_types entries
    match at least one entry in the event type registry.  Unknown event types
    (no wildcard, not in registry) emit a WARNING — they are not rejected,
    because the registry is comprehensive but not exhaustive.
    """

    def __init__(self) -> None:
        self._projections: dict[str, Projection] = {}
        # Build a set of known event_types from the event type registry for
        # validation (wildcard check uses LIKE semantics against prefixes).
        self._known_types: frozenset[str] = frozenset(e.event_type for e in all_entries())

    def register(self, projection: Projection) -> None:
        """Register a projection and validate its event type declarations."""
        if not projection.name:
            raise ValueError(f"Projection {type(projection).__name__} must define a non-empty name")
        self._validate_event_types(projection)
        self._projections[projection.name] = projection
        logger.info(
            "ProjectionRegistry: registered '%s' (source=%s, types=%s)",
            projection.name,
            projection.source_canonical,
            projection.consumed_event_types,
        )

    def _validate_event_types(self, projection: Projection) -> None:
        """Warn if any declared event type is not in the event type registry."""
        for et in projection.consumed_event_types:
            if "%" in et:
                # Wildcard — skip validation (matches a family of event types).
                continue
            if not is_registered(et):
                logger.warning(
                    "ProjectionRegistry: '%s' declares event_type '%s' which is not "
                    "in the event type registry.  Add it to config/event_type_registry.py "
                    "if this is a new canonical event type.",
                    projection.name,
                    et,
                )

    def get_projections_for_event_type(self, event_type: str, source: str) -> list[Projection]:
        """Return all projections that consume the given event_type from the given source.

        Matching rules:
          - exact match:    event_type == consumed_event_type
          - wildcard match: consumed_event_type ends with '%' and event_type
                            starts with the prefix before '%'
          - source filter:  projection.source_canonical must be source or "both"
        """
        result = []
        for proj in self._projections.values():
            if not _source_matches(proj.source_canonical, source):
                continue
            for pattern in proj.consumed_event_types:
                if _event_type_matches(event_type, pattern):
                    result.append(proj)
                    break
        return result

    def all_projections(self) -> list[Projection]:
        """Return all registered projections."""
        return list(self._projections.values())

    def projected_tables(self) -> frozenset:
        """Return the set of all target tables across registered projections."""
        tables: set = set()
        for proj in self._projections.values():
            tables.update(proj.target_tables)
        return frozenset(tables)

    def get(self, name: str) -> Projection | None:
        """Return projection by name or None."""
        return self._projections.get(name)

    def summary(self) -> dict[str, Any]:
        """Return summary dict for `ds projection list`."""
        return {
            "count": len(self._projections),
            "projections": [
                {
                    "name": p.name,
                    "source_canonical": p.source_canonical,
                    "consumed_event_types": p.consumed_event_types,
                    "target_tables": p.target_tables,
                    "retry_policy": {
                        "max_retries": p.retry_policy.max_retries,
                        "base_delay_seconds": p.retry_policy.base_delay_seconds,
                        "backoff_factor": p.retry_policy.backoff_factor,
                    },
                }
                for p in self._projections.values()
            ],
        }


# ── Matching helpers ──────────────────────────────────────────────────────────


def _event_type_matches(event_type: str, pattern: str) -> bool:
    """Return True if event_type matches pattern (supports trailing '%' wildcard)."""
    if pattern.endswith("%"):
        return event_type.startswith(pattern[:-1])
    return event_type == pattern


def _source_matches(projection_source: CanonicalSource, event_source: str) -> bool:
    """Return True if the projection should receive events from this source."""
    if projection_source == "both":
        return True
    return projection_source == event_source
