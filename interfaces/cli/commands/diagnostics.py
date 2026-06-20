"""ds diagnostics command group — TA3 diagnostic log stream (TA3)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``diagnostics`` subparser tree to *subcommands*."""
    diag_cmd = subcommands.add_parser(
        "diagnostics", help="Read or clear the TA3 diagnostic log stream"
    )
    diag_sub = diag_cmd.add_subparsers(dest="diagnostics_command", required=True)

    diag_list = diag_sub.add_parser("list", help="Show recent diagnostic entries")
    diag_list.add_argument(
        "--source", default=None, help="Filter by source prefix (e.g. token-capture)"
    )
    diag_list.add_argument(
        "--category",
        default=None,
        choices=["failure", "anomaly", "performance"],
        help="Filter by category",
    )
    diag_list.add_argument(
        "--limit", type=int, default=50, help="Max entries to return (default 50)"
    )

    diag_clear = diag_sub.add_parser("clear", help="Truncate diagnostic log files")
    diag_clear.add_argument(
        "--source", default=None, help="Clear only files matching this source prefix"
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(args: argparse.Namespace) -> int:
    from core.telemetry.diagnostics import _diagnostics_dir

    diag_dir = _diagnostics_dir()

    if args.diagnostics_command == "list":
        source_filter = getattr(args, "source", None)
        cat_filter = getattr(args, "category", None)
        limit = getattr(args, "limit", 50)
        entries: list[dict[str, Any]] = []
        if diag_dir.exists():
            jsonl_files = sorted(diag_dir.glob("*.jsonl"))
            if source_filter:
                jsonl_files = [f for f in jsonl_files if source_filter in f.stem]
            for path in jsonl_files:
                try:
                    for line in path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        entry = json.loads(line)
                        if cat_filter and entry.get("category") != cat_filter:
                            continue
                        entry["_file"] = path.name
                        entries.append(entry)
                except Exception:
                    pass
        # Most recent first; apply limit.
        entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
        entries = entries[:limit]
        print(json.dumps({"ok": True, "count": len(entries), "entries": entries}, indent=2))
        return 0

    if args.diagnostics_command == "clear":
        source_filter = getattr(args, "source", None)
        cleared: list[str] = []
        if diag_dir.exists():
            for path in diag_dir.glob("*.jsonl"):
                if source_filter and source_filter not in path.stem:
                    continue
                try:
                    path.write_text("", encoding="utf-8")
                    cleared.append(path.name)
                except Exception:
                    pass
        print(json.dumps({"ok": True, "cleared": cleared}, indent=2))
        return 0

    print(f"Unknown diagnostics command: {args.diagnostics_command}", file=sys.stderr)
    return 1
