"""ds config command group — operator-local key/value config (WO-FRICTION-CONFIG)."""

from __future__ import annotations

import argparse
from pathlib import Path

from interfaces.cli.cli_utils import _print

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``config`` subparser tree to *subcommands*."""
    config_cmd = subcommands.add_parser("config", help="Operator-local key/value config")
    config_sub = config_cmd.add_subparsers(dest="config_command", required=True)

    config_set_cmd = config_sub.add_parser("set", help="Set a config value")
    config_set_cmd.add_argument("key", help="Config key (e.g. eval.friction_threshold)")
    config_set_cmd.add_argument("value", help="Value to store")

    config_sub.add_parser("show", help="Show all config values")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Dispatch ds config {set,show} commands (WO-FRICTION-CONFIG)."""
    from core.config.authority import list_config, set_config_value
    from core.installed_runtime import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    )
    db_path = paths.sqlite_path

    if args.config_command == "set":
        set_config_value(args.key, args.value, db_path)
        return _print({"ok": True, "key": args.key, "value": args.value})

    if args.config_command == "show":
        rows = list_config(db_path)
        return _print({"ok": True, "config": rows, "count": len(rows)})
