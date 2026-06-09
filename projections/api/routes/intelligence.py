"""Intelligence API - converts raw metrics to actionable insights.

Provides tier-based intelligence for the dashboard:
- Tier 1: Critical issues needing immediate attention
- Tier 2: Health snapshot + positive signals (wins)
- Tier 3: Detailed metrics (served by existing routes)

All intelligence rules are data-driven with explicit thresholds.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import sqlite3
from datetime import datetime, timezone

from core.config.database import get_connection
from projections.api.safety import activity_log_filter_clause
from projections.core.collectors.authority_sources import skill_usage_sql, token_usage_sql

router = APIRouter()


# ── Tier 1: Critical Issues ──────────────────────────────────────────────────


def get_cost_alerts(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
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
        avg_per_session = tokens / sessions if sessions > 0 else 0

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
                "title": f"High token usage detected",
                "metric": f"{tokens/1e6:.1f}M tokens in 30 days",
                "context": f"{pct_budget:.0f}% of monthly budget ({sessions} sessions)",
                "action": "Review token usage patterns and enable caching",
                "action_link": "/dashboard_old#models",  # Link to detailed cost tab
                "impact": f"Could hit budget cap in {days_to_budget:.0f} days at current rate",
            }
        )

    return alerts


def get_reliability_alerts(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
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
                "action_link": f"/dashboard_old#skills",
                "impact": "Blocking workflows, causing user friction and delays",
            }
        )

    return alerts


def get_performance_alerts(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Detect slow hooks impacting developer experience.

    Alert triggered when: avg_duration > 10s in past 7 days
    """
    cursor = conn.cursor()

    query = """
        SELECT
            hook_name,
            AVG(duration_ms) as avg_duration,
            MAX(duration_ms) as max_duration,
            COUNT(*) as execution_count
        FROM hook_executions
        WHERE duration_ms IS NOT NULL
          AND started_at > datetime('now', '-7 days')
        GROUP BY hook_name
        HAVING avg_duration > 10000
        ORDER BY avg_duration DESC
        LIMIT 3
    """

    rows = cursor.execute(query).fetchall()

    alerts = []
    for row in rows:
        hook = row["hook_name"]
        avg_ms = row["avg_duration"]
        max_ms = row["max_duration"]
        count = row["execution_count"]

        alerts.append(
            {
                "severity": "medium",
                "category": "performance",
                "title": f"Slow hook: {hook}",
                "metric": f"{avg_ms/1000:.1f}s average (max: {max_ms/1000:.1f}s)",
                "context": f"{count} executions in past week",
                "action": f"Optimize {hook}: make async, reduce I/O, or add caching",
                "action_link": f"/dashboard_old#hooks",
                "impact": "Slowing down developer workflows and reducing productivity",
            }
        )

    return alerts


def get_critical_issues() -> List[Dict[str, Any]]:
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


def get_health_snapshot() -> Dict[str, Any]:
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

        # 3. Performance (avg hook duration in past 7 days)
        query = """
            SELECT AVG(duration_ms) as avg_duration
            FROM hook_executions
            WHERE duration_ms IS NOT NULL
              AND started_at > datetime('now', '-7 days')
        """
        row = cursor.execute(query).fetchone()
        avg_duration = row["avg_duration"] if row and row["avg_duration"] else 0
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


def get_whats_working() -> List[Dict[str, Any]]:
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

        # Win 2: Decision tracking active
        query = """
            SELECT COUNT(*) as decisions
            FROM decision_log
            WHERE timestamp > datetime('now', '-7 days')
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

        # Win 3: Hook reliability (if very high)
        query = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success
            FROM hook_executions
            WHERE started_at > datetime('now', '-7 days')
        """
        row = cursor.execute(query).fetchone()
        if row and row["total"] > 50:
            success_rate = row["success"] / row["total"]
            if success_rate >= 0.99:
                wins.append(
                    {
                        "category": "reliability",
                        "message": f"Hook execution: {success_rate*100:.1f}% success rate ({row['total']} runs)",
                        "icon": "🎯",
                    }
                )

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
async def get_overview() -> Dict[str, Any]:
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
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate intelligence overview: {str(e)}"
        )


