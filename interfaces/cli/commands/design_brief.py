"""ds design-brief command group — design brief management."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_VALID_DESIGN_SYSTEMS: frozenset[str] = frozenset(
    [
        "tech-minimal",
        "editorial-modern",
        "brutalist-bold",
        "playful-rounded",
        "executive-clean",
    ]
)

_BRIEF_UPDATABLE_FIELDS: frozenset[str] = frozenset(
    [
        "purpose",
        "audience",
        "tone",
        "design_system",
        "font_pairing",
        "brand_tokens",
        "raw_output",
    ]
)


# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``design-brief`` subparser tree to *subcommands*."""
    design_brief_cmd = subcommands.add_parser("design-brief", help="Manage project design briefs")
    db_sub = design_brief_cmd.add_subparsers(dest="design_brief_command", required=True)

    db_show = db_sub.add_parser("show", help="Show design brief for a project")
    db_show.add_argument("project_id", help="Project UUID")

    db_create = db_sub.add_parser("create", help="Create a draft design brief for a project")
    db_create.add_argument("project_id", help="Project UUID")

    db_lock = db_sub.add_parser("lock", help="Lock a design brief (human approval gate)")
    db_lock.add_argument("brief_id", help="Brief UUID")

    db_update = db_sub.add_parser("update", help="Update a field on a draft design brief")
    db_update.add_argument("brief_id", help="Brief UUID")
    db_update.add_argument("--field", required=True, help="Field to update")
    db_update.add_argument("--value", required=True, help="New value")

    db_set_system = db_sub.add_parser("set-system", help="Set the design system for a brief")
    db_set_system.add_argument("brief_id", help="Brief UUID")
    db_set_system.add_argument("system_name", help="Design system name")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    if args.design_brief_command == "show":
        return _design_brief_show(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.design_brief_command == "create":
        return _design_brief_create(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.design_brief_command == "lock":
        return _design_brief_lock(
            brief_id=args.brief_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.design_brief_command == "update":
        return _design_brief_update(
            brief_id=args.brief_id,
            field=args.field,
            value=args.value,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.design_brief_command == "set-system":
        return _design_brief_set_system(
            brief_id=args.brief_id,
            system_name=args.system_name,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    print(f"Unknown design-brief command: {args.design_brief_command}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


def _design_brief_show(
    *, project_id: str, source_root: Path, dream_studio_home: Path | None
) -> int:
    from core.design_briefs.queries import get_design_brief

    result = get_design_brief(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    # `get_design_brief` returns `{"ok": True, "brief": None, "message": ...}` when
    # no brief exists, vs a brief-shaped dict (with `brief_id`) when one exists.
    if result.get("ok") and result.get("brief_id") is None:
        print(result.get("message", "No design brief found."))
        return 0
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _design_brief_create(
    *, project_id: str, source_root: Path, dream_studio_home: Path | None
) -> int:
    """CLI wrapper around ``core.design_briefs.mutations.create_design_brief``."""

    from core.design_briefs.mutations import create_design_brief

    result = create_design_brief(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not result.get("ok"):
        print(json.dumps(result))
        return 1
    print(f"Draft brief created: {result['brief_id']}")
    print(f"Next: {result['next_step']}")
    return 0


def _design_brief_lock(*, brief_id: str, source_root: Path, dream_studio_home: Path | None) -> int:
    """CLI wrapper around ``core.design_briefs.mutations.lock_design_brief``."""

    from core.design_briefs.mutations import lock_design_brief

    result = lock_design_brief(
        brief_id=brief_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not result.get("ok"):
        print(json.dumps(result))
        return 1
    print(f"Brief {brief_id} locked.")
    return 0


def _design_brief_update(
    *, brief_id: str, field: str, value: str, source_root: Path, dream_studio_home: Path | None
) -> int:
    from core.design_briefs.mutations import update_design_brief_field

    result = update_design_brief_field(
        brief_id=brief_id,
        field=field,
        value=value,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _design_brief_set_system(
    *, brief_id: str, system_name: str, source_root: Path, dream_studio_home: Path | None
) -> int:
    from core.design_briefs.mutations import set_design_system

    result = set_design_system(
        brief_id=brief_id,
        system_name=system_name,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1
