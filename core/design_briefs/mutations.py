"""Design-brief mutations: create, field updates, design-system selection."""

from __future__ import annotations

import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect

VALID_DESIGN_SYSTEMS: frozenset[str] = frozenset(
    [
        "tech-minimal",
        "editorial-modern",
        "brutalist-bold",
        "playful-rounded",
        "executive-clean",
    ]
)

BRIEF_UPDATABLE_FIELDS: frozenset[str] = frozenset(
    [
        "purpose",
        "audience",
        "tone",
        "design_system",
        "font_pairing",
        "brand_tokens",
        "raw_output",
    ]
)


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    # Lazy import via ds.py — see core.projects.queries._require_db for rationale.
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")
    return paths.sqlite_path


def _emit(
    event_type: str, *, brief_id: str, project_id: str, payload: dict[str, Any], now: str
) -> None:
    """Write one design_brief.* event to the spool, then project it before returning.

    The mutations are emit-only (DesignBriefProjection is the sole writer of
    business_design_briefs), but ``ds design-brief ...`` is a one-shot process and no
    daemon is guaranteed: without the tick, ``create`` printed "Draft brief created"
    while the row never existed, so the next ``show``/``lock``/``update`` reported
    "Brief not found". Same emit-then-tick as core.clients.mutations._emit (Pattern C).

    A failed write is NOT swallowed: reporting a brief that was never emitted as
    created is exactly the defect this exists to prevent.
    """
    import spool.writer as _spool_writer

    from canonical.events.envelope import CanonicalEventEnvelope
    from core.projections.runner import sync_tick

    _spool_writer.write_event(
        CanonicalEventEnvelope(
            event_type=event_type,
            session_id=None,
            payload=payload,
            timestamp=now,
            severity="info",
            trace={
                "domain": "sdlc",
                "project_id": project_id,
                "brief_id": brief_id,
                "attribution_status": "fully_attributed",
            },
        ).to_dict()
    )
    sync_tick()


def _brief_row(db_path: Path, brief_id: str) -> tuple[Any, ...] | None:
    """``(status, project_id)`` for a brief, or None when no such brief is projected."""
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT status, project_id FROM business_design_briefs WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()


def create_design_brief(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Insert a fresh draft design brief for ``project_id``.

    Returns::

        {"ok": True, "brief_id": str, "project_id": str,
         "status": "draft", "created_at": str,
         "next_step": "Invoke website:discover with --work-order <wo_id> ..."}
    """

    db_path = _require_db(source_root, dream_studio_home)  # DB must exist before emitting
    # A brief for a project that is not registered can never materialize (the projection's
    # foreign key dead-letters it), so refuse it here rather than print "created".
    with _connect(db_path) as conn:
        known = conn.execute(
            "SELECT 1 FROM business_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
    if known is None:
        return {"ok": False, "error": f"Project not found: {project_id}"}
    brief_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    try:
        _emit(
            "design_brief.created",
            brief_id=brief_id,
            project_id=project_id,
            payload={"brief_id": brief_id, "project_id": project_id, "status": "draft"},
            now=now,
        )
    except Exception as exc:  # noqa: BLE001 - reported, never reported as success
        return {"ok": False, "error": f"design_brief.created not emitted: {exc}"}
    return {
        "ok": True,
        "brief_id": brief_id,
        "project_id": project_id,
        "status": "draft",
        "created_at": now,
        "next_step": ("Invoke website:discover with --work-order <wo_id> to populate the brief"),
    }


def lock_design_brief(
    *,
    brief_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Mark a design brief as ``locked`` so downstream gates can pass.

    Returns::

        {"ok": True, "brief_id": str, "status": "locked", "locked_at": str}

    or on missing brief::

        {"ok": False, "error": "Brief not found: <id>"}
    """

    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(UTC).isoformat()
    row = _brief_row(db_path, brief_id)
    if row is None:
        return {"ok": False, "error": f"Brief not found: {brief_id}"}
    try:
        _emit(
            "design_brief.locked",
            brief_id=brief_id,
            project_id=row[1],
            payload={"brief_id": brief_id},
            now=now,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"design_brief.locked not emitted: {exc}"}
    return {"ok": True, "brief_id": brief_id, "status": "locked", "locked_at": now}


def _emit_field_update(
    *,
    brief_id: str,
    field: str,
    value: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> dict[str, Any] | None:
    """Emit one field update on a draft brief: the error dict, or None on success."""
    db_path = _require_db(source_root, dream_studio_home)
    row = _brief_row(db_path, brief_id)
    if row is None:
        return {"ok": False, "error": f"Brief not found: {brief_id}"}
    if row[0] == "locked":
        return {"ok": False, "error": "Brief is locked and cannot be updated"}
    try:
        _emit(
            "design_brief.updated",
            brief_id=brief_id,
            project_id=row[1],
            payload={"brief_id": brief_id, "field": field, "new_value": value},
            now=datetime.now(UTC).isoformat(),
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"design_brief.updated not emitted: {exc}"}
    return None


def update_design_brief_field(
    *,
    brief_id: str,
    field: str,
    value: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    if field not in BRIEF_UPDATABLE_FIELDS:
        return {
            "ok": False,
            "error": (f"Unknown field: {field}. Valid fields: {sorted(BRIEF_UPDATABLE_FIELDS)}"),
        }
    failure = _emit_field_update(
        brief_id=brief_id,
        field=field,
        value=value,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if failure is not None:
        return failure
    return {"ok": True, "brief_id": brief_id, "field": field, "value": value}


def set_design_system(
    *,
    brief_id: str,
    system_name: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    if system_name not in VALID_DESIGN_SYSTEMS:
        return {
            "ok": False,
            "error": (
                f"Invalid design system: {system_name}. "
                f"Valid values: {sorted(VALID_DESIGN_SYSTEMS)}"
            ),
        }
    failure = _emit_field_update(
        brief_id=brief_id,
        field="design_system",
        value=system_name,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if failure is not None:
        return failure
    return {"ok": True, "brief_id": brief_id, "design_system": system_name}
