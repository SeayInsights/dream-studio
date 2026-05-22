"""Metrics API routes"""

import sqlite3
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from core.config.database import get_connection
from core.shared_intelligence.usage_accounting import REPORTABLE_COST_VISIBILITIES

from ..models.metrics import (
    MetricsQuery,
    AllMetricsResponse,
    SessionMetrics,
    SkillMetrics,
    TokenMetrics,
    ModelMetrics,
    LessonMetrics,
    WorkflowMetrics,
)
from projections.core.collectors import (
    SessionCollector,
    SkillCollector,
    TokenCollector,
    ModelCollector,
    LessonCollector,
    WorkflowCollector,
)
from projections.core.collectors.authority_sources import skill_usage_sql, token_usage_sql
from projections.api.queries.token_attribution import (
    attribution_coverage,
    canonical_token_metrics,
    exec_time_ranges_from_canonical,
)

router = APIRouter()


def get_db_path() -> str:
    """Get database path"""
    from core.config.database import get_db_path as _canonical

    return str(_canonical())


def _reportable_sql_placeholders() -> str:
    return ",".join("?" for _ in REPORTABLE_COST_VISIBILITIES)


def _round_optional(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _sum_optional(current: float | None, value: float | None) -> float | None:
    if value is None:
        return current
    return (current or 0.0) + value


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _build_token_timeline(db_path: str, days: int) -> List[Dict[str, Any]]:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    try:
        source_sql = token_usage_sql(conn)
        if source_sql is None:
            return []
        rows = conn.execute(
            f"""
            SELECT DATE(recorded_at) as date,
                   SUM(input_tokens) as input_tokens,
                   SUM(output_tokens) as output_tokens,
                   SUM(
                       CASE
                           WHEN cost_visibility IN ({_reportable_sql_placeholders()})
                           THEN estimated_cost
                           ELSE NULL
                       END
                   ) as reportable_cost
            FROM ({source_sql}) token_usage
            WHERE recorded_at >= ?
            GROUP BY DATE(recorded_at)
            ORDER BY date ASC
        """,
            (*REPORTABLE_COST_VISIBILITIES, cutoff),
        ).fetchall()
        by_date: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            d = r["date"]
            inp = r["input_tokens"] or 0
            out = r["output_tokens"] or 0
            cost = _optional_float(r["reportable_cost"])
            if d not in by_date:
                by_date[d] = {
                    "date": d,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached_tokens": 0,
                    "tokens": 0,
                    "cost_usd": None,
                }
            by_date[d]["input_tokens"] += inp
            by_date[d]["output_tokens"] += out
            by_date[d]["tokens"] += inp + out
            by_date[d]["cost_usd"] = _round_optional(_sum_optional(by_date[d]["cost_usd"], cost))
        return sorted(by_date.values(), key=lambda x: x["date"])
    finally:
        conn.close()


def _build_success_trend(db_path: str, days: int) -> List[Dict[str, Any]]:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    try:
        source_sql = skill_usage_sql(conn)
        if source_sql is None:
            return []
        rows = conn.execute(
            f"""
            SELECT
                DATE(invoked_at) as date,
                COUNT(*) as total,
                SUM(success) as successes
            FROM ({source_sql}) skill_usage
            WHERE invoked_at >= ?
            GROUP BY DATE(invoked_at)
            ORDER BY date ASC
        """,
            (cutoff,),
        ).fetchall()
        return [
            {
                "date": r["date"],
                "success_rate": round((r["successes"] or 0) / r["total"], 3) if r["total"] else 0,
            }
            for r in rows
        ]
    finally:
        conn.close()


def _build_skill_heatmap(db_path: str, days: int) -> List[Dict[str, Any]]:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    try:
        source_sql = skill_usage_sql(conn)
        if source_sql is None:
            return []
        rows = conn.execute(
            f"""
            SELECT
                skill_name,
                CAST(strftime('%H', invoked_at) AS INTEGER) as hour,
                COUNT(*) as invocations
            FROM ({source_sql}) skill_usage
            WHERE invoked_at >= ?
            GROUP BY skill_name, hour
            ORDER BY skill_name, hour
        """,
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/", response_model=AllMetricsResponse)
async def get_all_metrics(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    project: Optional[str] = Query(default=None, description="Filter by project"),
    skill: Optional[str] = Query(default=None, description="Filter by skill"),
    model: Optional[str] = Query(default=None, description="Filter by model"),
):
    """Get all metrics combined"""
    try:
        db_path = get_db_path()

        # Initialize collectors
        session_collector = SessionCollector(db_path)
        skill_collector = SkillCollector(db_path)
        token_collector = TokenCollector(db_path)
        model_collector = ModelCollector(db_path)
        lesson_collector = LessonCollector(db_path)
        workflow_collector = WorkflowCollector(db_path)

        # Collect all metrics
        sessions_data = session_collector.collect(days=days)
        skills_data = skill_collector.collect(days=days)
        tokens_data = token_collector.collect(days=days)
        models_data = model_collector.collect(days=days)
        lessons_data = lesson_collector.collect(days=days)
        workflows_data = workflow_collector.collect(days=days)

        # Map workflow collector fields to Pydantic model fields
        workflows_mapped = {
            "total_workflows": workflows_data["total_runs"],
            "by_workflow": workflows_data["by_workflow"],
            "overall_success_rate": workflows_data["success_rate"],
            "by_status": workflows_data["by_status"],
            "avg_completion_time_minutes": workflows_data["avg_completion_time_minutes"],
            "total_nodes": workflows_data["total_nodes_executed"],
        }

        # Build response
        return AllMetricsResponse(
            sessions=SessionMetrics(**sessions_data),
            skills=SkillMetrics(**skills_data),
            tokens=TokenMetrics(**tokens_data),
            models=ModelMetrics(**models_data),
            lessons=LessonMetrics(**lessons_data),
            workflows=WorkflowMetrics(**workflows_mapped),
            generated_at=datetime.now(),
            query_params=MetricsQuery(days=days, project=project, skill=skill, model=model),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting metrics: {str(e)}")


@router.get("/sessions", response_model=SessionMetrics)
async def get_session_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get session metrics"""
    try:
        db_path = get_db_path()
        collector = SessionCollector(db_path)
        data = collector.collect(days=days)
        return SessionMetrics(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting session metrics: {str(e)}")


@router.get("/skills")
async def get_skill_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get skill metrics with dashboard-friendly format"""
    try:
        db_path = get_db_path()
        collector = SkillCollector(db_path)
        data = collector.collect(days=days)

        exec_ranges = exec_time_ranges_from_canonical(days)

        leaderboard = []
        for skill_name, skill_data in data.get("by_skill", {}).items():
            avg_exec_s = skill_data.get("avg_exec_time_s", 0)
            avg_duration_minutes = avg_exec_s / 60 if avg_exec_s else 0
            ranges = exec_ranges.get(skill_name, {})

            input_tok = skill_data.get("avg_input_tokens", 0)
            output_tok = skill_data.get("avg_output_tokens", 0)
            leaderboard.append(
                {
                    "skill_name": skill_name,
                    "invocations": skill_data.get("count", 0),
                    "success_rate": skill_data.get("success_rate", 0) / 100,
                    "avg_exec_time_s": avg_exec_s,
                    "avg_duration_minutes": avg_duration_minutes,
                    "min_duration_minutes": ranges.get("min_m", 0),
                    "max_duration_minutes": ranges.get("max_m", 0),
                    "avg_cost": None,
                    "cost_visibility": "unavailable",
                    "cost_status": "unknown",
                    "avg_input_tokens": input_tok,
                    "avg_output_tokens": output_tok,
                }
            )

        # Get most used skill
        most_used_skill = (
            data.get("top_skills", [{}])[0].get("skill_name", "N/A")
            if data.get("top_skills")
            else "N/A"
        )
        most_used_count = (
            data.get("top_skills", [{}])[0].get("count", 0) if data.get("top_skills") else 0
        )

        # Calculate average duration across all skills
        avg_duration_minutes = 0
        if leaderboard:
            total_weighted_duration = sum(
                item["avg_duration_minutes"] * item["invocations"] for item in leaderboard
            )
            total_invocations = sum(item["invocations"] for item in leaderboard)
            avg_duration_minutes = (
                total_weighted_duration / total_invocations if total_invocations > 0 else 0
            )

        top_skills = [{**s, "usage_count": s.get("count", 0)} for s in data.get("top_skills", [])]

        return {
            **data,
            "top_skills": top_skills,
            "overall_success_rate": data.get("overall_success_rate", 0) / 100,
            "avg_duration_minutes": avg_duration_minutes,
            "leaderboard": leaderboard,
            "most_used_skill": most_used_skill,
            "most_used_count": most_used_count,
            "recent_failures": data.get("failures", []),
            "success_trend": _build_success_trend(db_path, days),
            "heatmap": _build_skill_heatmap(db_path, days),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting skill metrics: {str(e)}")


@router.get("/tokens")
async def get_token_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get token usage metrics with dashboard-friendly format"""
    try:
        data = canonical_token_metrics(days)
        timeline = data["timeline"]

        cache_hit_rate = data.get("cache_hits", 0) / max(data.get("total_tokens", 1), 1)
        cost_timeline = [{"date": t["date"], "cost": t.get("cost_usd")} for t in timeline]

        by_project = {
            k: {**v, "cost": v.get("cost_usd")} for k, v in data.get("by_project", {}).items()
        }
        raw_by_skill = data.get("by_skill", {})
        has_skill_costs = any(v.get("cost_usd") is not None for v in raw_by_skill.values())

        if has_skill_costs:
            by_skill = {
                k: {**v, "skill_name": k, "cost": v.get("cost_usd")}
                for k, v in raw_by_skill.items()
            }
        else:
            # No skill attribution in canonical_events token data — honest empty.
            by_skill = {}

        coverage = attribution_coverage()

        return {
            **data,
            "timeline": timeline,
            "cost_timeline": cost_timeline,
            "total_cost": data.get("total_cost_usd"),
            "cache_hit_rate": cache_hit_rate,
            "by_project": by_project,
            "by_skill": by_skill,
            "attribution_coverage": coverage,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting token metrics: {str(e)}")


@router.get("/models")
async def get_model_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get model usage metrics with dashboard-friendly format"""
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn = get_connection()
        conn.row_factory = sqlite3.Row

        source_sql = token_usage_sql(conn)
        rows = (
            conn.execute(
                f"""
                SELECT model,
                       COUNT(*) as record_count,
                       SUM(input_tokens) as input_tok,
                       SUM(output_tokens) as output_tok,
                       SUM(
                           CASE
                               WHEN cost_visibility IN ({_reportable_sql_placeholders()})
                               THEN estimated_cost
                               ELSE NULL
                           END
                       ) as reportable_cost
                FROM ({source_sql}) token_usage
                WHERE recorded_at >= ? AND model IS NOT NULL AND model != '<synthetic>'
                GROUP BY model ORDER BY (input_tok + output_tok) DESC
            """,
                (*REPORTABLE_COST_VISIBILITIES, cutoff),
            ).fetchall()
            if source_sql is not None
            else []
        )
        conn.close()

        total_records = sum(r["record_count"] for r in rows)
        total_tokens = sum((r["input_tok"] or 0) + (r["output_tok"] or 0) for r in rows)

        by_model = {}
        model_distribution = []
        model_performance = []
        token_efficiency = []
        distribution = []

        raw_tps = []
        for r in rows:
            name = r["model"]
            inp = r["input_tok"] or 0
            out = r["output_tok"] or 0
            tok = inp + out
            pct = round(tok / total_tokens * 100, 1) if total_tokens else 0
            cost = _optional_float(r["reportable_cost"])
            tps = round(tok / max(r["record_count"], 1), 1)
            raw_tps.append(tps)

            by_model[name] = {
                "input_tokens": inp,
                "output_tokens": out,
                "total_tokens": tok,
                "record_count": r["record_count"],
                "percentage": pct,
                "model_name": name,
                "cost": _round_optional(cost),
                "cost_usd": _round_optional(cost),
                "cost_visibility": "reportable" if cost is not None else "unavailable",
            }
            distribution.append({"model": name, "percentage": pct})
            model_distribution.append({"model_name": name, "usage_count": r["record_count"]})
            token_efficiency.append({"model_name": name, "tokens_per_second": tps})

        max_tps = max(raw_tps) if raw_tps else 1
        max_operational_eff = 0
        operational_effs = []
        for r in rows:
            tok = (r["input_tok"] or 0) + (r["output_tok"] or 0)
            oe = tok / max(r["record_count"], 1)
            operational_effs.append(oe)
            max_operational_eff = max(max_operational_eff, oe)

        top_n = sorted(range(len(rows)), key=lambda i: rows[i]["record_count"], reverse=True)[:4]
        for i in top_n:
            name = rows[i]["model"]
            tps = raw_tps[i]
            operational_efficiency = operational_effs[i]
            model_performance.append(
                {
                    "model_name": name,
                    "speed": round(tps / max_tps, 3),
                    "success_rate": round(by_model[name]["percentage"] / 100, 3),
                    "efficiency": (
                        round(operational_efficiency / max_operational_eff, 3)
                        if max_operational_eff
                        else 0
                    ),
                }
            )

        best = (
            max(token_efficiency, key=lambda x: x["tokens_per_second"]) if token_efficiency else {}
        )

        return {
            "total_invocations": total_records,
            "by_model": by_model,
            "distribution": distribution,
            "model_distribution": model_distribution,
            "model_performance": model_performance,
            "token_efficiency": token_efficiency,
            "most_efficient_model": best.get("model_name", "--"),
            "most_efficient_rate": best.get("tokens_per_second", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting model metrics: {str(e)}")


@router.get("/lessons", response_model=LessonMetrics)
async def get_lesson_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get lesson capture metrics"""
    try:
        db_path = get_db_path()
        collector = LessonCollector(db_path)
        data = collector.collect(days=days)
        # Collector returns correct field names - no mapping needed
        return LessonMetrics(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting lesson metrics: {str(e)}")


@router.get("/workflows", response_model=WorkflowMetrics)
async def get_workflow_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get workflow metrics"""
    try:
        db_path = get_db_path()
        collector = WorkflowCollector(db_path)
        data = collector.collect(days=days)

        # Map WorkflowCollector field names to WorkflowMetrics field names
        mapped_data = {
            "total_workflows": data["total_runs"],
            "by_workflow": data["by_workflow"],
            "overall_success_rate": data["success_rate"],
            "by_status": data["by_status"],
            "avg_completion_time_minutes": data["avg_completion_time_minutes"],
            "total_nodes": data["total_nodes_executed"],
        }

        return WorkflowMetrics(**mapped_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting workflow metrics: {str(e)}")
