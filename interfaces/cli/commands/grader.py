"""ds grader command group — inspect grader provider selection (WO-GRADER-PROFILE-REGISTRY).

``ds grader profiles`` prints, for each of the four grader roles, which provider will grade
that role under the current env + config — so an operator can inspect the mapping BEFORE
running verify. Read-only; no provider is spawned.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from interfaces.cli.cli_utils import _print


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``grader`` subparser tree to *subcommands*."""
    grader_cmd = subcommands.add_parser("grader", help="Inspect grader provider selection")
    grader_sub = grader_cmd.add_subparsers(dest="grader_command", required=True)

    profiles_cmd = grader_sub.add_parser(
        "profiles", help="Print which provider will grade each role (role -> provider)"
    )
    profiles_cmd.add_argument(
        "--grader-profile",
        dest="grader_profile",
        default=None,
        help="Explicit provider override (shlex argv), highest precedence, applied to all roles",
    )


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Dispatch ``ds grader profiles``."""
    from config.grader_profiles import describe_grader_selection

    if args.grader_command == "profiles":
        mapping = describe_grader_selection(cli_override=getattr(args, "grader_profile", None))
        return _print({"ok": True, "grader_selection": mapping})

    return _print({"ok": False, "error": f"unknown grader command: {args.grader_command}"})
