"""Global Dream Studio command surface.

This CLI is designed to run from outside the repository. It resolves Dream
Studio source/state through explicit arguments or installed runtime config,
never by assuming the caller's current working directory is the repo.

This module is a thin hub/dispatcher. All implementation logic lives in
``interfaces.cli.commands.<group>`` modules.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Core imports used in main()
from core.installed_runtime import resolve_installed_runtime_paths  # noqa: E402

# Per-group command modules
from interfaces.cli.commands import analyze  # noqa: E402
from interfaces.cli.commands import config  # noqa: E402
from interfaces.cli.commands import design_brief  # noqa: E402
from interfaces.cli.commands import diagnostics  # noqa: E402
from interfaces.cli.commands import eval as eval_cmd  # noqa: E402
from interfaces.cli.commands import integrate  # noqa: E402
from interfaces.cli.commands import milestone  # noqa: E402
from interfaces.cli.commands import project  # noqa: E402
from interfaces.cli.commands import skill  # noqa: E402
from interfaces.cli.commands import system  # noqa: E402
from interfaces.cli.commands import task  # noqa: E402
from interfaces.cli.commands import work_order  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ds", description="Dream Studio global command")
    parser.add_argument("--source-root", default=None, help="Dream Studio source/build root")
    parser.add_argument("--home", default=None, help="Dream Studio user-local state root")
    parser.add_argument(
        "--debug", action="store_true", help="Emit diagnostic output (DB path, authority, command)"
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    # -----------------------------------------------------------------------
    # Flat / system-level commands (registered via commands/system.py)
    # -----------------------------------------------------------------------
    system.register(subcommands)

    # -----------------------------------------------------------------------
    # Delegated command groups (registered via their legacy add_*_subcommand modules)
    # -----------------------------------------------------------------------
    # spool subcommand group (Slice 3)
    from interfaces.cli.ds_spool import add_spool_subcommand

    add_spool_subcommand(subcommands)

    # workflow subcommand group (Slice 9b)
    from interfaces.cli.ds_workflow import add_workflow_subcommand

    add_workflow_subcommand(subcommands)

    # learn subcommand group (Phase 19.3)
    from interfaces.cli.ds_learn import add_learn_subcommand

    add_learn_subcommand(subcommands)

    # memory subcommand group (Slice 5d)
    from interfaces.cli.ds_memory import add_memory_subcommand

    add_memory_subcommand(subcommands)

    # files subcommand group (WO-TS5)
    from interfaces.cli.ds_files import add_files_subcommand

    add_files_subcommand(subcommands)

    # projection subcommand group (Phase 18.1.5)
    from interfaces.cli.projection_cli import add_projection_subcommand

    add_projection_subcommand(subcommands)

    # Per-group command modules (commands/ package)
    project.register(subcommands)
    integrate.register(subcommands)
    skill.register(subcommands)
    work_order.register(subcommands)
    design_brief.register(subcommands)
    milestone.register(subcommands)
    task.register(subcommands)
    analyze.register(subcommands)
    eval_cmd.register(subcommands)
    config.register(subcommands)
    diagnostics.register(subcommands)

    # -----------------------------------------------------------------------
    # Parse & resolve globals
    # -----------------------------------------------------------------------
    args = parser.parse_args(argv)
    source_root = Path(args.source_root).resolve() if args.source_root else REPO_ROOT
    home = Path(args.home).resolve() if args.home else None

    if getattr(args, "debug", False):
        try:
            _paths = resolve_installed_runtime_paths(
                source_root=source_root, dream_studio_home=home
            )
            _db_path = _paths.sqlite_path
        except Exception as _e:
            _db_path = f"<error: {_e}>"
        print(f"[debug] source_root: {source_root}", file=sys.stderr)
        print(f"[debug] dream_studio_home: {home}", file=sys.stderr)
        print(f"[debug] db_path: {_db_path}", file=sys.stderr)
        print(f"[debug] command: {getattr(args, 'command', None)}", file=sys.stderr)
        _sub = getattr(args, "work_order_command", None) or getattr(args, "project_command", None)
        if _sub:
            print(f"[debug] subcommand: {_sub}", file=sys.stderr)

    # -----------------------------------------------------------------------
    # Dispatch
    # -----------------------------------------------------------------------
    try:
        # System-level flat commands
        if args.command in system.SYSTEM_COMMANDS:
            return system.dispatch(args, source_root=source_root, dream_studio_home=home)

        # Commands delegated to the legacy add_*_subcommand modules
        if args.command == "memory":
            if hasattr(args, "func"):
                return args.func(args)
            print("Usage: ds memory <subcommand>", file=sys.stderr)
            return 1
        if args.command == "spool":
            if hasattr(args, "func"):
                return args.func(args)
            print("Usage: ds spool <subcommand>", file=sys.stderr)
            return 1
        if args.command == "workflow":
            if hasattr(args, "func"):
                return args.func(args)
            print("Usage: ds workflow <subcommand>", file=sys.stderr)
            return 1
        if args.command == "learn":
            if hasattr(args, "func"):
                return args.func(args)
            print("Usage: ds learn review [--limit N] [--batch]", file=sys.stderr)
            return 1
        if args.command == "projection":
            from interfaces.cli.projection_cli import handle_projection_command

            return handle_projection_command(args)

        # Commands delegated to commands/ package modules
        if args.command == "project":
            return project.dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "integrate":
            return integrate.dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "skill":
            return skill.dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "work-order":
            return work_order.dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "design-brief":
            return design_brief.dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "milestone":
            return milestone.dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "task":
            return task.dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "diagnostics":
            return diagnostics.dispatch(args)
        if args.command == "config":
            return config.dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "analyze":
            return analyze.dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "eval":
            return eval_cmd.dispatch(args, source_root=source_root)

    except (RuntimeError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
