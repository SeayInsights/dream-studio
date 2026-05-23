"""ds spool subcommands (Slice 3 + lifecycle commands)."""

from __future__ import annotations
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Existing command
# ---------------------------------------------------------------------------


def cmd_ingest(args) -> int:
    """Process all pending spool events."""
    from spool.ingestor import ingest_pending

    result = ingest_pending()
    if result.processed == 0 and result.failed == 0:
        print("no events to ingest")
        return 0
    print(f"ingested: processed={result.processed} failed={result.failed} skipped={result.skipped}")
    return 0


# ---------------------------------------------------------------------------
# Command 1: ds spool archive
# ---------------------------------------------------------------------------


def cmd_archive(args) -> int:
    """Bundle prior-week processed files into a dated zip."""
    from spool.lifecycle import archive_week

    result = archive_week()
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


# ---------------------------------------------------------------------------
# Command 2: ds spool consolidate-year [YEAR]
# ---------------------------------------------------------------------------


def cmd_consolidate_year(args) -> int:
    """Bundle prior-year weekly archives into a single yearly zip."""
    from spool.lifecycle import consolidate_year

    result = consolidate_year(year=args.year)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


# ---------------------------------------------------------------------------
# Command 3: ds spool archives list
# ---------------------------------------------------------------------------


def cmd_archives_list(args) -> int:
    """List .zip files in the archives directory."""
    from spool.config import get_spool_root

    archives_dir = get_spool_root() / "archives"
    if not archives_dir.exists():
        print("no archives found")
        return 0

    zips = sorted(archives_dir.glob("*.zip"), key=lambda p: p.name, reverse=True)
    if not zips:
        print("no archives found")
        return 0

    for zp in zips:
        stat = zp.stat()
        size_kb = round(stat.st_size / 1024)
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
        print(f"{zp.name}  {size_kb} KB  {mtime}")

    return 0


# ---------------------------------------------------------------------------
# Command 4: ds spool archives inspect <archive_name>
# ---------------------------------------------------------------------------


def cmd_archives_inspect(args) -> int:
    """List entries inside a spool archive zip."""
    from spool.config import get_spool_root

    archives_dir = get_spool_root() / "archives"
    archive_path = archives_dir / args.archive_name

    if not archive_path.exists():
        print(f"error: archive not found: {args.archive_name}", file=sys.stderr)
        return 1

    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            infos = zf.infolist()
    except zipfile.BadZipFile as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"archive: {args.archive_name}  ({len(infos)} entries)")
    for info in infos:
        print(f"  {info.filename}  {info.file_size} bytes")

    return 0


# ---------------------------------------------------------------------------
# Fallback for bare "ds spool archives"
# ---------------------------------------------------------------------------


def _cmd_archives_help(args) -> int:
    print("Usage: ds spool archives <subcommand>", file=sys.stderr)
    print("Subcommands: list, inspect", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def add_spool_subcommand(subparsers):
    """Register the 'spool' subcommand group onto the parent parser."""
    spool_parser = subparsers.add_parser("spool", help="Spool event pipeline commands")
    spool_sub = spool_parser.add_subparsers(dest="spool_cmd")

    # -- ingest ---------------------------------------------------------------
    ingest_parser = spool_sub.add_parser("ingest", help="Process pending spool events")
    ingest_parser.set_defaults(func=cmd_ingest)

    # -- archive --------------------------------------------------------------
    archive_parser = spool_sub.add_parser(
        "archive", help="Bundle prior-week processed files into a dated zip"
    )
    archive_parser.set_defaults(func=cmd_archive)

    # -- consolidate-year [YEAR] ----------------------------------------------
    cy_parser = spool_sub.add_parser(
        "consolidate-year",
        help="Bundle prior-year weekly archives into a single yearly zip",
    )
    cy_parser.add_argument(
        "year",
        type=int,
        nargs="?",
        default=None,
        help="Year to consolidate (default: previous calendar year)",
    )
    cy_parser.set_defaults(func=cmd_consolidate_year)

    # -- archives (sub-group) -------------------------------------------------
    archives_parser = spool_sub.add_parser("archives", help="Manage spool archives")
    archives_parser.set_defaults(func=_cmd_archives_help)
    archives_sub = archives_parser.add_subparsers(dest="archives_cmd")

    archives_list_parser = archives_sub.add_parser(
        "list", help="List .zip files in the archives directory"
    )
    archives_list_parser.set_defaults(func=cmd_archives_list)

    archives_inspect_parser = archives_sub.add_parser(
        "inspect", help="List entries inside a spool archive zip"
    )
    archives_inspect_parser.add_argument(
        "archive_name",
        help="Name of the archive file (e.g. weekly-2025-W01.zip)",
    )
    archives_inspect_parser.set_defaults(func=cmd_archives_inspect)

    return spool_parser
