"""WO-DASH-ACTIONABILITY T4: learning charts show real data or an honest empty-state.

Operator: learning was blank. Until the learning pipeline lands, the tab must show an
honest empty-state that names the source + what populates it — never a blank canvas.
"""

from __future__ import annotations

from pathlib import Path

DASHBOARD = Path(__file__).resolve().parents[2] / "projections/frontend/dashboard.html"


def _html() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


def test_learning_data_or_honest_emptystate():
    html = _html()
    assert 'id="learning"' in html, "learning tab must exist"

    init_start = html.find("async function initLearningTab")
    assert init_start != -1, "initLearningTab must exist"
    init = html[init_start : init_start + 2400]  # noqa: E203

    # Honest empty-state: names the source table and what will populate it.
    assert "learning_event_records" in init, "empty-state must name the source table"
    assert (
        "ds-empty-state-overlay" in init
    ), "empty charts must get a visible empty-state overlay, not a blank canvas"
    assert (
        "honest empty" in init.lower() or "No data yet" in init
    ), "must declare an honest empty-state"

    # The overlay must replace (hide) the bare canvas so it doesn't read as broken.
    assert (
        "canvas.style.display = 'none'" in init
    ), "bare canvas must be hidden behind the empty-state"
