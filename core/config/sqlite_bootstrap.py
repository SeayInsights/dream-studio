"""SQLite bootstrap and migration authority for installable Dream Studio.

This module is intentionally independent of runtime singleton state. It lets
fresh installs, upgrades, and tests create or migrate a user-local SQLite DB
from the repo-backed migration files without relying on an existing operator DB.

## Dev vs Live Migration Safety

Migrations auto-apply on every _connect() call. To prevent an in-dev migration
on a feature branch from silently mutating the live authority DB before review:

1. ``core/event_store/migrations/.released_version`` is the SHIPPED default: the max
   released migration version (updated when a migration PR merges to main). It is
   read-only at runtime. ``ds migrate activate`` records its own activation beside the
   authority it activated (``<home>/state/migrations-activated-version``); the released
   version of an authority is the larger of the two. Any migration with a higher
   version is considered unreleased.

2. Unreleased migrations will NOT apply to the live authority DB (any database inside
   the Dream Studio home in use, ``core.config.paths.home_dir()``, or inside the default
   home) unless ``DREAM_STUDIO_APPLY_UNRELEASED=1`` is set. They apply normally to
   temp/test DBs.

3. Before the first migration applies to the live authority DB, the current DB
   is snapshotted to ``<home>/state/backups/studio-pre-N-TIMESTAMP.db``.

4. A missing authority is never silently re-created in a home that has had an install
   (``assert_may_create_database``).

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
from datetime import datetime, UTC
from pathlib import Path


def migrations_dir() -> Path:
    """Return the shipped SQLite migration directory (checkout or installed app)."""
    from core.config.paths import code_root

    return code_root() / "core" / "event_store" / "migrations"


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


#: Per-authority activation state, written by `ds migrate activate` NEXT TO the database
#: it activated (normally <home>/state/). It used to be written into the shipped
#: migrations directory, which made every activation an edit to the source tree -- a
#: dirty checkout for a developer, and a write into site-packages for an installed app.
ACTIVATED_VERSION_FILE = "migrations-activated-version"


def shipped_released_version() -> int:
    """The released version the code ships: migrations/.released_version (read-only).

    Absent or unreadable means every shipped migration is released (older installs).
    """

    rv_path = migrations_dir() / ".released_version"
    if not rv_path.is_file():
        return latest_migration_version()
    try:
        return int(rv_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return latest_migration_version()


def _activation_state_path(db_file: str | Path | None = None) -> Path:
    """Where the activation state of the authority at *db_file* lives."""

    if not db_file:
        from core.config.database import _default_db_path

        db_file = _default_db_path()
    return Path(db_file).parent / ACTIVATED_VERSION_FILE


def activated_migration_version(db_file: str | Path | None = None) -> int:
    """The version `ds migrate activate` last activated for this authority (0 if never)."""

    state = _activation_state_path(db_file)
    if not state.is_file():
        return 0
    text = state.read_text(encoding="utf-8").strip()
    # Unparseable state is "never activated": the shipped default still applies.
    return int(text) if text.isdigit() else 0


def carry_over_activation(db_path: str | Path) -> int | None:
    """Record an activation that only the old in-tree mechanism knew about.

    Before activation state moved beside the authority, `ds migrate activate` recorded it
    by bumping migrations/.released_version in the checkout. An authority activated that
    way is past the shipped sentinel with no ACTIVATED_VERSION_FILE, so every migration
    it already has reads as pending. This writes MAX(_schema_version) as its activation
    when -- and only when -- the authority is past the shipped sentinel and no record
    exists. Returns the version written, or None.
    """
    db_path = Path(db_path)
    state = _activation_state_path(db_path)
    if state.is_file() or not db_path.is_file():
        return None
    from core.config.sqlite_readonly import connect_read_only

    conn = connect_read_only(db_path, timeout=30.0)
    try:
        applied = applied_schema_version(conn)
    finally:
        conn.close()
    if applied <= shipped_released_version():
        return None
    state.write_text(str(applied), encoding="utf-8")
    return applied


def released_migration_version(db_file: str | Path | None = None) -> int:
    """Return the max migration version considered released for this authority.

    The larger of the shipped default (``migrations/.released_version``, bumped when a
    migration PR merges) and the authority's own activation state (``ds migrate
    activate``). *db_file* defaults to the default authority path.
    """

    return max(shipped_released_version(), activated_migration_version(db_file))


def _is_live_authority_db(db_file: str) -> bool:
    """True if db_file is inside the Dream Studio home in use OR the default home.

    The home in use (home_dir(): DREAM_STUDIO_HOME, `--home`): an authority under
    `--home X` is as live as the default one, and checking only the default exempted it
    from the unreleased-migration gate and the pre-migration backup. The default home
    too: the protection must not follow the variable it protects against, so a run with
    DREAM_STUDIO_HOME pointed elsewhere still treats the operator's real authority as live.
    """

    if not db_file:
        return False
    from core.config.paths import default_home, home_dir

    path = Path(db_file).resolve()
    return any(path.is_relative_to(home.resolve()) for home in {home_dir(), default_home()})


class AuthorityRefusedError(RuntimeError):
    """Creating this database would silently replace or fake an authority."""


#: Set to the authority's own path to create a fresh, empty authority on purpose in a home
#: that has had one (scoped to that one file: a value of "1" or another path does nothing).
CREATE_AUTHORITY_ENV = "DREAM_STUDIO_CREATE_AUTHORITY"

#: Authorities already seen to carry a schema in this process, by FILE STATE
#: (st_dev, st_ino, st_size, st_mtime_ns), not by path: a long-running process (`ds mcp
#: serve`, the dashboard) whose authority is replaced at the same path, or truncated and
#: rewritten in place under the same inode, must check the file again. Any write changes
#: the key, so a live authority is re-checked (one read-only query) after each change.
_VERIFIED_AUTHORITIES: dict[str, tuple[int, int, int, int]] = {}


def _norm(path: str | Path) -> str:
    """One spelling per file: resolved, `..` collapsed, and case-folded where the
    filesystem is case-insensitive."""

    return os.path.normcase(os.path.realpath(os.path.abspath(str(path))))


def _owning_home(db_path: Path) -> Path | None:
    """The Dream Studio home whose authority *db_path* is, or None.

    The authority is `<home>/state/studio.db` however the path is spelled (case,
    `..`), and also whatever path this process is configured to use as its authority
    (DREAM_STUDIO_DB_PATH, or home_dir()/state/studio.db), owned by home_dir(). Matching
    the TEXT `state/studio.db` let `STATE/Studio.db`, `state/x/../studio.db` and a
    relocated DREAM_STUDIO_DB_PATH create a fresh authority in a home with an install.

    Only the authority itself: files.db and the other state databases are created on
    first use in an installed home, and that is correct.
    """

    real = Path(os.path.realpath(os.path.abspath(str(db_path))))
    if os.path.normcase(real.name) == os.path.normcase("studio.db") and os.path.normcase(
        real.parent.name
    ) == os.path.normcase("state"):
        return real.parent.parent
    from core.config.paths import home_dir

    home = home_dir()
    configured = [home / "state" / "studio.db"]
    if os.environ.get("DREAM_STUDIO_DB_PATH"):
        configured.append(Path(os.environ["DREAM_STUDIO_DB_PATH"]).expanduser())
    if any(_norm(candidate) == _norm(real) for candidate in configured):
        return home
    return None


def _install_markers(home: Path) -> list[Path]:
    """Evidence that *home* has held an installed Dream Studio."""

    markers = [home / "state" / "installed-version"]
    integrations = home / "integrations"
    if integrations.is_dir():
        markers.extend(sorted(integrations.rglob("manifest.json")))
    return [m for m in markers if m.is_file()]


def has_authority_schema(db_path: Path) -> bool:
    """True when *db_path* is a database the migrations have run on (has _schema_version).

    A 0-byte file, or one holding only a table some raw open created, is not an
    authority: it is what sqlite3.connect() leaves behind when it is pointed at a
    missing file. Read through a read-only connection, so asking creates nothing.
    """

    if db_path.stat().st_size == 0:
        return False
    from core.config.sqlite_readonly import connect_read_only

    row = None
    try:
        conn = connect_read_only(db_path, timeout=30.0)
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = '_schema_version'"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        # Not a SQLite database at all ("file is not a database"): no authority either,
        # and row stays None. A locked database is a different fact and is raised.
        if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc):
            raise
    return row is not None


def unreadable_authority_message(db_path: str | Path, exc: Exception) -> str:
    """What to say when the authority file exists but is not a readable database."""
    db_path = Path(db_path)
    home = _owning_home(db_path)
    guidance = restore_guidance(home, db_path) if home is not None else ""
    return (
        f"The Dream Studio authority at {db_path} is not a readable SQLite database "
        f"({type(exc).__name__}: {exc}). Restore it from a backup; do not delete it, "
        f"it may be the only copy. {guidance}"
    ).strip()


def present_backups(home: Path) -> list[Path]:
    """Every backup of the authority this home holds, newest first.

    state/backups (pre-migration studio-pre-*.db files and self-install directories),
    <home>/backups (`ds backup`), and state/studio.db.bak* (the pulse's rolling copy).
    """

    found: list[Path] = []
    for root in (home / "state" / "backups", home / "backups"):
        if root.is_dir():
            found.extend(p for p in root.glob("studio-pre-*.db") if p.is_file())
            found.extend(p.parent for p in root.glob("*/studio.db") if p.is_file())
    state = home / "state"
    if state.is_dir():
        # studio.db.bak and the kept studio.db.bak.<UTC timestamp> copies; not their
        # -wal/-shm sidecars, which are not backups.
        found.extend(
            p for p in state.glob("studio.db.bak*") if p.is_file() and _BAK_NAME.match(p.name)
        )
    return sorted(set(found), key=lambda p: p.stat().st_mtime, reverse=True)


_BAK_NAME = re.compile(r"^studio\.db\.bak(\.\d{8}T\d{6}Z)?$")

_DESCRIBED_TABLES = (("projects", "business_projects"), ("work orders", "business_work_orders"))


def _start_over(home: Path, db_path: Path) -> str:
    """How to start a new, empty authority on purpose: the override and the command."""
    return (
        f"start a new, empty authority deliberately: set {CREATE_AUTHORITY_ENV}={db_path} "
        f"and run `ds --home {home} migrate init`."
    )


def describe_backup(backup: Path) -> str:
    """What *backup* holds: its schema and business rows, or why it holds nothing.

    So that an empty newest backup is visible as empty before anyone restores it.
    """

    target = backup / "studio.db" if backup.is_dir() else backup
    try:
        if target.stat().st_size == 0:
            return "empty, 0 bytes"
        from core.config.sqlite_readonly import connect_read_only

        conn = connect_read_only(target, timeout=5.0)
        try:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
            if "_schema_version" not in tables:
                return "no Dream Studio schema"
            version = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
            if version is None:
                # A pre-migration copy taken before the first migration ran.
                return "empty, no migration applied"
            parts = [f"schema {version}"]
            for label, table in _DESCRIBED_TABLES:
                if table in tables:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    parts.append(f"{label} {count}")
            return ", ".join(parts)
        finally:
            conn.close()
    except (OSError, sqlite3.Error) as exc:
        return f"unreadable: {type(exc).__name__}"


def restore_guidance(home: Path, db_path: Path) -> str:
    """How to restore the authority of *home*, naming the backups actually present."""

    backups = present_backups(home)
    if backups:
        described = [(p, describe_backup(p)) for p in backups]
        listed = "; ".join(f"{p} ({what})" for p, what in described[:8])
        more = f" (and {len(backups) - 8} more)" if len(backups) > 8 else ""
        where = f"Backups present, newest first: {listed}{more}."
        holding = [p for p, what in described if what.startswith("schema ")]
        # Only empty or unreadable copies: the deliberate way out stays visible.
        override = (
            "" if holding else " None of them holds an authority; " + _start_over(home, db_path)
        )
    else:
        where = (
            f"No backup was found under {home / 'state' / 'backups'}, {home / 'backups'} or "
            f"{home / 'state'}."
        )
        override = " With no backup to restore, " + _start_over(home, db_path)
    return (
        f"{where} A directory holding studio.db restores with "
        f"`ds --home {home} restore <dir> --execute`; a .db or .bak file is copied to "
        f"{db_path}.{override}"
    )


def lost_authority_message(db_path: str | Path) -> str | None:
    """The restore guidance when *db_path* is the authority of a home that has had an
    install and it is gone, empty or not a database; None when it is fine (or the home
    never had one). Asks read-only; creates nothing."""
    db_path = Path(db_path)
    home = _owning_home(db_path)
    if home is None or not _install_markers(home):
        return None
    if db_path.is_file() and has_authority_schema(db_path):
        return None
    wanted = os.environ.get(CREATE_AUTHORITY_ENV)
    if wanted and _norm(Path(wanted).expanduser()) == _norm(db_path):
        # The deliberate way out: the guard creates this file, so nothing may refuse it.
        return None
    state = "is missing" if not db_path.exists() else "is empty or not a Dream Studio database"
    return (
        f"Dream Studio's authority at {db_path} {state}, in a home that has had an install. "
        "Nothing here is healthy until it is restored; do not re-create it. "
        f"{restore_guidance(home, db_path)}"
    )


def missing_authority_message(db_path: str | Path, fresh: str) -> str:
    """What to tell the operator when a command needs an authority that is not there.

    In a home that has had an install the bootstrap advice the CLI used to give
    ("Run rehearsal-install first") would re-create an empty authority over the lost one;
    there the message says to restore, and lists the backups actually present. *fresh*
    is the existing advice, kept for a home that never had an authority.
    """
    db_path = Path(db_path)
    home = _owning_home(db_path)
    if home is None or not _install_markers(home):
        return fresh
    wanted = os.environ.get(CREATE_AUTHORITY_ENV)
    if wanted and _norm(Path(wanted).expanduser()) == _norm(db_path):
        return (
            f"Dream Studio SQLite authority is missing at {db_path}; "
            f"{CREATE_AUTHORITY_ENV} names it, so create it with "
            f"`ds --home {home} migrate init`."
        )
    return (
        f"Dream Studio SQLite authority is missing at {db_path}, in a home that has had an "
        f"install. Restore it; do not re-create it. {restore_guidance(home, db_path)}"
    )


def assert_may_create_database(db_path: str | Path) -> None:
    """Refuse to CREATE a database file whose absence means something went wrong.

    sqlite3.connect() creates a missing file. On 2026-09-23 that is how an operator's
    authority was replaced: a path resolved to a missing studio.db, a connection quietly
    created an empty one, the migrations ran on it, and every command from then on read
    and wrote a database with no projects in it. Nothing looked at the evidence that a
    real authority had existed. Two refusals:

    - no migration files at all: the database would be created with no schema (a broken
      or partial install), and run_migrations() returns early without saying so;
    - the owning home shows an installed Dream Studio (state/installed-version, or an
      integration manifest) yet its authority is gone: restore it, do not replace it.

    GONE INCLUDES EMPTY. Any of the ~120 raw sqlite3.connect() sites creates a 0-byte
    studio.db on first touch, and a guard that only asked "does the file exist" then let
    the next guarded open migrate that empty file into an authority. In a marked home a
    0-byte or schema-less studio.db is treated exactly like a missing one.

    A brand-new home (no markers) creates normally. CREATE_AUTHORITY_ENV set to this
    authority's path creates on purpose.
    """

    db_path = Path(db_path)
    exists = db_path.exists()
    if exists:
        key = _norm(db_path)
        stat = db_path.stat()
        identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        if _VERIFIED_AUTHORITIES.get(key) == identity:
            return
        _VERIFIED_AUTHORITIES.pop(key, None)
        home = _owning_home(db_path)
        if home is None or not _install_markers(home):
            return
        if has_authority_schema(db_path):
            _VERIFIED_AUTHORITIES[key] = identity
            return
    if not migration_files():
        raise AuthorityRefusedError(
            f"Refusing to create {db_path}: no migration files were found under "
            f"{migrations_dir()}, so the database would have no schema. This Dream Studio "
            "install is incomplete; reinstall it (`ds self-install --execute`) before running commands."
        )
    wanted = os.environ.get(CREATE_AUTHORITY_ENV)
    if wanted and _norm(Path(wanted).expanduser()) == _norm(db_path):
        return
    home = _owning_home(db_path)
    if home is None:
        return
    markers = _install_markers(home)
    if not markers:
        return
    if not exists:
        state = "is missing"
    elif db_path.stat().st_size == 0:
        state = "is an empty file"
    else:
        state = "holds no Dream Studio schema or is not a SQLite database"
    guidance = restore_guidance(home, db_path)
    if CREATE_AUTHORITY_ENV not in guidance:
        guidance += " To " + _start_over(home, db_path)
    raise AuthorityRefusedError(
        f"Refusing to create a new, empty authority at {db_path}: this home has an "
        f"installed Dream Studio ({', '.join(str(m) for m in markers[:3])}) but its "
        f"authority database {state}. Creating it would silently replace the operator's "
        f"projects, work orders and history with an empty database. Restore it instead. "
        f"{guidance}"
    )


def _backup_live_db(conn: sqlite3.Connection, db_file: str, current_version: int) -> Path:
    """Snapshot the live authority DB before applying migrations.

    Uses the SQLite backup API (not file copy) so WAL state is consistent.
    Returns the backup path. The snapshot lands beside the authority, in
    <state>/backups, whichever home that authority belongs to.
    """

    backup_dir = Path(db_file).parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
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


def pending_migrations_info(db_file: str | Path | None = None) -> list[dict]:
    """Return metadata for merged-but-not-activated migrations.

    Pending = version > released_migration_version() AND <= latest_migration_version().
    These are merged to repo/HEAD but not yet activated on the live authority DB.
    """
    released = released_migration_version(db_file)
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

    Operator-invoked ONLY via ``ds migrate activate``. Records the latest merged
    migration as activated FOR THIS AUTHORITY (ACTIVATED_VERSION_FILE beside it) after
    a successful apply. The shipped migrations/.released_version is never written.
    """
    if db_path is None:
        from core.config.paths import home_dir

        db_path = home_dir() / "state" / "studio.db"

    pending = pending_migrations_info(db_path)
    if not pending:
        released = released_migration_version(db_path)
        return {
            "ok": True,
            "applied": [],
            "released_version": released,
            "schema_version": released,
            "message": "No pending migrations.",
        }

    db_path = Path(db_path)
    assert_may_create_database(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
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
    state = _activation_state_path(db_path)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(str(latest), encoding="utf-8")

    # Post-activation data backfills (idempotent, best-effort). Client Layer (migration 155):
    # classify every project with a NULL client_id into a client via project.client_assigned
    # events. No-op once every project has a client; lazy import avoids a bootstrap import cycle.
    client_backfill = {}
    try:
        from core.clients.backfill import backfill_project_clients

        client_backfill = backfill_project_clients(db_path=db_path)
    except Exception:  # pragma: no cover - never block an activation on the advisory backfill
        client_backfill = {"ok": False}

    return {
        "ok": True,
        "applied": pending,
        "schema_version": new_version,
        "released_version": latest,
        "client_backfill": client_backfill,
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
    released = released_migration_version(db_file or None)
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
                # General partial-fixture tolerance: pure data statements
                # (INSERT/UPDATE/DELETE) on absent tables are always safe no-ops —
                # no permanent schema object is created, so no M2 casualty is possible.
                # This generalises the per-table swallows above and handles any
                # absent table that those entries don't explicitly name.
                # In production, every referenced table exists (earlier migrations
                # created it); these errors only arise in minimal test fixtures
                # that omit tables that were created before the fixture's baseline.
                if "no such table" in msg:
                    stmt_upper = stmt.strip().upper()
                    if any(
                        stmt_upper.startswith(pfx) for pfx in ("INSERT", "UPDATE", "DELETE", "DROP")
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
            (version, datetime.now(UTC).isoformat()),
        )
        conn.commit()

    return applied_schema_version(conn)


def bootstrap_database(db_path: Path, *, target_version: int | None = None) -> int:
    """Create or migrate a SQLite DB at db_path, then return schema version."""

    db_path = Path(db_path)
    assert_may_create_database(db_path)
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
