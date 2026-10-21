"""Atomic file operations and backup-before-write for the integration installer."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, UTC
from pathlib import Path


def file_newline(path: Path) -> str | None:
    """The newline an existing text file uses: "\\r\\n" when most of its line ends are CRLF,
    "\\n" when most are bare LF (a tie goes to LF), None when it is missing or has no line end
    (a lone CR is not one)."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    if crlf == 0 and lf == 0:
        return None
    return "\r\n" if crlf > lf else "\n"


def atomic_write(target: Path, content: str, newline: str = "\n") -> None:
    """Write content atomically using temp-file + rename pattern.

    The text is written with `newline` (default LF, on every OS). It used to take the
    platform's newlines, so on Windows an installed file was CRLF where the committed source
    is LF and no file hashed equal to its source. A caller merging into a file the operator
    owns passes that file's own newline (file_newline)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8", newline=newline)
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
    # Microseconds, and a counter if that still collides: two backups of one file in the
    # same second used to be one.
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    rel_parent = Path()
    if relative_to is not None:
        try:
            rel_parent = target.resolve().relative_to(relative_to.resolve()).parent
        except ValueError:
            rel_parent = Path()
    backup_path = backup_dir / rel_parent / f"{target.name}.{ts}.bak"
    n = 1
    while backup_path.exists():
        backup_path = backup_dir / rel_parent / f"{target.name}.{ts}-{n}.bak"
        n += 1
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copy2(target, backup_path)
    return backup_path
