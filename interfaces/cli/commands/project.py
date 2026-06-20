"""ds project command group — project lifecycle management."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``project`` subparser tree to *subcommands*."""
    project = subcommands.add_parser("project", help="Manage Dream Studio projects")
    project_sub = project.add_subparsers(dest="project_command", required=True)

    project_register = project_sub.add_parser("register", help="Register a new project")
    project_register.add_argument("--name", required=True, help="Project name")
    project_register.add_argument("--description", default="", help="Optional description")
    project_register.add_argument(
        "--path",
        required=True,
        metavar="DIR",
        help="Path to the project directory. A .dream-studio-project marker file will be written here.",
    )

    project_list = project_sub.add_parser("list", help="List registered projects")
    project_list.add_argument(
        "--status", default="active", help="Filter by status (default: active)"
    )
    project_list.add_argument(
        "--include-deleted",
        action="store_true",
        default=False,
        dest="include_deleted",
        help="Include soft-deleted projects (status=deleted) in output",
    )

    project_status_cmd = project_sub.add_parser(
        "status", help="Show milestone/work-order summary for a project"
    )
    project_status_cmd.add_argument("project_id", help="Project UUID")

    project_next_cmd = project_sub.add_parser(
        "next", help="Return the first open work order for a project"
    )
    project_next_cmd.add_argument("project_id", help="Project UUID")

    project_set_active = project_sub.add_parser(
        "set-active", help="Set the active project in the database"
    )
    project_set_active.add_argument("project_id", help="Project UUID to activate")

    project_deactivate = project_sub.add_parser("deactivate", help="Deactivate a project")
    project_deactivate.add_argument("project_id", help="Project UUID to deactivate")

    project_start_cmd = project_sub.add_parser(
        "start", help="Activate project and start its next open work order"
    )
    project_start_cmd.add_argument("project_id", help="Project UUID")
    project_start_cmd.add_argument(
        "--planning-root",
        default=None,
        dest="planning_root",
        help="Override .planning/ directory (default: <cwd>/.planning)",
    )

    project_delete = project_sub.add_parser(
        "delete", help="Delete a project and all its dependents"
    )
    project_delete.add_argument("project_id", help="Project UUID to delete")
    project_delete.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Required to confirm deletion of a project with dependents",
    )

    project_state_cmd = project_sub.add_parser(
        "state",
        help="Single-query project state: active project, next WO, gates, brief, tasks, gotchas",
    )
    project_state_cmd.add_argument(
        "--planning-root",
        default=None,
        dest="planning_root",
        help="Override .planning/ directory for gate file checks (default: <cwd>/.planning)",
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
    if args.project_command == "register":
        return _project_register(
            name=args.name,
            description=args.description,
            project_path=Path(args.path).resolve(),
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "list":
        return _project_list(
            status_filter=args.status,
            include_deleted=getattr(args, "include_deleted", False),
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "status":
        return _project_status(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "next":
        return _project_next(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "set-active":
        return _project_set_active(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "deactivate":
        return _project_deactivate(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "delete":
        return _project_delete(
            project_id=args.project_id,
            confirm=args.confirm,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "start":
        planning_root = Path(args.planning_root).resolve() if args.planning_root else None
        return _project_start(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            planning_root=planning_root,
        )
    if args.project_command == "state":
        planning_root = Path(args.planning_root).resolve() if args.planning_root else None
        return _project_state(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            planning_root=planning_root,
        )
    print(f"Unknown project command: {args.project_command}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


def _project_register(
    *,
    name: str,
    description: str,
    project_path: Path,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.mutations import register_project

    result = register_project(
        name=name,
        description=description,
        project_path=project_path,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if result.get("ok"):
        result["hint"] = (
            f"To make this the active project, run: ds project set-active {result['project_id']}"
        )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_list(
    *,
    status_filter: str,
    include_deleted: bool = False,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.queries import get_project_list

    result = get_project_list(
        status_filter=status_filter,
        include_deleted=include_deleted,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_status(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.queries import get_project_status

    result = get_project_status(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_next(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.queries import get_next_work_order

    result = get_next_work_order(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_set_active(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.mutations import set_active_project

    result = set_active_project(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_deactivate(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.mutations import deactivate_project

    result = deactivate_project(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_start(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    """CLI wrapper around `core.projects.start.start_project`.

    Converts the composer's compound result dict into the legacy
    operator-facing output: the inner `work_order_start` JSON on stdout
    (so tests that parse it still work), then a human-readable summary
    with the project name, work-order title, type/milestone, context.md
    path, task count, and close hint.
    """

    from core.projects.start import start_project

    result = start_project(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )

    if not result.get("ok"):
        print(json.dumps(result))
        return 1

    project_name = result.get("project_name", project_id)

    if result.get("no_open_work_orders"):
        print(
            f"Project activated: {project_name}\n"
            "No open work orders found.\n"
            f"Run `ds project next {project_id}` to check status."
        )
        return 0

    next_wo = result.get("next_work_order") or {}
    wo_id = next_wo.get("work_order_id", "")
    wo_title = next_wo.get("title", "")
    wo_type = next_wo.get("work_order_type") or "—"
    milestone_str = next_wo.get("milestone") or "—"
    context_path = result.get("context_path") or ""
    task_count = result.get("tasks_count", 0)
    tasks_str = f"{task_count} tasks queued" if task_count else "tasks queued"

    # Preserve the legacy operator surface: the inner work-order start JSON
    # was previously printed by _work_order_start before the summary.
    wo_start = result.get("work_order_start") or {}
    print(json.dumps(wo_start, indent=2))

    print(
        f"\nProject activated: {project_name}\n"
        f"Starting: {wo_title}\n"
        f"Type: {wo_type} | Milestone: {milestone_str}\n"
        f"\nContext loaded: {context_path}\n"
        f"Tasks ready: {tasks_str}\n"
        f"\nRun `ds work-order close {wo_id}` when done."
    )
    return 0


def _project_delete(
    *,
    project_id: str,
    confirm: bool,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """CLI wrapper around ``core.projects.mutations.delete_project``.

    The CLI ``--confirm`` flag maps to the function's ``confirm=True``
    kwarg. The function returns a dict whose error path mentions
    ``confirm=True`` (the kwarg name); the wrapper post-processes the
    message to use ``--confirm`` (the operator-facing flag name) so the
    CLI error text stays as it was before A6.3 lifted the function.
    """

    from core.projects.mutations import delete_project

    result = delete_project(
        project_id=project_id,
        confirm=confirm,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not result.get("ok"):
        error = result.get("error", "")
        if "Pass confirm=True" in error:
            result = {**result, "error": error.replace("Pass confirm=True", "Pass --confirm")}
        print(json.dumps(result))
        return 1
    print(json.dumps(result))
    return 0


def _project_state(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    """Single-call project state: active project + next WO + gates + brief + tasks + gotchas."""
    from core.projects.queries import get_project_state

    result = get_project_state(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1
