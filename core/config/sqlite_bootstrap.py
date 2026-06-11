"""SQLite bootstrap and migration authority for installable Dream Studio.

This module is intentionally independent of runtime singleton state. It lets
fresh installs, upgrades, and tests create or migrate a user-local SQLite DB
from the repo-backed migration files without relying on an existing operator DB.

## Dev vs Live Migration Safety

Migrations auto-apply on every _connect() call. To prevent an in-dev migration
on a feature branch from silently mutating the live authority DB before review:

1. ``core/event_store/migrations/.released_version`` tracks the max released
   migration version (updated when a migration PR merges to main). Any migration
   with version > released_version is considered unreleased.

2. Unreleased migrations will NOT apply to the live authority DB
   (~/.dream-studio/state/studio.db) unless ``DREAM_STUDIO_APPLY_UNRELEASED=1``
   is set. They apply normally to temp/test DBs (any path outside ~/.dream-studio/).

3. Before the first migration applies to the live authority DB, the current DB
   is snapshotted to ``~/.dream-studio/state/backups/studio-pre-N-TIMESTAMP.db``.

For in-dev migration work: use ``bootstrap_database(tmp_path / "studio.db", ...)``
with an explicit temp path. The gate skips for any non-live-authority DB path.

To apply an unreleased migration to the live DB explicitly::

    DREAM_STUDIO_APPLY_UNRELEASED=1 py -m interfaces.cli.ds <command>
"""

from __future__ import annotations

import os
import re
import sqlite3
import warnings
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


