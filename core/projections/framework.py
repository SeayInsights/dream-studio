"""Projection framework v2 — derives materialized L3 state from dual canonical events.

Phase 18.1.5: Rewrites the projection engine to read from business_canonical_events
and ai_canonical_events (the v2 dual canonical layer from Phase 18.1.2) instead of
the legacy canonical_events table.

Architecture:
  - Projection ABC: code-first Python classes with imperative handle() logic.
  - ProjectionRegistry: tracks registered projections; validates event_type declarations
    against the event type registry.
  - ProjectionEngine: cursor-based incremental dispatch — reads dual canonical tables,
    routes events by source_canonical declaration, retries on transient failure
    (exponential backoff), and dead-letters after max_retries exceeded.

Dead-letter pattern:
  Transient failures → projection_retry_queue (scheduled retry with backoff).
  Exhausted retries  → projection_dead_letter (status='active', operator resolves).
  The engine continues processing subsequent events after dead-lettering; one bad
  event does not block a projection's progress.

Backward compatibility:
  ProjectionCheckpoint, ProjectionResult, and projection_checkpoints DDL are all
  preserved so existing consumers.py projections keep working. The old Projection
  ABC interface (name, event_types, setup_tables, handle, pre_rebuild) is kept as
  properties/methods on the new base class; consumers.py is migrated in Phase 18.2.

Usage (new v2 projection):
    from core.projections.framework import Projection, ProjectionEngine, RetryPolicy

    class WorkOrderProjection(Projection):
        name = "work_order_projection"
        consumed_event_types = ["work_order.created", "work_order.started", "work_order.%"]
        source_canonical = "business"
        target_tables = ["business_work_orders"]
        retry_policy = RetryPolicy(max_retries=5, base_delay_seconds=2.0)

        def setup_tables(self, conn):
            pass  # migration 069 owns the DDL

        def handle(self, event, conn):
            # idempotency built in via is_already_processed()
            ...
            return 1

        def rebuild_from_canonical(self):
            # framework default: pre_rebuild() + replay via handle()
            super().rebuild_from_canonical()

Usage (engine):
    engine = ProjectionEngine()
    engine.register(WorkOrderProjection())
    engine.run_cycle()          # process pending retries + new events
    engine.rebuild("work_order_projection")

WO-GF-PROJECTION-ENGINE: implementation moved to framework_{shared,events,
projection,registry,engine,engine_dispatch,engine_retry,engine_rebuild,
engine_legacy}.py; this module re-exports the full public + private surface so
existing `from core.projections.framework import X` callers are unchanged.
"""

from __future__ import annotations

from .framework_engine import ProjectionEngine
from .framework_events import (
    _build_type_filter,
    _legacy_row_to_event,
    _parse_json,
    _row_to_event,
)
from .framework_projection import Projection
from .framework_registry import ProjectionRegistry, _event_type_matches, _source_matches
from .framework_shared import (
    CanonicalSource,
    ProjectionCheckpoint,
    ProjectionResult,
    RetryPolicy,
    _TABLE_FOR_SOURCE,
    logger,
)

__all__ = [
    "CanonicalSource",
    "Projection",
    "ProjectionCheckpoint",
    "ProjectionEngine",
    "ProjectionRegistry",
    "ProjectionResult",
    "RetryPolicy",
    "_TABLE_FOR_SOURCE",
    "_build_type_filter",
    "_event_type_matches",
    "_legacy_row_to_event",
    "_parse_json",
    "_row_to_event",
    "_source_matches",
    "logger",
]
