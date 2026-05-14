"""SQLite/query performance baseline helpers for telemetry growth."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def measure_sqlite_query_baseline(
    db_path: str | Path,
    queries: Mapping[str, str],
    *,
    warn_ms: float = 50.0,
) -> dict[str, Any]:
    """Measure supplied read-only SQLite queries against an explicit DB path."""

    path = Path(db_path)
    results: dict[str, Any] = {}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        for name, query in queries.items():
            started = time.perf_counter()
            rows = conn.execute(query).fetchall()
            elapsed_ms = (time.perf_counter() - started) * 1000
            results[name] = {
                "elapsed_ms": elapsed_ms,
                "row_count": len(rows),
                "status": "warn" if elapsed_ms > warn_ms else "ok",
            }
    return {
        "derived_view": True,
        "primary_authority": False,
        "db_path": str(path),
        "read_only": True,
        "warn_ms": warn_ms,
        "queries": results,
        "recommendations": recommend_performance_actions(results, warn_ms=warn_ms),
    }


def recommend_performance_actions(
    query_results: Mapping[str, Mapping[str, Any]], *, warn_ms: float = 50.0
) -> list[str]:
    """Recommend next performance actions from measured query results."""

    recommendations: list[str] = []
    slow = [
        name
        for name, result in query_results.items()
        if float(result.get("elapsed_ms", 0.0)) > warn_ms
    ]
    high_rows = [
        name for name, result in query_results.items() if int(result.get("row_count", 0)) > 1000
    ]
    if slow:
        recommendations.append(f"inspect_query_plan:{','.join(sorted(slow))}")
        recommendations.append("consider_index_or_projection_optimization")
    if high_rows:
        recommendations.append(f"consider_pagination_or_rollup:{','.join(sorted(high_rows))}")
        recommendations.append("consider_retention_policy_design")
    if not recommendations:
        recommendations.append("baseline_ok")
    return recommendations


def validate_performance_baseline(baseline: Mapping[str, Any]) -> list[str]:
    """Return safety/completeness violations for a performance baseline."""

    issues: list[str] = []
    if not baseline.get("read_only"):
        issues.append("performance_baseline_must_be_read_only")
    if baseline.get("primary_authority"):
        issues.append("performance_baseline_must_not_be_primary_authority")
    if not baseline.get("queries"):
        issues.append("query_results_required")
    return issues
