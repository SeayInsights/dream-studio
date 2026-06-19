"""WO-DASH-ACTIONABILITY T1: the evals tab leads with regressions + friction.

Operator: evals were "populated but just tables, nothing actionable". The tab must
lead with what needs attention (regressions + the friction queue) and a recommended
action per item — not raw baseline/run tables.
"""

from __future__ import annotations

from pathlib import Path

DASHBOARD = Path(__file__).resolve().parents[2] / "projections/frontend/dashboard.html"


def _html() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


def test_evals_leads_with_regressions_and_friction():
    html = _html()

    # A "Needs Attention" panel exists and is positioned BEFORE the raw tables.
    na = html.find('id="evals-needs-attention"')
    baselines = html.find('id="evals-baselines-body"')
    runs = html.find('id="evals-runs-body"')
    assert na != -1, "evals tab must have an evals-needs-attention panel"
    assert baselines != -1 and runs != -1
    assert na < baselines < runs, "Needs Attention must lead, before the baseline/run tables"

    # The render path draws on regressions AND the friction queue, with actions.
    fn_start = html.find("async function renderEvalsNeedsAttention")
    assert fn_start != -1, "renderEvalsNeedsAttention must exist"
    fn_end = fn_start + 2600
    fn = html[fn_start:fn_end]
    assert "friction_flag" in fn, "must surface friction-flagged evals"
    assert "pending_rerun" in fn, "must surface the pending-rerun queue"
    assert "baseline" in fn.lower(), "must surface regressions against baseline"
    assert "action" in fn.lower(), "each item must carry a recommended action"

    # Honest empty-state when nothing needs attention (not a blank panel).
    assert "No regressions" in fn, "must show an explicit all-clear empty-state"

    # It is actually wired into tab init.
    init_start = html.find("async function initEvalsTab")
    init = html[init_start : init_start + 1200]  # noqa: E203
    assert "renderEvalsNeedsAttention" in init, "initEvalsTab must call the Needs Attention render"
