"""Profile mutations (migration 159): create a profile, switch which one is active.

Dual-write, mirroring core.projects.mutations_activation.set_active_project exactly:
a direct SQL write (so the row is correct for a synchronous caller on return) plus a
best-effort canonical event emission for the audit trail. There is no ProfileProjection
in this change set -- nothing replays profile.* events to rebuild business_profiles;
the direct write is the only writer, same as set_active_project before any replay path
existed for business_projects.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect


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


def create_profile(
    *,
    name: str,
    client_id: str,
    claude_config_dir: str | None = None,
    mcp_client_name: str | None = None,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Create a profile (a switchable operating-context identity) attached to a client.

    Refuses clearly, naming the invalid id and the valid set, when ``client_id`` does
    not exist in business_clients (mirrors create_work_order's work_order_type refusal
    in core/work_orders/mutations.py).

    Inserted with status='active' directly -- mirrors register_project
    (core/projects/mutations_register.py), which inserts a new project row with
    status='active' and does not displace whatever else was active. A second profile
    created later does not pause this one; business_projects already tolerates more
    than one simultaneously 'active' row the same way (queries pick the
    most-recently-updated one). switch_active_profile is the explicit,
    set_active_project-mirroring mutation that actually enforces mutual exclusion.

    Returns::

        {"ok": True, "profile_id": str, "client_id": str, "name": str,
         "status": "active", "created_at": str}

    or on an unregistered client::

        {"ok": False, "error": "client_id 'nope' is not a registered client. Valid: ..."}
    """
    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(UTC).isoformat()
    profile_id = str(uuid.uuid4())
    with _connect(db_path) as conn:
        valid_ids = [
            r[0] for r in conn.execute("SELECT client_id FROM business_clients ORDER BY client_id")
        ]
        if client_id not in valid_ids:
            return {
                "ok": False,
                "error": (
                    f"client_id {client_id!r} is not a registered client."
                    f" Valid: {', '.join(valid_ids) if valid_ids else '(none registered)'}."
                ),
            }
        conn.execute(
            "INSERT INTO business_profiles"
            " (profile_id, client_id, name, claude_config_dir, mcp_client_name, status,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
            (profile_id, client_id, name, claude_config_dir, mcp_client_name, now, now),
        )
        conn.commit()

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="profile.created",
                session_id=None,
                payload={"profile_id": profile_id, "client_id": client_id, "name": name},
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "profile_id": profile_id,
                    "attribution_status": "fully_attributed",
                },
            ).to_dict()
        )
    except Exception as exc:
        from core.telemetry.diagnostics import log_diagnostic

        # log_diagnostic never raises (see its own docstring), so this is not itself
        # wrapped in a guarding try/except -- the event emission above is best-effort
        # (the direct SQL write already materialized the row), but a swallowed failure
        # here must still be observable rather than silent.
        log_diagnostic(
            category="failure",
            source="core.profiles.mutations.create_profile",
            context={"profile_id": profile_id, "client_id": client_id},
            details={"error_type": type(exc).__name__, "error_message": str(exc)},
        )

    return {
        "ok": True,
        "profile_id": profile_id,
        "client_id": client_id,
        "name": name,
        "status": "active",
        "created_at": now,
    }


def switch_active_profile(
    *,
    profile_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Make *profile_id* the active profile, displacing whichever profile(s) were active.

    Exactly mirrors core.projects.mutations_activation.set_active_project: collect the
    currently-active profile ids, pause all of them, activate the target, commit --
    then (best-effort, dual-write) emit a profile.deactivated event per displaced id
    followed by a profile.activated event for the target.
    """
    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(UTC).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT profile_id FROM business_profiles WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Profile not found: {profile_id}"}
        # Collect IDs of currently-active profiles before displacing them.
        displaced_ids = [
            r[0]
            for r in conn.execute(
                "SELECT profile_id FROM business_profiles WHERE status = 'active'",
            ).fetchall()
        ]
        conn.execute("UPDATE business_profiles SET status = 'paused' WHERE status = 'active'")
        conn.execute(
            "UPDATE business_profiles SET status = 'active', updated_at = ? WHERE profile_id = ?",
            (now, profile_id),
        )
        conn.commit()
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        for displaced_id in displaced_ids:
            _spool_writer.write_event(
                CanonicalEventEnvelope(
                    event_type="profile.deactivated",
                    session_id=None,
                    payload={"profile_id": displaced_id},
                    timestamp=now,
                    severity="info",
                    trace={
                        "domain": "sdlc",
                        "profile_id": displaced_id,
                        "attribution_status": "fully_attributed",
                    },
                ).to_dict()
            )
        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="profile.activated",
                session_id=None,
                payload={"profile_id": profile_id},
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "profile_id": profile_id,
                    "attribution_status": "fully_attributed",
                },
            ).to_dict()
        )
    except Exception as exc:
        from core.telemetry.diagnostics import log_diagnostic

        log_diagnostic(
            category="failure",
            source="core.profiles.mutations.switch_active_profile",
            context={"profile_id": profile_id, "displaced_ids": displaced_ids},
            details={"error_type": type(exc).__name__, "error_message": str(exc)},
        )
    return {"ok": True, "profile_id": profile_id, "status": "active"}
