"""ds memory ingest-entries/ingest-status/dedup-orphans — memory_entries maintenance.

Split from interfaces/cli/ds_memory.py (WO-GF-CLI-split). Owns the three
memory_entries-table-adjacent commands: syncing domain tables into
memory_entries (Chain 7), reporting the last automated ingestion run, and
deduping NULL-source_type orphan rows.
"""

from __future__ import annotations

import json
import sys


def cmd_memory_ingest_entries(args) -> int:
    """Entry point for `ds memory ingest-entries`.

    Syncs domain tables (reg_gotchas, raw_lessons, corrections, decisions) into
    memory_entries via run_all_ingestion(). Chain 7 prerequisite — populates the
    SQLite table queried by the on-context-inject hook.
    """
    dry_run = getattr(args, "dry_run", False)
    if dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "note": "dry-run: no changes written"}))
        return 0

    try:
        from core.memory.ingestion import run_all_ingestion
        from core.memory.store import MemoryStore

        store = MemoryStore()
        results = run_all_ingestion(store=store)
        summary = {
            "ok": True,
            "consumers": [
                {
                    "name": r.consumer_name,
                    "records_found": r.records_found,
                    "records_ingested": r.records_ingested,
                    "records_updated": r.records_updated,
                    "records_skipped": r.records_skipped,
                    "errors": r.errors,
                }
                for r in results
            ],
            "total_ingested": sum(r.records_ingested for r in results),
            "total_updated": sum(r.records_updated for r in results),
        }
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2))
    return 0


def cmd_memory_ingest_status(args) -> int:
    """Entry point for `ds memory ingest-status`.

    Reads ~/.dream-studio/state/memory-ingest-last-run.json and prints the
    last automated ingestion run summary.
    """
    import os
    from pathlib import Path

    state_file = (
        Path(os.path.expanduser("~")) / ".dream-studio" / "state" / "memory-ingest-last-run.json"
    )
    if not state_file.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "No ingestion run recorded yet. Memory ingestion fires automatically at session end via the Stop hook.",
                }
            )
        )
        return 0

    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception as exc:
        print(
            json.dumps({"ok": False, "error": f"Could not read state file: {exc}"}), file=sys.stderr
        )
        return 1

    print(json.dumps(data, indent=2))
    return 0


def cmd_memory_dedup_orphans(args) -> int:
    """Entry point for `ds memory dedup-orphans`.

    Removes NULL-source_type memory_entries that have a content-matched keyed
    counterpart. Dry-run by default; pass --execute to commit deletions.
    """
    from core.config.database import get_connection
    from core.memory.orphan_dedup import dedup_orphans

    try:
        with get_connection() as conn:
            result = dedup_orphans(conn, dry_run=not args.execute)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    payload = {
        "ok": not result.errors,
        "mode": "execute" if args.execute else "dry_run",
        "candidates_found": result.candidates_found,
        "deleted": result.deleted,
        "preserved_null_unmatched": result.preserved_null,
        "errors": result.errors,
    }
    print(json.dumps(payload, indent=2))
    return 0 if not result.errors else 1
