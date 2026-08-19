"""Open UNVERIFIED-risk aggregation across a project's work orders.

WO-FALSIFY-FIRST-PASS task 2 (the aggregation half, spawned as gap WO 5ed752d7
by this stage's own verify): the per-WO ledger made residual risk *recordable*,
but risk that only appears when you happen to close one work order is still
effectively invisible. This aggregates every open ledger for a project so
``ds project state`` — where operators and agents orient — answers "what does
this project know it has not verified?" in one place.

Read-only. Never raises: an unreadable ledger is reported as unreadable rather
than counted as zero, because "we could not read it" and "there is no risk" are
different facts.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def project_unverified_summary(
    project_id: str, *, planning_root: Path, db_path: Path
) -> dict[str, Any]:
    """Aggregate open UNVERIFIED risks across a project's non-closed work orders.

    Returns::

        {"total": int,                    # UNVERIFIED scenarios across those WOs
         "work_orders": [                 # newest-first, only WOs with entries
            {"work_order_id": str, "title": str, "count": int,
             "classes": [scenario_class, ...]}],
         "unreadable": [ {"work_order_id": str, "reason": str} ]}

    Closed work orders are excluded: their residual risk was surfaced at close
    and accepted. Open ones are where an unverified worst case still matters.
    """
    from core.work_orders.verify_persist import read_unverified_ledger

    summary: dict[str, Any] = {"total": 0, "work_orders": [], "unreadable": []}
    try:
        conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        summary["note"] = "authority DB unavailable"
        return summary
    try:
        rows = conn.execute(
            "SELECT work_order_id, title FROM business_work_orders"
            " WHERE project_id = ? AND status NOT IN ('closed', 'cancelled', 'deleted')"
            " ORDER BY updated_at DESC",
            (project_id,),
        ).fetchall()
    except sqlite3.Error:
        summary["note"] = "work-order query failed"
        return summary
    finally:
        conn.close()

    for work_order_id, title in rows:
        try:
            ledger = read_unverified_ledger(
                work_order_id, planning_root=planning_root, db_path=db_path
            )
        except Exception as exc:  # noqa: BLE001 - one bad ledger must not hide the rest
            summary["unreadable"].append(
                {"work_order_id": work_order_id, "reason": f"{type(exc).__name__}: {exc}"}
            )
            continue
        if ledger is None:
            continue
        if ledger.get("unreadable"):
            summary["unreadable"].append(
                {"work_order_id": work_order_id, "reason": ledger["unreadable"]}
            )
            continue
        entries = ledger.get("unverified") or []
        if not entries:
            continue
        summary["total"] += len(entries)
        summary["work_orders"].append(
            {
                "work_order_id": work_order_id,
                "title": title,
                "count": len(entries),
                "classes": sorted(
                    {e.get("scenario_class", "unknown") for e in entries if isinstance(e, dict)}
                ),
            }
        )
    return summary
