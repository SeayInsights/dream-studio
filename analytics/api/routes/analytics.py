"""Analytics routes for anomaly detection, trends, and performance analysis"""
import os
import sqlite3
import statistics
from datetime import datetime, timedelta
from fastapi import APIRouter, Query
from typing import Dict, Any, List

router = APIRouter()


def _get_db() -> str:
    return os.path.expanduser("~/.dream-studio/state/studio.db")


def _connect():
    conn = sqlite3.connect(_get_db())
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/anomalies")
async def get_anomalies(days: int = Query(default=30, ge=1, le=365)) -> Dict[str, Any]:
    """Detect anomalies using z-score on session duration and token usage"""
    conn = _connect()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        rows = conn.execute("""
            SELECT
                s.session_id,
                s.started_at,
                (julianday(s.ended_at) - julianday(s.started_at)) * 86400 as duration_s,
                COALESCE(t.total_tokens, 0) as tokens
            FROM raw_sessions s
            LEFT JOIN (
                SELECT session_id, SUM(input_tokens + output_tokens) as total_tokens
                FROM raw_token_usage
                GROUP BY session_id
            ) t ON s.session_id = t.session_id
            WHERE s.started_at >= ?
              AND s.ended_at IS NOT NULL
              AND duration_s > 0
        """, (cutoff,)).fetchall()

        if len(rows) < 3:
            return {
                "anomalies": [], "scatter_data": [],
                "summary": {"total_anomalies": 0, "severity_breakdown": {"low": 0, "medium": 0, "high": 0}, "affected_metrics": []},
                "last_detected": "Never", "detection_rate": 0, "avg_severity": "Low"
            }

        durations = [r["duration_s"] for r in rows]
        tokens = [r["tokens"] for r in rows]
        dur_mean, dur_std = statistics.mean(durations), statistics.pstdev(durations) or 1
        tok_mean, tok_std = statistics.mean(tokens), statistics.pstdev(tokens) or 1

        scatter_data: List[Dict[str, Any]] = []
        anomalies: List[Dict[str, Any]] = []
        severity_counts = {"low": 0, "medium": 0, "high": 0}

        for r in rows:
            dur_z = abs(r["duration_s"] - dur_mean) / dur_std
            tok_z = abs(r["tokens"] - tok_mean) / tok_std
            max_z = max(dur_z, tok_z)
            is_anomaly = max_z > 2.0

            scatter_data.append({
                "duration": round(r["duration_s"], 1),
                "tokens": r["tokens"],
                "is_anomaly": is_anomaly
            })

            if is_anomaly:
                severity = "high" if max_z > 3.0 else "medium" if max_z > 2.5 else "low"
                severity_counts[severity] += 1
                anomalies.append({
                    "session_id": r["session_id"],
                    "timestamp": r["started_at"],
                    "duration_s": round(r["duration_s"], 1),
                    "tokens": r["tokens"],
                    "z_score": round(max_z, 2),
                    "severity": severity
                })

        anomalies.sort(key=lambda a: a["z_score"], reverse=True)
        last_detected = anomalies[0]["timestamp"] if anomalies else "Never"
        avg_severity = "High" if severity_counts["high"] > 0 else "Medium" if severity_counts["medium"] > 0 else "Low"

        return {
            "anomalies": anomalies[:50],
            "scatter_data": scatter_data,
            "summary": {
                "total_anomalies": len(anomalies),
                "severity_breakdown": severity_counts,
                "affected_metrics": ["duration", "tokens"] if anomalies else []
            },
            "last_detected": last_detected,
            "detection_rate": round(len(anomalies) / len(rows), 3) if rows else 0,
            "avg_severity": avg_severity
        }
    finally:
        conn.close()


