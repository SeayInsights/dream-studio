"""Phase 19.9 Extension Dashboard API routes.

Added to intelligence router under /api/v1/intelligence/extensions/.
Four panels: Personalization Timeline, Patterns Awaiting Review,
Extension Health, Experimental Extensions.
Operator framing: "Changes Applied to Your Builds" language throughout.
"""

from __future__ import annotations

import json as _json
import sqlite3
from datetime import datetime, UTC
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config.database import get_connection

router = APIRouter()

# ── Helpers ───────────────────────────────────────────────────────────────


def _ext_tables_missing(conn: sqlite3.Connection) -> bool:
    """Graceful fallback when Phase 19 tables don't exist yet."""
    try:
        conn.execute("SELECT 1 FROM ds_user_extensions LIMIT 1")
        return False
    except sqlite3.OperationalError:
        return True


def _parse_vd(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return _json.loads(raw)
    except Exception:
        return {}


def _health_tier(ext: dict[str, Any]) -> str:
    current = ext.get("current_eval_score")
    baseline = ext.get("baseline_eval_score")
    if current is None or baseline is None or baseline == 0:
        return "untracked"
    ratio = current / baseline
    if ratio >= 1.0:
        return "improving"
    if ratio >= 0.95:
        return "steady"
    return "degrading"


def _type_label(ext_type: str) -> str:
    return {
        "threshold_override": "suppression",
        "option_override": "threshold adjustment",
        "gap_filler": "new detection rule",
        "mode_addition": "new skill mode",
        "example": "usage guide",
        "trigger_alias": "routing alias",
    }.get(ext_type, ext_type)


# ── API endpoints ─────────────────────────────────────────────────────────


@router.get("/extensions")
async def list_extensions(
    status: str = "active",
    limit: int = 50,
) -> dict[str, Any]:
    """List extensions filtered by status.

    Panel usage:
      Personalization Timeline → status=active
      Experimental Extensions → status=experimental
      All panels can filter.
    """
    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        if _ext_tables_missing(conn):
            return {"extensions": [], "count": 0, "status_filter": status}
        valid = ("proposed", "experimental", "active", "dismissed", "deprecated")
        sf = status if status in valid else "active"
        rows = conn.execute(
            "SELECT * FROM ds_user_extensions WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (sf, limit),
        ).fetchall()
        exts = []
        for r in rows:
            e = dict(r)
            e["health_tier"] = _health_tier(e)
            e["type_label"] = _type_label(e.get("extension_type", ""))
            e["validation_summary"] = _parse_vd(e.get("validation_detail"))
            exts.append(e)
        return {"extensions": exts, "count": len(exts), "status_filter": sf}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Extensions query failed: {str(ex)}")
    finally:
        conn.close()


@router.get("/extensions/health")
async def get_extension_health() -> dict[str, Any]:
    """Aggregated health view — Extension Health panel.

    Operator framing: which customizations are improving / holding / degrading.
    """
    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        if _ext_tables_missing(conn):
            return {"improving": [], "steady": [], "degrading": [], "untracked": []}
        rows = conn.execute(
            "SELECT * FROM ds_user_extensions WHERE status = 'active' ORDER BY created_at DESC"
        ).fetchall()
        buckets: dict[str, list[dict[str, Any]]] = {
            "improving": [],
            "steady": [],
            "degrading": [],
            "untracked": [],
        }
        for r in rows:
            e = dict(r)
            e["type_label"] = _type_label(e.get("extension_type", ""))
            buckets[_health_tier(e)].append(e)
        return buckets
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Health query failed: {str(ex)}")
    finally:
        conn.close()


@router.get("/extensions/summary")
async def get_extension_summary() -> dict[str, Any]:
    """Summary counts for the Adaptation tab header widget."""
    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        if _ext_tables_missing(conn):
            return {
                "extensions": {"total": 0, "active": 0, "experimental": 0, "proposed": 0},
                "friction_signals": {"total": 0, "classified": 0, "pending_review": 0},
            }
        ext_rows = conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM ds_user_extensions GROUP BY status"
        ).fetchall()
        ext_counts = {r["status"]: r["cnt"] for r in ext_rows}

        sig_total = conn.execute("SELECT COUNT(*) FROM ds_friction_signals").fetchone()[0]
        sig_classified = conn.execute(
            "SELECT COUNT(*) FROM ds_friction_signals WHERE classified_as IS NOT NULL"
        ).fetchone()[0]
        sig_pending = conn.execute(
            "SELECT COUNT(*) FROM ds_friction_signals "
            "WHERE classified_as IS NOT NULL "
            "AND (classification_skipped IS NULL OR classification_skipped=0) "
            "AND extension_id IS NULL"
        ).fetchone()[0]
        return {
            "extensions": {
                "total": sum(ext_counts.values()),
                "active": ext_counts.get("active", 0),
                "experimental": ext_counts.get("experimental", 0),
                "proposed": ext_counts.get("proposed", 0),
            },
            "friction_signals": {
                "total": sig_total,
                "classified": sig_classified,
                "pending_review": sig_pending,
            },
        }
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Summary query failed: {str(ex)}")
    finally:
        conn.close()


