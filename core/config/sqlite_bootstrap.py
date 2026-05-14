"""SQLite bootstrap and migration authority for installable Dream Studio.

This module is intentionally independent of runtime singleton state. It lets
fresh installs, upgrades, and tests create or migrate a user-local SQLite DB
from the repo-backed migration files without relying on an existing operator DB.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def migrations_dir() -> Path:
    """Return the repo-backed SQLite migration directory."""

    return Path(__file__).resolve().parents[1] / "event_store" / "migrations"


def migration_files() -> list[Path]:
    """Return ordered numeric migration files from the repo."""

    mdir = migrations_dir()
    if not mdir.is_dir():
        return []
    return sorted(mdir.glob("[0-9]*.sql"))


def latest_migration_version() -> int:
    """Return the highest migration version present in repo source."""

    files = migration_files()
    if not files:
        return 0
    return max(_migration_version(path) for path in files)


def split_statements(sql_text: str) -> list[str]:
    """Split SQL into executable statements while respecting trigger blocks."""

    statements: list[str] = []
    current: list[str] = []
    depth = 0

    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue

        current.append(line)
        upper = stripped.upper()

        if re.search(r"\bBEGIN\b", upper):
            depth += 1

        if stripped.endswith(";"):
            end_token = upper.rstrip(";").rstrip()
            if depth > 0 and end_token.endswith("END"):
                depth -= 1

            if depth == 0:
                stmt = "\n".join(current).strip().rstrip(";").strip()
                if stmt:
                    statements.append(stmt)
                current = []

    if current:
        stmt = "\n".join(current).strip().rstrip(";").strip()
        if stmt:
            statements.append(stmt)

    return statements


def run_migrations(conn: sqlite3.Connection, *, target_version: int | None = None) -> int:
    """Apply pending repo migrations and return the resulting schema version."""

    conn.execute(
        "CREATE TABLE IF NOT EXISTS _schema_version ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.commit()

    current = applied_schema_version(conn)
    files = migration_files()
    if not files:
        return current

    latest_code = latest_migration_version()
    if target_version is not None:
        latest_code = min(latest_code, target_version)

    if current > latest_migration_version():
        raise RuntimeError(
            f"Database schema v{current} is newer than code v{latest_migration_version()}. "
            "Update dream-studio to a compatible version."
        )

    for path in files:
        version = _migration_version(path)
        if version <= current or version > latest_code:
            continue

        sql_text = path.read_text(encoding="utf-8")
        for stmt in split_statements(sql_text):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as exc:
                msg = str(exc).lower()
                if "duplicate column name" in msg:
                    continue
                if "no such module" in msg:
                    continue
                if "no such table" in msg and ("fts_gotchas" in msg or "memory_entries" in msg):
                    continue
                raise

        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(?, ?)",
            (version, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    return applied_schema_version(conn)


def bootstrap_database(db_path: Path, *, target_version: int | None = None) -> int:
    """Create or migrate a SQLite DB at db_path, then return schema version."""

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return run_migrations(conn, target_version=target_version)
    finally:
        conn.close()


def applied_schema_version(conn: sqlite3.Connection) -> int:
    """Return max applied schema version, or 0 before bootstrap."""

    try:
        row = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int((row[0] if row else 0) or 0)


def _migration_version(path: Path) -> int:
    return int(path.stem.split("_", 1)[0])
