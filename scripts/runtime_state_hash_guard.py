#!/usr/bin/env python3
"""Observe native runtime state before and after a validation command.

This diagnostic helper is intentionally read-only. It records metadata for
watched files, runs one command, records metadata again, and fails if any
watched file changed. It does not open SQLite, restore backups, copy files, or
decide runtime authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

MUTATION_EXIT_CODE = 90


@dataclass(frozen=True)
class FileSnapshot:
    path: str
    exists: bool
    sha256: str | None
    size_bytes: int | None
    mtime_ns: int | None
    mtime_utc: str | None


def default_watch_paths(home: Path | None = None) -> list[Path]:
    state = (home or Path.home()) / ".dream-studio" / "state"
    return [
        state / "studio.db",
        state / "studio.db.bak",
        state / "studio.db.pre-restore.bak",
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def snapshot(path: Path) -> FileSnapshot:
    if not path.exists():
        return FileSnapshot(str(path), False, None, None, None, None)

    stat = path.stat()
    return FileSnapshot(
        path=str(path),
        exists=True,
        sha256=_sha256(path),
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        mtime_utc=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat().replace("+00:00", "Z"),
    )


def changed_paths(
    before: dict[str, FileSnapshot],
    after: dict[str, FileSnapshot],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for path, before_item in before.items():
        after_item = after[path]
        if before_item != after_item:
            changes.append(
                {
                    "path": path,
                    "before": asdict(before_item),
                    "after": asdict(after_item),
                }
            )
    return changes


def run_guard(
    command: list[str],
    *,
    watch_paths: list[Path] | None = None,
    label: str = "runtime_state_hash_guard",
) -> tuple[int, dict[str, Any]]:
    if not command:
        raise ValueError("command is required")

    paths = watch_paths or default_watch_paths()
    before = {str(path): snapshot(path) for path in paths}
    completed = subprocess.run(command, check=False)
    after = {str(path): snapshot(path) for path in paths}
    changes = changed_paths(before, after)

    guard_exit = MUTATION_EXIT_CODE if changes else completed.returncode
    return guard_exit, {
        "label": label,
        "command": command,
        "command_exit": completed.returncode,
        "guard_exit": guard_exit,
        "changed_count": len(changes),
        "changed": changes,
    }


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"HASH_GUARD_LABEL={report['label']}",
        f"COMMAND_EXIT={report['command_exit']}",
        f"HASH_GUARD_CHANGED={report['changed_count']}",
    ]
    for item in report["changed"]:
        before = item["before"]
        after = item["after"]
        lines.extend(
            [
                f"PATH={item['path']}",
                f"  BEFORE_HASH={before['sha256']}",
                f"  AFTER_HASH={after['sha256']}",
                f"  BEFORE_SIZE={before['size_bytes']}",
                f"  AFTER_SIZE={after['size_bytes']}",
                f"  BEFORE_MTIME_UTC={before['mtime_utc']}",
                f"  AFTER_MTIME_UTC={after['mtime_utc']}",
            ]
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail if watched runtime state files change while a command runs."
    )
    parser.add_argument("--label", default="runtime_state_hash_guard")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--watch",
        action="append",
        type=Path,
        default=None,
        help="File to watch. Defaults to native studio.db and local backups.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("command is required after --")

    exit_code, report = run_guard(
        command,
        watch_paths=args.watch,
        label=args.label,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_text(report))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