@router.get("/trends")
async def get_trends(days: int = Query(default=30, ge=1, le=365)) -> Dict[str, Any]:
    """Analyze daily trends for sessions, tokens, and cost with linear regression"""
    conn = _connect()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        session_rows = conn.execute("""
            SELECT DATE(started_at) as date, COUNT(*) as count
            FROM raw_sessions WHERE started_at >= ?
            GROUP BY DATE(started_at) ORDER BY date
        """, (cutoff,)).fetchall()

        token_rows = conn.execute("""
            SELECT DATE(recorded_at) as date,
                   SUM(input_tokens + output_tokens) as tokens,
                   SUM(
                       CASE
                           WHEN model LIKE '%opus%' THEN input_tokens * 0.015 / 1000.0 + output_tokens * 0.075 / 1000.0
                           WHEN model LIKE '%haiku%' THEN input_tokens * 0.00025 / 1000.0 + output_tokens * 0.00125 / 1000.0
                           ELSE input_tokens * 0.003 / 1000.0 + output_tokens * 0.015 / 1000.0
                       END
                   ) as cost
            FROM raw_token_usage WHERE recorded_at >= ?
            GROUP BY DATE(recorded_at) ORDER BY date
        """, (cutoff,)).fetchall()

        dates = sorted(set(
            [r["date"] for r in session_rows] + [r["date"] for r in token_rows]
        ))

        if not dates:
            return {
                "trends": {}, "dates": [],
                "summary": {"upward_trends": 0, "downward_trends": 0, "stable_metrics": 0}
            }

        sess_map = {r["date"]: r["count"] for r in session_rows}
        tok_map = {r["date"]: r["tokens"] for r in token_rows}
        cost_map = {r["date"]: r["cost"] or 0 for r in token_rows}

        def _regression(values: List[float]):
            n = len(values)
            if n < 2:
                return values[:], 0.0
            x_mean = (n - 1) / 2
            y_mean = sum(values) / n
            num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
            den = sum((i - x_mean) ** 2 for i in range(n))
            slope = num / den if den else 0
            intercept = y_mean - slope * x_mean
            reg = [round(intercept + slope * i, 2) for i in range(n)]
            return reg, slope

        trends = {}
        up = down = stable = 0

        for name, lookup in [("sessions", sess_map), ("tokens", tok_map), ("cost", cost_map)]:
            actual = [lookup.get(d, 0) for d in dates]
            reg, slope = _regression([float(v) for v in actual])
            trends[name] = {"actual": actual, "regression": reg}
            if slope > 0.01:
                up += 1
            elif slope < -0.01:
                down += 1
            else:
                stable += 1

        return {
            "trends": trends,
            "dates": dates,
            "summary": {"upward_trends": up, "downward_trends": down, "stable_metrics": stable}
        }
    finally:
        conn.close()


@router.get("/performance")
async def get_performance(days: int = Query(default=30, ge=1, le=365)) -> Dict[str, Any]:
    """Analyze session performance: flow breakdown, day-of-week, and hourly activity"""
    conn = _connect()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        outcome_rows = conn.execute("""
            SELECT
                COALESCE(outcome, 'unknown') as outcome,
                COUNT(*) as count
            FROM raw_sessions WHERE started_at >= ?
            GROUP BY outcome
        """, (cutoff,)).fetchall()

        outcome_map = {r["outcome"]: r["count"] for r in outcome_rows}
        total = sum(outcome_map.values())

        session_flow = {
            "started": total,
            "completed": outcome_map.get("success", 0) + outcome_map.get("completed", 0),
            "failed": outcome_map.get("failed", 0) + outcome_map.get("error", 0),
            "timeout": outcome_map.get("timeout", 0) + outcome_map.get("unknown", 0) + outcome_map.get("in_progress", 0)
        }

        dow_rows = conn.execute("""
            SELECT
                CAST(strftime('%w', started_at) AS INTEGER) as dow,
                COUNT(*) as count
            FROM raw_sessions WHERE started_at >= ?
            GROUP BY dow
        """, (cutoff,)).fetchall()

        dow_map = {r["dow"]: r["count"] for r in dow_rows}
        day_of_week = [dow_map.get((i % 7 + 1) % 7, 0) for i in range(7)]

        hourly_rows = conn.execute("""
            SELECT
                CAST(strftime('%w', started_at) AS INTEGER) as dow,
                CAST(strftime('%H', started_at) AS INTEGER) as hour,
                COUNT(*) as count
            FROM raw_sessions WHERE started_at >= ?
            GROUP BY dow, hour
        """, (cutoff,)).fetchall()

        hourly_map = {}
        for r in hourly_rows:
            hourly_map[(r["dow"], r["hour"])] = r["count"]

        hourly_activity = []
        for day_idx in range(7):
            sqlite_dow = (day_idx + 1) % 7
            hourly_activity.append([hourly_map.get((sqlite_dow, h), 0) for h in range(24)])

        return {
            "session_flow": session_flow,
            "day_of_week": day_of_week,
            "hourly_activity": hourly_activity,
            "performance": {},
            "summary": {
                "overall_score": round(session_flow["completed"] / total * 100, 1) if total else 0,
                "bottlenecks": [],
                "improvements": []
            },
            "sankey_data": {}
        }
    finally:
        conn.close()
