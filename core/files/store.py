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
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from core.config.paths import state_dir

_VALID_CATEGORIES = frozenset({"handoff", "evidence", "release", "rollback", "export", "planning"})

_DDL = """
CREATE TABLE IF NOT EXISTS ds_files (
    file_id      TEXT    NOT NULL PRIMARY KEY,
    project_id   TEXT,
    work_order_id TEXT,
    category     TEXT    NOT NULL
                         CHECK (category IN ('handoff','evidence','release','rollback','export','planning')),
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
# NB: the idx_ds_files_work_order index is created in _ensure_work_order_id_column,
# not here — on a pre-existing DB the work_order_id column is added by ALTER *after*
# this _DDL runs, so indexing it here would fail with "no such column".

# work_order_id is a SOFT reference to business_work_orders.work_order_id in the
# separate studio.db authority. SQLite cannot enforce a foreign key across database
# files, and files.db is NEVER-AUTHORITY, so this is a queryable logical link only —
# "which docs track to this work order" = WHERE work_order_id = ?. The relationship's
# truth still lives in the authority; this column just makes the docs discoverable
# from a work order id without a name convention or a stored query.


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


def _ensure_category_check(conn: sqlite3.Connection) -> None:
    """Widen the ds_files.category CHECK to cover every currently-valid category.

    SQLite cannot ALTER a CHECK constraint in place, so a files.db created before a
    new category was added still carries the old CHECK and would reject inserts of
    that category. This performs a one-time table rebuild (rename -> recreate from
    the current _DDL -> copy rows -> drop old). Idempotent: it no-ops once the live
    CHECK already lists every valid category. files.db is NEVER-AUTHORITY, so the
    rebuild carries no event/gate risk.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='ds_files'"
    ).fetchone()
    if row is None:
        return  # fresh DB — _DDL already created the table with the current CHECK
    live_sql = row[0] or ""
    if all(f"'{category}'" in live_sql for category in _VALID_CATEGORIES):
        return  # CHECK already covers every valid category
    conn.execute("ALTER TABLE ds_files RENAME TO _ds_files_old")
    # The indexes followed the rename onto _ds_files_old; drop them by name so the
    # _DDL below can recreate them on the rebuilt table without a name collision.
    conn.execute("DROP INDEX IF EXISTS idx_ds_files_project_category")
    conn.execute("DROP INDEX IF EXISTS idx_ds_files_name_version")
    conn.execute("DROP INDEX IF EXISTS idx_ds_files_work_order")
    conn.executescript(_DDL)
    # Copy the columns present in BOTH the old and new tables, so the rebuild is
    # robust to added columns (new-only columns take their defaults) and never
    # loses data on a future widening.
    old_cols = [r[1] for r in conn.execute("PRAGMA table_info(_ds_files_old)")]
    new_cols = [r[1] for r in conn.execute("PRAGMA table_info(ds_files)")]
    common = ", ".join(c for c in new_cols if c in set(old_cols))
    conn.execute(f"INSERT INTO ds_files ({common}) SELECT {common} FROM _ds_files_old")
    conn.execute("DROP TABLE _ds_files_old")
    conn.commit()


def _ensure_work_order_id_column(conn: sqlite3.Connection) -> None:
    """Add the ds_files.work_order_id soft-reference column to a pre-existing table.

    Adding a plain column (unlike changing a CHECK) is a simple ALTER, so this is a
    cheap idempotent guard: no-op once the column exists. Fresh DBs already have it
    from _DDL.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='ds_files'"
    ).fetchone()
    if row is None:
        return
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ds_files)")}
    if "work_order_id" not in cols:
        conn.execute("ALTER TABLE ds_files ADD COLUMN work_order_id TEXT")
    # Always ensure the index — the column may pre-exist (fresh DB via _DDL, or a
    # rebuild that dropped/recreated the table) without the index yet.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ds_files_work_order ON ds_files (work_order_id)")
    conn.commit()


def ensure_files_schema(conn: sqlite3.Connection) -> None:
    """Create ds_files if absent, widen a stale category CHECK, and ensure the
    work_order_id column + index (all idempotent).

    Order matters: the CHECK-widening rebuild recreates the table from _DDL (which
    includes the work_order_id column), so it runs before _ensure_work_order_id_column
    creates the index — that way the index survives a rebuild and is only ever created
    once the column is guaranteed to exist.
    """
    conn.executescript(_DDL)
    _ensure_category_check(conn)
    _ensure_work_order_id_column(conn)
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
    work_order_id: str | None = None,
    correlation_id: str | None = None,
    created_by: str | None = None,
    expires_at: str | None = None,
    db_path: Path | None = None,
) -> str:
    """Write a versioned artifact to files.db and return its file_id.

    A new version is created for every call with the same (name, project_id).
    ``work_order_id`` is an optional soft reference (see _DDL) so the artifact is
    discoverable from a work order id.
    """
    if category not in _VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category {category!r}. Must be one of: {sorted(_VALID_CATEGORIES)}"
        )

    file_id = str(uuid.uuid4())
    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    chk = _checksum(raw)

    conn = connect_files(db_path)
    try:
        ensure_files_schema(conn)
        version = _next_version(conn, name, project_id)
        conn.execute(
            "INSERT INTO ds_files"
            " (file_id, project_id, work_order_id, category, name, version, content_type,"
            "  content, correlation_id, created_at, created_by, expires_at, checksum)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                file_id,
                project_id,
                work_order_id,
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
            "SELECT file_id, project_id, work_order_id, category, name, version, content_type,"
            " content, correlation_id, created_at, created_by, expires_at, checksum"
            " FROM ds_files WHERE file_id = ?",
            (file_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise KeyError(f"No file found with file_id={file_id!r}")
    return dict(row)


def read_file_by_name(
    name: str,
    *,
    project_id: str | None = None,
    version: int | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Return an artifact row (with content) by ``name``.

    Returns the latest version for ``(name, project_id)`` unless ``version`` is given.
    Raises KeyError if no matching row exists. This is the read half of the
    docstore-as-filesystem surface: callers address content by its logical name
    (e.g. "personal/notes.md") rather than a file_id.
    """
    conn = connect_files(db_path)
    try:
        ensure_files_schema(conn)
        cols = (
            "file_id, project_id, work_order_id, category, name, version, content_type,"
            " content, correlation_id, created_at, created_by, expires_at, checksum"
        )
        if version is not None:
            row = conn.execute(
                f"SELECT {cols} FROM ds_files"
                " WHERE name = ? AND project_id IS ? AND version = ?",
                (name, project_id, version),
            ).fetchone()
        else:
            row = conn.execute(
                f"SELECT {cols} FROM ds_files"
                " WHERE name = ? AND project_id IS ?"
                " ORDER BY version DESC LIMIT 1",
                (name, project_id),
            ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise KeyError(f"No file found with name={name!r} (project_id={project_id!r})")
    return dict(row)


def list_files(
    *,
    project_id: str | None = None,
    category: str | None = None,
    work_order_id: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return artifact rows (without content blob) filtered by project_id, category,
    and/or work_order_id.

    ``work_order_id`` answers "which docs track to this work order" — the soft-link
    lookup (see _DDL). Returns the latest version of each (name, project_id) pair
    first, ordered by created_at desc.
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
        if work_order_id is not None:
            clauses.append("work_order_id = ?")
            params.append(work_order_id)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT file_id, project_id, work_order_id, category, name, version, content_type,"
            f" correlation_id, created_at, created_by, expires_at, checksum"
            f" FROM ds_files {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows]
