"""ds-dashboard: bootstrap analytics DB, harvest data, launch the real-time dashboard.

Usage:
    py scripts/ds_dashboard.py              # bootstrap + launch server + open browser
    py scripts/ds_dashboard.py --port 8001  # use a different port
    py scripts/ds_dashboard.py --restart    # stop running server then relaunch
    py scripts/ds_dashboard.py --stop       # stop running server without relaunching
    py scripts/ds_dashboard.py --reload     # launch with --reload for live code reload
    py scripts/ds_dashboard.py stop         # alias: stop running server

Launches the FastAPI analytics server at http://localhost:<port>/dashboard
with WebSocket real-time streaming. Auto-bootstraps DB on first run.

Use --restart after merging code to pick up the new version.
Use --stop to terminate an existing server process on the target port.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
from core.config import paths  # noqa: E402
from interfaces.cli.runtime_preflight import (  # noqa: E402
    canonical_db_path,
    format_schema_compatibility,
    inspect_schema_compatibility,
    schema_compatibility_is_blocking,
)

DEFAULT_PORT = 8000


def _db_exists() -> bool:
    return canonical_db_path().is_file()


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _find_pid_on_port(port: int) -> int | None:
    """Return the PID of the process listening on *port*, or None if not found.

    Uses stdlib-only process introspection via psutil when available (already a
    declared dependency), falling back to OS-level commands so the function
    still works in constrained environments.
    """
    try:
        import psutil  # noqa: PLC0415

        for conn in psutil.net_connections(kind="tcp"):
            if conn.laddr.port == port and conn.status in (
                "LISTEN",
                psutil.CONN_LISTEN,
            ):
                return conn.pid
        return None
    except Exception:
        pass

    # Fallback: OS commands
    if sys.platform == "win32":
        return _find_pid_netstat(port)
    return _find_pid_lsof(port)


def _find_pid_netstat(port: int) -> int | None:
    """Windows fallback: parse ``netstat -ano`` output."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        target = f":{port} "
        for line in result.stdout.splitlines():
            if "LISTENING" in line and target in line:
                parts = line.split()
                if parts:
                    try:
                        return int(parts[-1])
                    except ValueError:
                        pass
    except Exception:
        pass
    return None


def _find_pid_lsof(port: int) -> int | None:
    """POSIX fallback: try ``lsof`` then ``ss``."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        pid_str = result.stdout.strip().split()[0] if result.stdout.strip() else ""
        if pid_str:
            return int(pid_str)
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # ss output: pid=<N>,fd=... inside the last column
        for line in result.stdout.splitlines():
            if f":{port}" in line and "pid=" in line:
                start = line.index("pid=") + 4
                end_comma = line.find(",", start)
                end = end_comma if end_comma != -1 else len(line)
                chunk = line[start:end]
                try:
                    return int(chunk)
                except ValueError:
                    pass
    except Exception:
        pass

    return None


def _kill_pid(pid: int) -> bool:
    """Terminate *pid*. Returns True on success, False on any error."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False


def cmd_stop(port: int, host: str = "127.0.0.1") -> int:
    """Stop the server running on *port*. Returns 0 on success, 1 if nothing to stop."""
    pid = _find_pid_on_port(port)
    if pid is None:
        print(f"[dashboard] No server found on port {port}.")
        return 1
    print(f"[dashboard] Stopping server (PID {pid}) on port {port}...")
    ok = _kill_pid(pid)
    if ok:
        # Wait briefly for the port to free up
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if not _port_in_use(port):
                break
            time.sleep(0.2)
        print(f"[dashboard] Server (PID {pid}) stopped.")
        return 0
    print(f"[dashboard] Failed to stop server (PID {pid}).")
    return 1


def cmd_restart(port: int, host: str = "127.0.0.1", open_browser: bool = False) -> int:
    """Stop any running server then relaunch. Picks up new code after a merge."""
    if _port_in_use(port):
        rc = cmd_stop(port, host)
        if rc != 0:
            print(f"[dashboard] Could not stop existing server on port {port}. Aborting restart.")
            return 1
        # Brief pause to let the OS release the port
        time.sleep(0.5)

    # Relaunch via the normal boot path
    return _launch_and_serve(port=port, host=host, open_browser=open_browser)


