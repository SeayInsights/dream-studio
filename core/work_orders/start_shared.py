"""Shared constants and DB helpers for work-order start.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/start.py``. Holds the
UI-work-order-type / blocking-severity constants (some now dead but kept
verbatim + re-exported), the milestone sequence-order predecessor check, and
the authority-DB path resolver. No logic changes — extracted verbatim from
the original module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect

from .models import TERMINAL_WO_STATUSES, terminal_wo_status_placeholders

_UI_WO_TYPES: frozenset[str] = frozenset({"ui_component", "ui_page"})

_BLOCKING_SEVERITIES: frozenset[str] = frozenset({"critical", "high"})
_BLOCKING_STATUSES: frozenset[str] = frozenset({"open"})


# _check_preflight_gate: removed migration 148 (WO-SCHEMALEAN) — read the dropped
# business_work_order_preflights table (unwired, permanent no-op).


def _check_sequence_order(
    work_order_id: str,
    db_path: Path,
) -> list[dict[str, Any]]:
    """Return out-of-sequence predecessors in the same milestone.

    A predecessor is any WO in the same milestone with a lower sequence_order
    that is not yet in a terminal state (TERMINAL_WO_STATUSES — closed, cancelled,
    or deleted). Returns empty list when the table doesn't exist, the WO has no
    milestone, or no sequence_order is set.
    """
    try:
        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT milestone_id, sequence_order FROM business_work_orders"
                " WHERE work_order_id = ?",
                (work_order_id,),
            ).fetchone()
            if row is None or row[0] is None or row[1] is None:
                return []
            milestone_id, my_seq = row
            blockers = conn.execute(
                "SELECT work_order_id, title, sequence_order FROM business_work_orders"
                " WHERE milestone_id = ? AND work_order_id != ?"
                " AND sequence_order < ?"
                f" AND status NOT IN ({terminal_wo_status_placeholders()})"
                " ORDER BY sequence_order ASC",
                (milestone_id, work_order_id, my_seq, *TERMINAL_WO_STATUSES),
            ).fetchall()
    except Exception:
        return []
    return [{"work_order_id": r[0], "title": r[1], "sequence_order": r[2]} for r in blockers]


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    # Lazy import via ds.py — see core.projects.queries._require_db for rationale.
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")
    return paths.sqlite_path
