"""ProjectionEngine — runtime engine composing the dispatch/retry/rebuild/legacy mixins.

WO-GF-PROJECTION-ENGINE: split from ``core/projections/framework.py``. The
723-line ``ProjectionEngine`` class is decomposed into four private mixins
(each in its own ``framework_engine_<group>.py`` sibling); this module keeps
``__init__``, ``analytics_conn``, ``register``, ``register_without_setup``,
``_ensure_projection_state``, and ``run_cycle``, and composes the mixins onto
the concrete ``ProjectionEngine`` class. Method bodies on the mixins call each
other and ``Projection`` ABC methods via ``self`` — resolved at runtime, no
import needed between mixins.

CYCLE NOTE: this module imports ``Projection`` at module scope (one-directional
dependency). ``framework_projection.py``'s ``rebuild_from_canonical()`` imports
``ProjectionEngine`` back, but does so lazily (function-local) — see the note
in that module. Do not make this import lazy; do not make that one eager.
"""

from __future__ import annotations

from typing import Any

from core.config.database import transaction
from core.config.paths import state_dir

from .framework_engine_dispatch import _ProjectionEngineDispatchMixin
from .framework_engine_legacy import _ProjectionEngineLegacyMixin
from .framework_engine_rebuild import _ProjectionEngineRebuildMixin
from .framework_engine_retry import _ProjectionEngineRetryMixin
from .framework_projection import Projection
from .framework_registry import ProjectionRegistry
from .framework_shared import ProjectionResult, logger


class ProjectionEngine(
    _ProjectionEngineDispatchMixin,
    _ProjectionEngineRetryMixin,
    _ProjectionEngineRebuildMixin,
    _ProjectionEngineLegacyMixin,
):
    """Runtime engine: reads dual canonical tables and dispatches to projections.

    Cursor pattern:
      Each projection has a row in projection_state with two cursor columns:
        last_processed_business_event_id  — last event_id consumed from business
        last_processed_ai_event_id        — last event_id consumed from ai
      Events with event_timestamp > the cursor timestamp are fetched and
      dispatched in event_timestamp ASC order (deterministic replay).

    Retry / dead-letter cycle (per run_cycle()):
      1. Process any due entries in projection_retry_queue.
      2. Fetch new events from canonical tables past the current cursor.
      3. Dispatch to matching projections.
      4. On success: advance cursor in projection_state.
      5. On failure: schedule retry in projection_retry_queue.
      6. On retry exhaustion: move to projection_dead_letter.

    Backward compat:
      The old canonical_events table is NOT read by new v2 code paths.
      Old consumers.py projections continue to work via apply_incremental()
      which reads canonical_events (unchanged from pre-v2).  projection_checkpoints
      table is kept and still written for legacy projections.
    """

    def __init__(
        self,
        db_path: str | None = None,
        analytics_conn: Any | None = None,
    ) -> None:
        self.db_path = db_path or str(state_dir() / "studio.db")
        self._analytics_conn = analytics_conn  # DuckDB conn; None until WO-TS3 wires projections
        self._registry = ProjectionRegistry()
        # Legacy dict for backward compat with apply_incremental / rebuild
        self._projections: dict[str, Projection] = {}
        self._ensure_meta_tables()

    @property
    def analytics_conn(self) -> Any | None:
        """DuckDB analytics connection, or None if not yet wired (see WO-TS3)."""
        return self._analytics_conn

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, projection: Projection) -> None:
        """Register a projection and call setup_tables() to initialize DDL."""
        with transaction() as conn:
            projection.setup_tables(conn)
        self._registry.register(projection)
        self._projections[projection.name] = projection
        self._ensure_projection_state(projection.name)
        logger.info("ProjectionEngine: registered '%s'", projection.name)

    def register_without_setup(self, projection: Projection) -> None:
        """Register without calling setup_tables() (used internally by rebuild)."""
        if projection.name not in self._projections:
            self._registry.register(projection)
            self._projections[projection.name] = projection
            self._ensure_projection_state(projection.name)

    def _ensure_projection_state(self, projection_name: str) -> None:
        """Insert a default projection_state row if one doesn't exist."""
        with transaction() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO projection_state (projection_name)
                VALUES (?)
                """,
                (projection_name,),
            )

    # ── Main cycle ────────────────────────────────────────────────────────────

    def run_cycle(self, projection_name: str | None = None) -> list[ProjectionResult]:
        """Execute one full processing cycle: retries first, then new events.

        Args:
            projection_name: If provided, only process this projection.
                             Otherwise process all registered projections.

        Returns:
            List of ProjectionResult, one per projection processed.
        """
        targets: list[Projection] = (
            [self._projections[projection_name]]
            if projection_name and projection_name in self._projections
            else list(self._projections.values())
        )
        results = []
        for proj in targets:
            self._process_retries(proj)
            results.append(self._apply_v2(proj))
        return results
