"""ds analyze command group — brownfield intake and repo analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from interfaces.cli.cli_utils import _print

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``analyze`` subparser tree to *subcommands*."""
    analyze_cmd = subcommands.add_parser(
        "analyze", help="Analysis commands (brownfield intake, repo scanning)"
    )
    analyze_sub = analyze_cmd.add_subparsers(dest="analyze_command", required=True)

    analyze_aggregate = analyze_sub.add_parser(  # noqa: F841
        "aggregate", help="Run ML metrics aggregation (studio.db → aggregate_metrics.db)"
    )

    analyze_intake = analyze_sub.add_parser(
        "intake", help="Register a brownfield repo for intake scanning"
    )
    analyze_intake.add_argument(
        "target_path",
        metavar="TARGET_PATH",
        help="Path to the repository to scan",
    )
    analyze_intake.add_argument(
        "--persistent",
        action="store_true",
        default=False,
        help=(
            "Write a .dream-studio-project marker file for persistent session attribution "
            "(skips the interactive prompt)"
        ),
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    if args.analyze_command == "intake":
        return _analyze_intake(args, source_root=source_root, dream_studio_home=dream_studio_home)
    if args.analyze_command == "aggregate":
        return _analyze_aggregate(args)
    print(f"Unknown analyze command: {args.analyze_command}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


def _analyze_aggregate(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Run ML metrics aggregation from studio.db into aggregate_metrics.db."""
    from core.analytics.aggregate_metrics import run_aggregation

    result = run_aggregation()
    return _print(result)


def _analyze_intake(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Register a brownfield repo for intake scanning.

    Prompts interactively when stdin is a TTY and --persistent is not passed.
    Non-interactive callers (CI, scripts, pipes) get write_marker=False by default.
    """
    from core.projects.intake import register_project_for_intake

    target_path = Path(args.target_path).resolve()

    # Determine write_marker from flag or interactive prompt
    write_marker: bool = getattr(args, "persistent", False)

    if not write_marker and sys.stdin.isatty():
        print(
            "Scan type:\n"
            "  [1] One-time scan  (default — no marker written, no persistent project)\n"
            "  [2] Persistent project (write .dream-studio-project marker for session attribution)\n"
            "Enter 1 or 2 [1]: ",
            end="",
            flush=True,
        )
        try:
            choice = sys.stdin.readline().strip()
        except OSError:
            choice = ""
        if choice == "2":
            write_marker = True

    result = register_project_for_intake(
        target_path=target_path,
        write_marker=write_marker,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )

    if not result.get("ok"):
        print(json.dumps(result, indent=2), file=sys.stderr)
        return 1

    project_id = result.get("project_id", "")
    mode_label = "persistent" if write_marker else "one-time scan"
    print(f"✓ Project registered: {project_id} ({mode_label})")
    return 0