# ── Token Intelligence ────────────────────────────────────────────────────────


@router.get("/token-intelligence")
async def get_token_intelligence() -> Dict[str, Any]:
    """Get token/cost domain intelligence.

    Returns attention_needed, health metrics, and wins for token usage.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        attention_needed = []
        token_sql = token_usage_sql(conn)
        if token_sql is None:
            return {
                "attention_needed": [],
                "health": {
                    "budget_utilization": {"value": "0%", "status": "ok", "display": "0.0M tokens"},
                    "cost_trend": {"value": "0%", "status": "ok", "display": "vs last month"},
                    "active_sessions": {"value": "0", "status": "ok", "display": "past 7 days"},
                },
                "whats_working": [],
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "source_status": {
                    "classification": "empty by design",
                    "source_tables": ["token_usage_records"],
                },
            }

        # High token usage (top 3)
        query = f"""
            SELECT
                'Unknown' as repo_path,
                SUM(input_tokens + output_tokens) as total_tokens,
                COUNT(DISTINCT session_id) as sessions
            FROM ({token_sql}) token_usage
            WHERE recorded_at > datetime('now', '-30 days')
            GROUP BY repo_path
            HAVING total_tokens > 50000000
            ORDER BY total_tokens DESC
            LIMIT 3
        """
        rows = cursor.execute(query).fetchall()

        for row in rows:
            tokens = row["total_tokens"]
            sessions = row["sessions"]
            attention_needed.append(
                {
                    "severity": "high",
                    "category": "cost",
                    "title": f"High token usage detected",
                    "metric": f"{tokens/1e6:.1f}M tokens in 30 days",
                    "context": f"{sessions} sessions, avg {tokens/sessions/1e3:.1f}K per session",
                    "action": "Review token usage patterns",
                    "action_link": "/dashboard_old#models",
                }
            )

        # Health metrics
        query = f"""
            SELECT
                SUM(input_tokens + output_tokens) as total_30d,
                (SELECT SUM(input_tokens + output_tokens)
                 FROM ({token_sql}) token_usage_prev
                 WHERE recorded_at BETWEEN datetime('now', '-60 days') AND datetime('now', '-30 days')
                ) as total_prev_30d
            FROM ({token_sql}) token_usage
            WHERE recorded_at > datetime('now', '-30 days')
        """
        row = cursor.execute(query).fetchone()
        current = row["total_30d"] if row["total_30d"] else 0
        previous = row["total_prev_30d"] if row["total_prev_30d"] else 1
        trend = ((current - previous) / previous * 100) if previous else 0

        # Count active sessions
        query = f"""
            SELECT COUNT(DISTINCT session_id) as sessions
            FROM ({token_sql}) token_usage
            WHERE recorded_at > datetime('now', '-7 days')
        """
        sessions_row = cursor.execute(query).fetchone()
        active_sessions = sessions_row["sessions"] if sessions_row else 0

        health = {
            "budget_utilization": {
                "value": f"{current/100e6*100:.0f}%",
                "status": "critical" if current > 100e6 else "warning" if current > 80e6 else "ok",
                "display": f"{current/1e6:.1f}M tokens",
            },
            "cost_trend": {
                "value": f"{'↑' if trend > 0 else '↓'} {abs(trend):.0f}%",
                "status": "warning" if abs(trend) > 20 else "ok",
                "display": "vs last month",
            },
            "active_sessions": {
                "value": f"{active_sessions}",
                "status": "ok",
                "display": "past 7 days",
            },
        }

        # What's working (efficient usage)
        wins = []
        query = f"""
            SELECT COUNT(DISTINCT session_id) as efficient_sessions
            FROM ({token_sql}) token_usage
            WHERE recorded_at > datetime('now', '-7 days')
            GROUP BY session_id
            HAVING SUM(input_tokens + output_tokens) < 1000000
        """
        eff_count = len(cursor.execute(query).fetchall())
        if eff_count > 0:
            wins.append(
                {
                    "icon": "✅",
                    "message": f"{eff_count} sessions with efficient token usage (<1M tokens)",
                }
            )

        # Prompt caching wins: surface when cache_read_tokens shows active reuse.
        cache_query = f"""
            SELECT SUM(cache_read_tokens) as total_cache_reads
            FROM ({token_sql}) token_usage
            WHERE recorded_at > datetime('now', '-30 days')
        """
        cache_row = cursor.execute(cache_query).fetchone()
        total_cache_reads = int(cache_row["total_cache_reads"] or 0) if cache_row else 0
        if total_cache_reads > 0:
            wins.append(
                {
                    "icon": "⚡",
                    "message": f"Prompt caching active — {total_cache_reads:,} cache-read tokens saved in 30 days",
                }
            )

        return {
            "attention_needed": attention_needed,
            "health": health,
            "whats_working": wins,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate token intelligence: {str(e)}"
        )
    finally:
        conn.close()


# ── Agent Capabilities ────────────────────────────────────────────────────────


@router.get("/agent-capabilities")
async def get_agent_capabilities() -> Dict[str, Any]:
    """Get skills/agent domain intelligence.

    Returns attention_needed, health metrics, and wins for skills/agents.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        attention_needed = []
        skill_sql = skill_usage_sql(conn)
        if skill_sql is None:
            return {
                "attention_needed": [],
                "health": {
                    "success_rate": {"value": "0%", "status": "ok", "display": "0 total runs"},
                    "avg_duration": {
                        "value": "0.0s",
                        "status": "ok",
                        "display": "average execution",
                    },
                    "active_skills": {"value": "0", "status": "ok", "display": "skills in use"},
                },
                "whats_working": [],
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "source_status": {
                    "classification": "empty by design",
                    "source_tables": ["skill_invocations"],
                },
            }

        # Failing skills (failure rate > 20%, min 5 runs)
        query = f"""
            SELECT
                skill_name,
                COUNT(*) as total,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures,
                CAST(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as rate
            FROM ({skill_sql}) skill_usage
            WHERE invoked_at > datetime('now', '-7 days')
            GROUP BY skill_name
            HAVING rate > 0.2 AND total >= 5
            ORDER BY rate DESC
            LIMIT 3
        """
        rows = cursor.execute(query).fetchall()

        for row in rows:
            skill = row["skill_name"]
            total = row["total"]
            failures = row["failures"]
            rate = row["rate"]
            attention_needed.append(
                {
                    "severity": "high" if rate > 0.5 else "medium",
                    "category": "reliability",
                    "title": f"Skill failures: {skill}",
                    "metric": f"{rate*100:.0f}% failure rate ({failures}/{total} runs)",
                    "context": "Past 7 days",
                    "action": f"Debug {skill} and review error logs",
                    "action_link": "/dashboard_old#skills",
                }
            )

        # Slow skills (>30s average)
        query = f"""
            SELECT
                skill_name,
                AVG(execution_time_s) as avg_time,
                COUNT(*) as runs
            FROM ({skill_sql}) skill_usage
            WHERE invoked_at > datetime('now', '-7 days')
            AND execution_time_s IS NOT NULL
            GROUP BY skill_name
            HAVING avg_time > 30
            ORDER BY avg_time DESC
            LIMIT 2
        """
        rows = cursor.execute(query).fetchall()

        for row in rows:
            skill = row["skill_name"]
            avg_time = row["avg_time"]
            runs = row["runs"]
            attention_needed.append(
                {
                    "severity": "medium",
                    "category": "performance",
                    "title": f"Slow skill: {skill}",
                    "metric": f"{avg_time:.1f}s average execution time",
                    "context": f"{runs} runs in past 7 days",
                    "action": "Optimize skill performance",
                    "action_link": "/dashboard_old#skills",
                }
            )

        # Health metrics
        query = f"""
            SELECT
                CAST(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as success_rate,
                AVG(execution_time_s) as avg_duration,
                COUNT(DISTINCT skill_name) as active_skills,
                COUNT(*) as total_runs
            FROM ({skill_sql}) skill_usage
            WHERE invoked_at > datetime('now', '-7 days')
        """
        row = cursor.execute(query).fetchone()
        success_rate = row["success_rate"] if row and row["success_rate"] else 1.0
        avg_duration = row["avg_duration"] if row and row["avg_duration"] else 0
        active_skills = row["active_skills"] if row and row["active_skills"] else 0
        total_runs = row["total_runs"] if row and row["total_runs"] else 0

        health = {
            "success_rate": {
                "value": f"{success_rate*100:.0f}%",
                "status": (
                    "ok"
                    if success_rate >= 0.95
                    else "warning" if success_rate >= 0.8 else "critical"
                ),
                "display": f"{total_runs} total runs",
            },
            "avg_duration": {
                "value": f"{avg_duration:.1f}s",
                "status": (
                    "ok" if avg_duration < 10 else "warning" if avg_duration < 30 else "critical"
                ),
                "display": "average execution",
            },
            "active_skills": {
                "value": f"{active_skills}",
                "status": "ok",
                "display": "skills in use",
            },
        }

        # What's working (skills with 100% success rate, min 10 runs)
        wins = []
        query = f"""
            SELECT
                skill_name,
                COUNT(*) as runs
            FROM ({skill_sql}) skill_usage
            WHERE invoked_at > datetime('now', '-7 days')
            GROUP BY skill_name
            HAVING SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) = 0
            AND runs >= 10
            ORDER BY runs DESC
            LIMIT 3
        """
        rows = cursor.execute(query).fetchall()

        for row in rows:
            skill = row["skill_name"]
            runs = row["runs"]
            wins.append({"icon": "✅", "message": f"{skill}: 100% success rate ({runs} runs)"})

        # Add workflow success if available
        query = f"""
            SELECT COUNT(*) as workflow_count
            FROM ({skill_sql}) skill_usage
            WHERE invoked_at > datetime('now', '-7 days')
            AND skill_name LIKE '%workflow%'
            AND success = 1
        """
        wf_row = cursor.execute(query).fetchone()
        if wf_row and wf_row["workflow_count"] > 5:
            wins.append(
                {
                    "icon": "🔄",
                    "message": f"Workflows executing successfully ({wf_row['workflow_count']} runs)",
                }
            )

        return {
            "attention_needed": attention_needed,
            "health": health,
            "whats_working": wins,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate agent capabilities intelligence: {str(e)}"
        )
    finally:
        conn.close()


