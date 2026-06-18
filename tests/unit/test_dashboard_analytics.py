"""Tests for WO-DASH-ANALYTICS-TABS dashboard analytics tab fixes.

Six tasks validated:
  test_anomalies_outcomes_and_trend_real (T1)
      - session-outcome-flow does NOT use hardcoded fallback data
      - SVG diagram shows real outcomes: completed/failed/timeout/other buckets
      - "Other/Unknown" bucket present (not merged into Timeout)
      - trend-regression chart uses correct API key (reportable_cost not cost)
  test_learning_charts_render_or_emptystate (T2)
      - initLearningTab no longer calls buildLearningEmptyState with zero data
      - charts get honest empty-state overlay, not flat-zero lines
      - summary stats show 0 not --
  test_adaptation_renders_or_emptystate (T3)
      - loadAdaptationSummary shows 0 on error (not --)
      - _setAdaptationZeros helper present
  test_token_attribution_breakouts_present (T4)
      - loadAttributionBreakouts function present
      - breakout table DOM ids present (project/milestone/task/skill/agent)
      - route /api/v1/insights/attribution-breakouts present in insights.py
      - aggregation function covers all 5 dimensions
  test_config_and_memory_explain_or_removed (T5)
      - config tab has expanded description mentioning ds_config
      - memory-surface tab has expanded description mentioning memory_entries
      - neither tab is removed
  test_end_to_end (T6)
      - no stuck Loading text in key analytics tabs
      - fake cost gate: banned substrings absent from dashboard.html
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
DASHBOARD_HTML = REPO_ROOT / "projections/frontend/dashboard.html"
INSIGHTS_PY = REPO_ROOT / "projections/api/routes/insights.py"
ANALYTICS_PY = REPO_ROOT / "projections/api/routes/analytics.py"


# ---------------------------------------------------------------------------
# T1: Anomalies — outcomes and trend chart
# ---------------------------------------------------------------------------


def test_anomalies_outcomes_and_trend_real():
    """T1: session-outcome-flow uses real data; trend chart uses reportable_cost key."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    # The old hardcoded fallback must be gone (it fabricated 1000/750/150/100 counts).
    assert "started: 1000," not in text, (
        "initSessionFlowDiagram must not fall back to hardcoded 'started: 1000' — "
        "the fake fallback data has been removed in T1."
    )
    assert (
        "completed: 750," not in text
    ), "hardcoded 'completed: 750' synthetic fallback must be removed."

    # An honest empty-state path must exist when no real data is available.
    assert "No session data yet" in text, (
        "initSessionFlowDiagram must show an honest empty-state message when total === 0 "
        "instead of fabricated counts."
    )

    # The 4-bucket diagram must distinguish Timeout from Other/Unknown.
    assert "Other/Unknown" in text, (
        "Session-outcome-flow must render an 'Other/Unknown' bucket that is separate from "
        "'Timeout' — previously unknown/in_progress were merged into the Timeout bucket, "
        "making it appear all unresolved sessions had timed out."
    )

    # Timeout box must still exist (real timeout outcome).
    assert "Timeout" in text, "A 'Timeout' outcome box must still be present in the SVG."

    # Trend chart must use 'reportable_cost', not the incorrect 'cost' key.
    assert "reportable_cost" in text, (
        "initTrendAnalysisChart must use 'reportable_cost' as the metric key — "
        "the route returns data.trends['reportable_cost'], not data.trends['cost']."
    )
    # The old wrong key must not appear as a bare metric in the array.
    assert (
        "{ key: 'cost'" not in text
    ), "The old wrong key name 'cost' must be replaced by 'reportable_cost' in metricDefs."

    # Backend fix: unknown/in_progress must NOT be merged into timeout bucket.
    analytics_text = ANALYTICS_PY.read_text(encoding="utf-8")
    assert '"other": outcome_map.get("unknown", 0)' in analytics_text, (
        "analytics.py get_performance must return an 'other' bucket for unknown/in_progress — "
        "not merge them into timeout (that was the root cause of all-timeout display)."
    )
    assert (
        '+ outcome_map.get("unknown", 0)\n            + outcome_map.get("in_progress", 0),'
        not in analytics_text
    ), "The old merge of unknown/in_progress into timeout must be removed from analytics.py."


# ---------------------------------------------------------------------------
# T2: Learning — honest empty-state
# ---------------------------------------------------------------------------


