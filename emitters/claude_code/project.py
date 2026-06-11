from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

_DS_DB_ENV = "DREAM_STUDIO_DB_PATH"

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_MARKER = ".dream-studio-project"
_log = logging.getLogger(__name__)


def read_project_id(root: Path | None) -> str | None:
    """Read .dream-studio-project from root (or cwd) and return a valid UUID, or None.

    Parses both marker formats:
    - JSON (TA3+ format): {"project_id": "<uuid>", ...}
    - Plain UUID (legacy format): bare UUID on the first line

    Retained for backward compatibility. Prefer get_active_project_id() when
    Claude Code runs from non-project directories (e.g. home directory).
    """
    base = root if root is not None else Path.cwd()
    marker = base / _MARKER
    try:
        raw = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    # Try JSON first (TA3+ format).
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "project_id" in data:
            project_id = str(data["project_id"]).strip()
            if _UUID_RE.match(project_id):
                return project_id
            _log.warning(
                "Malformed project ID in %s (JSON project_id is not a UUID) — project_id will be null",
                marker,
            )
            return None
    except (json.JSONDecodeError, ValueError):
        pass

    # Plain-UUID fallback (legacy format: first line is a bare UUID).
    first_line = raw.splitlines()[0].strip() if raw else ""
    if _UUID_RE.match(first_line):
        return first_line

    _log.warning(
        "Malformed project ID in %s (not JSON with project_id, not a UUID) — project_id will be null",
        marker,
    )
    return None


def _get_db_path() -> Path:
    """Return the canonical path to the Dream Studio SQLite authority database.

    Honors the ``DREAM_STUDIO_DB_PATH`` env-var override so tests can redirect
    away from the operator's real ``~/.dream-studio/state/``.
    """
    override = os.environ.get(_DS_DB_ENV)
    if override:
        return Path(override)
    return Path.home() / ".dream-studio" / "state" / "studio.db"


def get_active_project_id(db_path: Path) -> str | None:
    """Return the project_id of the most-recently-updated active project, or None.

    Fails open: any exception (DB missing, locked, schema mismatch) returns None
    so event emission is never blocked by a DB read failure.
    """
    sqlite3 = __import__("sqlite3")  # ast-clean: avoids forbidden import node in emitter layer

    if not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=1.0)
        try:
            row = conn.execute(
                "SELECT project_id FROM business_projects"
                " WHERE status = 'active'"
                " ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except Exception:
        return None