# ── Architecture ──────────────────────────────────────────────────────────────


@router.get("/architecture")
async def get_architecture_intelligence() -> Dict[str, Any]:
    """Get projects/architecture domain intelligence.

    Returns attention_needed, health metrics, and wins for projects.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        attention_needed = []

        # Check for project-related activity (using session data as proxy)
        token_sql = token_usage_sql(conn)
        row = cursor.execute(f"""
                SELECT COUNT(DISTINCT session_id) as active_projects
                FROM ({token_sql}) token_usage
                WHERE recorded_at > datetime('now', '-7 days')
            """).fetchone() if token_sql is not None else None
        active_projects = row["active_projects"] if row else 0

        # Health metrics
        health = {
            "active_projects": {
                "value": f"{active_projects}",
                "status": "ok" if active_projects > 0 else "warning",
                "display": "past 7 days",
            },
            "prd_completion": {"value": "N/A", "status": "ok", "display": "no active PRDs"},
            "avg_health": {"value": "N/A", "status": "ok", "display": "tracking not enabled"},
        }

        # What's working
        wins = []
        if active_projects > 0:
            wins.append(
                {
                    "icon": "📦",
                    "message": f"{active_projects} active development sessions this week",
                }
            )

        # Check for decision tracking
        query = """
            SELECT COUNT(*) as decisions
            FROM decision_log
            WHERE timestamp > datetime('now', '-7 days')
        """
        dec_row = cursor.execute(query).fetchone()
        if dec_row and dec_row["decisions"] > 0:
            wins.append(
                {
                    "icon": "📋",
                    "message": f"Architecture decisions tracked ({dec_row['decisions']} decisions logged)",
                }
            )

        return {
            "attention_needed": attention_needed,
            "health": health,
            "whats_working": wins,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate architecture intelligence: {str(e)}"
        )
    finally:
        conn.close()


# ── System Controls ───────────────────────────────────────────────────────────


@router.get("/system-controls")
async def get_system_controls_intelligence() -> Dict[str, Any]:
    """Get hooks/security domain intelligence.

    Returns attention_needed, health metrics, and wins for system controls.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        attention_needed = []

        # Hook failures
        query = """
            SELECT
                hook_name,
                COUNT(*) as total,
                SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) as failures,
                CAST(SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as rate
            FROM hook_executions
            WHERE started_at > datetime('now', '-7 days')
            GROUP BY hook_name
            HAVING rate > 0.1 AND total >= 5
            ORDER BY rate DESC
            LIMIT 3
        """
        rows = cursor.execute(query).fetchall()

        for row in rows:
            hook = row["hook_name"]
            total = row["total"]
            failures = row["failures"]
            rate = row["rate"]
            attention_needed.append(
                {
                    "severity": "high" if rate > 0.3 else "medium",
                    "category": "reliability",
                    "title": f"Hook failures: {hook}",
                    "metric": f"{rate*100:.0f}% failure rate ({failures}/{total} runs)",
                    "context": "Past 7 days",
                    "action": f"Debug {hook} hook",
                    "action_link": "/dashboard_old#hooks",
                }
            )

        # Slow hooks (>5s average)
        query = """
            SELECT
                hook_name,
                AVG(duration_ms) as avg_duration,
                COUNT(*) as runs
            FROM hook_executions
            WHERE started_at > datetime('now', '-7 days')
            AND duration_ms IS NOT NULL
            GROUP BY hook_name
            HAVING avg_duration > 5000
            ORDER BY avg_duration DESC
            LIMIT 2
        """
        rows = cursor.execute(query).fetchall()

        for row in rows:
            hook = row["hook_name"]
            avg_ms = row["avg_duration"]
            runs = row["runs"]
            attention_needed.append(
                {
                    "severity": "medium",
                    "category": "performance",
                    "title": f"Slow hook: {hook}",
                    "metric": f"{avg_ms/1000:.1f}s average duration",
                    "context": f"{runs} executions in past 7 days",
                    "action": "Optimize hook performance",
                    "action_link": "/dashboard_old#hooks",
                }
            )

        # Health metrics
        query = """
            SELECT
                CAST(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as success_rate,
                AVG(duration_ms) as avg_duration,
                COUNT(*) as total_runs
            FROM hook_executions
            WHERE started_at > datetime('now', '-7 days')
        """
        row = cursor.execute(query).fetchone()
        success_rate = row["success_rate"] if row and row["success_rate"] else 1.0
        avg_duration = row["avg_duration"] if row and row["avg_duration"] else 0
        total_runs = row["total_runs"] if row and row["total_runs"] else 0

        health = {
            "hook_success_rate": {
                "value": f"{success_rate*100:.1f}%",
                "status": (
                    "ok"
                    if success_rate >= 0.95
                    else "warning" if success_rate >= 0.8 else "critical"
                ),
                "display": f"{total_runs} executions",
            },
            "avg_hook_time": {
                "value": f"{avg_duration/1000:.1f}s",
                "status": (
                    "ok"
                    if avg_duration < 3000
                    else "warning" if avg_duration < 5000 else "critical"
                ),
                "display": "average duration",
            },
            "security_score": {"value": "N/A", "status": "ok", "display": "no scans run"},
        }

        # What's working
        wins = []
        if success_rate >= 0.99 and total_runs > 50:
            wins.append(
                {
                    "icon": "🎯",
                    "message": f"Hook execution: {success_rate*100:.1f}% success rate ({total_runs} runs)",
                }
            )

        # Fast hooks
        query = """
            SELECT COUNT(DISTINCT hook_name) as fast_hooks
            FROM hook_executions
            WHERE started_at > datetime('now', '-7 days')
            AND duration_ms IS NOT NULL
            GROUP BY hook_name
            HAVING AVG(duration_ms) < 1000
        """
        fast_count = len(cursor.execute(query).fetchall())
        if fast_count > 0:
            wins.append(
                {"icon": "⚡", "message": f"{fast_count} hooks executing in under 1 second"}
            )

        return {
            "attention_needed": attention_needed,
            "health": health,
            "whats_working": wins,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate system controls intelligence: {str(e)}"
        )
    finally:
        conn.close()