def test_learning_charts_render_or_emptystate():
    """T2: Learning tab shows honest empty-state, not flat-zero chart lines."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    # The old implementation built fake zero-series and passed them to Chart.js.
    # The charts rendered as flat lines at 0 — not blank, not honest, but confusing.
    # The fix replaces this with an explicit empty-state overlay message.
    assert "ds-empty-state-overlay" in text, (
        "initLearningTab must apply a 'ds-empty-state-overlay' class to each chart canvas "
        "parent when there is no data — replacing the old zero-line charts."
    )

    # The old zero-series data builder must no longer pass zero data into chart functions.
    # We check that initLearningTab no longer calls buildLearningEmptyState to feed charts.
    learning_tab_start = text.find("async function initLearningTab()")
    learning_tab_end = text.find("\n        async function ", learning_tab_start + 1)
    if learning_tab_end == -1:
        learning_tab_end = text.find("\n        function ", learning_tab_start + 1)
    learning_tab_body = text[learning_tab_start:learning_tab_end]

    assert "initCacheHitRateChart(learningData" not in learning_tab_body, (
        "initLearningTab must not call initCacheHitRateChart with zero-filled learningData — "
        "that caused the chart to render as a flat-zero line instead of an honest empty-state."
    )

    # The honest empty-state text must be present.
    assert "No data yet" in text or "No learning_event_records" in text, (
        "Learning tab must show an honest empty-state message (e.g. 'No data yet') "
        "when learning_event_records is empty."
    )

    # Summary stats must show 0 rather than '--'.
    assert (
        "learning-cache-hit-rate').textContent = '0%'" in text
    ), "Learning summary stats must show '0%' on empty state, not leave '--'."


# ---------------------------------------------------------------------------
# T3: Adaptation — honest empty-state with 0 counts
# ---------------------------------------------------------------------------


def test_adaptation_renders_or_emptystate():
    """T3: Adaptation tab summary shows 0 on error/empty, not --."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    # Helper function that sets all stats to '0' must be present.
    assert "_setAdaptationZeros" in text, (
        "loadAdaptationSummary must have a _setAdaptationZeros() helper that sets all "
        "stat elements to '0' — previously errors were swallowed silently, leaving '--'."
    )

    # On fetch error, _setAdaptationZeros must be called.
    assert "catch (e) { _setAdaptationZeros(); }" in text, (
        "loadAdaptationSummary catch block must call _setAdaptationZeros() so that "
        "when ds_user_extensions table is missing, counts show 0 not --."
    )

    # The adaptation tab content must still exist (not removed).
    assert (
        '<div id="adaptation" class="tab-content">' in text
    ), "The adaptation tab-content div must still be present."

    # Honest empty-states in the panels themselves already existed (no fabricated data).
    assert (
        "No personalization changes yet" in text
    ), "Adaptation panel 1 must retain its honest empty-state message."
    assert (
        "No patterns noticed yet" in text
    ), "Adaptation panel 2 must retain its honest empty-state message."


# ---------------------------------------------------------------------------
# T4: Token attribution breakouts
# ---------------------------------------------------------------------------