def bootstrap_db() -> None:
    """Create studio.db and run all migrations. Idempotent."""
    from core.event_store.studio_db import _connect  # noqa: PLC0415

    compatibility = inspect_schema_compatibility(repo_root=_PROJECT_ROOT)
    if schema_compatibility_is_blocking(compatibility):
        print(
            "[dashboard] Runtime DB schema is not compatible with this checkout.", file=sys.stderr
        )
        print(format_schema_compatibility(compatibility), file=sys.stderr)
        raise RuntimeError("runtime DB schema is newer than this checkout")

    print("[dashboard] Ensuring database exists...")
    conn = _connect()
    conn.close()
    print("[dashboard] Database ready.")


def harvest_existing_data() -> dict[str, int]:
    """Pull data from all existing sources into studio.db. Returns counts."""
    results: dict[str, int] = {}

    try:
        from ds_analytics.backfill_pulse import backfill  # noqa: PLC0415

        count = backfill()
        results["pulse_snapshots"] = count
    except Exception as e:
        print(f"[dashboard] Pulse backfill skipped: {e}")
        results["pulse_snapshots"] = 0

    token_log = paths.meta_dir() / "token-log.md"
    if token_log.is_file():
        try:
            from backfill_token_sessions import (
                backfill_token_usage,
                backfill_sessions,
            )  # noqa: PLC0415

            tok_result = backfill_token_usage()
            results["token_rows"] = tok_result.get("inserted", 0)
            sess_result = backfill_sessions()
            results["session_rows"] = sess_result.get("inserted", 0)
        except Exception as e:
            print(f"[dashboard] Token backfill skipped: {e}")
            results["token_rows"] = 0
            results["session_rows"] = 0
    else:
        results["token_rows"] = 0
        results["session_rows"] = 0

    try:
        from migrate_to_db import main as migrate_main  # noqa: PLC0415

        sys.argv = ["migrate_to_db"]
        migrate_main()
        results["metadata_migrated"] = True
    except Exception as e:
        print(f"[dashboard] Metadata migration skipped: {e}")
        results["metadata_migrated"] = False

    return results


