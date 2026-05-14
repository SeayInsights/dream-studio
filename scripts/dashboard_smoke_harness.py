"""No-dependency dashboard smoke harness.

The harness uses FastAPI TestClient and a temp SQLite DB by default. It does
not start Docker, install browser packages, or write the live Dream Studio DB.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.event_store.studio_db import _connect
from projections.api.main import app

SMOKE_ENDPOINTS: tuple[str, ...] = (
    "/dashboard",
    "/api/telemetry/summary",
    "/api/telemetry/attention",
    "/api/telemetry/components",
    "/api/telemetry/modules",
    "/api/v1/hooks/executions?limit=50",
    "/api/v1/hooks/stats",
)

FRONTEND_MARKERS: tuple[str, ...] = (
    "Telemetry Traceability",
    "TELEMETRY_API_BASE = '/api/telemetry'",
    "fetchTelemetry('/summary')",
    "fetchTelemetry('/attention')",
    "fetchTelemetry('/components')",
    "fetchTelemetry('/modules')",
)


def run_dashboard_smoke(db_path: Path | str | None = None) -> dict[str, Any]:
    """Run dashboard smoke checks against a temp or supplied non-live DB path."""

    path = Path(db_path) if db_path is not None else Path(tempfile.mkdtemp()) / "dashboard-smoke.db"
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    if path.resolve() == live_db.resolve():
        raise RuntimeError("dashboard smoke harness refuses to use the live Dream Studio DB")

    conn = _connect(path)
    conn.close()
    previous = os.environ.get(DB_PATH_ENV)
    os.environ[DB_PATH_ENV] = str(path)
    DatabaseRuntime.reset_instance()
    try:
        client = TestClient(app)
        endpoints = []
        for endpoint in SMOKE_ENDPOINTS:
            response = client.get(endpoint)
            endpoints.append(
                {
                    "path": endpoint,
                    "status_code": response.status_code,
                    "ok": response.status_code == 200,
                }
            )
        dashboard = client.get("/dashboard")
        html = dashboard.text
        markers = {marker: (marker in html) for marker in FRONTEND_MARKERS}
        passed = all(item["ok"] for item in endpoints) and all(markers.values())
        return {
            "result": "passed" if passed else "failed",
            "db_path": str(path),
            "uses_live_db": False,
            "endpoints": endpoints,
            "frontend_markers": markers,
            "manual_browser_steps": [
                "Start the dashboard with DREAM_STUDIO_DB_PATH pointing to the smoke DB.",
                "Open http://localhost:8000/dashboard.",
                "Confirm legacy sections and Telemetry Traceability render without fatal frontend errors.",
            ],
        }
    finally:
        if previous is None:
            os.environ.pop(DB_PATH_ENV, None)
        else:
            os.environ[DB_PATH_ENV] = previous
        DatabaseRuntime.reset_instance()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Dream Studio dashboard smoke checks.")
    parser.add_argument(
        "--db-path", type=Path, default=None, help="Optional non-live SQLite DB path."
    )
    args = parser.parse_args()
    print(json.dumps(run_dashboard_smoke(args.db_path), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
