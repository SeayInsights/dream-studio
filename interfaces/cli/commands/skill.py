"""ds skill command group — skill invocation and listing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``skill`` subparser tree to *subcommands*."""
    skill = subcommands.add_parser("skill", help="Invoke or list Dream Studio skills")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)

    skill_invoke = skill_sub.add_parser("invoke", help="Invoke a skill (pack:mode format)")
    skill_invoke.add_argument(
        "specifier", help="Skill specifier in pack:mode format (e.g., core:build)"
    )
    skill_invoke.add_argument("--target", default=None, help="Target path or file")
    _invoke_ctx = skill_invoke.add_mutually_exclusive_group()
    _invoke_ctx.add_argument(
        "--work-order",
        default=None,
        dest="work_order_id",
        help="Work order UUID (sets pipeline mode)",
    )
    _invoke_ctx.add_argument(
        "--milestone",
        default=None,
        dest="milestone_id",
        help="Milestone UUID (writes to milestones dir)",
    )
    skill_invoke.add_argument("--project", default=None, dest="project_id", help="Project UUID")
    skill_invoke.add_argument(
        "--planning-root",
        default=None,
        dest="planning_root",
        help="Override .planning/ directory for gate artifact writes",
    )

    skill_list_cmd = skill_sub.add_parser("list", help="List available skills")
    skill_list_cmd.add_argument("--pack", default=None, help="Filter by pack name")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    if args.skill_command == "invoke":
        return _skill_invoke(
            specifier=args.specifier,
            target=args.target,
            work_order_id=args.work_order_id,
            milestone_id=args.milestone_id,
            project_id=args.project_id,
            planning_root=Path(args.planning_root) if args.planning_root else None,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.skill_command == "list":
        return _skill_list(
            pack_filter=args.pack,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    print(f"Unknown skill command: {args.skill_command}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


def _skill_invoke(
    *,
    specifier: str,
    target: str | None,
    work_order_id: str | None,
    milestone_id: str | None = None,
    project_id: str | None,
    planning_root: Path | None = None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """CLI wrapper around `core.skills.invocation`.

    Composes the three pure functions in dependency order:
    1. ``load_skill_content`` — validates specifier and reads SKILL.md;
       fail-fast prints to stderr and returns 1.
    2. Prints the SKILL.md body + operator footer to stdout (the legacy
       handler's user-facing output is preserved verbatim).
    3. ``record_skill_invocation`` — best-effort project_id resolution +
       `skill.invoked` spool event emission.
    4. ``seed_gate_artifact_files`` — writes the pre-shaped artifacts
       (design-critique.md / security-scan.md) and triggers the design
       brief seeding for website:discover.

    Steps 3 and 4 are best-effort: failure does not change the exit code.
    """

    from core.skills.invocation import (
        load_skill_content,
        record_skill_invocation,
        seed_gate_artifact_files,
    )

    load_result = load_skill_content(specifier=specifier, source_root=source_root)
    if not load_result.get("ok"):
        print(load_result["error"], file=sys.stderr)
        return 1

    record_result = record_skill_invocation(
        specifier=specifier,
        target=target,
        work_order_id=work_order_id,
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )

    print(load_result["skill_content"])
    print("---")
    print(f"Skill: {specifier}")
    print(f"Mode: {record_result['invocation_mode']}")
    print(f"Target: {target or 'not specified'}")
    print(f"Work order: {work_order_id or 'none'}")
    print("Invocation recorded.")
    print()
    print(
        "The AI reading this output has the skill instructions above and should now execute them."
    )

    seed_gate_artifact_files(
        specifier=specifier,
        target=target,
        work_order_id=work_order_id,
        milestone_id=milestone_id,
        project_id=project_id,
        planning_root=planning_root,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )

    return 0


def _skill_list(
    *,
    pack_filter: str | None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.skills.queries import list_skills

    result = list_skills(
        pack_filter=pack_filter,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1
