"""ds system command group — composed register()/dispatch() shell.

Split from interfaces/cli/commands/system.py (WO-GF-CLI-split). Unions the
command sets of the four content siblings (system_health, system_dashboard,
system_analytics, system_lifecycle) and routes to their register_*/dispatch_*
functions. The facade at interfaces/cli/commands/system.py re-exports
``register``/``dispatch``/``SYSTEM_COMMANDS`` from here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from interfaces.cli.commands.system_analytics import (
    ANALYTICS_COMMANDS,
    dispatch_analytics,
    register_analytics,
)
from interfaces.cli.commands.system_dashboard import (
    DASHBOARD_COMMANDS,
    dispatch_dashboard,
    register_dashboard,
)
from interfaces.cli.commands.system_health import (
    HEALTH_COMMANDS,
    dispatch_health,
    register_health,
)
from interfaces.cli.commands.system_lifecycle import (
    LIFECYCLE_COMMANDS,
    dispatch_lifecycle,
    register_lifecycle,
)

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------

#: Commands handled by this module (union of the four group command sets).
SYSTEM_COMMANDS = HEALTH_COMMANDS | DASHBOARD_COMMANDS | ANALYTICS_COMMANDS | LIFECYCLE_COMMANDS


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach all flat/system subparsers to *subcommands*."""
    register_health(subcommands)
    register_dashboard(subcommands)
    register_analytics(subcommands)
    register_lifecycle(subcommands)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Route a system-level command to the correct group implementation."""
    if args.command in HEALTH_COMMANDS:
        return dispatch_health(args, source_root=source_root, dream_studio_home=dream_studio_home)

    if args.command in DASHBOARD_COMMANDS:
        return dispatch_dashboard(
            args, source_root=source_root, dream_studio_home=dream_studio_home
        )

    if args.command in ANALYTICS_COMMANDS:
        return dispatch_analytics(
            args, source_root=source_root, dream_studio_home=dream_studio_home
        )

    if args.command in LIFECYCLE_COMMANDS:
        return dispatch_lifecycle(
            args, source_root=source_root, dream_studio_home=dream_studio_home
        )

    print(f"Unknown system command: {args.command}", file=sys.stderr)
    return 1
