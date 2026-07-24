"""Intelligence API - Tier 1 critical issues + Tier 2 health/wins + /overview.

WO-GF-API-ROUTES: split out of intelligence.py. Provides tier-based
intelligence for the dashboard:
- Tier 1: Critical issues needing immediate attention
- Tier 2: Health snapshot + positive signals (wins)

All intelligence rules are data-driven with explicit thresholds.
"""

from __future__ import annotations

from fastapi import HTTPException
from typing import Any
import sqlite3
from datetime import datetime, UTC

from core.config.database import get_connection
from core.analytics.duckdb_store import connect_analytics
from projections.api.safety import activity_log_filter_clause
from projections.core.collectors.authority_sources import skill_usage_sql, token_usage_sql

from .intelligence_router import router

# ── Tier 1: Critical Issues ──────────────────────────────────────────────────


def get_cost_alerts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Detect high token usage patterns that need attention.

    Alert triggered when: repo uses > 50M tokens in 30 days
    """
    cursor = conn.cursor()
    token_sql = token_usage_sql(conn)
    if token_sql is None:
        return []

    # Monthly budget assumption: 100M tokens (can be configured)
    MONTHLY_BUDGET = 100_000_000
    HIGH_USAGE_THRESHOLD = 50_000_000  # 50M tokens

    query = f"""
        SELECT
            'Unknown' as repo_path,  -- Token log doesn't track repo
            SUM(input_tokens + output_tokens) as total_tokens,
            COUNT(DISTINCT session_id) as sessions,
            MIN(recorded_at) as first_seen,
            MAX(recorded_at) as last_seen
        FROM ({token_sql}) token_usage
        WHERE recorded_at > datetime('now', '-30 days')
        GROUP BY repo_path
        HAVING total_tokens > ?
        ORDER BY total_tokens DESC
        LIMIT 5
    """

    rows = cursor.execute(query, (HIGH_USAGE_THRESHOLD,)).fetchall()

    alerts = []
    for row in rows:
        tokens = row["total_tokens"]
        sessions = row["sessions"]
        pct_budget = (tokens / MONTHLY_BUDGET) * 100
        # Calculate days since first seen to estimate burn rate
        first = datetime.fromisoformat(row["first_seen"].replace("Z", "+00:00"))
        last = datetime.fromisoformat(row["last_seen"].replace("Z", "+00:00"))
        days_active = max(1, (last - first).days)
        tokens_per_day = tokens / days_active
        days_to_budget = (MONTHLY_BUDGET - tokens) / tokens_per_day if tokens_per_day > 0 else 999

        alerts.append(
            {
                "severity": "high" if pct_budget > 60 else "medium",
                "category": "cost",
                "title": "High token usage detected",
                "metric": f"{tokens/1e6:.1f}M tokens in 30 days",
                "context": f"{pct_budget:.0f}% of monthly budget ({sessions} sessions)",
                "action": "Review token usage patterns and enable caching",
                "action_link": "/dashboard_old#models",  # Link to detailed cost tab
                "impact": f"Could hit budget cap in {days_to_budget:.0f} days at current rate",
            }
        )

    return alerts


def get_reliability_alerts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Detect skills with high failure rates.

    Alert triggered when: failure_rate > 20% AND total_runs >= 5 in past 7 days
    """
    cursor = conn.cursor()
    skill_sql = skill_usage_sql(conn)
    if skill_sql is None:
        return []

    query = f"""
        SELECT
            skill_name,
            COUNT(*) as total_runs,
            SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures,
            CAST(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as failure_rate,
            MAX(invoked_at) as last_failure
        FROM ({skill_sql}) skill_usage
        WHERE invoked_at > datetime('now', '-7 days')
        GROUP BY skill_name
        HAVING failure_rate > 0.2 AND total_runs >= 5
        ORDER BY failure_rate DESC, total_runs DESC
        LIMIT 5
    """

    rows = cursor.execute(query).fetchall()

    alerts = []
    for row in rows:
        skill = row["skill_name"]
        total = row["total_runs"]
        failures = row["failures"]
        rate = row["failure_rate"]

        alerts.append(
            {
                "severity": "high" if rate > 0.5 else "medium",
                "category": "reliability",
                "title": f"Skill failures: {skill}",
                "metric": f"{rate*100:.0f}% failure rate ({failures}/{total} runs)",
                "context": "Failing consistently over past 7 days",
                "action": f"Debug {skill}: check error logs and recent changes",
                "action_link": "/dashboard_old#skills",
                "impact": "Blocking workflows, causing user friction and delays",
            }
        )

    return alerts


