#!/usr/bin/env python3
"""Local backup and restore CLI for dream-studio's SQLite database.

Usage:
    py scripts/studio_backup.py                  # create backup
    py scripts/studio_backup.py --restore        # restore from default .bak
    py scripts/studio_backup.py --restore <path> # restore from specific file
    py scripts/studio_backup.py --export <path>  # copy .bak to target path
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HOOKS_LIB = SCRIPT_DIR.parent / "hooks" / "lib"
sys.path.insert(0, str(HOOKS_LIB.parent.parent))

from hooks.lib import paths


def _db_path() -> Path:
    return paths.state_dir() / "studio.db"


def _default_bak_path() -> Path:
    return _db_path().with_suffix(".db.bak")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup(db: Path | None = None) -> Path:
    """Create a backup of studio.db using the SQLite online backup API."""
    src_path = db or _db_path()
    if not src_path.is_file():
        print(f"ERROR: Database not found at {src_path}", file=sys.stderr)
        sys.exit(1)

    bak_path = src_path.with_suffix(".db.bak")
    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(bak_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    size_kb = bak_path.stat().st_size / 1024
    print(f"Backup created: {bak_path} ({size_kb:.1f} KB)")
    return bak_path


def restore(source: Path | None = None, db: Path | None = None) -> Path:
    """Restore studio.db from a backup file.

    Creates a pre-restore safety copy before overwriting.
    """
    bak_path = source or _default_bak_path()
    if not bak_path.is_file():
        print(f"ERROR: Backup file not found at {bak_path}", file=sys.stderr)
        sys.exit(1)

    # Validate the backup is a real SQLite DB
    try:
        conn = sqlite3.connect(str(bak_path))
        conn.execute("SELECT count(*) FROM sqlite_master")
        conn.close()
    except sqlite3.DatabaseError:
        print(f"ERROR: {bak_path} is not a valid SQLite database", file=sys.stderr)
        sys.exit(1)

    db_path = db or _db_path()

    # Safety copy before overwrite
    if db_path.is_file():
        safety = db_path.with_suffix(".db.pre-restore.bak")
        shutil.copy2(str(db_path), str(safety))
        print(f"Safety copy: {safety}")

    # Restore using SQLite backup API (safe for WAL mode)
    src = sqlite3.connect(str(bak_path))
    dst = sqlite3.connect(str(db_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    size_kb = db_path.stat().st_size / 1024
    print(f"Restored: {db_path} ({size_kb:.1f} KB)")
    return db_path


def export(target: str | Path, db: Path | None = None) -> Path:
    """Copy the latest .bak to a target path (e.g. OneDrive/Dropbox folder)."""
    bak_path = _default_bak_path()
    if not bak_path.is_file():
        print("No backup exists yet. Creating one first...")
        bak_path = backup(db)

    target_path = Path(target).resolve()
    if target_path.is_dir():
        target_path = target_path / f"studio-{_timestamp()}.db.bak"

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(bak_path), str(target_path))

    size_kb = target_path.stat().st_size / 1024
    print(f"Exported: {target_path} ({size_kb:.1f} KB)")
    return target_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Backup and restore dream-studio SQLite database"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--restore",
        nargs="?",
        const="__default__",
        metavar="PATH",
        help="Restore from .bak (default) or a specific file",
    )
    group.add_argument(
        "--export",
        metavar="PATH",
        help="Copy latest backup to target path",
    )
    group.add_argument(
        "--cloud",
        nargs="*",
        metavar="CMD",
        help="Cloud backup subcommands: setup, push, pull, auto",
    )

    args = parser.parse_args(argv)

    if args.restore is not None:
        source = None if args.restore == "__default__" else Path(args.restore)
        restore(source)
    elif args.export:
        export(args.export)
    elif args.cloud is not None:
        _cloud_dispatch(args.cloud)
    else:
        backup()


def _cloud_dispatch(cloud_args: list[str]) -> None:
    """Placeholder for T023 cloud subcommands."""
    if not cloud_args:
        print("Usage: studio_backup.py --cloud <setup|push|pull|auto>")
        sys.exit(1)
    print(f"Cloud subcommand '{cloud_args[0]}' not yet implemented.")
    sys.exit(1)


if __name__ == "__main__":
    main()
