"""ds milestone command group — milestone lifecycle management."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``milestone`` subparser tree to *subcommands*."""
    milestone_cmd = subcommands.add_parser("milestone", help="Manage project milestones")
    ms_sub = milestone_cmd.add_subparsers(dest="milestone_command", required=True)

    ms_close = ms_sub.add_parser("close", help="Close a milestone (runs verification sequence)")
    ms_close.add_argument("milestone_id", help="Milestone UUID")
    ms_close.add_argument(
        "--force", action="store_true", default=False, help="Bypass gate failures"
    )
    ms_close.add_argument("--planning-root", default=None, help="Override .planning/ directory")

    ms_list = ms_sub.add_parser("list", help="List milestones for a project")
    ms_list.add_argument("project_id", help="Project UUID")

    ms_status = ms_sub.add_parser("status", help="Show milestone detail and open gate checks")
    ms_status.add_argument("milestone_id", help="Milestone UUID")
    ms_status.add_argument("--planning-root", default=None, help="Override .planning/ directory")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    if args.milestone_command == "close":
        return _milestone_close(
            milestone_id=args.milestone_id,
            force=args.force,
            planning_root=Path(args.planning_root) if args.planning_root else None,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.milestone_command == "list":
        return _milestone_list(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.milestone_command == "status":
        return _milestone_status(
            milestone_id=args.milestone_id,
            planning_root=Path(args.planning_root) if args.planning_root else None,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    print(f"Unknown milestone command: {args.milestone_command}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


def _milestone_close(
    *,
    milestone_id: str,
    force: bool = False,
    planning_root: Path | None = None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """CLI wrapper around ``core.milestones.close.close_milestone``.

    The pure function returns one canonical result dict; this wrapper
    formats the legacy operator-facing output:
    - failures (missing milestone / open WOs / gate failures) → JSON to
      stdout + exit 1;
    - forced bypass with failures → emit
      ``[gate.bypassed] WARNING: <reason>`` to stderr per failure, then
      the success line;
    - success → plain-text ``Milestone <id> closed. Run ds project
      status <project_id> to see updated progress.``
    """

    from core.milestones.close import close_milestone

    result = close_milestone(
        milestone_id=milestone_id,
        force=force,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )

    if not result.get("ok"):
        print(json.dumps(result))
        return 1

    if result.get("forced") and result.get("bypassed_gates"):
        for reason in result["bypassed_gates"]:
            print(f"[gate.bypassed] WARNING: {reason}", file=sys.stderr)

    print(
        f"Milestone {milestone_id} closed."
        f" Run ds project status {result['project_id']} to see updated progress."
    )
    return 0


def _milestone_list(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.milestones.queries import list_milestones

    result = list_milestones(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _milestone_status(
    *,
    milestone_id: str,
    planning_root: Path | None = None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.milestones.queries import get_milestone_status

    result = get_milestone_status(
        milestone_id=milestone_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1
