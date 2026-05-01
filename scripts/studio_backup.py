#!/usr/bin/env python3
"""Local and cloud backup CLI for dream-studio's SQLite database.

Usage:
    py scripts/studio_backup.py                    # create backup
    py scripts/studio_backup.py --restore          # restore from default .bak
    py scripts/studio_backup.py --restore <path>   # restore from specific file
    py scripts/studio_backup.py --export <path>    # copy .bak to target path
    py scripts/studio_backup.py --cloud setup      # configure rclone remote
    py scripts/studio_backup.py --cloud push       # upload backup to cloud
    py scripts/studio_backup.py --cloud pull       # download backup from cloud
    py scripts/studio_backup.py --cloud auto       # toggle daily auto-push
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
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


def _backup_config_path() -> Path:
    return paths.state_dir() / "backup-config.json"


def _load_backup_config() -> dict:
    cfg = _backup_config_path()
    if cfg.is_file():
        try:
            return json.loads(cfg.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_backup_config(data: dict) -> Path:
    cfg = _backup_config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return cfg


def _has_rclone() -> bool:
    return shutil.which("rclone") is not None


def _rclone_run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["rclone", *args],
        capture_output=True, text=True, timeout=120,
    )


def _cloud_dispatch(cloud_args: list[str]) -> None:
    cmds = {"setup": cloud_setup, "push": cloud_push, "pull": cloud_pull, "auto": cloud_auto}
    if not cloud_args or cloud_args[0] not in cmds:
        print("Usage: studio_backup.py --cloud <setup|push|pull|auto>")
        sys.exit(1)
    cmds[cloud_args[0]]()


def cloud_setup() -> None:
    """Interactive setup: detect rclone, pick provider, test connection, save config."""
    if not _has_rclone():
        print("rclone is not installed.", file=sys.stderr)
        print("")
        print("Install it:")
        print("  Windows:  winget install Rclone.Rclone")
        print("  macOS:    brew install rclone")
        print("  Linux:    curl https://rclone.org/install.sh | sudo bash")
        print("")
        print("Alternatively, use --export <path> to copy backups to a synced folder.")
        sys.exit(1)

    # List existing remotes
    result = _rclone_run(["listremotes"])
    remotes = [r.strip().rstrip(":") for r in result.stdout.strip().splitlines() if r.strip()]

    if remotes:
        print("Existing rclone remotes:")
        for i, r in enumerate(remotes, 1):
            print(f"  {i}. {r}")
        print(f"  {len(remotes) + 1}. Create new remote")
        print("")
        choice = input(f"Select remote [1-{len(remotes) + 1}]: ").strip()
        try:
            idx = int(choice)
            if 1 <= idx <= len(remotes):
                remote_name = remotes[idx - 1]
            else:
                print("Run 'rclone config' to create a new remote, then re-run --cloud setup.")
                sys.exit(0)
        except ValueError:
            print("Invalid selection.")
            sys.exit(1)
    else:
        print("No rclone remotes configured.")
        print("Run 'rclone config' to create one, then re-run --cloud setup.")
        sys.exit(1)

    remote_path = input(f"Remote path for backups [{remote_name}:dream-studio-backup]: ").strip()
    if not remote_path:
        remote_path = f"{remote_name}:dream-studio-backup"

    # Test connection
    print(f"Testing connection to {remote_path}...")
    test = _rclone_run(["mkdir", remote_path])
    if test.returncode != 0:
        print(f"ERROR: Could not reach {remote_path}", file=sys.stderr)
        print(test.stderr, file=sys.stderr)
        sys.exit(1)

    config = _load_backup_config()
    config["remote"] = remote_path
    config["remote_name"] = remote_name
    config["configured_at"] = _timestamp()
    _save_backup_config(config)

    print(f"Cloud backup configured: {remote_path}")
    print(f"Config saved: {_backup_config_path()}")


def cloud_push() -> None:
    """Upload latest .bak to configured rclone remote."""
    if not _has_rclone():
        print("ERROR: rclone is not installed. Run --cloud setup first.", file=sys.stderr)
        sys.exit(1)

    config = _load_backup_config()
    remote = config.get("remote")
    if not remote:
        print("ERROR: No cloud remote configured. Run --cloud setup first.", file=sys.stderr)
        sys.exit(1)

    bak_path = _default_bak_path()
    if not bak_path.is_file():
        print("No backup exists. Creating one first...")
        bak_path = backup()

    dest = f"{remote}/studio-{_timestamp()}.db.bak"
    print(f"Pushing {bak_path.name} -> {dest}...")

    result = _rclone_run(["copyto", str(bak_path), dest])
    if result.returncode != 0:
        print(f"ERROR: Push failed", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    # Also copy as "latest" for easy pull
    latest_dest = f"{remote}/studio-latest.db.bak"
    _rclone_run(["copyto", str(bak_path), latest_dest])

    config["last_push"] = _timestamp()
    _save_backup_config(config)
    print(f"Push complete: {dest}")


def cloud_pull() -> None:
    """Download latest backup from configured rclone remote."""
    if not _has_rclone():
        print("ERROR: rclone is not installed. Run --cloud setup first.", file=sys.stderr)
        sys.exit(1)

    config = _load_backup_config()
    remote = config.get("remote")
    if not remote:
        print("ERROR: No cloud remote configured. Run --cloud setup first.", file=sys.stderr)
        sys.exit(1)

    src = f"{remote}/studio-latest.db.bak"
    pull_path = paths.state_dir() / "studio-cloud-pull.db.bak"

    print(f"Pulling {src}...")
    result = _rclone_run(["copyto", src, str(pull_path)])
    if result.returncode != 0:
        print(f"ERROR: Pull failed", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    size_kb = pull_path.stat().st_size / 1024
    print(f"Downloaded: {pull_path} ({size_kb:.1f} KB)")
    print("")
    answer = input("Restore from this backup? [y/N]: ").strip().lower()
    if answer == "y":
        restore(pull_path)
    else:
        print(f"Backup saved at {pull_path}. Restore later with: --restore {pull_path}")

    config["last_pull"] = _timestamp()
    _save_backup_config(config)


def cloud_auto() -> None:
    """Toggle daily auto-push flag in backup config."""
    config = _load_backup_config()
    if not config.get("remote"):
        print("ERROR: No cloud remote configured. Run --cloud setup first.", file=sys.stderr)
        sys.exit(1)

    current = config.get("auto_push", False)
    config["auto_push"] = not current
    _save_backup_config(config)

    state = "ENABLED" if config["auto_push"] else "DISABLED"
    print(f"Auto-push {state}")
    if config["auto_push"]:
        print("Backups will be pushed to cloud automatically after each daily pulse.")


if __name__ == "__main__":
    main()
