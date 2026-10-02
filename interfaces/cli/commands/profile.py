"""ds profile command group — switchable operating-context identity (migration 159).

A PROFILE is which real-world engagement/identity work is being done as (today:
SeayInsights, Fulcrum -- more to come), independent of which PROJECT (what work) is
active. These are thin CLI wrappers over core/profiles: create/list/switch/show.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    profile = subcommands.add_parser(
        "profile", help="Manage profiles (a switchable operating-context identity)"
    )
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)

    p_create = profile_sub.add_parser("create", help="Create a profile")
    p_create.add_argument("--name", required=True, help="Profile name")
    p_create.add_argument(
        "--client", required=True, dest="client_id", help="Client id this profile belongs to"
    )
    p_create.add_argument(
        "--claude-config-dir",
        default=None,
        dest="claude_config_dir",
        help="This profile's Claude Code config directory (stored only; not yet wired)",
    )
    p_create.add_argument(
        "--mcp-client-name",
        default=None,
        dest="mcp_client_name",
        help="This profile's MCP client identity name (stored only; not yet wired)",
    )

    profile_sub.add_parser("list", help="List profiles")

    p_switch = profile_sub.add_parser(
        "switch", help="Make this the active profile (pauses whichever profile was active)"
    )
    p_switch.add_argument("profile_id", help="Profile UUID to activate")

    profile_sub.add_parser("show", help="Show the currently active profile")


def _db_path(source_root: Path, dream_studio_home: Path | None) -> Path:
    from interfaces.cli.ds import resolve_installed_runtime_paths

    return resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    ).sqlite_path


def dispatch(args: argparse.Namespace, *, source_root: Path, dream_studio_home: Path | None) -> int:
    cmd = args.profile_command
    if cmd == "create":
        from core.profiles.mutations import create_profile

        return _print(
            create_profile(
                name=args.name,
                client_id=args.client_id,
                claude_config_dir=args.claude_config_dir,
                mcp_client_name=args.mcp_client_name,
                source_root=source_root,
                dream_studio_home=dream_studio_home,
            )
        )
    if cmd == "list":
        from core.profiles.queries import list_profiles

        db = _db_path(source_root, dream_studio_home)
        return _print({"ok": True, "profiles": list_profiles(db_path=db)})
    if cmd == "switch":
        from core.profiles.mutations import switch_active_profile

        return _print(
            switch_active_profile(
                profile_id=args.profile_id,
                source_root=source_root,
                dream_studio_home=dream_studio_home,
            )
        )
    if cmd == "show":
        from core.profiles.queries import active_profile

        db = _db_path(source_root, dream_studio_home)
        profile = active_profile(db_path=db)
        if profile is None:
            return _print({"ok": True, "profile": None, "message": "No active profile."})
        return _print({"ok": True, "profile": profile})
    print(f"Unknown profile command: {cmd}", file=sys.stderr)
    return 1


def _print(result: dict) -> int:
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1
