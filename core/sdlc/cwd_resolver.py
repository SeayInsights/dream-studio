"""CWD → project resolution via .dream-studio-project marker file.

Walks up from the current working directory looking for a marker file.
Supports both the legacy plain-UUID format and the new JSON format (TA3+).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

_MARKER = ".dream-studio-project"
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CWDProjectContext:
    project_id: str
    project_name: Optional[str]  # None for plain-UUID legacy markers
    marker_path: Path
    marker_format: Literal["json", "plain_uuid"]


def _is_valid_uuid(text: str) -> bool:
    return bool(_UUID_RE.match(text.strip()))


def _parse_marker(marker_path: Path) -> Optional[CWDProjectContext]:
    """Parse a marker file, trying JSON first then plain-UUID fallback.

    Returns CWDProjectContext on success, None on unrecoverable failure.
    Logs anomalies for malformed content.
    """
    try:
        raw = marker_path.read_text(encoding="utf-8").strip()
    except (OSError, IOError) as exc:
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
    """Best-effort: check whether project_id exists in ds_projects.

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
                "SELECT 1 FROM ds_projects WHERE project_id = ? LIMIT 1",
                (project_id,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return True  # fail open


def resolve_project_from_cwd() -> Optional[CWDProjectContext]:
    """Walk up from cwd looking for .dream-studio-project marker.

    Parsing strategy:
    1. Try JSON parse (TA3+ format with schema_version, project_id, project_name, metadata)
    2. On JSON failure, fall back to first line as plain UUID (legacy format)
    3. If neither succeeds, log anomaly and return None

    Reconciliation (Q3 decision):
    If the resolved project_id is NOT in ds_projects, log anomaly but return
    the context anyway — attribution proceeds with attribution_status=partial.
    The auditor handles drift reconciliation.
    """
    try:
        current = Path.cwd().resolve()
    except Exception:
        return None

    # DS_CWD_RESOLVER_ROOT caps the walk — used in tests to prevent the walker
    # from ascending past the test's tmp_path into real user directories.
    stop_at_env = os.environ.get("DS_CWD_RESOLVER_ROOT")
    stop_at = Path(stop_at_env).resolve() if stop_at_env else None

    for candidate in [current, *current.parents]:
        if stop_at is not None:
            try:
                candidate.relative_to(stop_at)
            except ValueError:
                break  # candidate is above stop_at; stop walking
        marker_path = candidate / _MARKER
        if not marker_path.is_file():
            continue

        ctx = _parse_marker(marker_path)
        if ctx is None:
            return None  # anomaly already logged

        # Q3: check marker against ds_projects; log anomaly if not found but return anyway.
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
                        "Marker file references project_id not found in ds_projects. "
                        "Marker may be stale or project was deleted. "
                        "Attribution proceeds with partial status."
                    )
                },
            )

        return ctx

    return None
