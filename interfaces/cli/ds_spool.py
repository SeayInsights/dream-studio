"""ds spool subcommands (Slice 3)."""

from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def cmd_ingest(args) -> int:
    """Process all pending spool events."""
    from spool.ingestor import ingest_pending

    result = ingest_pending()
    if result.processed == 0 and result.failed == 0:
        print("no events to ingest")
        return 0
    print(f"ingested: processed={result.processed} failed={result.failed} skipped={result.skipped}")
    return 0


def add_spool_subcommand(subparsers):
    """Register the 'spool' subcommand group onto the parent parser."""
    spool_parser = subparsers.add_parser("spool", help="Spool event pipeline commands")
    spool_sub = spool_parser.add_subparsers(dest="spool_cmd")

    ingest_parser = spool_sub.add_parser("ingest", help="Process pending spool events")
    ingest_parser.set_defaults(func=cmd_ingest)

    return spool_parser
