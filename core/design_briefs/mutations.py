"""Design-brief mutations: create, field updates, design-system selection."""

from __future__ import annotations

import os
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


def _same_file(a: Path, b: Path) -> bool:
    return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))


def _home_disagreement(db_path: Path) -> str | None:
    """Why the projection would not land in ``db_path``, or None when it would.

    The event goes to the spool the ENVIRONMENT names, the ingest reads the database the
    environment names, and the projection uses the process-wide DatabaseRuntime (whichever
    database it first opened). None of them takes this call's ``dream_studio_home``. So a
    call for home B in a process whose environment says home A emitted B's event into A,
    where it dead-lettered on the foreign key, while this function returned ok. The
    CLI's ``--home`` sets the environment, so it agrees by construction; an in-process
    caller that does not is refused before anything is written.
    """
    from core.config.database import DatabaseRuntime, _default_db_path

    ingest_db = _default_db_path()
    runtime = DatabaseRuntime._instance
    projection_db = runtime.db_path if runtime is not None else ingest_db
    for what, other in (("spool ingest", ingest_db), ("projection", projection_db)):
        if not _same_file(other, db_path):
            return (
                f"the {what} would write to {other}, not to {db_path}: the process "
                "environment (DREAM_STUDIO_DB_PATH / DREAM_STUDIO_HOME) names a different "
                "home than this call's dream_studio_home"
            )
    return None


def _emit(
    event_type: str,
    *,
    brief_id: str,
    project_id: str,
    payload: dict[str, Any],
    now: str,
    db_path: Path,
) -> None:
    """Write one design_brief.* event to the spool, then project it before returning.

    The mutations are emit-only (DesignBriefProjection is the sole writer of
    business_design_briefs), but ``ds design-brief ...`` is a one-shot process and no
    daemon is guaranteed: without the tick, ``create`` printed "Draft brief created"
    while the row never existed, so the next ``show``/``lock``/``update`` reported
    "Brief not found". Same emit-then-tick as core.clients.mutations._emit (Pattern C).

    A failed write is NOT swallowed, and neither is a refused home (see
    ``_home_disagreement``). ``sync_tick`` never raises by design, so a tick that did not
    apply the event is invisible here: every caller re-reads the row afterwards.
    """
    disagreement = _home_disagreement(db_path)
    if disagreement:
        raise RuntimeError(disagreement)

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


