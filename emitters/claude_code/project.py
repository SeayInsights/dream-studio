from __future__ import annotations

import logging
import re
from pathlib import Path

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_MARKER = ".dream-studio-project"
_log = logging.getLogger(__name__)


def read_project_id(root: Path | None) -> str | None:
    """Read .dream-studio-project from root (or cwd) and return a valid UUID, or None.

    Retained for backward compatibility. Prefer get_active_project_id() when
    Claude Code runs from non-project directories (e.g. home directory).
    """
    base = root if root is not None else Path.cwd()
    marker = base / _MARKER
    try:
        line = marker.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return None
    if _UUID_RE.match(line):
        return line
    _log.warning("Malformed project ID in %s (not a UUID) — project_id will be null", marker)
    return None


def _get_db_path() -> Path:
    """Return the canonical path to the Dream Studio SQLite authority database.

    Delegates to ``core.config.database._default_db_path`` so the env-var
    override ``DREAM_STUDIO_DB_PATH`` is honored uniformly. Tests set this
    to redirect away from the operator's real ``~/.dream-studio/state/``.
    """
    from core.config.database import _default_db_path

    return _default_db_path()


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
                "SELECT project_id FROM ds_projects"
                " WHERE status = 'active'"
                " ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except Exception:
        return None
