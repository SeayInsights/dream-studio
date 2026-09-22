"""Milestone mutations: create milestone.

Skills, workflows, and hooks should import these directly instead of
shelling out to raw SQL or CLI commands. Each function returns a dict;
the CLI wrapper in `interfaces/cli/ds.py` is responsible for serialization.
"""

from __future__ import annotations

import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")
    return paths.sqlite_path


#: The shortest REAL milestone description on the live authority is 54 characters
#: (89 of them, measured 2026-09-21). The only two below that are the literal
#: string "probe" from test fixtures. 50 refuses those and admits every genuine
#: description, including the terse ones.
_MIN_DESCRIPTION_CHARS = 50


def create_milestone(
    *,
    project_id: str,
    title: str,
    description: str = "",
    order_index: int = 0,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Insert a new milestone row for a project.

    Returns::

        {"ok": True, "milestone_id": str, "project_id": str,
         "title": str, "status": "pending"}

    or on missing project::

        {"ok": False, "error": "Project not found: <id>"}
    """

    # A MILESTONE IS A PROMPT, like the work orders and tasks beneath it. The
    # hierarchy is a prompt chain: a task is a specific instruction, a work order
    # is the goal those instructions add up to, a milestone is the goal those work
    # orders add up to. A milestone with only a title gives every work order under
    # it nothing to derive its own goal from.
    #
    # Measured on the authority 2026-09-21: 8 of 97 milestones had no description,
    # and the floor comes from the same measurement rather than from taste. Of the
    # 89 that did, the two shortest are both the literal string "probe" from test
    # fixtures; the shortest real one is 54 characters. 50 refuses the probes and
    # admits every genuine description, including the terse ones.
    #
    # Deliberately a floor and not a rubric -- a check that graded prompt quality
    # would be arguing with the author. This only refuses an absence.
    _description = (description or "").strip()
    if len(_description) < _MIN_DESCRIPTION_CHARS:
        return {
            "ok": False,
            "error": (
                "description is required: a milestone is the prompt the work orders"
                " under it answer to, so it must say what it is for (at least"
                f" {_MIN_DESCRIPTION_CHARS} characters; got {len(_description)})."
            ),
        }

    db_path = _require_db(source_root, dream_studio_home)
    milestone_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT project_id FROM business_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Project not found: {project_id}"}
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="milestone.created",
                session_id=None,
                payload={
                    "title": title,
                    "description": description,
                    "order_index": order_index,
                    "status": "pending",
                },
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "project_id": project_id,
                    "milestone_id": milestone_id,
                    "attribution_status": "fully_attributed",
                },
            ).to_dict()
        )
    except Exception:
        pass

    try:
        from core.projections.runner import sync_tick as _sync_tick

        _sync_tick()
    except Exception:
        pass

    return {
        "ok": True,
        "milestone_id": milestone_id,
        "project_id": project_id,
        "title": title,
        "status": "pending",
    }
