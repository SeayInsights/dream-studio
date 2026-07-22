"""Intelligence API - friction signals read API (Phase 19.2/19.3).

WO-GF-API-ROUTES: split out of intelligence.py.

Consumer contract for 19.3 Gap Classifier:
  GET /api/v1/intelligence/friction-signals -> list unclassified signals
  GET /api/v1/intelligence/friction-signals?signal_type=<type> -> filter
  GET /api/v1/intelligence/friction-signals/{signal_id} -> single signal

NOTE: /friction-signals/classifications MUST stay decorated before
/friction-signals/{signal_id} in this file — FastAPI matches routes in
registration order and the parameterized route would otherwise swallow
GET /friction-signals/classifications.
"""

from __future__ import annotations

from fastapi import HTTPException
from typing import Any
import sqlite3

from core.config.database import get_connection

from .intelligence_router import router


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
) -> dict[str, Any]:
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

        params: list[Any] = []
        conditions: list[str] = []

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
) -> dict[str, Any]:
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

        params: list[Any] = [min_confidence]
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
        by_type: dict[str, int] = {}
        for s in signals:
            t = s.get("classified_as") or "unclassified"
            by_type[t] = by_type.get(t, 0) + 1

        return {"signals": signals, "by_type": by_type, "count": len(signals)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classifications query failed: {str(e)}")
    finally:
        conn.close()


@router.get("/friction-signals/{signal_id}")
async def get_friction_signal(signal_id: str) -> dict[str, Any]:
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
