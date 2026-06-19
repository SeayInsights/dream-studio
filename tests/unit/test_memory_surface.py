"""WO-DASH-ACTIONABILITY T3: memory-surface shows relevant memories with why-it-
matters, or is removed.

Operator: memory-surface was "not useful". Surfaced memories must explain why they
matter (relevance to current work), or the tab must be cut.
"""

from __future__ import annotations

from pathlib import Path

DASHBOARD = Path(__file__).resolve().parents[2] / "projections/frontend/dashboard.html"


def _html() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


def test_memory_surface_relevant_or_removed():
    html = _html()

    tab_present = 'id="memory-surface"' in html and "loadMemorySurface" in html
    if not tab_present:
        # Acceptable outcome: the non-useful tab was cut.
        assert "loadMemorySurface" not in html
        return

    # Kept → each surfaced memory must carry a why-it-matters explanation.
    assert "memoryWhyItMatters" in html, "a why-it-matters helper must exist"
    assert "Why it matters" in html, "surfaced memories must render a why-it-matters line"

    fn_start = html.find("function memoryWhyItMatters")
    assert fn_start != -1
    fn = html[fn_start : fn_start + 900]  # noqa: E203
    # Concrete, category-specific relevance — not a single generic string.
    for cat in ("gotcha", "lesson", "correction"):
        assert cat in fn, f"why-it-matters must cover the {cat} category"

    # Honest, instructive empty-state (names when memories surface + how to populate).
    _mem = html.find("async function loadMemorySurface")
    load_fn = html[_mem : _mem + 1600]  # noqa: E203
    assert "ds memory ingest" in load_fn, "empty-state must tell the operator how to populate it"
