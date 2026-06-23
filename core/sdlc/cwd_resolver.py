"""CWD → project resolution via .dream-studio-project marker or SQLite path lookup.

Resolution order (first match wins):
  1. Walk up from CWD looking for .dream-studio-project marker (persistent projects)
  2. At the .git/ repo root boundary: SQLite project_path fallback (no-marker intake default)
  3. None — truly unregistered directory, graceful drop (never throws)

The SQLite fallback (step 2) supports brownfield repos registered without a marker.
It queries business_projects WHERE project_path = repo_root.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_MARKER = ".dream-studio-project"
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CWDProjectContext:
    project_id: str
    project_name: str | None  # None for plain-UUID legacy markers
    marker_path: Path | None  # None for project_path SQLite resolution
    marker_format: Literal["json", "plain_uuid", "project_path"]
    # "project_path" = resolved via SQLite business_projects.project_path (no marker)


def _is_valid_uuid(text: str) -> bool:
    return bool(_UUID_RE.match(text.strip()))


def _parse_marker(marker_path: Path) -> CWDProjectContext | None:
    """Parse a marker file, trying JSON first then plain-UUID fallback.

    Returns CWDProjectContext on success, None on unrecoverable failure.
    Logs anomalies for malformed content.
    """
    try:
        raw = marker_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        from core.telemetry.diagnostics import log_diagnostic

        log_diagnostic(
            category="failure",
            source="cwd_resolver._parse_marker",
            context={"marker_path": str(marker_path)},
            details={"error_type": type(exc).__name__, "error_message": str(exc)},
        )
        return None

    # Try JSON first (TA3+ format).
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "project_id" in data:
            project_id = data["project_id"]
            if not _is_valid_uuid(project_id):
                from core.telemetry.diagnostics import log_diagnostic

                log_diagnostic(
                    category="anomaly",
                    source="cwd_resolver._parse_marker",
                    context={"marker_path": str(marker_path)},
                    details={
                        "error_message": "JSON marker has invalid project_id UUID",
                        "raw_id": project_id[:64],
                    },
                )
                return None
            return CWDProjectContext(
                project_id=project_id.strip(),
                project_name=data.get("project_name"),
                marker_path=marker_path,
                marker_format="json",
            )
        # Valid JSON but not the expected shape — fall through to UUID check.
    except (json.JSONDecodeError, ValueError):
        pass

    # Plain-UUID fallback (legacy format: first line is a bare UUID).
    first_line = raw.splitlines()[0].strip() if raw else ""
    if _is_valid_uuid(first_line):
        return CWDProjectContext(
            project_id=first_line,
            project_name=None,
            marker_path=marker_path,
            marker_format="plain_uuid",
        )

    # Neither format matched.
    from core.telemetry.diagnostics import log_diagnostic

    log_diagnostic(
        category="anomaly",
        source="cwd_resolver._parse_marker",
        context={"marker_path": str(marker_path)},
        details={
            "error_message": "Marker file is malformed (not JSON with project_id, not plain UUID)",
            "raw_truncated": raw[:200],
        },
    )
    return None


def _check_project_in_db(project_id: str) -> bool:
    """Best-effort: check whether project_id exists in business_projects.

    Returns True if found or if the DB is unavailable (fail open).
    """
    try:
        from core.config.database import _default_db_path

        db_path = _default_db_path()
        if not db_path.is_file():
            return True  # DB not present — can't validate; treat as found
        conn = sqlite3.connect(str(db_path), timeout=1.0)
        try:
            row = conn.execute(
                "SELECT 1 FROM business_projects WHERE project_id = ? LIMIT 1",
                (project_id,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return True  # fail open


def _get_home() -> Path:
    return Path.home().resolve()


def resolve_project_from_cwd() -> CWDProjectContext | None:
    """Walk up from cwd looking for .dream-studio-project marker.

    Bounded walk stops at the first of:
    - A .dream-studio-project marker is found (returns context)
    - A .git/ directory is found (repo root boundary)
    - The user's home directory would be the next parent (exclusive upper bound)
    - The filesystem root is reached (current.parent == current)

    DS_CWD_RESOLVER_ROOT env var caps the walk in tests to prevent ascending
    past the test's tmp_path into real user directories.

    Q3 reconciliation: if the resolved project_id is NOT in business_projects, log
    anomaly but return the context anyway (attribution_status=partial).
    """
    try:
        current = Path.cwd().resolve()
    except Exception:
        return None

    home = _get_home()

    stop_at_env = os.environ.get("DS_CWD_RESOLVER_ROOT")
    stop_at = Path(stop_at_env).resolve() if stop_at_env else None

    while True:
        # Test isolation: DS_CWD_RESOLVER_ROOT caps the walk.
        if stop_at is not None:
            try:
                current.relative_to(stop_at)
            except ValueError:
                return None  # above the test boundary

        marker_path = current / _MARKER
        if marker_path.is_file():
            ctx = _parse_marker(marker_path)
            if ctx is None:
                return None  # anomaly already logged

            # Q3: check marker against business_projects; log anomaly if not found but return anyway.
            if not _check_project_in_db(ctx.project_id):
                from core.telemetry.diagnostics import log_diagnostic

                log_diagnostic(
                    category="anomaly",
                    source="cwd_resolver.resolve_project_from_cwd",
                    context={
                        "marker_path": str(marker_path),
                        "project_id": ctx.project_id,
                    },
                    details={
                        "error_message": (
                            "Marker file references project_id not found in business_projects. "
                            "Marker may be stale or project was deleted. "
                            "Attribution proceeds with partial status."
                        )
                    },
                )

            return ctx

        # Boundary 1: hit .git/ — repo root. Try SQLite project_path fallback before None.
        if (current / ".git").is_dir():
            return resolve_project_from_path(current)

        # Boundary 2 & 3: stop before reaching home, or at filesystem root.
        parent = current.parent
        if current == home or parent == home or current == parent:
            return None

        current = parent


def resolve_project_from_path(path: Path) -> CWDProjectContext | None:
    """SQLite fallback: resolve project from business_projects.project_path.

    Used when no .dream-studio-project marker is present (no-marker intake default).
    Queries business_projects WHERE project_path = resolved_path.

    Returns CWDProjectContext with marker_format="project_path" on success,
    or None if the path is not registered.
    Never throws — fail-open like the rest of the resolver.
    """
    try:
        from core.config.database import _default_db_path

        resolved = str(path.resolve())
        db_path = _default_db_path()
        if not db_path.is_file():
            return None
        conn = sqlite3.connect(str(db_path), timeout=1.0)
        try:
            row = conn.execute(
                "SELECT project_id, name FROM business_projects"
                " WHERE project_path = ? AND status != 'deleted'"
                " ORDER BY updated_at DESC LIMIT 1",
                (resolved,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return CWDProjectContext(
            project_id=row[0],
            project_name=row[1],
            marker_path=None,  # No marker file — resolved via SQLite
            marker_format="project_path",
        )
    except Exception:
        return None  # fail-open — never block a session on a lookup failure
