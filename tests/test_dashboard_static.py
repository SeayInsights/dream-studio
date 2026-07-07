"""WO-SPLIT-DASHBOARD: dashboard.html's inline <style>/<script> were extracted to
frontend/static/{dashboard.css,dashboard.js} and the shell loads them from /static.

The extraction is byte-faithful (exact line-slice, same load order) and dashboard.js
is a CLASSIC script (not type="module"), so the 71 inline event handlers keep
resolving against window globals. These tests pin the structural contract; behavior
preservation follows from the faithful extraction + classic-script load.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from projections.api.main import app

FRONTEND = Path(__file__).resolve().parents[1] / "projections" / "frontend"
STATIC = FRONTEND / "static"


def test_static_assets_extracted():
    assert (STATIC / "dashboard.css").is_file(), "dashboard.css not extracted"
    assert (STATIC / "dashboard.js").is_file(), "dashboard.js not extracted"


def test_static_assets_served():
    client = TestClient(app)
    css = client.get("/static/dashboard.css")
    js = client.get("/static/dashboard.js")
    assert css.status_code == 200, f"dashboard.css not served: {css.status_code}"
    assert js.status_code == 200, f"dashboard.js not served: {js.status_code}"
    assert css.content and js.content


def test_shell_references_static_assets():
    html = (FRONTEND / "dashboard.html").read_text(encoding="utf-8")
    assert "/static/dashboard.css" in html, "shell must <link> the extracted CSS"
    assert "/static/dashboard.js" in html, "shell must <script src> the extracted JS"


def test_shell_has_no_inline_style_or_script_blocks():
    html = (FRONTEND / "dashboard.html").read_text(encoding="utf-8")
    assert "<style>" not in html, "inline <style> block still present"
    assert "<script>" not in html, "inline <script> block still present"


def test_dashboard_js_loaded_as_classic_script():
    """dashboard.js must NOT be a module — the inline onclick= handlers resolve
    against window globals that ES-module scoping would hide."""
    html = (FRONTEND / "dashboard.html").read_text(encoding="utf-8")
    assert (
        '<script src="/static/dashboard.js"></script>' in html
    ), "dashboard.js must load as a classic (non-module) script tag"


def test_shell_is_substantially_smaller_than_extracted_js():
    shell = (FRONTEND / "dashboard.html").read_text(encoding="utf-8")
    js = (STATIC / "dashboard.js").read_text(encoding="utf-8")
    assert len(js) > len(shell), "JS should dominate; extraction likely incomplete"
    assert len(js) > 100_000, "extracted JS unexpectedly small"
