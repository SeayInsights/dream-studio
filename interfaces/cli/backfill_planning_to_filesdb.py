#!/usr/bin/env python3
"""Backfill every file under .planning/ into the files.db docstore (category 'planning').

Part of the "Files in Database (not on disk)" milestone (WO-FILESDB-P3): .planning
working state lives in the files.db document store, not as loose disk files. This is
the non-destructive first stage — it copies content INTO files.db; it does not delete
anything from disk (later stages redirect writes and drop the disk copies).

Every regular file under .planning/ is stored — all file types, INCLUDING
.planning/personal (which the enforcement layer historically exempted). The file's
path relative to .planning/ is the docstore `name` (e.g. "personal/notes.md"), so the
tree is reconstructable and re-runs are idempotent.

Idempotency: a file is written only when its content differs from the latest stored
version (SHA-256 compare). Re-running writes nothing for unchanged files, so it is
safe to run repeatedly.

Usage:
    py interfaces/cli/backfill_planning_to_filesdb.py            # apply
    py interfaces/cli/backfill_planning_to_filesdb.py --dry-run  # preview only
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.files.store import (  # noqa: E402
    _checksum,
    connect_files,
    ensure_files_schema,
    write_file,
)

_CATEGORY = "planning"


def _latest_checksum(name: str, db_path: Path | None) -> str | None:
    """Return the checksum of the latest stored version of `name`, or None if absent."""
    conn = connect_files(db_path)
    try:
        ensure_files_schema(conn)
        row = conn.execute(
            "SELECT checksum FROM ds_files"
            " WHERE name = ? AND project_id IS NULL"
            " ORDER BY version DESC LIMIT 1",
            (name,),
        ).fetchone()
        return row[0] if row is not None else None
    finally:
        conn.close()


def backfill_planning(
    *,
    planning_dir: Path | None = None,
    db_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Copy every regular file under ``planning_dir`` into files.db (category 'planning').

    Returns a result dict: ``{"written", "skipped", "errors", "total", "dir"}``.
    """
    root = planning_dir if planning_dir is not None else REPO_ROOT / ".planning"
    result: dict[str, Any] = {
        "written": 0,
        "skipped": 0,
        "errors": [],
        "total": 0,
        "dir": str(root),
    }
    if not root.exists():
        return result

    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        result["total"] += 1
        name = path.relative_to(root).as_posix()
        try:
            raw = path.read_bytes()
        except Exception as exc:  # unreadable file — record, keep going
            result["errors"].append(f"{name}: read failed: {exc}")
            continue

        if _latest_checksum(name, db_path) == _checksum(raw):
            result["skipped"] += 1
            continue

        if not dry_run:
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            write_file(name, raw, content_type, _CATEGORY, db_path=db_path)
        result["written"] += 1

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing.")
    args = parser.parse_args(argv)
    result = backfill_planning(dry_run=args.dry_run)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
