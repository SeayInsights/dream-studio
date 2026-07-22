"""ds learn — subcommand parser registration.

Split from interfaces/cli/ds_learn.py (WO-GF-CLI-split). There is no
``dispatch()`` function — routing is via ``set_defaults(func=cmd_X)`` — this
module wires the `learn` subparser tree onto the parent parser and points
each leaf subcommand at its implementation in ds_learn_review, ds_learn_expand,
or ds_learn_activation. ``_learn_help`` is the group-level default (bare
`ds learn` with no subcommand).
"""

from __future__ import annotations

from interfaces.cli.ds_learn_activation import cmd_disambiguate, cmd_validate
from interfaces.cli.ds_learn_expand import cmd_expand
from interfaces.cli.ds_learn_review import cmd_review


def add_learn_subcommand(subparsers) -> None:
    """Register the 'learn' subcommand group with ds CLI."""
    learn_parser = subparsers.add_parser(
        "learn",
        help="Operator learning and gap review workflows",
    )
    learn_sub = learn_parser.add_subparsers(dest="learn_command")

    # ds learn review
    review_parser = learn_sub.add_parser(
        "review",
        help="Review pending classified friction signals",
    )
    review_parser.add_argument("--limit", type=int, default=50)
    review_parser.add_argument("--batch", action="store_true")
    review_parser.set_defaults(func=cmd_review)

    # ds learn expand (19.4a — personalization only)
    expand_parser = learn_sub.add_parser(
        "expand",
        help="Compile personalization extensions from dismissal evidence (19.4a)",
    )
    expand_parser.add_argument(
        "extension_id",
        nargs="?",
        help="Compile a specific extension by ID (default: show all pending)",
    )
    expand_parser.add_argument("--all", action="store_true", help="Compile all pending")
    expand_parser.add_argument("--batch", action="store_true", help="JSON output, no interaction")
    expand_parser.add_argument(
        "--show-events",
        action="store_true",
        dest="show_events",
        help="Show cited event IDs for capability proposals",
    )
    expand_parser.set_defaults(func=cmd_expand)

    # ds learn validate (19.5 — retroactive validation)
    validate_parser = learn_sub.add_parser(
        "validate",
        help="Retroactive validation for compiled extensions (Decision 6)",
    )
    validate_parser.add_argument(
        "extension_id",
        nargs="?",
        help="Validate a specific extension (default: list pending)",
    )
    validate_parser.add_argument(
        "--all-proposed",
        action="store_true",
        dest="all_proposed",
        help="Validate all proposed/experimental extensions with sufficient WO history",
    )
    validate_parser.add_argument(
        "--force",
        action="store_true",
        help="Override the N≥5 minimum (requires explicit confirmation)",
    )
    validate_parser.set_defaults(func=cmd_validate)

    # ds learn disambiguate (19.6 — description collision resolution)
    disambig_parser = learn_sub.add_parser(
        "disambiguate",
        help="Resolve description collisions for blocked extensions (19.6)",
    )
    disambig_parser.add_argument("extension_id", help="Extension to disambiguate")
    disambig_parser.add_argument(
        "--rewrite",
        metavar="DESCRIPTION",
        help="New description to use; re-runs collision check after update",
    )
    disambig_parser.add_argument(
        "--accept-warning",
        action="store_true",
        dest="accept_warning",
        help="Accept a warning-tier collision (0.70-0.85 similarity) and activate",
    )
    disambig_parser.add_argument(
        "--force",
        metavar="REASON",
        help="Force-activate despite critical collision (≥0.85); requires a reason",
    )
    disambig_parser.set_defaults(func=cmd_disambiguate)

    learn_parser.set_defaults(func=_learn_help)


def _learn_help(args) -> int:
    print("Usage: ds learn review [--limit N] [--batch]")
    print("       ds learn expand [extension_id] [--all] [--batch]")
    print("       ds learn validate [extension_id] [--all-proposed] [--force]")
    print(
        "       ds learn disambiguate <extension_id> [--rewrite DESC] [--accept-warning] [--force REASON]"
    )
    return 0
