#!/usr/bin/env python3
"""Recover stuck events from `failed/` back to `spool/` for re-ingestion.

The pre-A0 hand-built dict emissions in
``core/work_orders/start.py`` / ``core/work_orders/close.py`` /
``core/milestones/close.py`` omitted ``schema_version``. The ingestor
requires it (``spool/ingestor.py:23-25``), so those events were moved
to ``failed/`` with reason ``missing_fields: ['schema_version']``.
``spool/writer.py:14-15`` now defensively enriches missing
``schema_version`` for *new* writes, but events that landed in
``failed/`` before that defense are permanently stuck unless requeued.

A0 (this script) rewrites each stuck JSON in place with the missing
field(s) added, then moves the file from ``failed/`` to ``spool/``
for the ingestor to pick up.

Usage::

    python scripts/requeue_failed.py             # requeue everything
    python scripts/requeue_failed.py --dry-run   # list what would change
    python scripts/requeue_failed.py --filter work_order   # only matching event_type substring
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

# Allow `python scripts/requeue_failed.py` to find the repo packages.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from spool.config import get_spool_root  # noqa: E402 — must come after sys.path edit


def _iter_failed_events(failed_dir: Path):
    if not failed_dir.is_dir():
        return
    for f in sorted(failed_dir.glob("*.json")):
        # The ingestor writes `<event_id>.reason.json` sidecars under
        # `failed/reasons/` (post-Slice 6c) and historically also at the
        # top level of `failed/`. Skip both.
        if f.name.endswith(".reason.json"):
            continue
        yield f


def _enrich(data: dict) -> tuple[dict, list[str]]:
    """Add any fields the ingestor requires that are missing. Return
    (enriched_data, list_of_fields_added)."""

    added: list[str] = []
    if "schema_version" not in data:
        data["schema_version"] = 1
        added.append("schema_version")
    if "event_id" not in data:
        data["event_id"] = str(uuid.uuid4())
        added.append("event_id")
    return data, added


def requeue(
    *,
    failed_dir: Path,
    spool_dir: Path,
    event_type_filter: str | None = None,
    dry_run: bool = False,
) -> int:
    """Requeue stuck events. Returns the number of events processed."""

    processed = 0
    for f in _iter_failed_events(failed_dir):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"SKIP {f.name}: cannot read — {exc}", file=sys.stderr)
            continue

        event_type = data.get("event_type", "<unknown>")
        if event_type_filter and event_type_filter not in event_type:
            continue

        enriched, added_fields = _enrich(data)
        added_str = ",".join(added_fields) if added_fields else "<no-op>"

        if dry_run:
            print(f"WOULD-REQUEUE {f.name} (event_type={event_type}, would-add={added_str})")
            processed += 1
            continue

        target = spool_dir / f.name
        try:
            target.write_text(json.dumps(enriched), encoding="utf-8")
        except OSError as exc:
            print(f"FAIL {f.name}: write to spool/ — {exc}", file=sys.stderr)
            continue

        try:
            f.unlink()
        except OSError as exc:
            # The spool/ copy already landed; the failed/ copy is stale.
            # Surface the issue but continue — the duplicate will be
            # dedup'd by event_id when the ingestor runs.
            print(
                f"WARN {f.name}: requeued but could not unlink failed/ copy — {exc}",
                file=sys.stderr,
            )

        print(f"REQUEUED {f.name} (event_type={event_type}, added={added_str})")
        processed += 1
    return processed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List what would change without modifying anything."
    )
    parser.add_argument(
        "--filter",
        dest="event_type_filter",
        default=None,
        help="Substring filter on event_type (default: all events).",
    )
    args = parser.parse_args()

    try:
        root = get_spool_root()
    except Exception as exc:
        print(f"ERROR resolving spool root: {exc}", file=sys.stderr)
        return 1

    failed_dir = root / "failed"
    spool_dir = root / "spool"
    spool_dir.mkdir(parents=True, exist_ok=True)

    if not failed_dir.is_dir():
        print(f"No failed/ directory at {failed_dir} — nothing to requeue.")
        return 0

    try:
        count = requeue(
            failed_dir=failed_dir,
            spool_dir=spool_dir,
            event_type_filter=args.event_type_filter,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"ERROR during requeue: {exc}", file=sys.stderr)
        return 1

    verb = "would requeue" if args.dry_run else "requeued"
    print(f"\n{verb} {count} event(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
