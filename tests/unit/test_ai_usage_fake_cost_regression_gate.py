from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dashboard_runtime_does_not_reintroduce_token_to_dollar_pricing() -> None:
    checked_files = [
        REPO_ROOT / "projections" / "api" / "routes" / "metrics.py",
        REPO_ROOT / "projections" / "api" / "routes" / "analytics.py",
        REPO_ROOT / "projections" / "core" / "collectors" / "token_collector.py",
        REPO_ROOT / "projections" / "frontend" / "dashboard.html",
    ]
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in checked_files
    )

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
        assert marker not in combined


def test_ai_usage_accounting_migration_declares_visibility_categories() -> None:
    """043_ai_usage_accounting.sql was collapsed into 142_lean_baseline.sql by
    WO-SQUASH-BASELINE (5fd84891, 2026-07-04); ai_usage_operational_records
    (and its CHECK-constrained visibility category columns) is still a live
    KEEP table, preserved verbatim in the baseline's CREATE TABLE IF NOT
    EXISTS re-emission."""
    migration = (
        REPO_ROOT / "core" / "event_store" / "migrations" / "142_lean_baseline.sql"
    ).read_text(encoding="utf-8")

    for marker in (
        "subscription_plan",
        "plan_allowance",
        "token_metered",
        "api_metered",
        "credit_metered",
        "enterprise_contract",
        "token_visibility",
        "cost_visibility",
        "usage_source",
        "confidence",
        "ai_usage_operational_records",
    ):
        assert marker in migration
