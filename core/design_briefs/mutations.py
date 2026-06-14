"""Design-brief mutations: create, field updates, design-system selection."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
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

    db_path = _require_db(source_root, dream_studio_home)
    brief_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="design_brief.created",
                session_id=None,
                payload={"brief_id": brief_id, "project_id": project_id, "status": "draft"},
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
    except Exception:
        pass
    # DesignBriefProjection applies the INSERT from design_brief.created.
    # No direct write here — projection is the sole writer.
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
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT brief_id, project_id FROM business_design_briefs WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Brief not found: {brief_id}"}
        _project_id = row[1]
        try:
            import spool.writer as _spool_writer

            from canonical.events.envelope import CanonicalEventEnvelope

            _spool_writer.write_event(
                CanonicalEventEnvelope(
                    event_type="design_brief.locked",
                    session_id=None,
                    payload={"brief_id": brief_id},
                    timestamp=now,
                    severity="info",
                    trace={
                        "domain": "sdlc",
                        "project_id": _project_id,
                        "brief_id": brief_id,
                        "attribution_status": "fully_attributed",
                    },
                ).to_dict()
            )
        except Exception:
            pass
        # DesignBriefProjection applies status='locked' from the design_brief.locked event.
        # No direct UPDATE here — projection is the sole writer (Phase 18.2 Fix #2 contract).
    return {"ok": True, "brief_id": brief_id, "status": "locked", "locked_at": now}


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
    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, project_id FROM business_design_briefs WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Brief not found: {brief_id}"}
        if row[0] == "locked":
            return {"ok": False, "error": "Brief is locked and cannot be updated"}
        _project_id = row[1]
        try:
            import spool.writer as _spool_writer

            from canonical.events.envelope import CanonicalEventEnvelope

            _spool_writer.write_event(
                CanonicalEventEnvelope(
                    event_type="design_brief.updated",
                    session_id=None,
                    payload={"brief_id": brief_id, "field": field, "new_value": value},
                    timestamp=now,
                    severity="info",
                    trace={
                        "domain": "sdlc",
                        "project_id": _project_id,
                        "brief_id": brief_id,
                        "attribution_status": "fully_attributed",
                    },
                ).to_dict()
            )
        except Exception:
            pass
        # DesignBriefProjection applies the field update from design_brief.updated.
        # No direct UPDATE here — projection is the sole writer.
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
    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, project_id FROM business_design_briefs WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Brief not found: {brief_id}"}
        if row[0] == "locked":
            return {"ok": False, "error": "Brief is locked and cannot be updated"}
        _project_id = row[1]
        try:
            import spool.writer as _spool_writer

            from canonical.events.envelope import CanonicalEventEnvelope

            _spool_writer.write_event(
                CanonicalEventEnvelope(
                    event_type="design_brief.updated",
                    session_id=None,
                    payload={
                        "brief_id": brief_id,
                        "field": "design_system",
                        "new_value": system_name,
                    },
                    timestamp=now,
                    severity="info",
                    trace={
                        "domain": "sdlc",
                        "project_id": _project_id,
                        "brief_id": brief_id,
                        "attribution_status": "fully_attributed",
                    },
                ).to_dict()
            )
        except Exception:
            pass
        # DesignBriefProjection applies design_system from design_brief.updated.
        # No direct UPDATE here — projection is the sole writer.
    return {"ok": True, "brief_id": brief_id, "design_system": system_name}
