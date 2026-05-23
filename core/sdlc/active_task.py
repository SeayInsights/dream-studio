"""Active task context: persist and retrieve the current operator task pointer."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
        set_at=datetime.now(timezone.utc).isoformat(),
    )

    path = _active_task_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(ctx)), encoding="utf-8")

    return ctx


def get_active_task() -> Optional[ActiveTaskContext]:
    """Returns the current active task context, or None if none set
    or the file is missing/corrupt.
    """
    path = _active_task_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ActiveTaskContext(**data)
    except Exception:
        return None


def clear_active_task() -> bool:
    """Removes the active task file. Returns True if a file was
    removed, False if no file existed.
    """
    path = _active_task_path()
    if path.exists():
        path.unlink()
        return True
    return False
