"""WO-DASH-ACTIONABILITY T5: end-to-end — every flagged surface is actionable or cut.

Ties the four surface contracts together: each of evals, config, memory-surface, and
learning must either answer "what is wrong + what to do" or be removed. No surface may
remain a raw data-dump.
"""

from __future__ import annotations

from tests.dashboard_source import dashboard_source

from pathlib import Path

DASHBOARD = Path(__file__).resolve().parents[2] / "projections/frontend/dashboard.html"


def _html() -> str:
    return dashboard_source()


def test_end_to_end():
    html = _html()

    # Evals: leads with a Needs Attention (regressions + friction) panel before tables.
    na = html.find('id="evals-needs-attention"')
    baselines = html.find('id="evals-baselines-body"')
    assert na != -1 and baselines != -1 and na < baselines, "evals must lead with Needs Attention"
    assert "renderEvalsNeedsAttention" in html

    # Config: explained (What it does) or removed.
    if 'id="ds-config-body"' in html:
        assert "What it does" in html and "dsConfigDescription" in html

    # Memory-surface: why-it-matters or removed.
    if "loadMemorySurface" in html:
        assert "memoryWhyItMatters" in html and "Why it matters" in html

    # Learning: honest empty-state naming the source.
    assert "initLearningTab" in html
    _lrn = html.find("async function initLearningTab")
    init = html[_lrn : _lrn + 2400]  # noqa: E203
    assert "learning_event_records" in init and "ds-empty-state-overlay" in init

    # Guard against regressions to bare data-dumps: the actionable hooks must all be wired.
    for hook in ("renderEvalsNeedsAttention", "initLearningTab"):
        assert hook in html, f"{hook} must remain wired"
