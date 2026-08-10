"""WO-DASH-COHERENCE T3: the PRD tab is rewired off the dead /api/prd/* routes.

The dashboard's PRD tab used to fetch `/api/prd/list` and `/api/prd/{id}` — routes
that were dropped, so the tab 404'd and never populated. T3 rewires it onto the live,
read-only derived PRD+SOW panel (`/api/v1/prd-sow/active` for the active project,
`/api/v1/prd-sow/{project_id}` for the detail modal). This is a projection over
milestones/WOs + docstore — no new studio.db table.

This test pins the rewire so the dead endpoints never creep back in.
"""

from __future__ import annotations

from pathlib import Path

from tests.dashboard_source import dashboard_source

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_JS = REPO_ROOT / "projections" / "frontend" / "static" / "dashboard.js"


def test_prd_tab_calls_live_prd_sow():
    content = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "/api/v1/prd-sow/active" in content, (
        "the PRD tab must fetch the active project's PRD+SOW panel via " "/api/v1/prd-sow/active"
    )
    assert "/api/v1/prd-sow/${" in content, (
        "the PRD detail modal must fetch the per-project panel via " "/api/v1/prd-sow/{project_id}"
    )


def test_prd_tab_has_no_dead_prd_fetch():
    content = DASHBOARD_JS.read_text(encoding="utf-8")
    assert (
        "/api/prd/list" not in content
    ), "the dead /api/prd/list route (dropped) must not be fetched"
    assert "/api/prd/" not in content, (
        "no dead /api/prd/* route (list or detail) may be fetched — the tab is "
        "rewired onto /api/v1/prd-sow"
    )


def test_prd_tab_rewire_holds_in_combined_source():
    """Combined html+css+js (see tests/dashboard_source.py) must also be clean —
    covers markup that lives in dashboard.html rather than dashboard.js."""
    content = dashboard_source()
    assert "/api/v1/prd-sow" in content
    assert "/api/prd/list" not in content
    assert "/api/prd/" not in content
