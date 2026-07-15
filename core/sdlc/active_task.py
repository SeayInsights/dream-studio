"""Active task context: persist and retrieve the current operator task pointer."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, UTC
from pathlib import Path

ACTIVE_TASK_PATH_ENV = "DS_ACTIVE_TASK_PATH"


@dataclass(frozen=True)
class ActiveTaskContext:
    task_id: str
    work_order_id: str
    milestone_id: str
    project_id: str
    set_at: str  # ISO timestamp


def _active_task_path() -> Path:
    """Canonical path resolver, env-overridable via DS_ACTIVE_TASK_PATH."""
    override = os.environ.get(ACTIVE_TASK_PATH_ENV)
    if override:
        return Path(override)
    return Path.home() / ".dream-studio" / "state" / "active_task.json"


def _use_authority() -> bool:
    """WO-FILESDB-P2: use the authority raw_runtime_state row only for the pure
    default — a DS_ACTIVE_TASK_PATH override means the caller wants that file."""
    return not os.environ.get(ACTIVE_TASK_PATH_ENV)


def set_active_task(task_id: str) -> ActiveTaskContext:
    """Resolves the full SDLC chain from task_id and persists to disk.

    Raises ValueError if task_id doesn't exist in business_tasks or if its
    parent work_order/milestone/project can't be resolved.
    """
    from core.config.database import _default_db_path
    from core.event_store.studio_db import _connect

    db_path = _default_db_path()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT t.task_id, t.work_order_id, t.project_id, wo.milestone_id"
            " FROM business_tasks t"
            " LEFT JOIN business_work_orders wo ON t.work_order_id = wo.work_order_id"
            " WHERE t.task_id = ?",
            (task_id,),
        ).fetchone()

    if row is None:
        raise ValueError(f"Task not found: {task_id}")

    work_order_id = row["work_order_id"]
    project_id = row["project_id"]

    if work_order_id is None or project_id is None:
        raise ValueError(f"Task {task_id} has no parent work order — cannot resolve SDLC chain")

    milestone_id = row["milestone_id"] or ""

    ctx = ActiveTaskContext(
        task_id=task_id,
        work_order_id=work_order_id,
        milestone_id=milestone_id,
        project_id=project_id,
        set_at=datetime.now(UTC).isoformat(),
    )

    # WO-FILESDB-P2: persist to the authority row first (pure default); the legacy
    # JSON file when a DS_ACTIVE_TASK_PATH override is set or the raw_runtime_state
    # table is absent (migration 146 unreleased).
    if _use_authority():
        from core.runtime_state import db_write_runtime_state

        if db_write_runtime_state("active_task", asdict(ctx)):
            return ctx

    path = _active_task_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(ctx)), encoding="utf-8")

    return ctx


def get_active_task() -> ActiveTaskContext | None:
    """Returns the current active task context, or None if none set
    or the file is missing/corrupt.
    """
    # WO-FILESDB-P2: authority row first (pure default); the legacy JSON file when
    # a DS_ACTIVE_TASK_PATH override is set or the table/row is absent.
    data: dict | None = None
    if _use_authority():
        from core.runtime_state import db_read_runtime_state

        data = db_read_runtime_state("active_task")
    if data is None:
        path = _active_task_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    try:
        return ActiveTaskContext(**data)
    except (TypeError, ValueError):
        return None


def clear_active_task() -> bool:
    """Removes the active task pointer. Returns True if one existed and was
    removed, False if none existed.
    """
    # WO-FILESDB-P2: clear the authority row (pure default) and/or the legacy JSON.
    removed = False
    if _use_authority():
        from core.runtime_state import db_clear_runtime_state

        removed = db_clear_runtime_state("active_task")
    path = _active_task_path()
    if path.exists():
        path.unlink()
        removed = True
    return removed