def _read_brief(db_path: Path, brief_id: str, *columns: str) -> dict[str, Any] | None:
    """``status``, ``project_id`` and any extra columns of a brief, or None when the brief
    is not in the read model. Extra columns are checked against the updatable allowlist
    plus ``updated_at`` so the SELECT is never built from caller text."""
    allowed = BRIEF_UPDATABLE_FIELDS | {"updated_at"}
    unknown = [c for c in columns if c not in allowed]
    if unknown:
        raise ValueError(f"not a readable brief column: {unknown}")
    names = ("status", "project_id", *columns)
    with _connect(db_path) as conn:
        row = conn.execute(
            f"SELECT {', '.join(names)} FROM business_design_briefs"  # noqa: S608
            " WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()
    return None if row is None else dict(zip(names, row))


def _not_applied(event_type: str, brief_id: str) -> dict[str, Any]:
    """The refusal for an event that was written but did not reach the read model.

    ``sync_tick`` swallows its own failures (a locked database, an ingest race, an
    unregistered project) because the projection daemon will retry. This call cannot
    wait for that, and printing success for a brief the next command cannot find is the
    defect this module exists to prevent -- so it says what happened and what is left.
    """
    return {
        "ok": False,
        "error": (
            f"{event_type} for brief {brief_id} was emitted but is not in the read model "
            "after the projection ran (database locked, a failed ingest, or a project "
            "that is not registered). The event stays queued in the spool and is applied "
            "when the projection next runs; check `ds design-brief show` before retrying."
        ),
    }


def create_design_brief(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Insert a fresh draft design brief for ``project_id``.

    A project that already has a DRAFT as its newest brief gets that draft back
    (``created: False``) rather than a second one: two drafts leave "the" brief
    ambiguous, and the readers (show, the start context, the close gate) all mean the
    newest. A project whose newest brief is locked gets a new draft -- that is how a
    locked brief is revised.

    Returns::

        {"ok": True, "created": bool, "brief_id": str, "project_id": str,
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
        newest = conn.execute(
            "SELECT brief_id, status, created_at FROM business_design_briefs"
            " WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    if known is None:
        return {"ok": False, "error": f"Project not found: {project_id}"}
    next_step = "Invoke website:discover with --work-order <wo_id> to populate the brief"
    if newest is not None and newest[1] == "draft":
        return {
            "ok": True,
            "created": False,
            "brief_id": newest[0],
            "project_id": project_id,
            "status": "draft",
            "created_at": newest[2],
            "message": "A draft brief already exists for this project; not creating another.",
            "next_step": next_step,
        }
    brief_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    try:
        _emit(
            "design_brief.created",
            brief_id=brief_id,
            project_id=project_id,
            payload={"brief_id": brief_id, "project_id": project_id, "status": "draft"},
            now=now,
            db_path=db_path,
        )
    except Exception as exc:  # noqa: BLE001 - reported, never reported as success
        return {"ok": False, "error": f"design_brief.created not emitted: {exc}"}
    if _read_brief(db_path, brief_id) is None:
        return _not_applied("design_brief.created", brief_id)
    return {
        "ok": True,
        "created": True,
        "brief_id": brief_id,
        "project_id": project_id,
        "status": "draft",
        "created_at": now,
        "next_step": next_step,
    }


def lock_design_brief(
    *,
    brief_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Mark a design brief as ``locked`` so downstream gates can pass.

    Locking an already-locked brief is a no-op that reports the ORIGINAL lock time. The
    lock time is the row's ``updated_at`` (there is no ``locked_at`` column), and
    ``brief_currency`` measures staleness from it: a second ``lock`` that refreshed it
    would make a stale brief current again with no review and no reason recorded.
    ``ds design-brief reviewed-no-change --note`` is the recorded way to do that.

    Returns::

        {"ok": True, "brief_id": str, "status": "locked", "locked_at": str}

    or on missing brief::

        {"ok": False, "error": "Brief not found: <id>"}
    """

    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(UTC).isoformat()
    row = _read_brief(db_path, brief_id, "updated_at")
    if row is None:
        return {"ok": False, "error": f"Brief not found: {brief_id}"}
    if row["status"] == "locked":
        return {
            "ok": True,
            "brief_id": brief_id,
            "status": "locked",
            "locked_at": row["updated_at"],
            "message": (
                f"Brief {brief_id} is already locked (since {row['updated_at']}); the lock "
                "time is unchanged. To record that a stale brief still holds, use "
                "`ds design-brief reviewed-no-change`."
            ),
        }
    try:
        _emit(
            "design_brief.locked",
            brief_id=brief_id,
            project_id=row["project_id"],
            payload={"brief_id": brief_id},
            now=now,
            db_path=db_path,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"design_brief.locked not emitted: {exc}"}
    after = _read_brief(db_path, brief_id)
    if after is None or after["status"] != "locked":
        return _not_applied("design_brief.locked", brief_id)
    return {"ok": True, "brief_id": brief_id, "status": "locked", "locked_at": now}


def _emit_field_update(
    *,
    brief_id: str,
    field: str,
    value: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> dict[str, Any] | None:
    """Emit one field update on a draft brief and confirm it landed: the error dict, or
    None on success."""
    db_path = _require_db(source_root, dream_studio_home)
    row = _read_brief(db_path, brief_id)
    if row is None:
        return {"ok": False, "error": f"Brief not found: {brief_id}"}
    if row["status"] == "locked":
        return {"ok": False, "error": "Brief is locked and cannot be updated"}
    try:
        _emit(
            "design_brief.updated",
            brief_id=brief_id,
            project_id=row["project_id"],
            payload={"brief_id": brief_id, "field": field, "new_value": value},
            now=datetime.now(UTC).isoformat(),
            db_path=db_path,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"design_brief.updated not emitted: {exc}"}
    after = _read_brief(db_path, brief_id, field)
    if after is None or after[field] != value:
        return _not_applied("design_brief.updated", brief_id)
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
