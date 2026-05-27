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
from typing import List, Optional

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
        self._engine = ProjectionEngine()
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

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, projection: Projection) -> "ProjectionRunner":
        """Register a projection with the engine. Returns self for chaining."""
        self._engine.register(projection)
        return self

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
                except Exception:
                    logger.exception("ProjectionRunner: unexpected error in run_cycle()")

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

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log_cycle_summary(self, results: List[ProjectionResult]) -> None:
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

    def read_pid(self) -> Optional[int]:
        """Read PID from pid file. Returns None if the file does not exist."""
        try:
            return int(self._pid_path.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError):
            return None

    def is_running(self) -> bool:
        """Return True if a daemon process is alive (PID file exists and process is live)."""
        pid = self.read_pid()
        if pid is None:
            return False
        # os.kill(pid, 0) checks process existence without sending a real signal.
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            # ProcessLookupError → process is gone.
            # PermissionError on Unix → process exists but belongs to another user.
            return False

    # ── Signal handling ───────────────────────────────────────────────────────

    def _install_signal_handlers(self) -> None:
        """Install graceful shutdown handlers for SIGTERM and SIGINT.

        Windows does not have SIGTERM; SIGBREAK is the closest equivalent.
        We register whatever is available and skip silently if a signal
        constant is missing on the current platform.
        """

        def _shutdown(signum: int, frame: object) -> None:
            logger.info("ProjectionRunner: shutdown signal received (%d) — finishing cycle", signum)
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
        logger.info(
            "ProjectionRunner shutdown complete (total events=%d, total errors=%d)",
            self._total_events,
            self._total_errors,
        )


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

    runner.run()


if __name__ == "__main__":
    main()
