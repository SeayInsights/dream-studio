"""Atomic file operations and backup-before-write for the integration installer."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, UTC
from pathlib import Path


def atomic_write(target: Path, content: str) -> None:
    """Write content atomically using temp-file + rename pattern."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_copy(source: Path, target: Path) -> None:
    """Copy source to target atomically using temp-file + rename pattern."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        shutil.copy2(source, tmp)
        os.replace(tmp, target)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def backup_before_write(target: Path, backup_dir: Path, *, relative_to: Path | None = None) -> Path:
    """Copy target to backup_dir with a timestamp suffix before modifying it.

    With *relative_to*, the backup keeps the target's path relative to it, so seven
    `__init__.py` files under one root are seven backups, not one overwritten seven
    times. Returns the backup path (whether or not the source existed).
    """
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rel_parent = Path()
    if relative_to is not None:
        try:
            rel_parent = target.resolve().relative_to(relative_to.resolve()).parent
        except ValueError:
            rel_parent = Path()
    backup_path = backup_dir / rel_parent / f"{target.name}.{ts}.bak"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copy2(target, backup_path)
    return backup_path
