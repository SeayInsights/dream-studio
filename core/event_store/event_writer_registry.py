"""event_writer registry group: reg_gotchas + business_projects writers.

WO-GF-PROJECTION-ENGINE: split from ``core/event_store/event_writer.py``.
"""

from __future__ import annotations
from pathlib import Path

from .connection import (
    _CanonicalEventType,
    _NOW,
    _db_transaction,
    _reraise_if_busy,
    _try_emit_canonical,
    _with_retry,
)


@_with_retry
def upsert_gotcha(
    gotcha_id: str,
    skill_id: str,
    severity: str,
    title: str,
    *,
    context: str = "",
    fix: str = "",
    keywords: str = "",
    discovered: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT OR REPLACE INTO reg_gotchas
                   (gotcha_id, skill_id, severity, title, context, fix,
                    keywords, discovered, times_hit, last_hit)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                           COALESCE((SELECT times_hit FROM reg_gotchas WHERE gotcha_id=? AND skill_id=?), 0),
                           (SELECT last_hit FROM reg_gotchas WHERE gotcha_id=? AND skill_id=?))""",
                (
                    gotcha_id,
                    skill_id,
                    severity,
                    title,
                    context,
                    fix,
                    keywords,
                    discovered,
                    gotcha_id,
                    skill_id,
                    gotcha_id,
                    skill_id,
                ),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def clear_registry(db_path: Path | None = None) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute("DELETE FROM reg_gotchas")  # noqa: S608
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def upsert_project(
    project_id: str,
    project_path: str,
    *,
    project_name: str | None = None,
    project_type: str | None = None,
    git_remote: str | None = None,
    db_path: Path | None = None,
) -> bool:
    # reg_projects deleted in migration 084. Writes to business_projects instead.
    # project_type maps to detected_stack; git_remote has no equivalent column (ignored).
    # INSERT OR IGNORE preserves existing rows, then selectively UPDATE changed fields.
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                "INSERT OR IGNORE INTO business_projects"
                " (project_id, name, project_path, detected_stack, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 'active', ?, ?)",
                (
                    project_id,
                    project_name or project_id,
                    project_path,
                    project_type,
                    _NOW(),
                    _NOW(),
                ),
            )
            # Update mutable fields only when the row already existed
            c.execute(
                "UPDATE business_projects SET"
                " project_path = ?,"
                " updated_at = ?"
                " WHERE project_id = ?",
                (project_path, _NOW(), project_id),
            )
            if project_name:
                c.execute(
                    "UPDATE business_projects SET name = ? WHERE project_id = ? AND name = ?",
                    (project_name, project_id, project_id),
                )
            if project_type:
                c.execute(
                    "UPDATE business_projects SET detected_stack = ? WHERE project_id = ?",
                    (project_type, project_id),
                )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def update_project_stats(
    project_id: str, *, sessions_delta: int = 0, tokens_delta: int = 0, db_path: Path | None = None
) -> bool:
    # reg_projects deleted in migration 084. Update business_projects instead.
    # Only applies when project_id is a UUID that exists in business_projects.
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """UPDATE business_projects SET
                    total_sessions = total_sessions + ?,
                    total_tokens = total_tokens + ?,
                    last_session_at = ?,
                    updated_at = ?
                   WHERE project_id = ?""",
                (sessions_delta, tokens_delta, _NOW(), _NOW(), project_id),
            )

            # Event emission (additive side-effect) — TA0c: activity_log retired
            _try_emit_canonical(
                _CanonicalEventType.PROJECT_STATS_UPDATED,
                {
                    "project_id": project_id,
                    "sessions_delta": sessions_delta,
                    "tokens_delta": tokens_delta,
                },
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False