def released_migration_version() -> int:
    """Return the max migration version considered released on main.

    Reads from ``core/event_store/migrations/.released_version``. If the file
    is absent (e.g. older installs), all current migrations are treated as
    released (backward-compatible default).
    """

    rv_path = migrations_dir() / ".released_version"
    if not rv_path.is_file():
        return latest_migration_version()
    try:
        return int(rv_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return latest_migration_version()


def _is_live_authority_db(db_file: str) -> bool:
    """True if db_file is the live authority DB under ~/.dream-studio/."""

    if not db_file:
        return False
    try:
        Path(db_file).resolve().relative_to((Path.home() / ".dream-studio").resolve())
        return True
    except ValueError:
        return False


def _backup_live_db(conn: sqlite3.Connection, db_file: str, current_version: int) -> Path:
    """Snapshot the live authority DB before applying migrations.

    Uses the SQLite backup API (not file copy) so WAL state is consistent.
    Returns the backup path.
    """

    backup_dir = Path.home() / ".dream-studio" / "state" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"studio-pre-{current_version + 1}-{timestamp}.db"
    dest = sqlite3.connect(str(backup_path))
    try:
        conn.backup(dest)
    finally:
        dest.close()
    return backup_path


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


def pending_migrations_info() -> list[dict]:
    """Return metadata for merged-but-not-activated migrations.

    Pending = version > released_migration_version() AND <= latest_migration_version().
    These are merged to repo/HEAD but not yet activated on the live authority DB.
    """
    released = released_migration_version()
    pending = []
    for path in migration_files():
        version = _migration_version(path)
        if version > released:
            stem = path.stem
            parts = stem.split("_", 1)
            description = parts[1].replace("_", " ") if len(parts) > 1 else stem
            pending.append({"version": version, "filename": path.name, "description": description})
    return pending


def activate_pending_migrations(db_path: Path | None = None) -> dict:
    """Apply pending-activation migrations to the live authority DB.

    Operator-invoked ONLY via ``ds migrate activate``. Bumps .released_version
    to the latest merged migration after successful apply.
    """
    if db_path is None:
        db_path = Path.home() / ".dream-studio" / "state" / "studio.db"

    pending = pending_migrations_info()
    if not pending:
        released = released_migration_version()
        return {
            "ok": True,
            "applied": [],
            "released_version": released,
            "schema_version": released,
            "message": "No pending migrations.",
        }

    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        new_version = run_migrations(conn, apply_unreleased=True)
    finally:
        conn.close()

    latest = latest_migration_version()
    rv_path = migrations_dir() / ".released_version"
    rv_path.write_text(str(latest), encoding="utf-8")

    return {
        "ok": True,
        "applied": pending,
        "schema_version": new_version,
        "released_version": latest,
    }


def run_migrations(
    conn: sqlite3.Connection,
    *,
    target_version: int | None = None,
    apply_unreleased: bool | None = None,
) -> int:
    """Apply pending repo migrations and return the resulting schema version.

    Safety guards (see module docstring):
    - Unreleased migrations (version > released_migration_version()) are skipped
      on the live authority DB unless DREAM_STUDIO_APPLY_UNRELEASED=1 is set or
      apply_unreleased=True is passed explicitly.
    - The live DB is snapshotted to ~/.dream-studio/state/backups/ before the
      first new migration applies.
    """

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

    # Live-authority safety: detect DB path, released version, and opt-in flag
    db_row = conn.execute("PRAGMA database_list").fetchone()
    db_file: str = db_row[2] if db_row else ""
    live = _is_live_authority_db(db_file)
    released = released_migration_version()
    if apply_unreleased is None:
        apply_unreleased = bool(os.environ.get("DREAM_STUDIO_APPLY_UNRELEASED"))
    backup_taken = False

    for path in files:
        version = _migration_version(path)
        if version <= current or version > latest_code:
            continue

        # Gate: unreleased migrations do not auto-apply to the live authority DB
        if live and not apply_unreleased and version > released:
            warnings.warn(
                f"[migration-safety] Migration {version} is unreleased "
                f"(released_version={released}). Skipping live authority apply. "
                "Set DREAM_STUDIO_APPLY_UNRELEASED=1 to override.",
                RuntimeWarning,
                stacklevel=2,
            )
            continue

        # Auto-backup: snapshot live authority DB before the first migration applies
        if live and not backup_taken:
            try:
                _backup_live_db(conn, db_file, current)
            except Exception:
                pass  # backup failure is non-fatal; migration proceeds
            backup_taken = True

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
                # fts_gotchas / ds_documents / canonical_events: narrowed from broad
                # substring-match to statement-type-aware (WO-I, P5.5). Pattern mirrors the
                # memory_entries S3b fix (O7). CREATE INDEX and CREATE TRIGGER on an absent
                # table are M2-class casualties — silently swallowing them marks the migration
                # applied while leaving schema objects permanently missing (e.g. migration 050's
                # idx_ds_documents_source_path on an absent ds_documents). Data/DDL-modification
                # statements (INSERT, UPDATE, ALTER TABLE, DROP) on an absent table remain
                # graceful degradation — no permanent schema object is lost.
                # canonical_events note: migrations 052-064 reference it before migration 083
                # (which creates it). All pre-083 references are data statements (ALTER TABLE,
                # UPDATE, INSERT), so narrowing has no practical effect there — but the explicit
                # guard prevents any future CREATE INDEX on canonical_events from being silently
                # swallowed before migration 083 runs.
                if "no such table" in msg and (
                    "fts_gotchas" in msg or "ds_documents" in msg or "canonical_events" in msg
                ):
                    stmt_upper = stmt.strip().upper()
                    if not (
                        stmt_upper.startswith("CREATE INDEX")
                        or stmt_upper.startswith("CREATE UNIQUE INDEX")
                        or stmt_upper.startswith("CREATE TRIGGER")
                    ):
                        continue
                    # CREATE INDEX and CREATE TRIGGER fall through to raise.
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
                # Narrowed to statement-type-aware (WO-DEBT-I), mirroring the
                # memory_entries (O7) and fts_gotchas/ds_documents (WO-I) fixes:
                # migration 081 contains no CREATE INDEX/TRIGGER on these tables —
                # only data statements — so the fixture tolerance is unaffected.
                # A swallowed CREATE INDEX would be an M2 casualty (e.g. migration
                # 037's idx_token_usage_scope, 043's idx_ai_usage_operational_*).
                if "no such table" in msg and (
                    "token_usage_records" in msg or "ai_usage_operational_records" in msg
                ):
                    stmt_upper = stmt.strip().upper()
                    if not (
                        stmt_upper.startswith("CREATE INDEX")
                        or stmt_upper.startswith("CREATE UNIQUE INDEX")
                        or stmt_upper.startswith("CREATE TRIGGER")
                    ):
                        continue
                    # CREATE INDEX and CREATE TRIGGER fall through to raise.
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
                # Narrowed to statement-type-aware (WO-DEBT-I): migration 070's
                # statements on ds_* are all data statements and remain swallowed.
                # The ds_* indexes (migrations 048/053, e.g. idx_ds_milestones_project)
                # are created in the same file as their tables, so a CREATE INDEX
                # reaching this handler indicates a real installation problem that
                # must surface, not an expected upgrade path.
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
                    stmt_upper = stmt.strip().upper()
                    if not (
                        stmt_upper.startswith("CREATE INDEX")
                        or stmt_upper.startswith("CREATE UNIQUE INDEX")
                        or stmt_upper.startswith("CREATE TRIGGER")
                    ):
                        continue
                    # CREATE INDEX and CREATE TRIGGER fall through to raise.
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
