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


def _slugify(text: str) -> str:
    """Return a URL-safe slug: lowercase, spaces/underscores -> hyphens, strip extras."""
    text = text.lower().strip()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^a-z0-9-]", "", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


def resolve_project_uuid(key: str, conn: sqlite3.Connection) -> str | None:
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


# This module is intentionally WRITE-FREE: it only RESOLVES keys to UUIDs.
# The forward fix lives at the capture sites (core/telemetry/execution_spine.py,
# control/analysis/synthesis.py), which resolve project_id to the UUID on insert.
# The one-time historical remap was run as an operator action (not a committed
# writer), so execution_events keeps its existing writers and no single-writer
# ownership boundary is crossed.
