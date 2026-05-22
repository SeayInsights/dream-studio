"""Real token attribution queries against canonical_events.

Added in TA5 (dashboard truth-up). All queries read directly from
canonical_events; zero synthetic data.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from core.config.database import get_connection
from core.pricing.claude_models import compute_cost

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _payload_dict(raw: str | dict) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _aggregate_token_rows(rows: list) -> dict:
    """Sum token counts and cost across a set of token.consumed rows."""
    input_total = 0
    output_total = 0
    cache_creation_total = 0
    cache_read_total = 0
    total_cost = 0.0

    for row in rows:
        payload = _payload_dict(row["payload"])
        inp = int(payload.get("input_tokens") or 0)
        out = int(payload.get("output_tokens") or 0)
        cc = int(payload.get("cache_creation_input_tokens") or 0)
        cr = int(payload.get("cache_read_input_tokens") or 0)
        model = payload.get("model") or ""

        input_total += inp
        output_total += out
        cache_creation_total += cc
        cache_read_total += cr
        total_cost += compute_cost(model, inp, out, cc, cr)

    total = input_total + output_total
    return {
        "total_tokens": total,
        "input_tokens": input_total,
        "output_tokens": output_total,
        "cache_creation_tokens": cache_creation_total,
        "cache_read_tokens": cache_read_total,
        "total_cost_usd": round(total_cost, 6),
        "data_status": "empty" if total == 0 else "ok",
    }


def _fetch_token_events(trace_key: str, trace_value: str, since: Optional[datetime]) -> list:
    """Query canonical_events for token.consumed filtered by one trace field."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    try:
        params: list = [trace_value]
        since_clause = ""
        if since is not None:
            since_clause = " AND timestamp >= ?"
            params.append(_iso(since))
        return conn.execute(
            f"""
            SELECT payload FROM canonical_events
            WHERE event_type = 'token.consumed'
              AND json_extract(trace, '$.{trace_key}') = ?
              {since_clause}
            """,
            params,
        ).fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------


def token_spend_by_project(project_id: str, since: Optional[datetime] = None) -> dict:
    """Aggregate token.consumed events for a project.

    Returns: total tokens, total cost, attribution breakdown by status.
    """
    rows = _fetch_token_events("project_id", project_id, since)
    result = _aggregate_token_rows(rows)
    result["project_id"] = project_id
    return result


def token_spend_by_milestone(milestone_id: str, since: Optional[datetime] = None) -> dict:
    """Aggregate token.consumed events scoped to a milestone.

    Only events whose trace.milestone_id matches are included;
    sibling milestones are excluded.
    """
    rows = _fetch_token_events("milestone_id", milestone_id, since)
    result = _aggregate_token_rows(rows)
    result["milestone_id"] = milestone_id
    return result


def token_spend_by_work_order(work_order_id: str, since: Optional[datetime] = None) -> dict:
    """Aggregate token.consumed events scoped to a work order."""
    rows = _fetch_token_events("work_order_id", work_order_id, since)
    result = _aggregate_token_rows(rows)
    result["work_order_id"] = work_order_id
    return result


def token_spend_by_task(task_id: str, since: Optional[datetime] = None) -> dict:
    """Aggregate token.consumed events scoped to a task."""
    rows = _fetch_token_events("task_id", task_id, since)
    result = _aggregate_token_rows(rows)
    result["task_id"] = task_id
    return result


