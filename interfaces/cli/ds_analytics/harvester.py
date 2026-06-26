"""Harvesters: collect raw data from skill telemetry and operational snapshots."""

from __future__ import annotations

import sqlite3
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.config import paths
from core.event_store import studio_db
from core.config.database import get_connection

# ---------------------------------------------------------------------------
# Operational harvester (reads from raw_operational_snapshots)
# ---------------------------------------------------------------------------


def harvest_operational(db_path: Path | None = None, project_slug: str | None = None) -> list[dict]:
    """Read operational snapshots from SQLite.

    When project_slug is provided, filters to that project.
    Returns list of dicts with snapshot_date and metric columns.
    """
    db = db_path or paths.state_dir() / "studio.db"
    if not db.exists():
        return []

    conn = get_connection()
    try:
        if project_slug:
            rows = conn.execute(
                "SELECT snapshot_date, ci_status, open_prs, stale_branches, "
                "pending_drafts, open_escalations FROM raw_operational_snapshots "
                "WHERE project_slug = ? ORDER BY snapshot_date",
                (project_slug,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT snapshot_date, ci_status, open_prs, stale_branches, "
                "pending_drafts, open_escalations FROM raw_operational_snapshots "
                "ORDER BY snapshot_date"
            ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []
    conn.close()

    cols = [
        "snapshot_date",
        "ci_status",
        "open_prs",
        "stale_branches",
        "pending_drafts",
        "open_escalations",
    ]
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# Skill telemetry harvester
# ---------------------------------------------------------------------------

_EMPTY_VELOCITY_COLS = ["skill_name", "week", "invocation_count", "success_rate"]


def harvest_skill_velocity(db_path: Path | None = None) -> pd.DataFrame:
    """Query effective_skill_runs and compute weekly skill velocity.

    Returns a DataFrame with columns: ``skill_name``, ``week``,
    ``invocation_count``, ``success_rate``.  Returns an empty DataFrame
    with the correct columns if no telemetry data exists.
    """
    conn = studio_db._connect(db_path)

    # Check if the view has any rows
    try:
        row_count = conn.execute("SELECT COUNT(*) FROM effective_skill_runs").fetchone()[0]
    except sqlite3.OperationalError:
        conn.close()
        return pd.DataFrame(columns=_EMPTY_VELOCITY_COLS)

    if row_count == 0:
        conn.close()
        return pd.DataFrame(columns=_EMPTY_VELOCITY_COLS)

    query = """
        SELECT skill_name,
               strftime('%Y-W%W', invoked_at) AS week,
               COUNT(*)                        AS invocation_count,
               AVG(success)                    AS success_rate
        FROM effective_skill_runs
        GROUP BY skill_name, week
        ORDER BY skill_name, week
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


# ---------------------------------------------------------------------------
# Hook timing harvester
# ---------------------------------------------------------------------------


def harvest_hook_timing() -> dict:
    """Read hook-timing.jsonl and compute per-handler averages.

    Returns dict with keys: handlers (list of {handler, event, avg_ms, count}),
    total_overhead_ms, slowest_handler.
    """
    import json

    timing_file = paths.state_dir() / "hook-timing.jsonl"
    if not timing_file.exists():
        return {"handlers": [], "total_overhead_ms": 0, "slowest_handler": None}

    stats: dict[str, dict] = {}
    try:
        for line in timing_file.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            record = json.loads(line)
            key = record["handler"]
            if key not in stats:
                stats[key] = {
                    "handler": key,
                    "event": record.get("event", ""),
                    "total_ms": 0.0,
                    "count": 0,
                }
            stats[key]["total_ms"] += record.get("duration_ms", 0)
            stats[key]["count"] += 1
    except Exception:
        return {"handlers": [], "total_overhead_ms": 0, "slowest_handler": None}

    handlers = []
    for s in stats.values():
        avg = s["total_ms"] / s["count"] if s["count"] > 0 else 0
        handlers.append(
            {
                "handler": s["handler"],
                "event": s["event"],
                "avg_ms": round(avg, 2),
                "count": s["count"],
            }
        )

    handlers.sort(key=lambda h: h["avg_ms"], reverse=True)
    total = sum(h["avg_ms"] for h in handlers)
    slowest = handlers[0]["handler"] if handlers else None

    return {
        "handlers": handlers,
        "total_overhead_ms": round(total, 2),
        "slowest_handler": slowest,
    }
