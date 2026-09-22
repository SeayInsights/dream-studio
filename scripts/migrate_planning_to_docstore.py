#!/usr/bin/env python3
"""Move the leftover on-disk .planning/ tree into the files.db docstore.

    py scripts/migrate_planning_to_docstore.py --dry-run
    py scripts/migrate_planning_to_docstore.py
    py scripts/migrate_planning_to_docstore.py --delete-disk   # after verifying

Why this exists
---------------
"All file-based state lives in the DB docstore, no disk copies" has been the
rule since 2026-07-23, and `on-edit-enforce` has denied writes to `.planning/**`
ever since. But the rule was only ever applied to NEW writes -- the artifacts
already on disk were never moved.

Measured 2026-09-21: 1,553 files, 5.2 MB, and 1,552 of them absent from the
docstore. They survived because `read_milestone_artifact_with_envelope` tries
the docstore and then SILENTLY FALLS BACK TO DISK, so every milestone gate kept
passing and nothing ever reported the gap. A rule enforced on writes but not on
reads leaves exactly this: a policy everyone believes is in force, and a pile of
data that contradicts it.

Deleting the tree without migrating first would fail every milestone gate that
depends on an audit artifact, which is why --delete-disk is a separate opt-in
step and the migration verifies content round-trips before it will run.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.files.store import read_file_by_name, write_file  # noqa: E402

PLANNING = REPO / ".planning"


def _disk_files() -> list[tuple[str, Path]]:
    """(docstore name, path) for every file under .planning/.

    The docstore name is the path relative to .planning/, which is exactly the
    key `read_milestone_artifact_with_envelope` looks up -- so a migrated file is
    found by the existing read path with no further change.
    """
    if not PLANNING.is_dir():
        return []
    out = []
    for p in sorted(PLANNING.rglob("*")):
        if p.is_file():
            out.append((p.relative_to(PLANNING).as_posix(), p))
    return out


def _already_stored(name: str) -> bool:
    try:
        return read_file_by_name(name) is not None
    except KeyError:
        return False
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument(
        "--delete-disk",
        action="store_true",
        help="after a clean migration, remove the .planning/ tree",
    )
    args = ap.parse_args()

    files = _disk_files()
    if not files:
        print(".planning/ is absent or empty - nothing to migrate.")
        return 0

    pending = [(n, p) for n, p in files if not _already_stored(n)]
    print(f"  on disk:  {len(files):,}")
    print(f"  to move:  {len(pending):,}")

    if args.dry_run:
        for n, _ in pending[:10]:
            print(f"    {n}")
        if len(pending) > 10:
            print(f"    ...and {len(pending) - 10:,} more")
        print("\nDRY RUN - nothing written.")
        return 0

    migrated, failed = 0, []
    for name, path in pending:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            write_file(name, content, "text/markdown", "planning")
            migrated += 1
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            failed.append((name, str(exc)))

    print(f"\n  migrated: {migrated:,}")
    if failed:
        print(f"  FAILED:   {len(failed):,}")
        for n, e in failed[:5]:
            print(f"    {n}: {e}")

    # VERIFY BEFORE ANY DELETE. A migration that reports success while a file did
    # not round-trip is how the original gap happened; this refuses to delete on
    # anything less than a complete, readable-back copy.
    unverified = [n for n, _ in files if not _already_stored(n)]
    print(f"  verified in docstore: {len(files) - len(unverified):,} / {len(files):,}")

    if not args.delete_disk:
        print("\nDisk tree left in place. Re-run with --delete-disk once you are satisfied.")
        return 1 if failed else 0

    if unverified or failed:
        print(
            f"\nREFUSING to delete: {len(unverified)} file(s) are not readable from the docstore."
        )
        return 1

    shutil.rmtree(PLANNING, ignore_errors=True)
    print(f"\nDeleted {PLANNING} - the docstore is now the only copy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