def get_performance_alerts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Detect slow hooks impacting developer experience.

    Alert triggered when: avg_duration > 10s in past 7 days.
    Reads hook_executions from DuckDB (derived from canonical events via events_fact).
    The conn parameter is unused; kept for API compatibility with get_critical_issues().
    """
    duck_conn = None
    try:
        duck_conn = connect_analytics(read_only=True)
        query = """
            SELECT
                hook_name,
                AVG(duration_ms) as avg_duration,
                MAX(duration_ms) as max_duration,
                COUNT(*) as execution_count
            FROM hook_executions
            WHERE duration_ms IS NOT NULL
              AND started_at > (now() - INTERVAL '7 days')::VARCHAR
            GROUP BY hook_name
            HAVING avg_duration > 10000
            ORDER BY avg_duration DESC
            LIMIT 3
        """

        rows = duck_conn.execute(query).fetchall()

        alerts = []
        for row in rows:
            hook = row[0]
            avg_ms = row[1]
            max_ms = row[2]
            count = row[3]

            alerts.append(
                {
                    "severity": "medium",
                    "category": "performance",
                    "title": f"Slow hook: {hook}",
                    "metric": f"{avg_ms/1000:.1f}s average (max: {max_ms/1000:.1f}s)",
                    "context": f"{count} executions in past week",
                    "action": f"Optimize {hook}: make async, reduce I/O, or add caching",
                    "action_link": "/dashboard_old#hooks",
                    "impact": "Slowing down developer workflows and reducing productivity",
                }
            )

        return alerts
    except Exception:
        # Includes AnalyticsStoreMissingError (store not built yet) — no alerts.
        return []
    finally:
        if duck_conn is not None:
            duck_conn.close()


def get_critical_issues() -> list[dict[str, Any]]:
    """Get all critical issues sorted by priority.

    Returns list of issues needing immediate attention.
    Sorted by: critical > high > medium severity, then by impact.
    """
    conn = get_connection()
    try:
        issues = []

        # Collect all types of alerts
        issues.extend(get_cost_alerts(conn))
        issues.extend(get_reliability_alerts(conn))
        issues.extend(get_performance_alerts(conn))

        # Sort by severity (critical > high > medium)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        issues.sort(key=lambda x: severity_order.get(x["severity"], 99))

        # Limit to top 5 issues
        return issues[:5]

    finally:
        conn.close()


# ── Tier 2: Health Snapshot ──────────────────────────────────────────────────


def get_health_snapshot() -> dict[str, Any]:
    """Get overall system health across 4 dimensions.

    Returns dict with quality, cost, performance, and activity scores.
    Each score includes: value, status (ok/warning/critical), display string, color.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # 1. Quality Score (skill success rate in past 7 days)
        skill_sql = skill_usage_sql(conn)
        row = cursor.execute(f"""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success
                FROM ({skill_sql}) skill_usage
                WHERE invoked_at > datetime('now', '-7 days')
            """).fetchone() if skill_sql is not None else None
        if row and row["total"] > 0:
            quality_score = row["success"] / row["total"]
        else:
            quality_score = 1.0  # No data = assume healthy

        quality_status = (
            "ok" if quality_score >= 0.95 else "warning" if quality_score >= 0.80 else "critical"
        )

        # 2. Cost Status (token usage in past 30 days)
        token_sql = token_usage_sql(conn)
        row = cursor.execute(f"""
                SELECT SUM(input_tokens + output_tokens) as total
                FROM ({token_sql}) token_usage
                WHERE recorded_at > datetime('now', '-30 days')
            """).fetchone() if token_sql is not None else None
        tokens_30d = row["total"] if row and row["total"] else 0
        cost_status = "high" if tokens_30d > 100_000_000 else "ok"

        # 3. Performance (avg hook duration in past 7 days) — reads DuckDB hook_executions view
        duck_conn = None
        try:
            duck_conn = connect_analytics(read_only=True)
            hook_row = duck_conn.execute("""
                SELECT AVG(duration_ms) as avg_duration
                FROM hook_executions
                WHERE duration_ms IS NOT NULL
                  AND started_at > (now() - INTERVAL '7 days')::VARCHAR
            """).fetchone()
            avg_duration = hook_row[0] if hook_row and hook_row[0] else 0
        except Exception:
            # Includes AnalyticsStoreMissingError (store not built yet).
            avg_duration = 0
        finally:
            if duck_conn is not None:
                duck_conn.close()
        perf_status = "slow" if avg_duration > 5000 else "ok"

        # 4. Activity Level (events in past 7 days, excluding private)
        _afilter = activity_log_filter_clause("ce", col="event_type")
        query = f"""
            SELECT COUNT(*) as event_count
            FROM canonical_events ce
            WHERE ce.timestamp > datetime('now', '-7 days')
            {_afilter}
        """
        row = cursor.execute(query).fetchone()
        recent_activity = row["event_count"] if row else 0
        activity_status = "active" if recent_activity > 50 else "quiet"

        return {
            "quality": {
                "score": quality_score,
                "status": quality_status,
                "display": f"{quality_score*100:.0f}%",
                "color": (
                    "green"
                    if quality_status == "ok"
                    else "yellow" if quality_status == "warning" else "red"
                ),
            },
            "cost": {
                "status": cost_status,
                "display": f"{tokens_30d/1e6:.1f}M tokens/mo",
                "color": "yellow" if cost_status == "high" else "green",
            },
            "performance": {
                "status": perf_status,
                "display": f"{avg_duration/1000:.1f}s avg",
                "color": "yellow" if perf_status == "slow" else "green",
            },
            "activity": {
                "status": activity_status,
                "display": f"{recent_activity} events/week",
                "color": "green" if activity_status == "active" else "yellow",
            },
        }

    finally:
        conn.close()


