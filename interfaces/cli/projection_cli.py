"""CLI command handler for `ds projection ...` commands.

Phase 18.1.5: Exposes the v2 projection framework to operators via the ds CLI.
Commands cover projection state inspection, full rebuilds, dead-letter management,
and daemon lifecycle.
"""

from __future__ import annotations

import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config.database import get_connection, transaction  # noqa: E402
from core.config.paths import state_dir  # noqa: E402


# ── Engine / runner factories ─────────────────────────────────────────────────


def _get_engine():
    from core.projections.framework import ProjectionEngine
    from core.projections.work_order_projection import WorkOrderProjection

    engine = ProjectionEngine()
    engine.register(WorkOrderProjection())
    return engine


def _pid_file() -> Path:
    return state_dir() / "projection-runner.pid"


# ── argparse registration ─────────────────────────────────────────────────────


def add_projection_subcommand(subcommands) -> None:
    """Register 'ds projection ...' commands into the main ds argparse subcommands."""
    projection = subcommands.add_parser("projection", help="Manage v2 projection framework")
    proj_sub = projection.add_subparsers(dest="projection_command", required=True)

    # list
    proj_sub.add_parser("list", help="List all projections with state")

    # status
    status_cmd = proj_sub.add_parser("status", help="Detailed status for one projection")
    status_cmd.add_argument("name", help="Projection name")

    # rebuild
    rebuild_cmd = proj_sub.add_parser("rebuild", help="Drop and rebuild from canonical events")
    rebuild_cmd.add_argument("name", help="Projection name")

    # dead-letter
    dl = proj_sub.add_parser("dead-letter", help="Manage dead-letter entries")
    dl_sub = dl.add_subparsers(dest="dl_command", required=True)
    dl_list = dl_sub.add_parser("list", help="List dead-letter entries")
    dl_list.add_argument("--projection", default=None, help="Filter by projection name")
    dl_retry = dl_sub.add_parser("retry", help="Re-queue a dead-letter entry")
    dl_retry.add_argument("event_id", help="Event ID to retry")
    dl_resolve = dl_sub.add_parser("resolve", help="Mark dead-letter entry as resolved")
    dl_resolve.add_argument("event_id", help="Event ID to resolve")

    # daemon
    daemon = proj_sub.add_parser("daemon", help="Manage the projection runner daemon")
    daemon_sub = daemon.add_subparsers(dest="daemon_command", required=True)
    daemon_sub.add_parser("status", help="Check if daemon is running")
    daemon_sub.add_parser("start", help="Print daemon start instructions")
    daemon_sub.add_parser("stop", help="Stop the running daemon")


# ── Top-level dispatcher ──────────────────────────────────────────────────────


def handle_projection_command(args) -> int:
    """Handle a `ds projection ...` command. Returns exit code (0=success)."""
    cmd = args.projection_command

    if cmd == "list":
        return _cmd_list()
    elif cmd == "status":
        return _cmd_status(args.name)
    elif cmd == "rebuild":
        return _cmd_rebuild(args.name)
    elif cmd == "dead-letter":
        dl_cmd = args.dl_command
        if dl_cmd == "list":
            return _cmd_dl_list(getattr(args, "projection", None))
        elif dl_cmd == "retry":
            return _cmd_dl_retry(args.event_id)
        elif dl_cmd == "resolve":
            return _cmd_dl_resolve(args.event_id)
        else:
            print(f"Unknown dead-letter subcommand: {dl_cmd}", file=sys.stderr)
            return 1
    elif cmd == "daemon":
        daemon_cmd = args.daemon_command
        if daemon_cmd == "status":
            return _cmd_daemon_status()
        elif daemon_cmd == "start":
            return _cmd_daemon_start()
        elif daemon_cmd == "stop":
            return _cmd_daemon_stop()
        else:
            print(f"Unknown daemon subcommand: {daemon_cmd}", file=sys.stderr)
            return 1
    else:
        print(f"Unknown projection subcommand: {cmd}", file=sys.stderr)
        return 1


# ── Command implementations ───────────────────────────────────────────────────


def _cmd_list() -> int:
    """List all registered projections with their state from projection_state."""
    try:
        with get_connection(read_only=True) as conn:
            rows = conn.execute(
                """
                SELECT
                    projection_name,
                    last_processed_business_event_id,
                    last_processed_ai_event_id,
                    events_processed_total,
                    events_failed_total,
                    last_run_at
                FROM projection_state
                ORDER BY projection_name
                """
            ).fetchall()
    except Exception as exc:
        print(f"Error reading projection_state: {exc}", file=sys.stderr)
        return 1

    if not rows:
        print("No projections registered.")
        return 0

    # Pull source_canonical and target_tables from the live registry.
    registry_meta: dict[str, dict] = {}
    try:
        engine = _get_engine()
        for proj in engine._registry.all_projections():
            registry_meta[proj.name] = {
                "source_canonical": proj.source_canonical,
                "target_tables": ", ".join(proj.target_tables),
            }
    except Exception:
        # Registry unavailable — display what we have from DB alone.
        pass

    header = (
        f"{'NAME':<30}  {'SOURCE':<10}  {'TABLES':<30}  "
        f"{'PROCESSED':>10}  {'FAILED':>8}  {'LAST_RUN':<26}  "
        f"{'LAST_BIZ_EVENT':<40}  {'LAST_AI_EVENT':<40}"
    )
    print(header)
    print("-" * len(header))

    for row in rows:
        name = row[0] or ""
        last_biz = row[1] or ""
        last_ai = row[2] or ""
        processed = row[3] or 0
        failed = row[4] or 0
        last_run = row[5] or ""

        meta = registry_meta.get(name, {})
        source = meta.get("source_canonical", "")
        tables = meta.get("target_tables", "")

        print(
            f"{name:<30}  {source:<10}  {tables:<30}  "
            f"{processed:>10}  {failed:>8}  {last_run:<26}  "
            f"{last_biz:<40}  {last_ai:<40}"
        )

    return 0


