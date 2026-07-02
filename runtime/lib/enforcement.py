"""Shared logic for SQLite-usage enforcement hooks.

Used by runtime/hooks/meta/on-edit-enforce.py (PreToolUse) and
runtime/hooks/meta/on-stop-enforce.py (Stop). Enforces two rules:

1. Authority — edits to product source inside a registered project require an
   in_progress work order in ~/.dream-studio/state/studio.db, and a session
   that edited product source must record at least one authority write
   (task.completed / work_order.closed event, or a fresh row update) before
   it may end.
2. Docstore — persistent documentation artifacts (docs/**, .planning/**
   excluding .planning/personal/) written during a session must have a
   matching ds_files record in ~/.dream-studio/state/files.db.

Every public function fails open: any exception yields the permissive result.
Enforcement must never brick an adapter — a broken authority DB means no
enforcement, not no editing. DS_ENFORCE=0 disables everything.

Authority-write detection intentionally accepts EITHER signal direction:
`ds work-order start` updates the business_work_orders row immediately while
its canonical event lands later via spool ingest; `task-done` emits the event
immediately while the business_tasks row lags until sync_tick. Checking both
sides makes same-session detection robust to both lag directions.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

STATE_DIR = Path.home() / ".dream-studio" / "state"
AUTHORITY_DB = STATE_DIR / "studio.db"
FILES_DB = STATE_DIR / "files.db"
SESSION_DIR = STATE_DIR / "enforce"

# Paths never subject to enforcement (module constants so tests can patch them).
DS_HOME = Path.home() / ".dream-studio"
TEMP_ROOT = Path(tempfile.gettempdir())

# Repo-internal directories whose files are never product source.
_EXEMPT_SEGMENTS = frozenset(
    {".git", ".claude", ".venv", "__pycache__", "node_modules", "graphify-out"}
)

_SESSION_FILE_MAX_AGE_SECS = 7 * 24 * 3600


def enforcement_disabled() -> bool:
    return os.environ.get("DS_ENFORCE", "").strip() == "0"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts


def _connect_ro(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


# ---------------------------------------------------------------------------
# Path classification
# ---------------------------------------------------------------------------


def _resolve(path_str: str) -> Path | None:
    try:
        return Path(path_str).expanduser().resolve()
    except (OSError, ValueError):
        return None


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        # Windows paths compare case-insensitively.
        try:
            Path(str(path).lower()).relative_to(Path(str(root).lower()))
            return True
        except ValueError:
            return False


def match_registered_project(file_path: str) -> dict | None:
    """Return {project_id, name, project_path} for the registered project
    containing file_path, or None. Prefers active over paused projects and
    the longest matching project_path."""
    resolved = _resolve(file_path)
    if resolved is None:
        return None
    if _is_under(resolved, DS_HOME) or _is_under(resolved, TEMP_ROOT):
        return None

    conn = _connect_ro(AUTHORITY_DB)
    if conn is None:
        return None
    try:
        rows = conn.execute(
            "SELECT project_id, name, status, project_path FROM business_projects"
            " WHERE status IN ('active', 'paused') AND project_path IS NOT NULL"
        ).fetchall()
    except sqlite3.Error:
        return None
    finally:
        conn.close()

    candidates = []
    for row in rows:
        root = _resolve(row["project_path"])
        if root is not None and _is_under(resolved, root):
            candidates.append((row["status"] != "active", -len(str(root)), row))
    if not candidates:
        return None
    best = min(candidates)[2]
    return {
        "project_id": best["project_id"],
        "name": best["name"],
        "project_path": best["project_path"],
    }


def classify_path(file_path: str, project_path: str) -> str:
    """Classify a file inside a project as 'source', 'doc', or 'exempt'.

    doc    — persistent documentation artifact: docs/** or .planning/**
             (excluding .planning/personal/); must be registered in files.db.
    exempt — repo-internal noise (.git, .claude, caches) plus .planning/personal/;
             never denied, never tracked.
    source — everything else; requires an in_progress work order.
    """
    resolved = _resolve(file_path)
    root = _resolve(project_path)
    if resolved is None or root is None:
        return "exempt"
    try:
        rel_parts = resolved.relative_to(root).parts
    except ValueError:
        try:
            rel_parts = Path(str(resolved).lower()).relative_to(Path(str(root).lower())).parts
        except ValueError:
            return "exempt"
    if not rel_parts:
        return "exempt"
    if any(part in _EXEMPT_SEGMENTS for part in rel_parts):
        return "exempt"
    if rel_parts[0] == ".planning":
        if len(rel_parts) > 1 and rel_parts[1] == "personal":
            return "exempt"
        return "doc"
    if rel_parts[0] == "docs":
        return "doc"
    return "source"


# ---------------------------------------------------------------------------
# Authority queries
# ---------------------------------------------------------------------------


def in_progress_work_order(project_id: str) -> dict | None:
    conn = _connect_ro(AUTHORITY_DB)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT work_order_id, title FROM business_work_orders"
            " WHERE project_id = ? AND status = 'in_progress'"
            " ORDER BY started_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return {"work_order_id": row[0], "title": row[1]} if row else None


def next_created_work_order(project_id: str) -> dict | None:
    conn = _connect_ro(AUTHORITY_DB)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT wo.work_order_id, wo.title FROM business_work_orders wo"
            " LEFT JOIN business_milestones m ON m.milestone_id = wo.milestone_id"
            " WHERE wo.project_id = ? AND wo.status = 'created'"
            " ORDER BY m.order_index ASC, wo.sequence_order ASC NULLS LAST,"
            " wo.created_at ASC LIMIT 1",
            (project_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return {"work_order_id": row[0], "title": row[1]} if row else None


def authority_write_since(work_order_id: str, since_iso: str) -> bool:
    """True if any authority write for the WO landed at/after since_iso."""
    since = parse_ts(since_iso)
    if since is None:
        return True  # unusable window — fail open
    conn = _connect_ro(AUTHORITY_DB)
    if conn is None:
        return True
    try:
        rows = conn.execute(
            "SELECT event_timestamp, received_at FROM business_canonical_events"
            " WHERE work_order_id = ?"
            " AND event_type IN ('task.completed', 'work_order.closed')",
            (work_order_id,),
        ).fetchall()
        for row in rows:
            ts = parse_ts(row[0]) or parse_ts(row[1])
            if ts is not None and ts >= since:
                return True
        rows = conn.execute(
            "SELECT updated_at FROM business_tasks" " WHERE work_order_id = ? AND status = 'done'",
            (work_order_id,),
        ).fetchall()
        for row in rows:
            ts = parse_ts(row[0])
            if ts is not None and ts >= since:
                return True
        row = conn.execute(
            "SELECT status, closed_at FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if row is not None and row[0] in ("closed", "cancelled"):
            return True
    except sqlite3.Error:
        return True
    finally:
        conn.close()
    return False


def docstore_record_since(name_hint: str, since_iso: str) -> bool:
    """True if a ds_files record whose name contains name_hint landed at/after since_iso."""
    since = parse_ts(since_iso)
    if since is None:
        return True
    conn = _connect_ro(FILES_DB)
    if conn is None:
        return False  # no docstore at all — the artifact cannot be registered
    try:
        rows = conn.execute(
            "SELECT created_at FROM ds_files WHERE name LIKE ?",
            (f"%{name_hint}%",),
        ).fetchall()
    except sqlite3.Error:
        return True
    finally:
        conn.close()
    for row in rows:
        ts = parse_ts(row[0])
        if ts is not None and ts >= since:
            return True
    return False


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def _session_file(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")[:80]
    return SESSION_DIR / f"{safe}.json"


def load_session(session_id: str) -> dict | None:
    path = _session_file(session_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_session(session_id: str, data: dict) -> None:
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        _session_file(session_id).write_text(json.dumps(data, indent=1), encoding="utf-8")
    except OSError:
        pass


def delete_session(session_id: str) -> None:
    try:
        _session_file(session_id).unlink(missing_ok=True)
    except OSError:
        pass


def gc_session_files() -> None:
    """Best-effort cleanup of stale session files from sessions that never stopped."""
    try:
        cutoff = time.time() - _SESSION_FILE_MAX_AGE_SECS
        for path in list(SESSION_DIR.glob("*.json"))[:200]:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
    except OSError:
        pass


def record_edit(
    session_id: str,
    *,
    file_path: str,
    kind: str,
    project_id: str,
    work_order_id: str | None,
) -> None:
    """Record an allowed edit so on-stop-enforce can check the session's writes."""
    data = load_session(session_id) or {
        "session_id": session_id,
        "started_at": now_iso(),
        "source_edits": [],
        "doc_edits": [],
        "stop_blocked_at": None,
    }
    bucket = data.setdefault("source_edits" if kind == "source" else "doc_edits", [])
    normalized = str(_resolve(file_path) or file_path)
    for entry in bucket:
        if entry.get("path") == normalized:
            entry["work_order_id"] = work_order_id
            entry["ts"] = now_iso()
            break
    else:
        if len(bucket) < 500:
            bucket.append(
                {
                    "path": normalized,
                    "project_id": project_id,
                    "work_order_id": work_order_id,
                    "ts": now_iso(),
                }
            )
    save_session(session_id, data)