def launch_server(port: int, host: str = "127.0.0.1", reload: bool = False) -> subprocess.Popen:
    """Start the FastAPI analytics server as a background process.

    Args:
        port: TCP port to bind.
        host: Bind address.
        reload: When True, passes ``--reload`` to uvicorn so the server picks
                up code changes without a manual restart.
    """
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "projections.api.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        cmd += [
            "--reload",
            "--reload-dir",
            "projections",
            "--reload-dir",
            "core",
        ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(_PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def wait_for_server(port: int, timeout: int = 15) -> bool:
    """Wait until the server is accepting connections."""
    start = time.time()
    while time.time() - start < timeout:
        if _port_in_use(port):
            return True
        time.sleep(0.3)
    return False


def run_check(port: int) -> int:
    """Read-only preflight check — verifies dashboard readiness without starting server."""
    errors = 0

    # 1. Check dependencies
    for mod_name in ("fastapi", "uvicorn", "sqlite3"):
        try:
            __import__(mod_name)
            print(f"  [ok] {mod_name} importable")
        except ImportError:
            print(f"  [FAIL] {mod_name} not importable")
            errors += 1

    # 2. Check API app importability
    try:
        from projections.api.main import app, start_api  # noqa: F401

        print("  [ok] projections.api.main importable")
    except Exception as e:
        print(f"  [FAIL] projections.api.main import error: {e}")
        errors += 1

    # 3. Check DB path availability (read-only — no creation)
    db_path = canonical_db_path()
    if db_path.is_file():
        print(f"  [ok] studio.db exists at {db_path}")
    else:
        print(f"  [warn] studio.db not found at {db_path} (will be created on first launch)")
    compatibility = inspect_schema_compatibility(repo_root=_PROJECT_ROOT)
    print(format_schema_compatibility(compatibility))
    if schema_compatibility_is_blocking(compatibility):
        print("  [FAIL] Runtime DB readiness blocked: blocked_newer_than_code")
        errors += 1

    # 4. Check host/CORS safety
    try:
        from projections.api.safety import SAFE_DEFAULT_HOST, localhost_origins

        print(f"  [ok] default host: {SAFE_DEFAULT_HOST}")
        origins = localhost_origins(port)
        print(f"  [ok] CORS origins: {origins}")
        if SAFE_DEFAULT_HOST == "127.0.0.1":
            print("  [ok] host is localhost-safe")
        else:
            print(f"  [WARN] host {SAFE_DEFAULT_HOST} may expose dashboard to network")
            errors += 1
    except Exception as e:
        print(f"  [FAIL] safety module error: {e}")
        errors += 1

    # 5. Check port availability
    if _port_in_use(port):
        print(f"  [info] port {port} already in use (server may be running)")
    else:
        print(f"  [ok] port {port} available")

    if errors == 0:
        print("\n[dashboard] Preflight check PASSED — ready to launch")
    else:
        print(f"\n[dashboard] Preflight check: {errors} error(s)")
    return errors


def run_smoke(db_path: Path | None = None) -> int:
    """Run no-dependency dashboard smoke checks without launching a server."""
    from dashboard_smoke_harness import run_dashboard_smoke  # noqa: PLC0415

    result = run_dashboard_smoke(db_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("result") == "passed" else 1


def _launch_and_serve(
    port: int, host: str = "127.0.0.1", open_browser: bool = True, reload: bool = False
) -> int:
    """Bootstrap DB, launch server, optionally open browser. Shared by normal launch and restart."""
    url = f"http://localhost:{port}/dashboard"

    # Bootstrap DB if needed
    had_db = _db_exists()
    bootstrap_db()

    if not had_db:
        print("[dashboard] First run — harvesting existing data...")
        results = harvest_existing_data()
        print("[dashboard] Harvest complete:")
        for k, v in results.items():
            print(f"  {k}: {v}")

    # Launch the FastAPI server
    print(f"[dashboard] Starting analytics server on {host}:{port}...")
    proc = launch_server(port, host=host, reload=reload)

    if not wait_for_server(port):
        print("[dashboard] Server failed to start. Check stderr:")
        stderr = proc.stderr.read().decode() if proc.stderr else ""
        print(stderr)
        return 1

    print(f"[dashboard] Server running at {url}")
    print(f"[dashboard] API docs at http://localhost:{port}/api/docs")
    if reload:
        print("[dashboard] Hot-reload enabled — code changes in projections/ and core/ are live.")
    print("[dashboard] Press Ctrl+C to stop\n")

    if open_browser:
        webbrowser.open(url)

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n[dashboard] Shutting down...")
        proc.terminate()
        proc.wait(timeout=5)

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Bootstrap and launch the analytics dashboard. "
            "Use --restart to pick up new code after a merge. "
            "Use --stop (or subcommand 'stop') to terminate a running server."
        )
    )
    ap.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"Server port (default: {DEFAULT_PORT})"
    )
    ap.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1). Use 0.0.0.0 for network access (unsafe).",
    )
    ap.add_argument(
        "--check", action="store_true", help="Run read-only preflight check without starting server"
    )
    ap.add_argument(
        "--smoke",
        action="store_true",
        help="Run temp-DB dashboard smoke checks without starting server",
    )
    ap.add_argument(
        "--smoke-db-path",
        type=Path,
        default=None,
        help="Optional non-live SQLite DB path for --smoke",
    )
    ap.add_argument(
        "--restart",
        action="store_true",
        help=(
            "Stop the running server on --port then relaunch with current code. "
            "Use this after merging new code to avoid serving a stale version."
        ),
    )
    ap.add_argument(
        "--stop",
        action="store_true",
        help="Stop the running server on --port without relaunching.",
    )
    ap.add_argument(
        "--reload",
        action="store_true",
        help=(
            "Enable uvicorn --reload so code changes in projections/ and core/ are "
            "picked up automatically without restarting the server."
        ),
    )
    # Also accept 'stop' as a positional subcommand for discoverability
    ap.add_argument(
        "subcommand",
        nargs="?",
        choices=["stop"],
        help="'stop' — terminate the running server (alias for --stop)",
    )
    args = ap.parse_args()

    port = args.port
    host = args.host

    if args.check:
        return run_check(port)
    if args.smoke:
        return run_smoke(args.smoke_db_path)

    # --stop / stop subcommand
    if args.stop or args.subcommand == "stop":
        return cmd_stop(port, host)

    # --restart
    if args.restart:
        return cmd_restart(port, host, open_browser=True)

    url = f"http://localhost:{port}/dashboard"

    if host == "0.0.0.0":
        print(
            "[dashboard] WARNING: --host 0.0.0.0 exposes dashboard to all network interfaces",
            file=sys.stderr,
        )

    # If server is already running, warn and just open the browser
    if _port_in_use(port):
        print(f"[dashboard] Server already running on port {port}")
        print(
            f"WARNING: A server is already running on port {port}. " "It may be serving stale code."
        )
        print("  To restart with current code, run: ds dashboard --restart")
        print(f"[dashboard] Opening {url}")
        webbrowser.open(url)
        return 0

    return _launch_and_serve(port=port, host=host, open_browser=True, reload=args.reload)


if __name__ == "__main__":
    sys.exit(main())
