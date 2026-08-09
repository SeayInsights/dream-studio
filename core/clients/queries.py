"""Read-only client queries (Client Layer, Attribution Coherence Phase 2).

Includes candidate_projects_for_work — the CLIENT-level project-fit signal, the twin of
core.projects.milestone_fit.candidate_milestones_for_work: given proposed work and a client, it
surfaces the client's projects + a deterministic lexical fit verdict so the attribution flow can
ask which project new work belongs to instead of dumping it into whatever project is active.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.projects.milestone_fit import _CLEAR_MIN_SHARED, _terms

# The default client every unmatched / new project belongs to (operator decision 2026-08-08).
DEFAULT_CLIENT_ID = "seayinsights"


def _resolve_db(db_path: Path | None) -> Path:
    if db_path is not None:
        return Path(db_path)
    from core.config.database import _default_db_path

    return _default_db_path()


def list_clients(
    *, include_archived: bool = False, db_path: Path | None = None
) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(_resolve_db(db_path)))
    conn.row_factory = sqlite3.Row
    try:
        sql = "SELECT client_id, name, description, status FROM business_clients"
        if not include_archived:
            sql += " WHERE status = 'active'"
        sql += " ORDER BY name"
        return [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()


def get_client(client_id: str, *, db_path: Path | None = None) -> dict[str, Any] | None:
    conn = sqlite3.connect(str(_resolve_db(db_path)))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT client_id, name, description, status FROM business_clients WHERE client_id = ?",
            (client_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def projects_for_client(client_id: str, *, db_path: Path | None = None) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(_resolve_db(db_path)))
    conn.row_factory = sqlite3.Row
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT project_id, name, status FROM business_projects"
                " WHERE client_id = ? AND status NOT IN ('deleted')"
                " ORDER BY name",
                (client_id,),
            )
        ]
    finally:
        conn.close()


def resolve_default_client(*, db_path: Path | None = None) -> str:
    """Return the default client id (SeayInsights) for new/unmatched projects."""
    return DEFAULT_CLIENT_ID


def projects_grouped_by_client(*, db_path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Return non-deleted projects grouped by client id: {client_id: [{project_id, name, status}]}.

    Guarded for a pre-migration-155 DB: if business_projects has no client_id column, every project
    is grouped under '(unassigned)' rather than erroring.
    """
    conn = sqlite3.connect(str(_resolve_db(db_path)))
    conn.row_factory = sqlite3.Row
    try:
        has_col = any(
            r[1] == "client_id" for r in conn.execute("PRAGMA table_info(business_projects)")
        )
        client_expr = "COALESCE(client_id, '(unassigned)')" if has_col else "'(unassigned)'"
        rows = conn.execute(
            f"SELECT project_id, name, status, {client_expr} AS client_id FROM business_projects"
            " WHERE status NOT IN ('deleted') ORDER BY client_id, name"
        ).fetchall()
    finally:
        conn.close()

    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(r["client_id"], []).append(
            {"project_id": r["project_id"], "name": r["name"], "status": r["status"]}
        )
    return groups


def candidate_projects_for_work(
    client_id: str,
    work_title: str,
    work_description: str = "",
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Fit proposed work against a client's open projects, so the flow asks which project it belongs
    to instead of auto-filing. Same verdict ladder as the milestone fit-check:

      clear_single | ambiguous | no_fit | no_projects

    Deterministic lexical overlap (no LLM) between the proposed work and each project's
    name+description.
    """
    work_terms = _terms(f"{work_title} {work_description}")

    conn = sqlite3.connect(str(_resolve_db(db_path)))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT project_id, name, COALESCE(description, '') AS description FROM business_projects"
            " WHERE client_id = ? AND status NOT IN ('deleted') ORDER BY name",
            (client_id,),
        ).fetchall()
    finally:
        conn.close()

    candidates: list[dict[str, Any]] = []
    for r in rows:
        shared = sorted(work_terms & _terms(f"{r['name']} {r['description']}"))
        if len(shared) >= _CLEAR_MIN_SHARED:
            fit = "clear"
        elif shared:
            fit = "possible"
        else:
            fit = "none"
        candidates.append(
            {
                "project_id": r["project_id"],
                "name": r["name"],
                "description": r["description"],
                "fit": fit,
                "overlap_terms": shared,
            }
        )

    clear = [c for c in candidates if c["fit"] == "clear"]
    possible = [c for c in candidates if c["fit"] == "possible"]
    best = max(candidates, key=lambda c: len(c["overlap_terms"]), default=None)
    best_id = best["project_id"] if best and best["overlap_terms"] else None

    if not candidates:
        verdict = "no_projects"
    elif len(clear) == 1:
        verdict = "clear_single"
    elif clear or possible:
        verdict = "ambiguous"
    else:
        verdict = "no_fit"

    return {
        "client_id": client_id,
        "candidates": candidates,
        "verdict": verdict,
        "best": best_id,
    }