def _cmd_status(name: str) -> int:
    """Detailed status for one projection."""
    try:
        with get_connection(read_only=True) as conn:
            ps_row = conn.execute(
                """
                SELECT
                    projection_name,
                    last_processed_business_event_id,
                    last_processed_ai_event_id,
                    last_run_at,
                    events_processed_total,
                    events_failed_total
                FROM projection_state
                WHERE projection_name = ?
                """,
                (name,),
            ).fetchone()

            if ps_row is None:
                print(f"Projection '{name}' not found in projection_state.", file=sys.stderr)
                return 1

            active_dl = conn.execute(
                """
                SELECT COUNT(*) FROM projection_dead_letter
                WHERE projection_name = ? AND status = 'active'
                """,
                (name,),
            ).fetchone()[0]

            pending_retries = conn.execute(
                """
                SELECT COUNT(*) FROM projection_retry_queue
                WHERE projection_name = ?
                """,
                (name,),
            ).fetchone()[0]

    except Exception as exc:
        print(f"Error reading projection state: {exc}", file=sys.stderr)
        return 1

    print(f"Projection: {ps_row[0]}")
    print(f"  last_processed_business_event_id : {ps_row[1] or '(none)'}")
    print(f"  last_processed_ai_event_id       : {ps_row[2] or '(none)'}")
    print(f"  last_run_at                      : {ps_row[3] or '(never)'}")
    print(f"  events_processed_total           : {ps_row[4] or 0}")
    print(f"  events_failed_total              : {ps_row[5] or 0}")
    print(f"  active_dead_letters              : {active_dl}")
    print(f"  pending_retries                  : {pending_retries}")

    # Target table row counts from the live registry.
    try:
        engine = _get_engine()
        proj = engine._registry.get(name)
        if proj and proj.target_tables:
            print("  target_tables:")
            with get_connection(read_only=True) as conn:
                for table in proj.target_tables:
                    try:
                        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        print(f"    {table}: {count} rows")
                    except Exception:
                        print(f"    {table}: (unavailable)")
    except Exception:
        pass

    return 0


def _cmd_rebuild(name: str) -> int:
    """Drop and re-populate a projection from canonical events."""
    print(f"Rebuilding projection '{name}' from canonical events …")
    try:
        engine = _get_engine()
        if name not in engine._projections:
            print(
                f"Projection '{name}' is not registered. Available: "
                + ", ".join(engine._projections.keys()),
                file=sys.stderr,
            )
            return 1
        result = engine.rebuild(name)
    except Exception as exc:
        print(f"Rebuild failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Done.  events_processed={result.events_processed}  "
        f"rows_written={result.rows_written}  "
        f"duration_ms={result.duration_ms:.1f}"
    )
    if result.errors:
        print(f"  {len(result.errors)} error(s) during rebuild:")
        for err in result.errors:
            print(f"    {err}")
        return 1
    return 0


def _cmd_dl_list(projection_filter: Optional[str]) -> int:
    """List dead-letter entries, optionally filtered by projection name."""
    try:
        if projection_filter:
            rows = _fetch_dl_rows(projection_filter)
        else:
            rows = _fetch_dl_rows(None)
    except Exception as exc:
        print(f"Error reading dead-letter table: {exc}", file=sys.stderr)
        return 1

    if not rows:
        msg = "No dead-letter entries"
        if projection_filter:
            msg += f" for projection '{projection_filter}'"
        print(msg + ".")
        return 0

    header = (
        f"{'ID':>6}  {'EVENT_ID':<40}  {'PROJECTION':<28}  "
        f"{'FAILED_AT':<26}  {'RETRIES':>7}  {'STATUS':<10}  ERROR"
    )
    print(header)
    print("-" * len(header))

    for row in rows:
        dl_id = row[0]
        event_id = row[1] or ""
        proj_name = row[2] or ""
        failed_at = row[3] or ""
        retry_count = row[4] or 0
        status = row[5] or ""
        error_msg = (row[6] or "")[:80]

        print(
            f"{dl_id:>6}  {event_id:<40}  {proj_name:<28}  "
            f"{failed_at:<26}  {retry_count:>7}  {status:<10}  {error_msg}"
        )

    return 0


