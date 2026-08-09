"""Event-sourced backfill: assign every unassigned project a client (Client Layer, Phase 2).

Classification (operator 2026-08-08): a project whose name OR path mentions "fulcrum" -> Fulcrum;
"hypershift" -> Hypershift; everything else -> SeayInsights (the default). Each assignment is a
project.client_assigned EVENT (attribution_status='backfill') applied by ProjectProjection — no
direct read-model write. Idempotent: only projects with client_id IS NULL are touched.

Wired into ``core.config.sqlite_bootstrap.activate_pending_migrations`` so activating migration 155
(``ds migrate activate``) classifies the existing projects. Fresh installs have no projects, so it
is a no-op there.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

_MATCH_RULES = (
    ("fulcrum", "fulcrum"),
    ("hypershift", "hypershift"),
)


def classify_project(name: str | None, project_path: str | None) -> str:
    """Return the client_id a project maps to by name-or-path (else the SeayInsights default)."""
    haystack = f"{name or ''} {project_path or ''}".lower()
    for client_id, term in _MATCH_RULES:
        if term in haystack:
            return client_id
    return "seayinsights"


def _resolve_db(db_path: Path | None) -> Path:
    if db_path is not None:
        return Path(db_path)
    from core.config.database import _default_db_path

    return _default_db_path()


def backfill_project_clients(*, db_path: Path | None = None) -> dict[str, Any]:
    """Emit a project.client_assigned event for every project with client_id IS NULL, classified by
    name/path. Returns {ok, assigned: {client_id: count}}."""
    from core.clients.mutations import assign_project_client

    db = _resolve_db(db_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT project_id, name, project_path FROM business_projects WHERE client_id IS NULL"
        ).fetchall()
    finally:
        conn.close()

    counts: dict[str, int] = {}
    for r in rows:
        client_id = classify_project(r["name"], r["project_path"])
        assign_project_client(
            project_id=r["project_id"], client_id=client_id, attribution_status="backfill"
        )
        counts[client_id] = counts.get(client_id, 0) + 1
    return {"ok": True, "assigned": counts}
