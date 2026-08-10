"""WO-DASH-COHERENCE T4: dead dashboard UI for retired features stays removed.

The schema-lean campaigns dropped the source tables / routes these panels read, so
they could only ever show empty/404 state — the incoherence the operator flagged
("some panels populate, others no longer do"). T4 removes them:

- Alerts firing history + analytics (migration 131 retired /api/v1/alerts/history
  and /api/v1/alerts/analytics; alerts fire in-memory only): the Alert History
  timeline sub-panel, the Top Triggered Rules + Resolution Time charts, and the
  dead /api/v1/alerts/history fetch behind the Active Alerts KPI (now an honest 0).
- Project detail sub-tabs PRDs (prd_documents dropped) and Dependencies
  (pi_dependencies dropped) — Overview/Security/Activity remain.
- The findings-based extension effect count (findings dropped -> effect-summary is
  always empty).

The live Alerts surface (SLA gauges + rule CRUD) and Project Overview/Security/
Activity tabs are retained. This test pins the removals so they never creep back in.
"""

from __future__ import annotations

from pathlib import Path

from tests.dashboard_source import dashboard_source

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_JS = REPO_ROOT / "projections" / "frontend" / "static" / "dashboard.js"


def test_dead_alert_history_analytics_removed():
    src = dashboard_source()
    # Dead fetches (retired routes) — assert the call sites, not prose mentions.
    assert "fetchAlerts('/history')" not in src, "the dead alerts /history fetch must stay removed"
    assert (
        "fetchAlerts('/analytics')" not in src
    ), "the dead alerts /analytics fetch must stay removed"
    assert (
        "fetch('/api/v1/alerts/history')" not in src
    ), "the dead /api/v1/alerts/history KPI fetch must stay removed"
    # Dead render functions + their DOM targets.
    for symbol in (
        "populateAlertHistoryTimeline",
        "initTopTriggeredRulesChart",
        "initResolutionTimeChart",
        "alertHistoryTimeline",
        "topTriggeredRulesChart",
        "resolutionTimeChart",
    ):
        assert symbol not in src, f"dead alerts UI symbol {symbol!r} must stay removed"


def test_dead_project_subtabs_removed():
    src = dashboard_source()
    # PRDs + Dependencies project sub-tabs (dropped source tables) — buttons, panels,
    # loaders, and switcher branches.
    for symbol in (
        'data-project-tab="prds"',
        'data-project-tab="dependencies"',
        "project-tab-prds",
        "project-tab-dependencies",
        "modal-prds-content",
        "modal-dependencies-content",
        "loadProjectPRDs",
        "loadProjectDependencies",
        "switchProjectTab('prds')",
        "switchProjectTab('dependencies')",
        "/api/v1/projects/${projectId}/prds",
        "/api/v1/projects/${projectId}/dependencies",
    ):
        assert symbol not in src, f"dead project sub-tab artifact {symbol!r} must stay removed"


def test_dead_findings_effect_count_removed():
    src = dashboard_source()
    assert (
        "loadEffectSummary" not in src
    ), "the findings-based effect-count loader must stay removed"
    assert "effect-summary" not in src, "the dead extensions effect-summary fetch must stay removed"


def test_pi_violations_list_absent():
    """The pi_violations list was already gone; pin it so it does not reappear
    (pi_violations was dropped; security findings come from the security_events spine)."""
    assert "pi_violations" not in dashboard_source()


def test_live_alert_and_project_surfaces_retained():
    """Guard against over-removal: the live surfaces must survive."""
    src = dashboard_source()
    # Alerts tab keeps SLA + rule CRUD.
    assert "populateAlertRulesTable" in src
    assert "fetchAlerts('/sla')" in src
    assert "fetchAlerts('/rules')" in src
    # Project modal keeps Overview / Security / Activity.
    assert 'data-project-tab="security"' in src
    assert "data-project-tab='activity'" in src
    assert "loadProjectSecurity" in src
    assert "loadProjectActivity" in src
