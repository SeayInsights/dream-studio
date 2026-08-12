"""WO-DASH-XSS-ESCAPE: the PRD+SOW dashboard tab escapes authority-derived strings.

The PRD+SOW tab (WO-DASH-COHERENCE T3) interpolates milestone/capability titles, SOW
text, and statuses into innerHTML. Those are authority-derived strings and must be
HTML-escaped via escHtml (as the project drill-down already does) so a title containing
markup cannot inject into the dashboard DOM. This test pins the escaping so the raw
interpolations don't creep back in.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_JS = REPO_ROOT / "projections" / "frontend" / "static" / "dashboard.js"


def test_prd_tab_escapes_authority_strings():
    content = DASHBOARD_JS.read_text(encoding="utf-8")
    # The escaped forms must be present.
    for escaped in (
        "escHtml(m.title || m.milestone_id)",
        "escHtml(m.status)",
        "escHtml(c.title || c.capability_id)",
        "escHtml(c.status)",
        "escHtml(m.set_out_to || '—')",
        "escHtml(m.accomplished || '—')",
    ):
        assert escaped in content, f"PRD tab must escape via {escaped!r}"


def test_prd_tab_has_no_raw_authority_interpolation():
    content = DASHBOARD_JS.read_text(encoding="utf-8")
    # The raw, unescaped interpolations must be gone (the escaped form carries an
    # `${escHtml(` prefix, so these exact substrings only match the unescaped version).
    for raw in (
        "${m.title || m.milestone_id}",
        "${c.title || c.capability_id}",
        "${m.set_out_to || '—'}",
        "${m.accomplished || '—'}",
    ):
        assert raw not in content, f"raw unescaped PRD interpolation {raw!r} must be escaped"
