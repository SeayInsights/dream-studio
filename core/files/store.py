"""Versioned artifact store backed by files.db.

files.db lives at ~/.dream-studio/state/files.db and is NEVER-AUTHORITY:
no canonical events, no gate decisions originate from this store.
It accepts forward-only writes (handoffs, evidence, release bundles, exports).

Schema: ds_files table with auto-incrementing version per (project_id, name).
Checksum: SHA-256 hex of the raw content bytes.
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config.paths import state_dir

_VALID_CATEGORIES = frozenset({"handoff", "evidence", "release", "rollback", "export"})

_DDL = """
CREATE TABLE IF NOT EXISTS ds_files (
    file_id      TEXT    NOT NULL PRIMARY KEY,
    project_id   TEXT,
    category     TEXT    NOT NULL
                         CHECK (category IN ('handoff','evidence','release','rollback','export')),
    name         TEXT    NOT NULL,
    version      INTEGER NOT NULL DEFAULT 1,
    content_type TEXT    NOT NULL,
    content      BLOB    NOT NULL,
    correlation_id TEXT,
    created_at   TEXT    NOT NULL
                         DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by   TEXT,
    expires_at   TEXT,
    checksum     TEXT
);
CREATE INDEX IF NOT EXISTS idx_ds_files_project_category
    ON ds_files (project_id, category);
CREATE INDEX IF NOT EXISTS idx_ds_files_name_version
    ON ds_files (name, version);
"""


def files_db_path() -> Path:
    """Return the absolute path to files.db (does not create the file)."""
    return state_dir() / "files.db"


def connect_files(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a read-write connection to files.db.

    Callers are responsible for closing the returned connection.
    """
    path = db_path if db_path is not None else files_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_files_schema(conn: sqlite3.Connection) -> None:
    """Create ds_files table and indexes if they do not already exist (idempotent)."""
    conn.executescript(_DDL)
    conn.commit()


def _checksum(content: bytes | str) -> str:
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _next_version(conn: sqlite3.Connection, name: str, project_id: str | None) -> int:
    row = conn.execute(
        "SELECT MAX(version) FROM ds_files WHERE name = ? AND project_id IS ?",
        (name, project_id),
    ).fetchone()
    current = row[0]
    return 1 if current is None else current + 1


def write_file(
    name: str,
    content: bytes | str,
    content_type: str,
    category: str,
    *,
    project_id: str | None = None,
    correlation_id: str | None = None,
    created_by: str | None = None,
    expires_at: str | None = None,
    db_path: Path | None = None,
) -> str:
    """Write a versioned artifact to files.db and return its file_id.

    A new version is created for every call with the same (name, project_id).
    """
    if category not in _VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category {category!r}. Must be one of: {sorted(_VALID_CATEGORIES)}"
        )

    file_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    chk = _checksum(raw)

    conn = connect_files(db_path)
    try:
        ensure_files_schema(conn)
        version = _next_version(conn, name, project_id)
        conn.execute(
            "INSERT INTO ds_files"
            " (file_id, project_id, category, name, version, content_type,"
            "  content, correlation_id, created_at, created_by, expires_at, checksum)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                file_id,
                project_id,
                category,
                name,
                version,
                content_type,
                raw,
                correlation_id,
                created_at,
                created_by,
                expires_at,
                chk,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return file_id


def read_file(file_id: str, *, db_path: Path | None = None) -> dict[str, Any]:
    """Return a single artifact row as a dict, or raise KeyError if not found."""
    conn = connect_files(db_path)
    try:
        ensure_files_schema(conn)
        row = conn.execute(
            "SELECT file_id, project_id, category, name, version, content_type,"
            " content, correlation_id, created_at, created_by, expires_at, checksum"
            " FROM ds_files WHERE file_id = ?",
            (file_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise KeyError(f"No file found with file_id={file_id!r}")
    return dict(row)


def list_files(
    *,
    project_id: str | None = None,
    category: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return artifact rows (without content blob) filtered by project_id and/or category.

    Returns the latest version of each (name, project_id) pair first, ordered by created_at desc.
    """
    if category is not None and category not in _VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category {category!r}. Must be one of: {sorted(_VALID_CATEGORIES)}"
        )

    conn = connect_files(db_path)
    try:
        ensure_files_schema(conn)
        clauses: list[str] = []
        params: list[Any] = []

        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        if category is not None:
            clauses.append("category = ?")
            params.append(category)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT file_id, project_id, category, name, version, content_type,"
            f" correlation_id, created_at, created_by, expires_at, checksum"
            f" FROM ds_files {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows]
