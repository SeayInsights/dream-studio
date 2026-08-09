"""Event-sourced client mutations (Client Layer, Attribution Coherence Phase 2).

Each mutation emits a canonical event and runs a projection tick; the ClientProjection /
ProjectProjection materialize business_clients / business_projects.client_id. There are NO direct
read-model writes here — that was the architectural finding that failed the WO-CLIENT-SCHEMA
backfill review.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any


def slugify_client(name: str) -> str:
    """Stable, human-readable client_id from a name (lowercase, dash-separated)."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or uuid.uuid4().hex[:8]


def _emit(envelope_dict: dict[str, Any]) -> None:
    """Write a canonical event to the spool, then run an inline projection tick so the
    materialized row is queryable on return (Pattern C). Both steps best-effort/non-fatal."""
    import spool.writer as _spool_writer

    _spool_writer.write_event(envelope_dict)
    try:
        from core.projections.runner import sync_tick

        sync_tick()
    except Exception:
        pass


def create_client(
    *, name: str, description: str = "", client_id: str | None = None
) -> dict[str, Any]:
    """Create a client (emits client.created). Returns {ok, client_id, name}."""
    from canonical.events.envelope import CanonicalEventEnvelope

    cid = client_id or slugify_client(name)
    now = datetime.now(UTC).isoformat()
    _emit(
        CanonicalEventEnvelope(
            event_type="client.created",
            session_id=None,
            payload={"client_id": cid, "name": name, "description": description},
            timestamp=now,
            severity="info",
            trace={"domain": "sdlc", "attribution_status": "fully_attributed"},
        ).to_dict()
    )
    return {"ok": True, "client_id": cid, "name": name}


def archive_client(*, client_id: str) -> dict[str, Any]:
    """Archive a client (emits client.archived; status → archived)."""
    from canonical.events.envelope import CanonicalEventEnvelope

    now = datetime.now(UTC).isoformat()
    _emit(
        CanonicalEventEnvelope(
            event_type="client.archived",
            session_id=None,
            payload={"client_id": client_id},
            timestamp=now,
            severity="info",
            trace={"domain": "sdlc", "attribution_status": "fully_attributed"},
        ).to_dict()
    )
    return {"ok": True, "client_id": client_id, "status": "archived"}


def delete_client(*, client_id: str) -> dict[str, Any]:
    """Soft-delete a client (emits client.deleted; status → deleted). The row stays queryable, like
    project.deleted."""
    from canonical.events.envelope import CanonicalEventEnvelope

    now = datetime.now(UTC).isoformat()
    _emit(
        CanonicalEventEnvelope(
            event_type="client.deleted",
            session_id=None,
            payload={"client_id": client_id},
            timestamp=now,
            severity="info",
            trace={"domain": "sdlc", "attribution_status": "fully_attributed"},
        ).to_dict()
    )
    return {"ok": True, "client_id": client_id, "status": "deleted"}


def assign_project_client(
    *, project_id: str, client_id: str, attribution_status: str = "fully_attributed"
) -> dict[str, Any]:
    """Attach a project to a client (emits project.client_assigned; sets business_projects.client_id).

    attribution_status='backfill' is used by the migration-155 activation backfill.
    """
    from canonical.events.envelope import CanonicalEventEnvelope

    now = datetime.now(UTC).isoformat()
    _emit(
        CanonicalEventEnvelope(
            event_type="project.client_assigned",
            session_id=None,
            payload={"project_id": project_id, "client_id": client_id},
            timestamp=now,
            severity="info",
            trace={
                "domain": "sdlc",
                "project_id": project_id,
                "attribution_status": attribution_status,
            },
        ).to_dict()
    )
    return {"ok": True, "project_id": project_id, "client_id": client_id}


def detach_project_client(*, project_id: str) -> dict[str, Any]:
    """Detach a project from its client by reassigning it to the default (SeayInsights) — every
    project keeps a client rather than dropping to NULL."""
    from core.clients.queries import DEFAULT_CLIENT_ID

    return assign_project_client(project_id=project_id, client_id=DEFAULT_CLIENT_ID)