# ── Tier 2: What's Working (Wins) ────────────────────────────────────────────


def get_whats_working() -> list[dict[str, Any]]:
    """Get positive signals - what's going well.

    Returns list of wins to reinforce good patterns.
    Shows only meaningful wins (not trivial positives).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        wins = []

        # Win 1: Skills with 100% success rate (minimum 10 runs)
        skill_sql = skill_usage_sql(conn)
        rows = cursor.execute(f"""
                SELECT
                    skill_name,
                    COUNT(*) as runs,
                    CAST(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as success_rate
                FROM ({skill_sql}) skill_usage
                WHERE invoked_at > datetime('now', '-7 days')
                GROUP BY skill_name
                HAVING runs >= 10 AND success_rate = 1.0
                ORDER BY runs DESC
                LIMIT 3
            """).fetchall() if skill_sql is not None else []
        for row in rows:
            wins.append(
                {
                    "category": "quality",
                    "message": f"{row['skill_name']}: 100% success rate ({row['runs']} runs)",
                    "icon": "✅",
                }
            )

        # Win 2: Decision tracking active — decision.recorded canonical events
        # replaced decision_log rows (T4, WO-DBA-EVAL-DECISION).
        query = """
            SELECT COUNT(*) as decisions
            FROM business_canonical_events
            WHERE event_type = 'decision.recorded'
              AND event_timestamp > datetime('now', '-7 days')
        """
        row = cursor.execute(query).fetchone()
        if row and row["decisions"] > 0:
            wins.append(
                {
                    "category": "governance",
                    "message": f"Decision tracking active: {row['decisions']} decisions logged this week",
                    "icon": "📋",
                }
            )

        # Win 3: Hook reliability (if very high) — reads DuckDB hook_executions view
        duck_conn_wins = None
        try:
            duck_conn_wins = connect_analytics(read_only=True)
            hook_row = duck_conn_wins.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success
                FROM hook_executions
                WHERE started_at > (now() - INTERVAL '7 days')::VARCHAR
            """).fetchone()
            if hook_row and hook_row[0] > 50:
                success_rate = hook_row[1] / hook_row[0]
                if success_rate >= 0.99:
                    wins.append(
                        {
                            "category": "reliability",
                            "message": f"Hook execution: {success_rate*100:.1f}% success rate ({hook_row[0]} runs)",
                            "icon": "🎯",
                        }
                    )
        except Exception:
            # Includes AnalyticsStoreMissingError (store not built yet) — skip this win.
            pass
        finally:
            if duck_conn_wins is not None:
                duck_conn_wins.close()

        # Win 4: Active event tracking (excluding private)
        _af = activity_log_filter_clause("ce", col="event_type")
        query = f"""
            SELECT COUNT(*) as events
            FROM canonical_events ce
            WHERE ce.timestamp > datetime('now', '-7 days')
            {_af}
        """
        row = cursor.execute(query).fetchone()
        if row and row["events"] > 100:
            wins.append(
                {
                    "category": "observability",
                    "message": f"Event tracking active: {row['events']} events captured this week",
                    "icon": "📊",
                }
            )

        return wins[:5]  # Limit to top 5 wins

    finally:
        conn.close()


# ── API Endpoint ──────────────────────────────────────────────────────────────


@router.get("/overview")
async def get_overview() -> dict[str, Any]:
    """Get complete dashboard intelligence in one call.

    Returns all three tiers:
    - tier1_critical: List of issues needing attention
    - tier2_health: Health snapshot with 4 scores
    - tier2_wins: Positive signals (what's working)

    This is the single endpoint powering the entire dashboard V2.
    """
    try:
        return {
            "tier1_critical": get_critical_issues(),
            "tier2_health": get_health_snapshot(),
            "tier2_wins": get_whats_working(),
            "last_updated": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate intelligence overview: {str(e)}"
        )