def test_token_attribution_breakouts_present():
    """T4: Token attribution breakout tables and JS wiring are present."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    # JS function must be present.
    assert (
        "async function loadAttributionBreakouts()" in text
    ), "loadAttributionBreakouts() JS function must be added to dashboard.html."

    # Route must be called.
    assert (
        "/api/v1/insights/attribution-breakouts" in text
    ), "loadAttributionBreakouts must call /api/v1/insights/attribution-breakouts."

    # DOM table bodies for each dimension.
    for dim_id in [
        "attr-breakout-project",
        "attr-breakout-milestone",
        "attr-breakout-task",
        "attr-breakout-skill",
        "attr-breakout-agent",
    ]:
        assert (
            f'id="{dim_id}"' in text
        ), f"Token Attribution tab must contain a table body with id='{dim_id}'."

    # Function must be wired on tab navigation.
    assert (
        "loadAttributionBreakouts()" in text
    ), "loadAttributionBreakouts() must be called when the attribution-coverage tab opens."

    # Backend route must exist.
    insights_text = INSIGHTS_PY.read_text(encoding="utf-8")
    assert (
        "/attribution-breakouts" in insights_text
    ), "GET /attribution-breakouts route must be defined in projections/api/routes/insights.py."
    assert (
        "by_project" in insights_text
    ), "attribution-breakouts route must return a 'by_project' field."
    assert (
        "by_milestone" in insights_text
    ), "attribution-breakouts route must return a 'by_milestone' field."
    assert "by_task" in insights_text, "attribution-breakouts route must return a 'by_task' field."
    assert (
        "by_skill" in insights_text
    ), "attribution-breakouts route must return a 'by_skill' field."
    assert (
        "by_agent" in insights_text
    ), "attribution-breakouts route must return a 'by_agent' field."

    # Empty-state must be handled (data_status check).
    assert (
        "data_status" in insights_text
    ), "attribution-breakouts route must return a data_status field for empty-state detection."


# ---------------------------------------------------------------------------
# T5: Config and Memory-Surface descriptions
# ---------------------------------------------------------------------------


def test_config_and_memory_explain_or_removed():
    """T5: Config and Memory-Surface tabs have clear operator descriptions; neither is removed."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    # Config tab must still exist.
    assert (
        '<div id="config" class="tab-content">' in text
    ), "Config tab must not be removed — operator needs visibility into ds_config keys."

    # Config description must explain what ds_config is.
    # Use the next <div id= as the section boundary (avoids false short match on the
    # opening tag's own class="tab-content" attribute).
    config_start = text.find('<div id="config" class="tab-content">')
    config_end = text.find("<div id=", config_start + 50)
    config_section = text[config_start:config_end]

    assert (
        "ds_config" in config_section
    ), "Config tab description must mention 'ds_config' so operators know the data source."
    assert (
        "resolution order" in config_section.lower() or "Resolution order" in config_section
    ), "Config tab must explain resolution order (env var > ds_config row > default)."

    # Memory-Surface tab must still exist.
    assert (
        '<div id="memory-surface" class="tab-content">' in text
    ), "Memory-Surface tab must not be removed."

    # Memory-Surface description must explain what it shows.
    mem_start = text.find('<div id="memory-surface" class="tab-content">')
    mem_end = text.find("<div id=", mem_start + 50)
    mem_section = text[mem_start:mem_end]

    assert (
        "memory_entries" in mem_section
    ), "Memory-Surface tab description must mention 'memory_entries' table."
    assert (
        "on-context-inject" in mem_section
    ), "Memory-Surface tab must explain the on-context-inject hook mechanism."
    assert "honest empty state" in mem_section or "honest" in mem_section, (
        "Memory-Surface tab must clarify that total_entries=0 is an honest empty state, "
        "not a display error."
    )


# ---------------------------------------------------------------------------
# T6: End-to-end regression checks
# ---------------------------------------------------------------------------


def test_end_to_end():
    """T6: No stuck Loading text in analytics tabs; fake-cost strings absent."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    # --- Fake cost gate (mirrors test_ai_usage_fake_cost_regression_gate) ---
    banned = [
        "_estimate_cost",
        "PRICING =",
        "input_tokens * 0.003",
        "output_tokens * 0.015",
        "$0.00/session",
        "Estimated cost",
        "Estimated USD",
    ]
    for substring in banned:
        assert (
            substring not in text
        ), f"FAKE-COST GATE: banned substring '{substring}' must not appear in dashboard.html."

    # --- No stuck Loading text in the analytics tab init paths ---
    # Check the initLearningTab body does not leave the insights div in Loading state.
    learning_start = text.find("async function initLearningTab()")
    learning_end = text.find("\n        async function ", learning_start + 1)
    if learning_end == -1:
        learning_end = text.find("\n        function ", learning_start + 1)
    learning_body = text[learning_start:learning_end]
    assert "Loading learning insights" not in learning_body, (
        "initLearningTab must not leave 'Loading learning insights...' in the insights panel — "
        "it must call updateLearningInsights() with an honest empty-state message."
    )

    # --- Adaptation tab has the 4 required stat element ids ---
    for el_id in [
        "ad-active-count",
        "ad-experimental-count",
        "ad-signals-total",
        "ad-pending-review",
    ]:
        assert f'id="{el_id}"' in text, f"Adaptation tab must contain stat element id='{el_id}'."

    # --- Attribution coverage tab has the breakout section ---
    assert (
        "Token Spend Breakouts" in text
    ), "Token Attribution tab must contain the 'Token Spend Breakouts' section heading (T4)."

    # --- Session flow diagram has honest empty-state path ---
    assert (
        "No session data yet" in text
    ), "initSessionFlowDiagram must have an honest empty-state text path when total === 0."

    # --- Trend chart uses sessions-actual and sessions-trend series ---
    # 'sessions' key must be in metricDefs
    assert "key: 'sessions'" in text, (
        "Trend chart metricDefs must include the 'sessions' key so sessions-actual and "
        "sessions-trend series are plotted."
    )

    # --- analytics.py backend: _empty_performance includes 'other' key ---
    analytics_text = ANALYTICS_PY.read_text(encoding="utf-8")
    assert (
        '"other": 0' in analytics_text
    ), "_empty_performance in analytics.py must include an 'other' key in session_flow."
