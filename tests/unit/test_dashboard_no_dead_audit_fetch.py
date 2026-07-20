"""Regression guard: the dead Audit History tab / Security Audits subtab must
stay removed from the dashboard frontend.

Migration 149 (core/event_store/migrations/149_drop_audit_runs.sql) dropped the
audit_runs table and the backend /api/v1/audits/* route module. The dashboard's
Audit History tab and Security Audits subtab were dead UI wired to those
now-404 endpoints — WO-SCHEMALEAN's follow-up dead-UI cleanup removed them from
projections/frontend/static/dashboard.js. This test pins that removal so the
dead fetches, tab id, and subtab id never creep back in.
"""

from __future__ import annotations

from pathlib import Path

from tests.dashboard_source import dashboard_source

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_JS = REPO_ROOT / "projections" / "frontend" / "static" / "dashboard.js"


def test_dashboard_js_has_no_dead_audits_fetch():
    content = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "/api/v1/audits/" not in content, (
        "dashboard.js must not fetch the removed /api/v1/audits/* routes "
        "(dropped with audit_runs in migration 149)"
    )
    assert "audit-history" not in content, (
        "the dead Audit History tab (id/tabsInitialized key/switchTab branch) "
        "must not be reintroduced"
    )
    assert (
        "security-audits-subtab" not in content
    ), "the dead Security Audits subtab must not be reintroduced"


def test_dashboard_source_has_no_dead_audits_fetch():
    """Combined html+css+js source (see tests/dashboard_source.py) must also be clean —
    covers the case where the tab/subtab markup lives in dashboard.html instead of JS."""
    content = dashboard_source()
    assert "/api/v1/audits/" not in content
    assert "audit-history" not in content
    assert "security-audits-subtab" not in content