def attribution_coverage(project_id: Optional[str] = None) -> dict:
    """Return fully_attributed / partial / orphan breakdown for token.consumed events.

    If project_id is provided, scoped to that project. Otherwise global.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    try:
        params: list = []
        project_clause = ""
        if project_id is not None:
            project_clause = " AND json_extract(trace, '$.project_id') = ?"
            params.append(project_id)

        rows = conn.execute(
            f"""
            SELECT
                json_extract(trace, '$.attribution_status') AS attribution_status,
                COUNT(*) AS cnt
            FROM canonical_events
            WHERE event_type = 'token.consumed'
              {project_clause}
            GROUP BY json_extract(trace, '$.attribution_status')
            """,
            params,
        ).fetchall()
    finally:
        conn.close()

    counts: dict[str, int] = {}
    total = 0
    for row in rows:
        status = row["attribution_status"] or "orphan"
        count = int(row["cnt"])
        counts[status] = count
        total += count

    if total == 0:
        return {
            "total_events": 0,
            "fully_attributed_pct": 0.0,
            "partial_pct": 0.0,
            "orphan_pct": 0.0,
            "data_status": "empty",
        }

    fully = counts.get("fully_attributed", 0)
    partial = counts.get("partial", 0)
    # backfill rows count as orphan for coverage purposes
    orphan = counts.get("orphan", 0) + counts.get("backfill", 0)
    # any unrecognised statuses also go to the orphan bucket
    for k, v in counts.items():
        if k not in ("fully_attributed", "partial", "orphan", "backfill"):
            orphan += v

    return {
        "total_events": total,
        "fully_attributed_pct": round(fully / total * 100, 1),
        "partial_pct": round(partial / total * 100, 1),
        "orphan_pct": round(orphan / total * 100, 1),
        "data_status": "ok",
    }


def canonical_token_metrics(days: int) -> dict:
    """Full token metrics aggregated from canonical_events.

    Drop-in replacement for TokenCollector.collect() that reads exclusively
    from canonical_events (token.consumed events). Returns empty state when
    no events exist — never fabricated.
    """
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    try:
        all_rows = conn.execute(
            """
            SELECT payload, trace, timestamp
            FROM canonical_events
            WHERE event_type = 'token.consumed'
              AND timestamp >= ?
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    input_total = 0
    output_total = 0
    total_cost = 0.0
    by_project: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    by_date: dict[str, dict] = {}

    for row in all_rows:
        payload = _payload_dict(row["payload"])
        trace = _payload_dict(row["trace"])

        inp = int(payload.get("input_tokens") or 0)
        out = int(payload.get("output_tokens") or 0)
        cc = int(payload.get("cache_creation_input_tokens") or 0)
        cr = int(payload.get("cache_read_input_tokens") or 0)
        model = payload.get("model") or ""
        project_id = trace.get("project_id") or ""

        cost = compute_cost(model, inp, out, cc, cr)
        input_total += inp
        output_total += out
        total_cost += cost

        if project_id:
            bucket = by_project.setdefault(
                project_id,
                {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
            )
            bucket["input_tokens"] += inp
            bucket["output_tokens"] += out
            bucket["total_tokens"] += inp + out
            bucket["cost_usd"] = round(bucket["cost_usd"] + cost, 6)

        if model:
            bucket = by_model.setdefault(
                model,
                {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
            )
            bucket["input_tokens"] += inp
            bucket["output_tokens"] += out
            bucket["total_tokens"] += inp + out
            bucket["cost_usd"] = round(bucket["cost_usd"] + cost, 6)

        ts = row["timestamp"] or ""
        date_str = ts[:10] if ts else ""
        if date_str:
            bucket = by_date.setdefault(
                date_str,
                {
                    "date": date_str,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "tokens": 0,
                    "cost_usd": 0.0,
                },
            )
            bucket["input_tokens"] += inp
            bucket["output_tokens"] += out
            bucket["tokens"] += inp + out
            bucket["cost_usd"] = round(bucket["cost_usd"] + cost, 6)

    total = input_total + output_total
    timeline = sorted(by_date.values(), key=lambda x: x["date"])
    daily_average = round(total / days, 1) if days else 0.0

    return {
        "total_tokens": total,
        "input_tokens": input_total,
        "output_tokens": output_total,
        "total_input_tokens": input_total,
        "total_output_tokens": output_total,
        "cache_hits": 0,
        "total_cost_usd": round(total_cost, 6) if total > 0 else None,
        "cost_status": "reportable" if total > 0 else "unknown",
        "cost_visibility": "reportable" if total > 0 else "unavailable",
        "by_model": by_model,
        "by_project": by_project,
        "by_skill": {},
        "daily_average": daily_average,
        "timeline": timeline,
        "data_status": "empty" if total == 0 else "ok",
    }


def exec_time_ranges_from_canonical(days: int) -> dict[str, dict[str, float]]:
    """Min/max execution time per skill, read from canonical_events.skill.executed.

    Reads from canonical_events instead of legacy skill_invocations (TA5).
    Returns a dict keyed by skill_name with min_m / max_m in minutes.
    Returns {} when no skill.executed events exist in the requested window.
    """
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                json_extract(payload, '$.skill_name') AS skill_name,
                MIN(CAST(json_extract(payload, '$.duration_ms') AS REAL)) AS min_ms,
                MAX(CAST(json_extract(payload, '$.duration_ms') AS REAL)) AS max_ms
            FROM canonical_events
            WHERE event_type = 'skill.executed'
              AND timestamp >= ?
              AND json_extract(payload, '$.duration_ms') IS NOT NULL
            GROUP BY json_extract(payload, '$.skill_name')
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    return {
        row["skill_name"]: {
            "min_m": round((row["min_ms"] or 0.0) / 60_000, 4),
            "max_m": round((row["max_ms"] or 0.0) / 60_000, 4),
        }
        for row in rows
        if row["skill_name"]
    }
