from __future__ import annotations

import sqlite3

from core.telemetry.performance_baseline import (
    measure_sqlite_query_baseline,
    recommend_performance_actions,
    validate_performance_baseline,
)


def test_performance_baseline_measures_temp_sqlite_read_only_queries(tmp_path) -> None:
    db_path = tmp_path / "baseline.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE events(id INTEGER PRIMARY KEY, component TEXT)")
        conn.executemany("INSERT INTO events(component) VALUES (?)", [("hook",), ("tool",)])

    baseline = measure_sqlite_query_baseline(
        db_path,
        {"events": "SELECT * FROM events ORDER BY id"},
        warn_ms=1000,
    )

    assert baseline["derived_view"] is True
    assert baseline["primary_authority"] is False
    assert baseline["read_only"] is True
    assert baseline["queries"]["events"]["row_count"] == 2
    assert baseline["queries"]["events"]["status"] == "ok"
    assert validate_performance_baseline(baseline) == []


def test_performance_recommendations_flag_slow_or_large_queries() -> None:
    recommendations = recommend_performance_actions(
        {
            "slow": {"elapsed_ms": 101.0, "row_count": 2},
            "large": {"elapsed_ms": 1.0, "row_count": 2000},
        },
        warn_ms=50,
    )

    assert "inspect_query_plan:slow" in recommendations
    assert "consider_index_or_projection_optimization" in recommendations
    assert "consider_pagination_or_rollup:large" in recommendations
    assert "consider_retention_policy_design" in recommendations


def test_performance_baseline_validator_rejects_unsafe_shapes() -> None:
    issues = validate_performance_baseline(
        {"read_only": False, "primary_authority": True, "queries": {}}
    )

    assert "performance_baseline_must_be_read_only" in issues
    assert "performance_baseline_must_not_be_primary_authority" in issues
    assert "query_results_required" in issues
