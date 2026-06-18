"""Project attribution helpers for execution_events.

Resolves project keys (folder names, slugs, path basenames) to their
registered business_projects UUID so execution_events.project_id
holds a stable UUID rather than a free-text key.

Design rules:
- Only map confidently-resolvable keys. Return None for unknowns.
- Match against: name, slug(name), basename(project_path).
- Never fabricate a UUID for an unresolvable key.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Optional


def _slugify(text: str) -> str:
    """Return a URL-safe slug: lowercase, spaces/underscores -> hyphens, strip extras."""
    text = text.lower().strip()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^a-z0-9-]", "", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


def resolve_project_uuid(key: str, conn: sqlite3.Connection) -> Optional[str]:
    """Resolve a project key to a registered business_projects UUID.

    Tries (in order):
    1. Exact match on business_projects.name
    2. Slug of name matches slug of key
    3. Basename of business_projects.project_path matches key

    Returns the UUID string on a confident match, None otherwise.
    Keys that match nothing registered are returned as-is by the caller.
    """
    if not key or not key.strip():
        return None

    key = key.strip()
    key_slug = _slugify(key)

    try:
        rows = conn.execute(
            "SELECT project_id, name, project_path FROM business_projects"
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    for row in rows:
        project_id = row[0] if isinstance(row, tuple) else row["project_id"]
        name = row[1] if isinstance(row, tuple) else row["name"]
        project_path = row[2] if isinstance(row, tuple) else row["project_path"]

        # 1. Exact name match
        if name and name.strip() == key:
            return project_id

        # 2. Slug match (handles "dream-studio-clean" == "Dream Studio Clean", etc.)
        if name and _slugify(name) == key_slug:
            return project_id

        # 3. Basename of project_path
        if project_path:
            try:
                basename = Path(project_path).name
                if basename and basename == key:
                    return project_id
                if basename and _slugify(basename) == key_slug:
                    return project_id
            except (TypeError, ValueError):
                pass

    return None


def backfill_execution_events(conn: sqlite3.Connection) -> dict[str, int]:
    """Remap resolvable free-text project keys in execution_events to UUIDs.

    Only updates rows where project_id is a confidently-resolvable key
    (matches a business_projects name, slug, or path basename). Rows with
    already-UUID values or unresolvable garbage keys are left untouched.

    Returns a dict mapping each resolved key to the number of rows updated.
    """
    try:
        raw_keys = conn.execute(
            "SELECT DISTINCT project_id FROM execution_events WHERE project_id IS NOT NULL"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}

    summary: dict[str, int] = {}

    for row in raw_keys:
        key = row[0] if isinstance(row, tuple) else row["project_id"]
        if not key:
            continue

        # Skip rows that already look like UUIDs (8-4-4-4-12 hex pattern)
        if re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            key,
            re.IGNORECASE,
        ):
            continue

        resolved = resolve_project_uuid(key, conn)
        if resolved is None:
            continue

        # Don't remap a key to itself (key already IS the UUID — caught above,
        # but defensive check in case of odd data).
        if resolved == key:
            continue

        count = conn.execute(
            "SELECT COUNT(*) FROM execution_events WHERE project_id = ?", (key,)
        ).fetchone()[0]

        if count > 0:
            conn.execute(
                "UPDATE execution_events SET project_id = ? WHERE project_id = ?",
                (resolved, key),
            )
            summary[key] = count

    return summary


def run_live_backfill(db_path: Path) -> dict[str, int]:
    """Connect to the live authority DB and run the backfill.

    Returns the per-key update counts. Commits on success.
    """
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        summary = backfill_execution_events(conn)
        conn.commit()
        return summary
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
