"""Attribution coverage, orphan drilldown, memory surface, and attribution
breakout diagnostic endpoints.

WO-GF-API-ROUTES: split out of insights.py.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, Query

from core.telemetry.attribution_config import ATTRIBUTION_COVERAGE_MIN as _ATTRIBUTION_COVERAGE_MIN

from .insights_router import router

# ---------------------------------------------------------------------------
# Attribution coverage — 18.4.2a
# ---------------------------------------------------------------------------


@router.get("/attribution-coverage")
async def get_attribution_coverage(project_id: str = Query(default=None)):
    """Return attribution coverage breakdown for token.consumed events.

    Internal diagnostic panel — surfaced under Intelligence > Token Attribution.
    Compares fully_attributed / partial / orphan counts.
    Logs a warning when coverage drops below the configured threshold.
    """
    from projections.api.queries.token_attribution import attribution_coverage
    import logging

    log = logging.getLogger(__name__)

    try:
        data = attribution_coverage(project_id=project_id)
        fully_pct = data.get("fully_attributed_pct", 0.0)

        # Log warning if fully-attributed coverage falls below threshold.
        if data.get("data_status") == "ok" and (fully_pct / 100) < _ATTRIBUTION_COVERAGE_MIN:
            log.warning(
                "attribution_coverage below threshold: %.1f%% < %.0f%% "
                "(project_id=%s total_events=%d)",
                fully_pct,
                _ATTRIBUTION_COVERAGE_MIN * 100,
                project_id,
                data.get("total_events", 0),
            )

        return {
            "schema": "dream_studio.attribution_coverage.v1",
            "project_id": project_id,
            "total_events": data.get("total_events", 0),
            "fully_attributed_count": data.get("fully_attributed_count", 0),
            "partial_count": data.get("partial_count", 0),
            "orphan_count": data.get("orphan_count", 0),
            "fully_attributed_pct": data.get("fully_attributed_pct", 0.0),
            "partial_pct": data.get("partial_pct", 0.0),
            "orphan_pct": data.get("orphan_pct", 0.0),
            "coverage_threshold_pct": _ATTRIBUTION_COVERAGE_MIN * 100,
            "below_threshold": (fully_pct / 100) < _ATTRIBUTION_COVERAGE_MIN,
            "data_status": data.get("data_status", "empty"),
            "visibility": "internal",
            "generated_at": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error computing attribution coverage: {exc}")


@router.get("/attribution-coverage/orphans")
async def get_attribution_orphans(
    project_id: str = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Return recent orphan token.consumed events for drill-down.

    Orphans are events where attribution_status is NULL or 'orphan'.
    No raw payloads or PII are included.
    """
    from projections.api.queries.token_attribution import orphan_events

    try:
        events = orphan_events(project_id=project_id, limit=limit)
        return {
            "schema": "dream_studio.attribution_orphans.v1",
            "project_id": project_id,
            "orphan_count": len(events),
            "limit": limit,
            "orphans": events,
            "generated_at": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching orphan events: {exc}")


# ---------------------------------------------------------------------------
# Memory Surface — Chain 7 dashboard panel (18.4.4)
# ---------------------------------------------------------------------------


@router.get("/memory-surface")
async def get_memory_surface(project_id: str = Query(default=None)) -> dict:
    """Return memory_entries summary for the Chain 7 dashboard panel.

    Shows total entries, surfaced-this-session count, source type breakdown,
    and the 10 most recently surfaced entries. Read-only.
    """
    from core.config.database import get_connection

    try:
        conn = get_connection()
        conn.row_factory = __import__("sqlite3").Row
        try:
            total = conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0]

            surfaced = conn.execute(
                "SELECT COUNT(*) FROM memory_entries WHERE intelligence_surfaced_at IS NOT NULL"
            ).fetchone()[0]

            source_rows = conn.execute(
                "SELECT source, COUNT(*) cnt FROM memory_entries GROUP BY source ORDER BY cnt DESC"
            ).fetchall()
            source_types = {r["source"]: r["cnt"] for r in source_rows}

            recent_rows = conn.execute(
                "SELECT memory_id, content, importance, category, intelligence_surfaced_at"
                " FROM memory_entries"
                " WHERE intelligence_surfaced_at IS NOT NULL"
                " ORDER BY intelligence_surfaced_at DESC LIMIT 10"
            ).fetchall()

            def _label(imp: float) -> str:
                if imp >= 0.8:
                    return "high"
                if imp >= 0.5:
                    return "medium"
                return "low"

            recently_surfaced = [
                {
                    "memory_id": r["memory_id"],
                    "content": (r["content"] or "")[:150],
                    "importance": r["importance"],
                    "importance_label": _label(r["importance"] or 0.5),
                    "category": r["category"],
                    "surfaced_at": r["intelligence_surfaced_at"],
                }
                for r in recent_rows
            ]
        finally:
            conn.close()

        return {
            "schema": "dream_studio.memory_surface.v1",
            "project_id": project_id,
            "total_entries": total,
            "surfaced_this_session": surfaced,
            "source_types": source_types,
            "recently_surfaced": recently_surfaced,
            "generated_at": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching memory surface: {exc}")


# ---------------------------------------------------------------------------
# Attribution Breakouts — token usage aggregated by dimension (18.x)
# ---------------------------------------------------------------------------


@router.get("/attribution-breakouts")
async def get_attribution_breakouts() -> dict:
    """Return token usage aggregated by project, milestone, task, skill, and agent.

    WO-DBA-DROP (migration 137): reads the DuckDB aggregate_metrics.db
    token_usage_records view (derived from canonical token.consumed events via
    events_fact) instead of the retired SQLite token_usage_records table.
    business_projects.name enrichment stays on SQLite (two-connection pattern
    also used in projections/api/routes/analytics.py). If the analytics store
    or view is unavailable, returns ``data_status="empty"`` with empty lists —
    never a 500.
    """
    import sqlite3 as _sqlite3
    from core.analytics.duckdb_store import AnalyticsStoreMissingError, connect_analytics
    from core.config.database import get_connection
    from projections.api.routes.sqlite_schema import object_exists

    _EMPTY = {
        "schema": "dream_studio.attribution_breakouts.v1",
        "total_tokens": 0,
        "total_records": 0,
        "by_project": [],
        "by_milestone": [],
        "by_task": [],
        "by_skill": [],
        "by_agent": [],
        "data_status": "empty",
        "generated_at": datetime.now().isoformat(),
    }

    try:
        duck_conn = connect_analytics(read_only=True)
        try:
            # Totals
            totals_row = duck_conn.execute(
                "SELECT"
                "  COALESCE(SUM(COALESCE(input_tokens,0) + COALESCE(output_tokens,0)), 0) AS total_tokens,"
                "  COUNT(*) AS total_records"
                " FROM token_usage_records"
            ).fetchone()
            total_tokens = int((totals_row[0] if totals_row else 0) or 0)
            total_records = int((totals_row[1] if totals_row else 0) or 0)

            def _breakout(column: str) -> list[dict]:
                rows = duck_conn.execute(
                    f"SELECT {column} AS key,"
                    f"  SUM(COALESCE(input_tokens,0) + COALESCE(output_tokens,0)) AS tokens,"
                    f"  COUNT(*) AS records"
                    f" FROM token_usage_records"
                    f" WHERE {column} IS NOT NULL"
                    f" GROUP BY {column}"
                    f" ORDER BY tokens DESC"
                    f" LIMIT 20"
                ).fetchall()
                return [
                    {
                        column: row[0],
                        "tokens": int(row[1] or 0),
                        "records": int(row[2] or 0),
                    }
                    for row in rows
                ]

            by_project = _breakout("project_id")
            by_milestone = _breakout("milestone_id")
            by_task = _breakout("task_id")
            by_skill = _breakout("skill_id")
            by_agent = _breakout("agent_id")
        except Exception:
            # Fresh analytics store: the projection runner has not created the
            # compat views yet. Empty shape, never a 500.
            return _EMPTY
        finally:
            duck_conn.close()

        # Enrich by_project rows with human-readable project names from SQLite.
        # Falls back to None per row if business_projects doesn't exist or lookup fails.
        try:
            sql_conn = get_connection()
            sql_conn.row_factory = _sqlite3.Row
            try:
                if by_project and object_exists(sql_conn, "business_projects"):
                    project_ids = [row["project_id"] for row in by_project]
                    placeholders = ",".join("?" * len(project_ids))
                    name_rows = sql_conn.execute(
                        f"SELECT project_id, name FROM business_projects"
                        f" WHERE project_id IN ({placeholders})",
                        project_ids,
                    ).fetchall()
                    name_map: dict[str, str | None] = {
                        r["project_id"]: r["name"] for r in name_rows
                    }
                    by_project = [
                        {
                            "project_id": row["project_id"],
                            "project_name": name_map.get(row["project_id"]),
                            "tokens": row["tokens"],
                            "records": row["records"],
                        }
                        for row in by_project
                    ]
                else:
                    by_project = [{**row, "project_name": None} for row in by_project]
            finally:
                sql_conn.close()
        except Exception:
            by_project = [{**row, "project_name": None} for row in by_project]

        return {
            "schema": "dream_studio.attribution_breakouts.v1",
            "total_tokens": total_tokens,
            "total_records": total_records,
            "by_project": by_project,
            "by_milestone": by_milestone,
            "by_task": by_task,
            "by_skill": by_skill,
            "by_agent": by_agent,
            "data_status": "ok" if total_records > 0 else "empty",
            "generated_at": datetime.now().isoformat(),
        }
    except AnalyticsStoreMissingError:
        # Analytics store not built yet — honest empty shape, never a fabricated store.
        return _EMPTY
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error computing attribution breakouts: {exc}")
