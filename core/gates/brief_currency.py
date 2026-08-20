"""Is the locked design brief still CURRENT? (WO-BRIEF-CURRENCY)

``design_brief_locked`` asked one question: does a row exist with
``status='locked'``. A brief locked in May satisfied it in August, after months of
UI work had moved the surfaces it describes. The gate proved *existence*, and
existence is not currency — so a UI work order could close against a design brief
that no longer described the design.

CURRENCY IS DERIVED FROM AUTHORITY STATE, not from the repo. The brief describes a
project's design surface, and the authority already records when that surface
moved: UI-class work orders closing. So "stale" means UI work closed after the
brief was locked, which needs no file introspection and therefore works identically
for an external project DS is only governing.

Rejected alternative, explicitly (the WO says so too): do NOT re-scope the brief
per work order. ``business_design_briefs`` is project-scoped on purpose. Giving
every UI work order its own brief would trade one defect for a worse one — a
proliferation of near-duplicate briefs, and no shared design language, which is
the entire point of having a brief.

THE ESCAPE HATCH IS A DECLARATION, NOT A FLAG. Where the surface moved but the
brief genuinely still holds, an operator declares reviewed-no-change — the same
idiom the docs-drift gates already use — and that declaration is recorded with its
own timestamp, so it ages exactly like a lock does. A boolean "ignore staleness"
would never age, and would quietly disable the gate forever.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# The work-order types whose closing means the design surface moved. `saas_feature`
# is included because it spans UI and API by definition; `api_endpoint`,
# `data_pipeline`, `infrastructure`, `deployment` and `documentation` are not, so a
# backend-only stretch of work does not stale a brief that still describes the UI.
_UI_TYPES = ("ui_component", "ui_page", "saas_feature")

_RNC_KEY_PREFIX = "brief_reviewed_no_change."


def _rnc_key(project_id: str) -> str:
    return f"{_RNC_KEY_PREFIX}{project_id}"


def declare_reviewed_no_change(
    project_id: str,
    *,
    note: str,
    when: str,
    db_path: Path | None = None,
) -> bool:
    """Record that the brief was reviewed against a moved surface and still holds.

    Stored in ``ds_config`` via the runtime-state helpers — no new table and no
    migration, the same pattern the main-CI cache and the delivery boundary use.
    Carries its own timestamp so the declaration AGES: further UI work after it
    stales the brief again, which a boolean override never would.
    """
    try:
        from core.runtime_state import db_write_runtime_state

        return db_write_runtime_state(
            _rnc_key(project_id),
            {"project_id": project_id, "reviewed_at": when, "note": note},
            db_path=db_path,
        )
    except Exception:
        return False


def _read_rnc(project_id: str, db_path: Path | None) -> dict[str, Any] | None:
    try:
        from core.runtime_state import db_read_runtime_state

        entry = db_read_runtime_state(_rnc_key(project_id), db_path=db_path)
        return entry if isinstance(entry, dict) else None
    except Exception:
        return None


def brief_currency(project_id: str, *, conn: Any, db_path: Path | None = None) -> dict[str, Any]:
    """``{current, exists, locked_at, effective_since, moved_by, reason}``.

    ``current`` is False when a locked brief exists but UI-class work has closed
    since it was locked (or since a later reviewed-no-change declaration).

    Fails OPEN — ``current=True`` with a reason — when currency cannot be
    determined: an unreadable table, a brief with no timestamp, a schema that
    predates this check. Refusing to close a UI work order because DS could not
    read its own bookkeeping would be a worse defect than the staleness this
    catches, and the existence half of the gate still applies either way.
    """
    result: dict[str, Any] = {
        "current": True,
        "exists": False,
        "locked_at": None,
        "effective_since": None,
        "moved_by": [],
        "reason": None,
    }
    try:
        row = conn.execute(
            "SELECT brief_id, updated_at, created_at FROM business_design_briefs"
            " WHERE project_id = ? AND status = 'locked'"
            " ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    except Exception as exc:  # noqa: BLE001 - unreadable bookkeeping must not block a close
        result["reason"] = f"brief currency undetermined: {type(exc).__name__}"
        return result
    if row is None:
        # Existence is the other half of the gate and is checked there; nothing to
        # judge the currency of.
        result["reason"] = "no locked brief for this project"
        return result

    result["exists"] = True
    locked_at = row[1] or row[2]
    if not isinstance(locked_at, str) or not locked_at:
        result["reason"] = "locked brief carries no timestamp — currency undeterminable"
        return result
    result["locked_at"] = locked_at

    effective = locked_at
    rnc = _read_rnc(project_id, db_path)
    if rnc and isinstance(rnc.get("reviewed_at"), str) and rnc["reviewed_at"] > effective:
        effective = rnc["reviewed_at"]
        result["reviewed_no_change_at"] = rnc["reviewed_at"]
        result["reviewed_no_change_note"] = rnc.get("note")
    result["effective_since"] = effective

    placeholders = ",".join("?" for _ in _UI_TYPES)
    try:
        moved = conn.execute(
            f"SELECT work_order_id, title, closed_at FROM business_work_orders"
            f" WHERE project_id = ? AND status = 'closed'"
            f"   AND work_order_type IN ({placeholders})"
            f"   AND closed_at IS NOT NULL AND closed_at > ?"
            f" ORDER BY closed_at DESC LIMIT 10",
            (project_id, *_UI_TYPES, effective),
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        result["reason"] = f"design-surface movement undetermined: {type(exc).__name__}"
        return result

    if not moved:
        return result

    result["current"] = False
    result["moved_by"] = [{"work_order_id": r[0], "title": r[1], "closed_at": r[2]} for r in moved]
    newest = moved[0]
    result["reason"] = (
        f"{len(moved)} UI-class work order(s) closed after the brief became effective"
        f" ({effective}); newest: {newest[1]!r} at {newest[2]}. The brief proves"
        " existence but not currency — re-lock it (ds-project:brief), or declare"
        " reviewed-no-change if the design language genuinely still holds."
    )
    return result


def currency_failure(project_id: str, *, conn: Any, db_path: Path | None = None) -> str | None:
    """Gate-facing wrapper: a failure string when the brief is stale, else None."""
    info = brief_currency(project_id, conn=conn, db_path=db_path)
    if info["current"] or not info["exists"]:
        return None
    return str(info["reason"])


def currency_evidence(project_id: str, *, conn: Any, db_path: Path | None = None) -> str:
    """A JSON evidence blob for the record — what was compared, and against what."""
    return json.dumps(brief_currency(project_id, conn=conn, db_path=db_path), indent=2)