@router.get("/extensions/{extension_id}/effect-summary")
async def get_extension_effect_summary(extension_id: str) -> dict[str, Any]:
    """What has this extension actually done since going active?

    Personalization: finding count (can be derived from findings table).
    Capability/onboarding: honest 'not yet tracked' — no instrumentation exists.
    This avoids claiming metrics that don't exist.
    """
    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        if _ext_tables_missing(conn):
            raise HTTPException(status_code=503, detail="Extension tables not yet available")
        row = conn.execute(
            "SELECT extension_id, skill_id, extension_type, status, user_confirmed_at "
            "FROM ds_user_extensions WHERE extension_id = ?",
            (extension_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Extension {extension_id!r} not found")
        e = dict(row)
        ext_type = e.get("extension_type", "")
        if ext_type in ("threshold_override", "option_override"):
            try:
                dismissed_since = conn.execute(
                    "SELECT COUNT(*) FROM findings "
                    "WHERE dismissed_at >= ? AND introduced_by_skill_id = ?",
                    (e.get("user_confirmed_at") or "1970-01-01", e.get("skill_id", "")),
                ).fetchone()[0]
            except sqlite3.OperationalError:
                dismissed_since = 0
            return {
                "extension_id": extension_id,
                "tracked": True,
                "effect_type": "findings_suppressed",
                "count": dismissed_since,
                "description": f"{dismissed_since} findings filtered since extension activated",
            }
        return {
            "extension_id": extension_id,
            "tracked": False,
            "effect_type": ext_type,
            "description": (
                "Effect tracking not yet instrumented for this extension type — "
                "active and being applied"
            ),
        }
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
    finally:
        conn.close()


@router.get("/extensions/{extension_id}")
async def get_extension_detail(extension_id: str) -> dict[str, Any]:
    """Full extension detail with validation timeline."""
    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        if _ext_tables_missing(conn):
            raise HTTPException(status_code=503, detail="Extension tables not yet available")
        row = conn.execute(
            "SELECT * FROM ds_user_extensions WHERE extension_id = ?", (extension_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Extension {extension_id!r} not found")
        e = dict(row)
        e["health_tier"] = _health_tier(e)
        e["type_label"] = _type_label(e.get("extension_type", ""))
        e["validation_detail_parsed"] = _parse_vd(e.get("validation_detail"))
        return e
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
    finally:
        conn.close()


class RevertRequest(BaseModel):
    reason: str = ""


@router.post("/extensions/{extension_id}/revert")
async def revert_extension(extension_id: str, body: RevertRequest) -> dict[str, Any]:
    """Revert (dismiss) an active extension.

    The revert button is the most important UX control in Phase 19 — it surfaces
    operator authority over the adaptive learning system.

    After revert:
      - status = 'deprecated'
      - validation_detail.revert records reason + timestamp
      - ExtensionLoader cache invalidated
      - Next dispatch ignores this extension
    """
    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        if _ext_tables_missing(conn):
            raise HTTPException(status_code=503, detail="Extension tables not yet available")
        row = conn.execute(
            "SELECT * FROM ds_user_extensions WHERE extension_id = ?", (extension_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Extension {extension_id!r} not found")
        e = dict(row)
        detail = _parse_vd(e.get("validation_detail"))
        detail["revert"] = {
            "reverted_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "reason": body.reason or "operator reverted via dashboard",
            "previous_status": e.get("status"),
        }
        conn.execute(
            "UPDATE ds_user_extensions SET status = 'deprecated', validation_detail = ? "
            "WHERE extension_id = ?",
            (_json.dumps(detail), extension_id),
        )
        conn.commit()
        try:
            from core.expansion.loader import ExtensionLoader

            ExtensionLoader.invalidate_cache()
        except Exception:
            pass
        return {
            "extension_id": extension_id,
            "status": "deprecated",
            "reverted_at": detail["revert"]["reverted_at"],
        }
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
    finally:
        conn.close()
