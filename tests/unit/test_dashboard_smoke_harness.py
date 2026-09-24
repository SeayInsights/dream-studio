from __future__ import annotations

from pathlib import Path

import pytest

from core.config.database import _default_db_path
from scripts.dashboard_smoke_harness import FRONTEND_MARKERS, SMOKE_ENDPOINTS, run_dashboard_smoke


def test_dashboard_smoke_harness_uses_temp_db_and_checks_routes(tmp_path: Path) -> None:
    db_path = tmp_path / "dashboard-smoke.db"

    result = run_dashboard_smoke(db_path)

    assert result["result"] == "passed"
    assert result["db_path"] == str(db_path)
    assert result["uses_live_db"] is False
    assert {item["path"] for item in result["endpoints"]} == set(SMOKE_ENDPOINTS)
    assert all(item["status_code"] == 200 for item in result["endpoints"])
    assert set(result["frontend_markers"]) == set(FRONTEND_MARKERS)
    assert all(result["frontend_markers"].values())
    assert result["manual_browser_steps"]


def test_dashboard_smoke_harness_refuses_live_db_path() -> None:
    # _default_db_path(), not a hardcoded Path.home() / ".dream-studio": the harness's
    # own safety check now resolves through it too (honoring DREAM_STUDIO_HOME), so the
    # "live" path this test probes with has to be computed the same way or the two never
    # match and the refusal this test exists to prove never fires.
    live_db = _default_db_path()

    with pytest.raises(RuntimeError, match="refuses to use the live Dream Studio DB"):
        run_dashboard_smoke(live_db)
