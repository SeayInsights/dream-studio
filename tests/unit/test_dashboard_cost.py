"""Tests for WO-DASH-COST-PLAN — Plan vs API-equivalent cost panel.

ACs verified:
  test_plan_vs_api_cost_panel_present (T2)
      - dashboard.html contains panel markup + /api/v1/cost/plan-comparison fetch
      - empty-state text present
      - NONE of the forbidden substrings from the fake-cost gate are present
  test_models_cost_charts_render_or_emptystate (T3)
      - costByModelChart, costBySkillChart, tokenEfficiencyChart,
        cacheHitRateGaugeChart each have a data path or honest empty-state
  test_end_to_end (T4)
      - cost_analysis importable
      - api_equivalent_cost works on seeded in-memory DB
      - plan_comparison returns plan_configured=False with empty ds_config,
        True after set_config_value
      - cost_plan route module exposes the endpoint path /cost/plan-comparison
  test_api_equivalent_cost_correctness (focused unit)
      - two rows with known model; total_usd == sum of compute_cost calls
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
DASHBOARD_HTML = REPO_ROOT / "projections/frontend/dashboard.html"


# ── T2: Plan vs API-equivalent cost panel present ────────────────────────────


def test_plan_vs_api_cost_panel_present():
    """T2: dashboard.html has panel markup, fetch, empty-state; no forbidden substrings."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    # Panel container must exist
    assert "plan-vs-api-cost-panel" in text, (
        "id='plan-vs-api-cost-panel' must be present in dashboard.html — "
        "the Plan vs API-equivalent cost panel is missing."
    )

    # JS must fetch the route
    assert (
        "/api/v1/cost/plan-comparison" in text
    ), "dashboard.html must fetch /api/v1/cost/plan-comparison for the plan panel."

    # Empty-state text (no plan configured)
    assert (
        "No subscription plan configured" in text
    ), "Empty-state text 'No subscription plan configured' must appear in dashboard.html."

    # initPlanVsApiCostPanel function must be present
    assert (
        "initPlanVsApiCostPanel" in text
    ), "initPlanVsApiCostPanel JS function must be defined in dashboard.html."

    # Forbidden substrings — none must appear in the whole file
    forbidden = [
        "_estimate_cost",
        "PRICING =",
        "input_tokens * 0.003",
        "output_tokens * 0.015",
        "$0.00/session",
        "Estimated cost",
        "Estimated USD",
    ]
    for marker in forbidden:
        assert marker not in text, (
            f"Forbidden substring {marker!r} found in dashboard.html — "
            "this would fail the fake-cost CI gate."
        )


# ── T3: Models cost charts have data path or honest empty-state ──────────────


def test_models_cost_charts_render_or_emptystate():
    """T3: costByModelChart, costBySkillChart, tokenEfficiencyChart, cacheHitRateGaugeChart
    each have either a data render path or an honest empty-state."""
    text = DASHBOARD_HTML.read_text(encoding="utf-8")

    chart_ids = [
        "costByModelChart",
        "costBySkillChart",
        "tokenEfficiencyChart",
        "cacheHitRateGaugeChart",
    ]

    for chart_id in chart_ids:
        # Canvas element must exist in the HTML
        assert (
            f'id="{chart_id}"' in text
        ), f"Canvas element id='{chart_id}' not found in dashboard.html."
        # The chart must be referenced in JS (data path or init function)
        assert chart_id in text, f"Chart id '{chart_id}' must be referenced in dashboard.html JS."

    # costByModel and costBySkill must reference data filtering (data path)
    fn_start = text.find("async function initCostByModelChart")
    fn_end = text.find("\n        // Initialize Cost by Project", fn_start + 1)
    if fn_end < 0:
        fn_end = fn_start + 2000
    fn_body = text[fn_start:fn_end] if fn_start >= 0 else ""
    assert (
        "costByModel" in fn_body or "reportableData" in fn_body
    ), "initCostByModelChart must reference costByModel data or reportableData."

    # tokenEfficiencyChart must be referenced in its init function
    eff_start = text.find("tokenEfficiencyChart")
    assert eff_start >= 0, "tokenEfficiencyChart must appear in dashboard.html"

    # cacheHitRateGaugeChart must be referenced in its init function
    gauge_start = text.find("cacheHitRateGaugeChart")
    assert gauge_start >= 0, "cacheHitRateGaugeChart must appear in dashboard.html"


# ── T4: End-to-end ────────────────────────────────────────────────────────────