def _fetch_dl_rows(projection_filter: Optional[str]) -> list:
    with get_connection(read_only=True) as conn:
        if projection_filter:
            return conn.execute(
                """
                SELECT id, event_id, projection_name, failed_at,
                       retry_count, status, error_message
                FROM projection_dead_letter
                WHERE projection_name = ?
                ORDER BY failed_at DESC
                """,
                (projection_filter,),
            ).fetchall()
        return conn.execute(
            """
            SELECT id, event_id, projection_name, failed_at,
                   retry_count, status, error_message
            FROM projection_dead_letter
            ORDER BY failed_at DESC
            """
        ).fetchall()


def _cmd_dl_retry(event_id: str) -> int:
    """Re-queue a dead-letter entry: set status='active', add to retry queue."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        with get_connection(read_only=True) as conn:
            dl_row = conn.execute(
                """
                SELECT id, event_id, event_source, projection_name, retry_count
                FROM projection_dead_letter
                WHERE event_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (event_id,),
            ).fetchone()

        if dl_row is None:
            print(f"No dead-letter entry found for event_id '{event_id}'.", file=sys.stderr)
            return 1

        dl_id, ev_id, ev_source, proj_name, retry_count = dl_row

        with transaction() as conn:
            conn.execute(
                "UPDATE projection_dead_letter SET status = 'active' WHERE id = ?",
                (dl_id,),
            )
            conn.execute(
                """
                INSERT INTO projection_retry_queue
                    (event_id, event_source, projection_name, next_retry_at, retry_count)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                (ev_id, ev_source, proj_name, now, retry_count),
            )

    except Exception as exc:
        print(f"Error re-queuing dead-letter entry: {exc}", file=sys.stderr)
        return 1

    print(f"Re-queued event '{event_id}' for projection '{proj_name}' (next_retry_at={now}).")
    return 0


def _cmd_dl_resolve(event_id: str) -> int:
    """Mark a dead-letter entry as resolved."""
    try:
        with transaction() as conn:
            result = conn.execute(
                "UPDATE projection_dead_letter SET status = 'resolved' WHERE event_id = ?",
                (event_id,),
            )
        if result.rowcount == 0:
            print(f"No dead-letter entry found for event_id '{event_id}'.", file=sys.stderr)
            return 1
    except Exception as exc:
        print(f"Error resolving dead-letter entry: {exc}", file=sys.stderr)
        return 1

    print(f"Resolved dead-letter entry for event '{event_id}'.")
    return 0


# ── Daemon commands ───────────────────────────────────────────────────────────


def _read_pid() -> Optional[int]:
    """Return the PID from the PID file, or None if file absent / unreadable."""
    pid_path = _pid_file()
    if not pid_path.exists():
        return None
    try:
        return int(pid_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _process_is_running(pid: int) -> bool:
    """Return True if the process with pid is currently running."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        # ProcessLookupError → process does not exist
        # PermissionError on Windows → process exists but we can't signal it;
        # treat as running so the operator can investigate.
        return isinstance(SystemError, PermissionError) or _windows_pid_exists(pid)
    except OSError:
        return False


def _windows_pid_exists(pid: int) -> bool:
    """Windows fallback: check process existence via tasklist."""
    if sys.platform != "win32":
        return False
    try:
        import subprocess

        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return str(pid) in out
    except Exception:
        return False


def _cmd_daemon_status() -> int:
    """Report whether the projection runner daemon is active."""
    pid = _read_pid()
    if pid is None:
        print("not running (no PID file)")
        return 0

    if _process_is_running(pid):
        print(f"running (pid={pid})")
    else:
        print(f"not running (stale PID file: pid={pid})")
    return 0


def _cmd_daemon_start() -> int:
    """Print instructions for starting the projection runner daemon."""
    print(
        "To start the projection runner daemon, run the following command in a "
        "dedicated terminal or process manager:\n"
        "\n"
        "    py -m core.projections.runner\n"
        "\n"
        "The runner writes its PID to:\n"
        f"    {_pid_file()}\n"
        "\n"
        "Use your OS process manager (systemd, NSSM, supervisor, etc.) to keep "
        "it running across restarts."
    )
    return 0


def _cmd_daemon_stop() -> int:
    """Stop the running daemon by sending SIGTERM (or taskkill on Windows)."""
    pid = _read_pid()
    if pid is None:
        print("Daemon is not running (no PID file).")
        return 0

    if not _process_is_running(pid):
        print(f"Daemon is not running (stale PID file: pid={pid}).")
        _pid_file().unlink(missing_ok=True)
        return 0

    try:
        if sys.platform == "win32":
            import subprocess

            subprocess.check_call(["taskkill", "/PID", str(pid), "/F"])
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception as exc:
        print(f"Failed to stop daemon (pid={pid}): {exc}", file=sys.stderr)
        return 1

    print(f"Sent stop signal to daemon (pid={pid}).")
    return 0
