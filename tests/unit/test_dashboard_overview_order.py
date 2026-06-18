"""WO-DASH-OVERVIEW-ORDER: Telemetry Traceability must render BELOW the primary
graphs on the Overview tab (it previously rendered before them, which was
confusing). KPIs stay at the top.

Module-level functions so the work order's TEST-CHECK node-ids `file::function`
resolve directly.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
DASHBOARD_HTML = REPO_ROOT / "projections/frontend/dashboard.html"

# The four primary Overview graphs.
_GRAPH_CANVASES = (
    "sessionTimelineChart",
    "topSkillsChart",
    "modelDistributionChart",
    "costOverTimeChart",
)


def test_telemetry_after_graphs():
    """Telemetry Traceability section appears AFTER all four primary graph canvases."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    tel_idx = text.find('id="telemetry-traceability-section"')
    assert tel_idx > 0, "telemetry-traceability-section not found"

    for canvas in _GRAPH_CANVASES:
        canvas_idx = text.find(f'id="{canvas}"')
        assert canvas_idx > 0, f"graph canvas {canvas} not found"
        assert canvas_idx < tel_idx, (
            f"{canvas} must render BEFORE the Telemetry Traceability section "
            "(graphs first, telemetry below them)"
        )


def test_kpis_stay_at_top():
    """The cost/success/alerts KPIs remain above both the graphs and telemetry."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")
    kpi_idx = text.find("kpi-total-cost")
    tel_idx = text.find('id="telemetry-traceability-section"')
    first_graph_idx = text.find('id="sessionTimelineChart"')
    assert kpi_idx > 0, "kpi-total-cost not found"
    assert kpi_idx < first_graph_idx, "KPIs must stay above the primary graphs"
    assert kpi_idx < tel_idx, "KPIs must stay above the Telemetry Traceability section"


def test_end_to_end():
    """Overview order end-to-end: KPIs -> primary graphs -> Telemetry Traceability,
    all within the overview tab, with the section structure intact."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    # The overview tab still exists and the telemetry section is a single instance.
    assert 'id="overview" class="tab-content' in text
    assert text.count('id="telemetry-traceability-section"') == 1

    overview_idx = text.find('id="overview"')
    kpi_idx = text.find("kpi-total-cost")
    last_graph_idx = max(text.find(f'id="{c}"') for c in _GRAPH_CANVASES)
    tel_idx = text.find('id="telemetry-traceability-section"')
    eval_idx = text.find("Eval Health")

    assert (
        overview_idx < kpi_idx < last_graph_idx < tel_idx
    ), "Overview order must be: tab -> KPIs -> primary graphs -> Telemetry Traceability"
    # Telemetry now sits below the graphs and before the Eval Health panel.
    assert tel_idx < eval_idx, "Telemetry Traceability should precede the Eval Health panel"
