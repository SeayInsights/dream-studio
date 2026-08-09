"""Assign every existing project a client (Attribution Coherence Phase 2, WO-CLIENT-SCHEMA).

The classification the operator specified (2026-08-08): a project whose name OR path mentions
"fulcrum" belongs to the Fulcrum client; "hypershift" to Hypershift; everything else to
SeayInsights (the default client). Idempotent — only rows with ``client_id IS NULL`` are touched,
so re-running never reassigns a project that already has a client.

Fresh installs have no projects, so the migration seeds the clients and this helper is a no-op
there; it does the real work on the live authority when migration 155 is activated (and is unit
tested against seeded sample projects).
"""

from __future__ import annotations

import sqlite3

# (client_id, match term) — order matters only in that the SeayInsights catch-all runs last.
_MATCH_RULES = (
    ("fulcrum", "fulcrum"),
    ("hypershift", "hypershift"),
)


def backfill_project_clients(conn: sqlite3.Connection) -> dict[str, int]:
    """Assign a client to every project with ``client_id IS NULL``. Returns rows-updated per client.

    Matches ``fulcrum`` / ``hypershift`` by name OR project_path (case-insensitive); all remaining
    unassigned projects go to ``seayinsights``. The caller commits.
    """
    updated: dict[str, int] = {}
    for client_id, term in _MATCH_RULES:
        cur = conn.execute(
            "UPDATE business_projects SET client_id = ?"
            " WHERE client_id IS NULL"
            " AND (lower(name) LIKE ? OR lower(COALESCE(project_path, '')) LIKE ?)",
            (client_id, f"%{term}%", f"%{term}%"),
        )
        updated[client_id] = cur.rowcount
    cur = conn.execute(
        "UPDATE business_projects SET client_id = 'seayinsights' WHERE client_id IS NULL"
    )
    updated["seayinsights"] = cur.rowcount
    return updated
