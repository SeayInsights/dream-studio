#!/usr/bin/env python3
"""Disaster recovery: unzip a spool archive and replay events through the ingestor.

Usage::

    py scripts/spool_restore.py <archive_name> [--dry-run] [--db-path PATH] [--spool-root PATH]

``archive_name`` is the bare filename (no path) of the archive located under
``{spool_root}/archives/``.  Two formats are supported:

* **Weekly**: ``spool-processed-YYYY-MM-DD.zip`` — contains individual
  ``{event_id}.json`` files.
* **Yearly**: ``spool-processed-YYYY.zip`` — contains weekly ``.zip`` files,
  each of which contains individual ``{event_id}.json`` files.

WARNING
-------
This script replays spool events into SQLite.  Run only after SQLite loss or
corruption.  Running it on a healthy database is safe (events already ingested
will be deduped by the ingestor), but generates unnecessary write traffic.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import time
import zipfile
from pathlib import Path

# Allow ``py scripts/spool_restore.py`` to find the repo packages.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spool.config import get_spool_root  # noqa: E402
from spool.ingestor import ingest_pending  # noqa: E402
from spool.states import SpoolState, ensure_dirs, state_dir  # noqa: E402

_WEEKLY_RE = re.compile(r"^spool-processed-\d{4}-\d{2}-\d{2}\.zip$")
_YEARLY_RE = re.compile(r"^spool-processed-\d{4}\.zip$")

_LARGE_WEEKLY_THRESHOLD = 1000  # events
_LARGE_YEARLY_THRESHOLD = 52    # weekly zips


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify(name: str) -> str:
    """Return 'weekly' or 'yearly', or raise ValueError."""
    if _WEEKLY_RE.match(name):
        return "weekly"
    if _YEARLY_RE.match(name):
        return "yearly"
    raise ValueError(
        f"Archive name '{name}' does not match expected patterns:\n"
        "  weekly: spool-processed-YYYY-MM-DD.zip\n"
        "  yearly: spool-processed-YYYY.zip"
    )


def _json_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Return ZipInfo entries for all direct .json members (non-directory)."""
    return [m for m in zf.infolist() if not m.is_dir() and m.filename.endswith(".json")]


def _copy_to_inbox(zf: zipfile.ZipFile, member: zipfile.ZipInfo, inbox: Path) -> bool:
    """Extract *member* from *zf* into *inbox*.

    Uses the bare filename (strips any directory prefix).
    Returns True if the file was written, False if it already existed (skipped).
    """
    dest = inbox / Path(member.filename).name
    if dest.exists():
        return False
    dest.write_bytes(zf.read(member))
    return True


# ---------------------------------------------------------------------------
# Weekly restore
# ---------------------------------------------------------------------------


def restore_weekly(
    archive_path: Path,
    inbox: Path,
    *,
    dry_run: bool,
    db_path: Path | None,
    root: Path,
) -> None:
    with zipfile.ZipFile(archive_path) as zf:
        json_members = _json_members(zf)

    total = len(json_members)
    archive_name = archive_path.name

    if dry_run:
        print("=== DISASTER RECOVERY (DRY RUN) ===")
        print(f"Archive: {archive_name} (weekly)")
        print(f"Files found: {total} events")
        print(f"Would extract to: {inbox}")
        print("No changes made (dry run).")
        return

    print("=== DISASTER RECOVERY ===")
    print(f"Archive: {archive_name} (weekly)")
    print(f"Files to restore: {total} events")
    print(f"WARNING: This will replay {total} events into SQLite.")

    if total > _LARGE_WEEKLY_THRESHOLD:
        print(
            f"WARNING: Large archive ({total} events > {_LARGE_WEEKLY_THRESHOLD} threshold). "
            "Proceeding in 3 seconds..."
        )
        time.sleep(3)

    print("Extracting events to spool inbox...")
    written = 0
    skipped = 0
    with zipfile.ZipFile(archive_path) as zf:
        for member in json_members:
            if _copy_to_inbox(zf, member, inbox):
                written += 1
            else:
                skipped += 1

    print(f"  Extracted: {written}, already present (skipped): {skipped}")
    print("Ingesting events...")
    result = ingest_pending(root=root, db_path=db_path)
    print(
        f"Done: processed={result.processed}, failed={result.failed}, "
        f"skipped={result.skipped}"
    )


# ---------------------------------------------------------------------------
# Yearly restore
# ---------------------------------------------------------------------------


def _scan_yearly(archive_path: Path) -> tuple[int, int]:
    """Scan a yearly archive and return (weekly_zip_count, total_event_count)."""
    weekly_count = 0
    event_count = 0
    with zipfile.ZipFile(archive_path) as outer:
        for member in outer.infolist():
            if member.is_dir() or not member.filename.endswith(".zip"):
                continue
            weekly_count += 1
            raw = outer.read(member)
            with zipfile.ZipFile(io.BytesIO(raw)) as inner:
                event_count += len(_json_members(inner))
    return weekly_count, event_count


