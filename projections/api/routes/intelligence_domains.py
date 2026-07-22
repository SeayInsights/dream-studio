"""Intelligence API - per-domain intelligence endpoints.

WO-GF-API-ROUTES: split out of intelligence.py. Domain-scoped intelligence for
tokens/cost, skills/agents, projects/architecture, and hooks/security.
"""

from __future__ import annotations

from fastapi import HTTPException
from typing import Any
from datetime import datetime, UTC

from core.config.database import get_connection
from core.analytics.duckdb_store import connect_analytics
from projections.core.collectors.authority_sources import skill_usage_sql, token_usage_sql

from .intelligence_router import router

# ── Token Intelligence ────────────────────────────────────────────────────────


@router.get("/token-intelligence")
async def get_token_intelligence() -> dict[str, Any]:
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
                "last_updated": datetime.now(UTC).isoformat(),
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
                    "title": "High token usage detected",
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
            "last_updated": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate token intelligence: {str(e)}"
        )
    finally:
        conn.close()


# ── Agent Capabilities ────────────────────────────────────────────────────────


@router.get("/agent-capabilities")
async def get_agent_capabilities() -> dict[str, Any]:
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
                "last_updated": datetime.now(UTC).isoformat(),
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
            "last_updated": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate agent capabilities intelligence: {str(e)}"
        )
    finally:
        conn.close()


# ── Architecture ──────────────────────────────────────────────────────────────


@router.get("/architecture")
async def get_architecture_intelligence() -> dict[str, Any]:
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

        # Check for decision tracking — decision.recorded canonical events
        # replaced decision_log rows (T4, WO-DBA-EVAL-DECISION).
        query = """
            SELECT COUNT(*) as decisions
            FROM business_canonical_events
            WHERE event_type = 'decision.recorded'
              AND event_timestamp > datetime('now', '-7 days')
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
            "last_updated": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate architecture intelligence: {str(e)}"
        )
    finally:
        conn.close()


# ── System Controls ───────────────────────────────────────────────────────────


@router.get("/system-controls")
async def get_system_controls_intelligence() -> dict[str, Any]:
    """Get hooks/security domain intelligence.

    Returns attention_needed, health metrics, and wins for system controls.
    Reads hook_executions from DuckDB aggregate_metrics.db (derived from canonical events).
    """
    conn = connect_analytics(read_only=True)
    try:
        attention_needed = []

        # Hook failures — DuckDB hook_executions view, 7-day filter using ISO timestamp comparison
        rows = conn.execute("""
            SELECT
                hook_name,
                COUNT(*) as total,
                SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) as failures,
                CAST(SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) AS DOUBLE) / COUNT(*) as rate
            FROM hook_executions
            WHERE started_at > (now() - INTERVAL '7 days')::VARCHAR
            GROUP BY hook_name
            HAVING rate > 0.1 AND total >= 5
            ORDER BY rate DESC
            LIMIT 3
        """).fetchall()

        for row in rows:
            hook = row[0]
            total = row[1]
            failures = row[2]
            rate = row[3]
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
        rows = conn.execute("""
            SELECT
                hook_name,
                AVG(duration_ms) as avg_duration,
                COUNT(*) as runs
            FROM hook_executions
            WHERE started_at > (now() - INTERVAL '7 days')::VARCHAR
            AND duration_ms IS NOT NULL
            GROUP BY hook_name
            HAVING avg_duration > 5000
            ORDER BY avg_duration DESC
            LIMIT 2
        """).fetchall()

        for row in rows:
            hook = row[0]
            avg_ms = row[1]
            runs = row[2]
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
        row = conn.execute("""
            SELECT
                CAST(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS DOUBLE) / NULLIF(COUNT(*), 0) as success_rate,
                AVG(duration_ms) as avg_duration,
                COUNT(*) as total_runs
            FROM hook_executions
            WHERE started_at > (now() - INTERVAL '7 days')::VARCHAR
        """).fetchone()
        success_rate = row[0] if row and row[0] is not None else 1.0
        avg_duration = row[1] if row and row[1] is not None else 0
        total_runs = row[2] if row and row[2] is not None else 0

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
        fast_rows = conn.execute("""
            SELECT hook_name
            FROM hook_executions
            WHERE started_at > (now() - INTERVAL '7 days')::VARCHAR
            AND duration_ms IS NOT NULL
            GROUP BY hook_name
            HAVING AVG(duration_ms) < 1000
        """).fetchall()
        fast_count = len(fast_rows)
        if fast_count > 0:
            wins.append(
                {"icon": "⚡", "message": f"{fast_count} hooks executing in under 1 second"}
            )

        return {
            "attention_needed": attention_needed,
            "health": health,
            "whats_working": wins,
            "last_updated": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate system controls intelligence: {str(e)}"
        )
    finally:
        conn.close()