# ── Workflow Pattern Detection (18.8.4) ──────────────────────────────────────


@router.get("/workflow-patterns")
async def get_workflow_patterns(
    project_id: str | None = None,
    include_suppressed: bool = False,
    min_confidence: float = 0.0,
):
    """Return detected workflow skill co-occurrence patterns.

    Observation-only — no action. Phase 19 reads confidence_score >= 0.8
    AND suppressed = 0 as input to adaptive learning.

    Pattern types:
      - always_paired: two skills invoked together in the same session
      - post_completion: skill invoked after work order closes
      - pre_close: skill invoked just before work order closes
    """
    conn = get_connection()
    try:
        from projections.core.analyzers.workflow_patterns import WorkflowPatternAnalyzer

        analyzer = WorkflowPatternAnalyzer(conn)
        patterns = analyzer.get_patterns(
            project_id=project_id,
            include_suppressed=include_suppressed,
            min_confidence=min_confidence,
        )
        return {
            "patterns": patterns,
            "total": len(patterns),
            "project_id": project_id,
            "include_suppressed": include_suppressed,
            "min_confidence": min_confidence,
            "phase19_eligible": sum(
                1 for p in patterns if p["confidence_score"] >= 0.8 and not p["suppressed"]
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get workflow patterns: {str(e)}")
    finally:
        conn.close()


@router.post("/workflow-patterns/{pattern_id}/suppress")
async def suppress_workflow_pattern(pattern_id: str):
    """Dismiss a workflow pattern — sets suppressed=1.

    Suppressed patterns:
      - Still visible via GET with include_suppressed=true
      - Excluded from Phase 19 adaptive learning reads
      - Will NOT be auto-re-surfaced on next analyze() run

    Operator action: 'This pattern isn't meaningful, don't act on it.'
    """
    conn = get_connection()
    try:
        from projections.core.analyzers.workflow_patterns import WorkflowPatternAnalyzer

        analyzer = WorkflowPatternAnalyzer(conn)
        updated = analyzer.suppress_pattern(pattern_id)
        if not updated:
            raise HTTPException(status_code=404, detail=f"Pattern {pattern_id} not found")
        return {"pattern_id": pattern_id, "suppressed": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to suppress pattern: {str(e)}")
    finally:
        conn.close()


@router.post("/workflow-patterns/analyze")
async def run_workflow_pattern_analysis(
    project_id: str | None = None,
    min_occurrences: int = 2,
    min_confidence: float = 0.3,
):
    """Run the pattern analyzer on canonical_events history.

    Detects all three pattern types and upserts to ds_workflow_pattern_signals.
    Typically called on session-end harvest. Can also be called on-demand.
    """
    conn = get_connection()
    try:
        from projections.core.analyzers.workflow_patterns import WorkflowPatternAnalyzer

        analyzer = WorkflowPatternAnalyzer(conn)
        signals = analyzer.analyze(
            project_id=project_id,
            min_occurrences=min_occurrences,
            min_confidence=min_confidence,
        )
        return {
            "signals_detected": len(signals),
            "project_id": project_id,
            "patterns_by_type": {
                "always_paired": sum(1 for s in signals if s["pattern_type"] == "always_paired"),
                "post_completion": sum(
                    1 for s in signals if s["pattern_type"] == "post_completion"
                ),
                "pre_close": sum(1 for s in signals if s["pattern_type"] == "pre_close"),
            },
            "high_confidence": sum(1 for s in signals if s["confidence_score"] >= 0.8),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pattern analysis failed: {str(e)}")
    finally:
        conn.close()


# ── Friction signals read API (Phase 19.2) ────────────────────────────────
# Consumer contract for 19.3 Gap Classifier:
#   GET /api/v1/intelligence/friction-signals → list unclassified signals
#   GET /api/v1/intelligence/friction-signals?signal_type=<type> → filter
#   GET /api/v1/intelligence/friction-signals/{signal_id} → single signal


def _friction_table_missing(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1 FROM ds_friction_signals LIMIT 1")
        return False
    except sqlite3.OperationalError:
        return True


@router.get("/friction-signals")
async def list_friction_signals(
    signal_type: str | None = None,
    classified: bool = False,
    limit: int = 100,
) -> Dict[str, Any]:
    """List friction signals. Default: unclassified only (19.3 consumer view).

    Query params:
      signal_type — filter to one signal type (dismissed_finding, partial_completion, pattern_gap)
      classified  — if true, include already-classified signals
      limit       — max rows (default 100)
    """
    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        if _friction_table_missing(conn):
            return {"signals": [], "count": 0, "note": "Migration 096 not yet applied"}

        params: List[Any] = []
        conditions: List[str] = []

        if not classified:
            conditions.append("classified_as IS NULL")
        if signal_type:
            conditions.append("signal_type = ?")
            params.append(signal_type)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)

        rows = conn.execute(
            f"SELECT * FROM ds_friction_signals {where} ORDER BY created_at LIMIT ?",
            params,
        ).fetchall()
        signals = [dict(r) for r in rows]
        return {"signals": signals, "count": len(signals)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Friction signals query failed: {str(e)}")
    finally:
        conn.close()


# -- Friction signal classifications read API (Phase 19.3) ------------------
# IMPORTANT: This route MUST be defined before /friction-signals/{signal_id}.
# FastAPI matches routes in order — the parameterized route would swallow
# GET /friction-signals/classifications if it came first.


@router.get("/friction-signals/classifications")
async def get_friction_classifications(
    classified_as: str | None = None,
    min_confidence: float = 0.0,
    limit: int = 100,
) -> Dict[str, Any]:
    """Classified signals grouped by classification type.

    Query params:
      classified_as   - filter to capability | personalization | onboarding
      min_confidence  - minimum classification_confidence (default 0.0)
      limit           - max rows (default 100)
    """
    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("SELECT 1 FROM ds_friction_signals LIMIT 1")
        except sqlite3.OperationalError:
            return {"signals": [], "by_type": {}, "count": 0}

        params: List[Any] = [min_confidence]
        conditions = [
            "classified_as IS NOT NULL",
            "classification_confidence >= ?",
            "(classification_skipped IS NULL OR classification_skipped = 0)",
        ]
        if classified_as:
            conditions.append("classified_as = ?")
            params.append(classified_as)
        params.append(limit)

        where = "WHERE " + " AND ".join(conditions)
        rows = conn.execute(
            f"SELECT * FROM ds_friction_signals {where} ORDER BY classification_confidence DESC LIMIT ?",
            params,
        ).fetchall()

        signals = [dict(r) for r in rows]
        by_type: Dict[str, int] = {}
        for s in signals:
            t = s.get("classified_as") or "unclassified"
            by_type[t] = by_type.get(t, 0) + 1

        return {"signals": signals, "by_type": by_type, "count": len(signals)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classifications query failed: {str(e)}")
    finally:
        conn.close()


@router.get("/friction-signals/{signal_id}")
async def get_friction_signal(signal_id: str) -> Dict[str, Any]:
    """Retrieve a single friction signal by ID."""
    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        if _friction_table_missing(conn):
            raise HTTPException(status_code=503, detail="Migration 096 not yet applied")
        row = conn.execute(
            "SELECT * FROM ds_friction_signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Signal {signal_id!r} not found")
        return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
