"""No-dependency dashboard smoke harness.

The harness uses FastAPI TestClient and a temp SQLite DB by default. It does
not start Docker, install browser packages, or write the live Dream Studio DB.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from core.config.database import DB_PATH_ENV, DatabaseRuntime  # noqa: E402
from core.event_store.studio_db import _connect  # noqa: E402
from projections.api.main import app  # noqa: E402

SMOKE_ENDPOINTS: tuple[str, ...] = (
    "/dashboard",
    "/api/telemetry/summary",
    "/api/telemetry/attention",
    "/api/telemetry/components",
    "/api/telemetry/modules",
    "/api/v1/insights/?days=7",
    "/api/v1/hooks/executions?limit=50",
    "/api/v1/hooks/stats",
    # WO-SPLIT-DASHBOARD: the inline CSS/JS was extracted to /static/*; the harness
    # fetches them so a missing/unmounted asset fails the smoke, and the frontend
    # markers (now in dashboard.js) are checked against the served assets.
    "/static/dashboard.js",
    "/static/dashboard.css",
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
        # Build the derived analytics schema for this DREAM_STUDIO_HOME before serving.
        # The dashboard's DuckDB-backed endpoints (e.g. /api/v1/hooks/*) read views like
        # hook_executions that are views over events_fact — created ONLY by the aggregation
        # pipeline (ensure_analytics_schema), never on connect. Under an isolated home (the
        # pytest session temp home, or any freshly-supplied smoke DB) that pipeline has never
        # run, so the views are absent and the reads 500. Building the (idempotent) schema here
        # makes the views exist; over an empty events_fact they return 0 rows and the endpoints
        # take their normal empty/fallback path. No rows are seeded — this asserts the real
        # read contract against a structurally-complete but empty store.
        from core.analytics.duckdb_store import (
            connect_analytics as _connect_analytics,
            ensure_analytics_schema as _ensure_analytics_schema,
        )

        _analytics = _connect_analytics(read_only=False)
        try:
            _ensure_analytics_schema(_analytics)
        finally:
            _analytics.close()

        client = TestClient(app)
        endpoints = []
        responses = {}
        for endpoint in SMOKE_ENDPOINTS:
            response = client.get(endpoint)
            responses[endpoint] = response
            endpoints.append(
                {
                    "path": endpoint,
                    "status_code": response.status_code,
                    "ok": response.status_code == 200,
                }
            )
        # Frontend markers now live in the extracted /static assets (WO-SPLIT-DASHBOARD);
        # check them across the shell HTML + the served static JS/CSS.
        combined = "\n".join(
            responses[p].text
            for p in ("/dashboard", "/static/dashboard.js", "/static/dashboard.css")
        )
        markers = {marker: (marker in combined) for marker in FRONTEND_MARKERS}
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