def restore_yearly(
    archive_path: Path,
    inbox: Path,
    *,
    dry_run: bool,
    db_path: Path | None,
    root: Path,
) -> None:
    archive_name = archive_path.name

    print("Scanning yearly archive (this may take a moment)...")
    weekly_count, event_count = _scan_yearly(archive_path)

    if dry_run:
        print("=== DISASTER RECOVERY (DRY RUN) ===")
        print(f"Archive: {archive_name} (yearly)")
        print(f"Files found: {event_count} events across {weekly_count} weekly archives")
        print(f"Would extract to: {inbox}")
        print("No changes made (dry run).")
        return

    print("=== DISASTER RECOVERY ===")
    print(f"Archive: {archive_name} (yearly)")
    print(f"Files to restore: {event_count} events across {weekly_count} weekly archives")
    print(f"WARNING: This will replay {event_count} events into SQLite.")

    if weekly_count > _LARGE_YEARLY_THRESHOLD:
        print(
            f"WARNING: Large yearly archive ({weekly_count} weekly zips > "
            f"{_LARGE_YEARLY_THRESHOLD} threshold). Proceeding in 3 seconds..."
        )
        time.sleep(3)

    print("Extracting events to spool inbox...")
    total_written = 0
    total_skipped = 0

    with zipfile.ZipFile(archive_path) as outer:
        weekly_members = [
            m for m in outer.infolist()
            if not m.is_dir() and m.filename.endswith(".zip")
        ]
        for idx, weekly_member in enumerate(weekly_members, start=1):
            print(
                f"  Processing weekly zip {idx}/{len(weekly_members)}: "
                f"{weekly_member.filename}"
            )
            raw = outer.read(weekly_member)
            with zipfile.ZipFile(io.BytesIO(raw)) as inner:
                for event_member in _json_members(inner):
                    if _copy_to_inbox(inner, event_member, inbox):
                        total_written += 1
                    else:
                        total_skipped += 1

    print(f"  Extracted: {total_written}, already present (skipped): {total_skipped}")
    print("Ingesting events...")
    result = ingest_pending(root=root, db_path=db_path)
    print(
        f"Done: processed={result.processed}, failed={result.failed}, "
        f"skipped={result.skipped}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "archive_name",
        help=(
            "Filename of the archive to restore (e.g. spool-processed-2026-05-18.zip "
            "or spool-processed-2026.zip). Must exist in {spool_root}/archives/."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="List what would be restored without writing anything or calling the ingestor.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        metavar="PATH",
        help="Override the SQLite database path (default: auto-resolved by ingestor).",
    )
    parser.add_argument(
        "--spool-root",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Override the spool root directory "
            "(default: resolved from DS_SPOOL_ROOT env or ~/.dream-studio/events)."
        ),
    )
    args = parser.parse_args()

    # Resolve spool root.
    if args.spool_root is not None:
        root = args.spool_root.resolve()
    else:
        try:
            root = get_spool_root()
        except Exception as exc:
            print(f"ERROR resolving spool root: {exc}", file=sys.stderr)
            return 1

    # Ensure all spool state directories exist.
    try:
        ensure_dirs(root)
    except Exception as exc:
        print(f"ERROR creating spool directories under {root}: {exc}", file=sys.stderr)
        return 1

    # Locate the archive under {spool_root}/archives/.
    archive_dir = state_dir(SpoolState.ARCHIVES, root)
    archive_path = archive_dir / args.archive_name

    if not archive_path.exists():
        print(
            f"ERROR: Archive not found: {archive_path}\n"
            f"Expected location: {archive_dir}",
            file=sys.stderr,
        )
        return 1

    if not zipfile.is_zipfile(archive_path):
        print(f"ERROR: File is not a valid zip archive: {archive_path}", file=sys.stderr)
        return 1

    # Classify archive format from filename.
    try:
        kind = _classify(args.archive_name)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # The inbox is the SPOOL state dir — this is where ingest_pending reads from.
    inbox = state_dir(SpoolState.SPOOL, root)
    inbox.mkdir(parents=True, exist_ok=True)

    db_path: Path | None = args.db_path.resolve() if args.db_path else None

    try:
        if kind == "weekly":
            restore_weekly(
                archive_path,
                inbox,
                dry_run=args.dry_run,
                db_path=db_path,
                root=root,
            )
        else:
            restore_yearly(
                archive_path,
                inbox,
                dry_run=args.dry_run,
                db_path=db_path,
                root=root,
            )
    except zipfile.BadZipFile as exc:
        print(f"ERROR: Corrupt or invalid zip file — {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: I/O failure — {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: Unexpected failure — {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
