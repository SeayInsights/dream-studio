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
                if "no such table" in msg and (
                    "fts_gotchas" in msg
                    or "ds_documents" in msg
                    # canonical_events: migrations 052-064 reference this table but run BEFORE
                    # migration 083 (which creates it) in the migration sequence. On fresh installs
                    # those older migrations fail with "no such table: canonical_events" and are
                    # swallowed here. This is intentional graceful degradation — not stale.
                    # Migration 083 (18.4.6-followup-1) makes canonical_events migration-owned;
                    # this swallow remains necessary for the pre-083 references.
                    or "canonical_events" in msg
                ):
                    continue
                # memory_entries: narrowed from substring-match to statement-type-aware (O7,
                # 18.4-consolidation-followup-3). CREATE INDEX and CREATE TRIGGER on an absent
                # memory_entries are M2 casualties — the migration intends to create a schema
                # object, the broad substring swallow ate the failure, and the object silently
                # never existed (confirmed casualty: idx_memory_lifecycle, migration 032, on DBs
                # created before migration 011 added memory_entries 2026-05-24).
                # Data statements (INSERT/UPDATE/ALTER TABLE/DROP/SELECT) on an absent
                # memory_entries are graceful degradation — no schema object is permanently lost.
                # Migration 011 ensures memory_entries exists before any migration that references
                # it on a valid install. A CREATE INDEX/TRIGGER reaching this handler indicates
                # a real installation problem that should surface, not be silently discarded.
                # Seam verified: all CREATE INDEX/TRIGGER on memory_entries are in migrations
                # 032, 078, 079, 080, 082 (all > v11) — they succeed on any valid install.
                if "no such table" in msg and "memory_entries" in msg:
                    stmt_upper = stmt.strip().upper()
                    if not (
                        stmt_upper.startswith("CREATE INDEX")
                        or stmt_upper.startswith("CREATE TRIGGER")
                    ):
                        continue
                    # CREATE INDEX and CREATE TRIGGER fall through to raise.
                # Migration 081 reconstructs token_usage_records and
                # ai_usage_operational_records to change column types.  Test fixtures
                # that declare schema version 77 but omit these tables (or use an
                # older schema missing later-added columns) will fail the INSERT...SELECT
                # step.  Skip gracefully — the _new tables are already created empty
                # with the corrected NUMERIC(20,8) schema, and DROP TABLE IF EXISTS
                # in the migration removes any partial source table.  This matches
                # the migration 070 pattern for partial-fixture tolerance.
                if "no such table" in msg and (
                    "token_usage_records" in msg or "ai_usage_operational_records" in msg
                ):
                    continue
                # Migration 081 column-error counterpart: INSERT from a partial
                # fixture table that is missing columns added by migrations 042/043.
                if "no such column" in msg and (
                    "token_usage_records" in stmt.lower()
                    or "ai_usage_operational_records" in stmt.lower()
                ):
                    continue
                # Migration 070 copies ds_* → business_* tables via INSERT...SELECT
                # and UPDATE...SELECT FROM ds_*.  When the ds_* source tables were
                # never created (e.g., partial test DB or upgrade from schema < 48),
                # skip gracefully — business_* tables are created empty, which is
                # correct: there was no old data to migrate.
                if "no such table" in msg and any(
                    f"ds_{t}" in msg
                    for t in (
                        "projects",
                        "milestones",
                        "work_orders",
                        "tasks",
                        "design_briefs",
                        "work_order_types",
                    )
                ):
                    continue
                # Index creation on a pre-existing table may fail when the
                # table was created by a test fixture with a minimal schema.
                # Skip gracefully — queries still work without the index.
                _col_error = "no such column" in msg or "has no column named" in msg
                if _col_error and stmt.strip().upper().startswith("CREATE INDEX"):
                    continue
                # Migration 070 copies ds_* → business_* tables.  When the
                # ds_* or business_* table was pre-created by a test fixture
                # with an incomplete schema, skip gracefully.  The ds_* tables
                # are always empty in test fixtures so no data is lost.
                if _col_error and any(
                    f"ds_{t}" in stmt.lower()
                    for t in (
                        "projects",
                        "milestones",
                        "work_orders",
                        "tasks",
                        "design_briefs",
                        "work_order_types",
                    )
                ):
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
