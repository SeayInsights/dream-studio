"""ds enforce command group — inspect graduated enforcement (WO-ENFORCE-TIERS).

``ds enforce report`` answers "what would have been blocked, and by which rule" from the
observe/warn-tier records — the artifact that earns a team's consent to escalate from
observe → warn → enforce. ``ds enforce tier`` prints the currently resolved tier. Read-only.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from interfaces.cli.cli_utils import _print


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``enforce`` subparser tree."""
    enforce_cmd = subcommands.add_parser("enforce", help="Inspect graduated enforcement tiers")
    enforce_sub = enforce_cmd.add_subparsers(dest="enforce_command", required=True)

    report_cmd = enforce_sub.add_parser(
        "report", help="What would have been blocked (observe/warn tier), by rule"
    )
    report_cmd.add_argument(
        "--since",
        default=None,
        help="ISO timestamp lower bound (e.g. 2026-08-01T00:00:00Z); default: all recorded",
    )

    enforce_sub.add_parser("tier", help="Print the currently resolved enforcement tier")


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Dispatch ``ds enforce`` subcommands."""
    from runtime.lib import enforcement

    if args.enforce_command == "report":
        report = enforcement.observations_report(since_iso=getattr(args, "since", None))
        return _print({"ok": True, "observe_report": report})

    if args.enforce_command == "tier":
        return _print(
            {"ok": True, "tier": enforcement.resolve_tier(), "tiers": list(enforcement.VALID_TIERS)}
        )

    return _print({"ok": False, "error": f"unknown enforce command: {args.enforce_command}"})
