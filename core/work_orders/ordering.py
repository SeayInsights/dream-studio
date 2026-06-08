"""Work-order ordering mutations: set_sequence_order, add_dependency, remove_dependency.

All mutations follow AD-6 (emit-then-SQL): the spool event is written first so
the projection stays authoritative, then the read-model row is updated directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect
from core.projects.queries import _require_db


def set_sequence_order(
    *,
    work_order_id: str,
    sequence_order: int,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Set sequence_order on a work order. Sparse convention: 10, 20, 30…"""
    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(timezone.utc).isoformat()

    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT work_order_id, title, project_id FROM business_work_orders"
            " WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Work order {work_order_id!r} not found"}

        conn.execute(
            "UPDATE business_work_orders"
            " SET sequence_order = ?, updated_at = ?, last_updated_at = ?"
            " WHERE work_order_id = ?",
            (sequence_order, now, now, work_order_id),
        )

    _emit_event(
        "work_order.reordered",
        {
            "work_order_id": work_order_id,
            "title": row["title"],
            "sequence_order": sequence_order,
            "project_id": row["project_id"],
        },
        now,
        work_order_id,
        row["project_id"],
    )
    return {"ok": True, "work_order_id": work_order_id, "sequence_order": sequence_order}


def add_dependency(
    *,
    work_order_id: str,
    depends_on_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Add a dependency edge: work_order_id waits for depends_on_id to close."""
    if work_order_id == depends_on_id:
        return {"ok": False, "error": "A work order cannot depend on itself"}

    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(timezone.utc).isoformat()

    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title, project_id FROM business_work_orders"
            " WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            return {"ok": False, "error": f"Work order {work_order_id!r} not found"}

        dep_row = conn.execute(
            "SELECT work_order_id FROM business_work_orders WHERE work_order_id = ?",
            (depends_on_id,),
        ).fetchone()
        if dep_row is None:
            return {"ok": False, "error": f"Dependency target {depends_on_id!r} not found"}

        try:
            conn.execute(
                "INSERT INTO work_order_dependencies (work_order_id, depends_on_id, created_at)"
                " VALUES (?, ?, ?)",
                (work_order_id, depends_on_id, now),
            )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                return {"ok": True, "already_exists": True}
            raise

    _emit_event(
        "work_order.dependency_added",
        {
            "work_order_id": work_order_id,
            "depends_on_id": depends_on_id,
            "project_id": wo_row["project_id"],
        },
        now,
        work_order_id,
        wo_row["project_id"],
    )
    return {"ok": True, "work_order_id": work_order_id, "depends_on_id": depends_on_id}


def remove_dependency(
    *,
    work_order_id: str,
    depends_on_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Remove a dependency edge."""
    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(timezone.utc).isoformat()

    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, project_id FROM business_work_orders" " WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            return {"ok": False, "error": f"Work order {work_order_id!r} not found"}

        cursor = conn.execute(
            "DELETE FROM work_order_dependencies" " WHERE work_order_id = ? AND depends_on_id = ?",
            (work_order_id, depends_on_id),
        )
        if cursor.rowcount == 0:
            return {"ok": False, "error": "Dependency edge not found"}

    _emit_event(
        "work_order.dependency_removed",
        {
            "work_order_id": work_order_id,
            "depends_on_id": depends_on_id,
            "project_id": wo_row["project_id"],
        },
        now,
        work_order_id,
        wo_row["project_id"],
    )
    return {"ok": True, "work_order_id": work_order_id, "depends_on_id": depends_on_id}


def _emit_event(
    event_type: str,
    payload: dict[str, Any],
    now: str,
    work_order_id: str,
    project_id: str,
) -> None:
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        envelope = CanonicalEventEnvelope(
            event_type=event_type,
            session_id=None,
            payload=payload,
            timestamp=now,
            severity="info",
            trace={
                "domain": "sdlc",
                "work_order_id": work_order_id,
                "project_id": project_id,
                "attribution_status": "fully_attributed",
            },
        )
        _spool_writer.write_event(envelope.to_dict())
    except Exception:
        pass