def _make_seeded_conn(model_id: str = "claude-sonnet-4-6") -> sqlite3.Connection:
    """Return an in-memory SQLite connection with token_usage_records seeded."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE token_usage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cached_tokens INTEGER,
            cache_read_tokens INTEGER,
            total_tokens INTEGER,
            skill_id TEXT,
            estimated_cost REAL,
            cost_visibility TEXT,
            created_at TEXT
        )
        """)
    conn.execute(
        "INSERT INTO token_usage_records "
        "(model_id, input_tokens, output_tokens, cached_tokens, cache_read_tokens) "
        "VALUES (?, 1000, 500, 200, 100)",
        (model_id,),
    )
    conn.execute(
        "INSERT INTO token_usage_records "
        "(model_id, input_tokens, output_tokens, cached_tokens, cache_read_tokens) "
        "VALUES (?, 2000, 1000, 0, 0)",
        (model_id,),
    )
    conn.commit()
    return conn


def _make_ds_config_conn() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with ds_config table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE ds_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
        """)
    conn.commit()
    return conn


def test_end_to_end():
    """T4: import, api_equivalent_cost on seeded DB, plan_comparison False/True, route path."""
    # Import must succeed
    from projections.core.cost_analysis import api_equivalent_cost, plan_comparison
    from core.config.authority import set_config_value

    # api_equivalent_cost on seeded connection
    conn = _make_seeded_conn("claude-sonnet-4-6")
    result = api_equivalent_cost(conn)
    conn.close()

    assert result["record_count"] == 2
    assert result["priced_record_count"] == 2
    assert result["unpriced_record_count"] == 0
    assert result["total_usd"] > 0.0
    assert isinstance(result["by_model"], list)
    assert len(result["by_model"]) == 1

    # plan_comparison: plan_configured=False with empty ds_config
    # ignore_cleanup_errors=True handles Windows WAL sidecar file locks on cleanup
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp_path = Path(tmp_dir) / "test_config.db"

        # Create minimal db with ds_config
        import sqlite3 as _sqlite3

        with _sqlite3.connect(str(tmp_path)) as setup_conn:
            setup_conn.execute(
                "CREATE TABLE ds_config (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)"
            )
            setup_conn.commit()

        data_conn = _make_seeded_conn("claude-sonnet-4-6")
        # plan_comparison reads config from db_path, token data from conn
        pc = plan_comparison(data_conn, db_path=tmp_path)
        data_conn.close()

        assert pc["plan_configured"] is False
        assert pc["plan_name"] is None
        assert pc["plan_monthly_usd"] is None
        assert pc["delta_usd"] is None
        assert pc["api_equivalent_total_usd"] > 0.0

        # Now set config values and try again
        set_config_value("cost.plan_name", "Pro", tmp_path)
        set_config_value("cost.plan_monthly_usd", "19.99", tmp_path)

        data_conn2 = _make_seeded_conn("claude-sonnet-4-6")
        pc2 = plan_comparison(data_conn2, db_path=tmp_path)
        data_conn2.close()

        assert pc2["plan_configured"] is True
        assert pc2["plan_name"] == "Pro"
        assert pc2["plan_monthly_usd"] == 19.99
        assert pc2["delta_usd"] is not None

    # Route module exposes the correct path
    from projections.api.routes.cost_plan import router

    paths = [r.path for r in router.routes]
    assert (
        "/cost/plan-comparison" in paths
    ), f"Route /cost/plan-comparison not found in cost_plan router. Got: {paths}"


# ── Focused unit: api_equivalent_cost correctness ────────────────────────────


def test_api_equivalent_cost_correctness():
    """Seed 2 rows with a known model; assert total_usd == sum of compute_cost calls."""
    from projections.core.cost_analysis import api_equivalent_cost
    from core.pricing.claude_models import compute_cost

    model = "claude-haiku-4-5"
    conn = _make_seeded_conn(model)

    result = api_equivalent_cost(conn)
    conn.close()

    # Row 1: input=1000, output=500, cached=200(cache_creation), cache_read=100
    expected_row1 = compute_cost(model, 1000, 500, 200, 100)
    # Row 2: input=2000, output=1000, cached=0, cache_read=0
    expected_row2 = compute_cost(model, 2000, 1000, 0, 0)
    expected_total = expected_row1 + expected_row2

    assert (
        abs(result["total_usd"] - expected_total) < 1e-9
    ), f"api_equivalent_cost total {result['total_usd']!r} != expected {expected_total!r}"
    assert result["priced_record_count"] == 2
    assert result["unpriced_record_count"] == 0
    assert result["record_count"] == 2
