"""ds-dashboard: bootstrap analytics DB, harvest data, launch the real-time dashboard.

Usage:
    py scripts/ds_dashboard.py              # bootstrap + launch server + open browser
    py scripts/ds_dashboard.py --port 8001  # use a different port

Launches the FastAPI analytics server at http://localhost:<port>/dashboard
with WebSocket real-time streaming. Auto-bootstraps DB on first run.
"""
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "hooks"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
from lib import paths  # noqa: E402

DEFAULT_PORT = 8000


def _db_exists() -> bool:
    return (paths.state_dir() / "studio.db").is_file()


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def bootstrap_db() -> None:
    """Create studio.db and run all migrations. Idempotent."""
    from lib.studio_db import _connect  # noqa: PLC0415

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
            from backfill_token_sessions import backfill_token_usage, backfill_sessions  # noqa: PLC0415
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


def launch_server(port: int) -> subprocess.Popen:
    """Start the FastAPI analytics server as a background process."""
    cmd = [
        sys.executable, "-m", "uvicorn",
        "analytics.api.main:app",
        "--host", "127.0.0.1",
        "--port", str(port),
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Bootstrap and launch the analytics dashboard")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Server port (default: {DEFAULT_PORT})")
    args = ap.parse_args()

    port = args.port
    url = f"http://localhost:{port}/dashboard"

    # If server is already running, just open the browser
    if _port_in_use(port):
        print(f"[dashboard] Server already running on port {port}")
        print(f"[dashboard] Opening {url}")
        webbrowser.open(url)
        return 0

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
    print(f"[dashboard] Starting analytics server on port {port}...")
    proc = launch_server(port)

    if not wait_for_server(port):
        print("[dashboard] Server failed to start. Check stderr:")
        stderr = proc.stderr.read().decode() if proc.stderr else ""
        print(stderr)
        return 1

    print(f"[dashboard] Server running at {url}")
    print(f"[dashboard] API docs at http://localhost:{port}/api/docs")
    print(f"[dashboard] Press Ctrl+C to stop\n")

    webbrowser.open(url)

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n[dashboard] Shutting down...")
        proc.terminate()
        proc.wait(timeout=5)

    return 0


if __name__ == "__main__":
    sys.exit(main())
