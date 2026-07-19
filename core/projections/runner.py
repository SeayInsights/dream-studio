"""Projection runner daemon — Phase 18.1.5.

Reads from business_canonical_events and ai_canonical_events on a trigger
(every POLL_INTERVAL_SECONDS, or when EVENT_TRIGGER_COUNT new events accumulate)
and dispatches to all registered projections via ProjectionEngine.run_cycle().

Start/stop/status is managed by `ds projection daemon start/stop/status`, which
reads the PID file written here.

Usage:
    runner = ProjectionRunner()
    runner.register(WorkOrderProjection())
    runner.run()  # blocks; handles SIGTERM/SIGINT for clean shutdown

Direct execution:
    py -m core.projections.runner
"""

import logging
import os
import signal
import sys
import time
from pathlib import Path

from core.config.paths import state_dir
from core.projections.framework import Projection, ProjectionEngine, ProjectionResult

logger = logging.getLogger(__name__)


class ProjectionRunner:
    """Daemon process for the v2 projection framework.

    Reads business_canonical_events and ai_canonical_events on a trigger
    (every POLL_INTERVAL_SECONDS, or when EVENT_TRIGGER_COUNT new events
    accumulate) and dispatches to all registered projections.

    Lifecycle:
        runner = ProjectionRunner()
        runner.register(WorkOrderProjection())
        runner.run()  # blocks; handles SIGTERM/SIGINT for clean shutdown
    """

    POLL_INTERVAL_SECONDS: float = 5.0
    EVENT_TRIGGER_COUNT: int = 100
    PID_FILE_NAME: str = "projection_runner.pid"

    # How often to emit an aggregate health log even when no events arrived.
    _HEALTH_LOG_INTERVAL_SECONDS: float = 60.0
    # How often to re-run the spool lifecycle check inside a running daemon.
    _ARCHIVE_CHECK_INTERVAL_SECONDS: float = 86400.0  # 24 hours

    def __init__(self) -> None:
        analytics_conn = self._open_analytics_conn()
        self._engine = ProjectionEngine(analytics_conn=analytics_conn)
        self._analytics_conn = analytics_conn
        self._poll_interval = float(
            os.environ.get("PROJECTION_POLL_INTERVAL", str(self.POLL_INTERVAL_SECONDS))
        )
        self._event_trigger = int(
            os.environ.get("PROJECTION_EVENT_TRIGGER", str(self.EVENT_TRIGGER_COUNT))
        )
        self._pid_path: Path = state_dir() / self.PID_FILE_NAME
        self._running: bool = False
        self._total_events: int = 0
        self._total_errors: int = 0
        self._last_archive_check: float = 0.0
        self._spine_projections: list = []

    @staticmethod
    def _open_analytics_conn() -> object | None:
        """Open the DuckDB analytics store (read-write).

        Resilient on the SDLC write path (returns None so a missing/unavailable
        analytics store never blocks the SQLite projection), but fail-LOUD on a
        wrong-format store: a non-DuckDB file is a real misconfiguration that
        must not be silently ignored (WO-DUCKDB-REAL T2), so it is logged at
        WARNING with the actionable AnalyticsStoreFormatError message. It still
        returns None rather than crashing work-order creation — the store is
        rebuildable and the operator resolves it by deleting the file.
        """
        try:
            from core.analytics.duckdb_store import (
                AnalyticsStoreFormatError,
                connect_analytics,
                ensure_analytics_schema,
            )

            conn = connect_analytics(read_only=False)
            ensure_analytics_schema(conn)
            return conn
        except AnalyticsStoreFormatError as exc:
            logger.warning("ProjectionRunner: analytics store rejected — %s", exc)
            return None
        except Exception:
            logger.debug(
                "ProjectionRunner: DuckDB analytics conn unavailable (non-fatal)",
                exc_info=True,
            )
            return None

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, projection: Projection) -> "ProjectionRunner":
        """Register a projection with the engine. Returns self for chaining."""
        self._engine.register(projection)
        return self

    def register_spine(self, projection: object) -> "ProjectionRunner":
        """Register a spine projection (reads from a local event spine, not canonical).

        The projection must implement fold_spine(conn) -> int.
        Called on each cycle after canonical projections complete.
        """
        self._spine_projections.append(projection)
        return self

    # ── Synchronous tick (Pattern C emit-then-tick) ───────────────────────────

    def tick(self) -> list[ProjectionResult]:
        """Run one synchronous projection cycle without daemon overhead.

        Does not require write_pid() or _install_signal_handlers(). Safe to call
        from SDLC creators or any non-daemon context after emitting a canonical
        event (emit-then-tick Pattern C). Returns the projection results.
        """
        results = self._engine.run_cycle()
        self._fold_spine_projections()
        self._refresh_events_fact()
        return results

    def _refresh_events_fact(self) -> None:
        """Incrementally derive the DuckDB events_fact from SQLite canonical events.

        Fail-open: the DuckDB dashboard read surface never blocks the SQLite
        projection path. Runner is the sole writer of events_fact.
        """
        if self._analytics_conn is None:
            return
        try:
            from core.analytics.duckdb_store import derive_events_fact
            from core.config.database import get_db_path

            derive_events_fact(self._analytics_conn, str(get_db_path()))
        except Exception:
            logger.debug("events_fact refresh failed (non-fatal)", exc_info=True)

    # ── Main daemon loop ──────────────────────────────────────────────────────

    def run(self) -> None:
        """Block indefinitely, processing projections on schedule or trigger.

        Installs SIGTERM/SIGINT handlers so that a signal causes the current
        cycle to complete before the process exits cleanly.
        """
        self.write_pid()
        self._install_signal_handlers()
        self._running = True
        logger.info(
            "ProjectionRunner started (pid=%d, interval=%.1fs, trigger=%d events)",
            os.getpid(),
            self._poll_interval,
            self._event_trigger,
        )

        # Run spool archive check at startup so a daemon restart on Monday or
        # January 1 does not miss the window if the daemon was down overnight.
        self._run_archive_check()

        last_health_log = time.monotonic()

        try:
            while self._running:
                cycle_start = time.monotonic()

                pending = self._count_pending_events()
                triggered = pending >= self._event_trigger
                if triggered:
                    logger.debug(
                        "Event trigger fired: %d pending events (threshold=%d)",
                        pending,
                        self._event_trigger,
                    )

                try:
                    results = self._engine.run_cycle()
                    self._log_cycle_summary(results)
                    for r in results:
                        self._total_events += r.events_processed
                        self._total_errors += len(r.errors)
                    self._refresh_events_fact()
                except Exception:
                    logger.exception("ProjectionRunner: unexpected error in run_cycle()")

                self._fold_spine_projections()

                now = time.monotonic()

                # Periodic health summary even during quiet periods.
                if now - last_health_log >= self._HEALTH_LOG_INTERVAL_SECONDS:
                    logger.info(
                        "ProjectionRunner health: %d total events processed, %d total errors",
                        self._total_events,
                        self._total_errors,
                    )
                    last_health_log = now

                # Daily spool archive check (covers Monday/January-1 conditions).
                if now - self._last_archive_check >= self._ARCHIVE_CHECK_INTERVAL_SECONDS:
                    self._run_archive_check()

                elapsed = time.monotonic() - cycle_start
                sleep_for = max(0.0, self._poll_interval - elapsed)
                if sleep_for > 0 and self._running:
                    time.sleep(sleep_for)

        finally:
            self._cleanup()

    # ── Spool lifecycle integration ───────────────────────────────────────────

    def _run_archive_check(self) -> None:
        """Run the spool lifecycle check and update the last-check timestamp.

        Delegates entirely to spool.lifecycle.check_and_archive() which is
        conditional on the calendar (Monday for weekly, Jan 1 for yearly) and
        idempotent (skips if archive already exists). Safe to call at any time.
        """
        try:
            from spool.lifecycle import check_and_archive

            check_and_archive()
        except Exception:
            logger.exception("ProjectionRunner: spool archive check failed")
        finally:
            self._last_archive_check = time.monotonic()

    # ── Pending-event count (for trigger logic) ───────────────────────────────

    def _count_pending_events(self) -> int:
        """Count new events past the max cursor across all registered projections.

        Returns 0 on any error — a failed count must never block the cycle.
        """
        try:
            from core.config.database import get_connection

            # Find the most-recent cursor timestamp across all projection_state rows.
            # We use the max of both cursor columns to represent "last seen anywhere".
            with get_connection(read_only=True) as conn:
                row = conn.execute("""
                    SELECT MAX(
                        COALESCE(last_processed_business_event_id, ''),
                        COALESCE(last_processed_ai_event_id, '')
                    )
                    FROM projection_state
                    """).fetchone()
                last_event_id = row[0] if row and row[0] else None

            # Resolve the timestamp for the cursor event (if we have one).
            if last_event_id:
                cutoff_ts = self._resolve_event_timestamp(last_event_id)
            else:
                cutoff_ts = "1970-01-01T00:00:00+00:00"

            # Count new events in both canonical tables past that timestamp.
            count = 0
            for table in ("business_canonical_events", "ai_canonical_events"):
                try:
                    with get_connection(read_only=True) as conn:
                        n = conn.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE event_timestamp > ?",
                            (cutoff_ts,),
                        ).fetchone()[0]
                    count += n
                except Exception:
                    # Table may not exist yet (first run before any migration).
                    pass
            return count
        except Exception:
            logger.debug("_count_pending_events failed; defaulting to 0", exc_info=True)
            return 0

    def _resolve_event_timestamp(self, event_id: str) -> str:
        """Look up event_timestamp for event_id across both canonical tables."""
        from core.config.database import get_connection

        for table in ("business_canonical_events", "ai_canonical_events"):
            try:
                with get_connection(read_only=True) as conn:
                    row = conn.execute(
                        f"SELECT event_timestamp FROM {table} WHERE event_id = ?",
                        (event_id,),
                    ).fetchone()
                if row:
                    return row[0]
            except Exception:
                pass
        return "1970-01-01T00:00:00+00:00"

    # ── Spine projection fold ─────────────────────────────────────────────────

    def _fold_spine_projections(self) -> None:
        """Run fold_spine() for every registered spine projection."""
        if not self._spine_projections:
            return
        try:
            from core.config.database import get_connection

            with get_connection() as conn:
                for proj in self._spine_projections:
                    try:
                        proj.fold_spine(conn)
                    except Exception:
                        logger.exception(
                            "ProjectionRunner: spine fold failed for %s",
                            getattr(proj, "name", repr(proj)),
                        )
        except Exception:
            logger.exception("ProjectionRunner: _fold_spine_projections setup failed")

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log_cycle_summary(self, results: list[ProjectionResult]) -> None:
        """Log one line summarising the completed cycle."""
        total_events = sum(r.events_processed for r in results)
        total_rows = sum(r.rows_written for r in results)
        total_errors = sum(len(r.errors) for r in results)
        if total_events > 0 or total_errors > 0:
            logger.info(
                "Cycle complete: %d events processed, %d rows written, %d errors",
                total_events,
                total_rows,
                total_errors,
            )
        else:
            logger.debug("Cycle complete: no new events")

    # ── PID file management ───────────────────────────────────────────────────

    def write_pid(self) -> None:
        """Write current PID to the pid file."""
        self._pid_path.write_text(str(os.getpid()), encoding="utf-8")
        logger.debug("PID file written: %s (pid=%d)", self._pid_path, os.getpid())

    # ── Signal handling ───────────────────────────────────────────────────────

    def _install_signal_handlers(self) -> None:
        """Install graceful shutdown handlers for SIGTERM and SIGINT.

        Windows does not have SIGTERM; SIGBREAK is the closest equivalent.
        We register whatever is available and skip silently if a signal
        constant is missing on the current platform.
        """

        def _shutdown(signum: int, frame: object) -> None:
            logger.info(
                "ProjectionRunner: shutdown signal received (%d) — finishing cycle",
                signum,
            )
            self._running = False

        for sig_name in ("SIGTERM", "SIGINT", "SIGBREAK"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                try:
                    signal.signal(sig, _shutdown)
                except (OSError, ValueError):
                    # Some signals cannot be caught in certain environments.
                    pass

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def _cleanup(self) -> None:
        """Remove PID file and emit final log on exit."""
        try:
            self._pid_path.unlink(missing_ok=True)
        except Exception:
            pass
        if self._analytics_conn is not None:
            try:
                self._analytics_conn.close()
            except Exception:
                pass
        logger.info(
            "ProjectionRunner shutdown complete (total events=%d, total errors=%d)",
            self._total_events,
            self._total_errors,
        )


# ── Pattern C sync tick (used by SDLC creators) ───────────────────────────────


def sync_tick() -> None:
    """Ingest pending spool events and run one SDLC projection cycle.

    Called by SDLC creators immediately after spool.writer.write_event() to
    guarantee the emitted row is queryable on return (Pattern C emit-then-tick).
    Steps:
      1. spool.ingestor.ingest()  — flush spool files into canonical events tables
      2. ProjectionEngine.run_cycle() — project canonical events into read-model tables

    Never raises — both steps are wrapped in try/except so a transient failure
    (DB lock, import error) degrades gracefully: the daemon will pick up the
    event on its next 5-second cycle.
    """
    try:
        from spool.ingestor import ingest as _ingest

        _ingest()
    except Exception:
        logger.debug("sync_tick: spool ingest failed (non-fatal)", exc_info=True)

    try:
        from core.projections.design_brief_projection import DesignBriefProjection
        from core.projections.milestone_projection import MilestoneProjection
        from core.projections.project_projection import ProjectProjection
        from core.projections.task_projection import TaskProjection
        from core.projections.work_order_projection import WorkOrderProjection

        runner = ProjectionRunner()
        runner.register(WorkOrderProjection())
        runner.register(TaskProjection())
        runner.register(MilestoneProjection())
        runner.register(ProjectProjection())
        # DesignBriefProjection MUST be registered here too: the synchronous
        # Pattern C tick is the only projection pass in a one-shot CLI process
        # (create_design_brief -> update_design_brief_field in the same run).
        # Without it the brief row is never materialized and the update fails
        # with "Brief not found" until the daemon's next cycle (WO 2325f95d).
        runner.register(DesignBriefProjection())
        # TokenConsumptionProjection (token.consumed -> token_usage_records) was
        # removed WO-DBA-DROP (migration 137 drops token_usage_records); the
        # DuckDB aggregate_metrics.db token_usage_records view over events_fact
        # is now the sole read side for token analytics.
        runner.tick()
    except Exception:
        logger.debug("sync_tick: projection cycle failed (non-fatal)", exc_info=True)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point for `py -m core.projections.runner`."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    runner = ProjectionRunner()

    try:
        from core.projections.work_order_projection import WorkOrderProjection

        runner.register(WorkOrderProjection())
    except ImportError:
        logger.warning(
            "WorkOrderProjection not found — running with no registered projections. "
            "This is expected until core/projections/work_order_projection.py is written."
        )

    try:
        from core.projections.task_projection import TaskProjection

        runner.register(TaskProjection())
    except ImportError:
        logger.warning("TaskProjection not found — skipping registration.")

    try:
        from core.projections.milestone_projection import MilestoneProjection

        runner.register(MilestoneProjection())
    except ImportError:
        logger.warning("MilestoneProjection not found — skipping registration.")

    try:
        from core.projections.design_brief_projection import DesignBriefProjection

        runner.register(DesignBriefProjection())
    except ImportError:
        logger.warning("DesignBriefProjection not found — skipping registration.")

    try:
        from core.projections.project_projection import ProjectProjection

        runner.register(ProjectProjection())
    except ImportError:
        logger.warning("ProjectProjection not found — skipping registration.")

    # PreflightProjection: removed migration 148 (WO-SCHEMALEAN) — the preflight_events /
    # business_work_order_preflights stack was an unwired aspirational loop (no writer);
    # dropped as duplicative of the live CI blast-radius gate.

    # FindingsProjection removed WO dff23cb0 (migration 140 drops
    # findings_current_status); security/lifecycle-status readers now derive
    # current status from security_events directly (see
    # core/findings/current_status.py).

    # TokenConsumptionProjection removed WO-DBA-DROP (migration 137 drops
    # token_usage_records); the DuckDB events_fact pipeline is the read side now.

    runner.run()


if __name__ == "__main__":
    main()
