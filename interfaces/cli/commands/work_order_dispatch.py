"""ds work-order command group — parser registration and dispatch.

Split from interfaces/cli/commands/work_order.py (WO-GF-CLI-split).
``register()`` and ``dispatch()`` move here WHOLE and unsplit (no per-group
decomposition needed — the whole `work-order` subparser tree and the
implementation call it routes to are small enough to keep as one shell);
the implementation helpers themselves live grouped by lifecycle/tasks/query
in the three sibling modules.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from interfaces.cli.commands.work_order_lifecycle import (
    _work_order_block,
    _work_order_close,
    _work_order_start,
    _work_order_unblock,
)
from interfaces.cli.commands.work_order_query import (
    _work_order_artifact,
    _work_order_executor,
    _work_order_list,
    _work_order_next,
    _work_order_packet,
    _work_order_verify,
)
from interfaces.cli.commands.work_order_tasks import (
    _work_order_add_dep,
    _work_order_remove_dep,
    _work_order_set_order,
    _work_order_task_done,
    _work_order_tasks,
)

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``work-order`` subparser tree to *subcommands*."""
    work_order = subcommands.add_parser("work-order", help="Manage work orders")
    work_order_sub = work_order.add_subparsers(dest="work_order_command", required=True)

    wo_start = work_order_sub.add_parser("start", help="Start a work order and write context")
    wo_start.add_argument("work_order_id", help="Work order UUID")
    wo_start.add_argument(
        "--planning-root",
        default=None,
        help="Override .planning/ directory (default: <cwd>/.planning)",
    )
    wo_start.add_argument(
        "--in-sequence",
        action="store_true",
        default=False,
        dest="in_sequence",
        help="Abort (exit 1) if earlier-sequence WOs in the same milestone are not closed",
    )

    wo_list = work_order_sub.add_parser("list", help="List work orders")
    wo_list.add_argument("--project", default=None, dest="project_id", help="Filter by project_id")
    wo_list.add_argument("--status", default=None, dest="status_filter", help="Filter by status")

    wo_close = work_order_sub.add_parser("close", help="Close a work order (gate-checked)")
    wo_close.add_argument("work_order_id", help="Work order UUID")
    wo_close.add_argument(
        "--force", action="store_true", default=False, help="Bypass gate failures"
    )
    wo_close.add_argument(
        "--planning-root",
        default=None,
        help="Override .planning/ directory (default: <cwd>/.planning)",
    )

    wo_block = work_order_sub.add_parser("block", help="Block a work order with a reason")
    wo_block.add_argument("work_order_id", help="Work order UUID")
    wo_block.add_argument("--reason", required=True, help="Block reason")

    wo_unblock = work_order_sub.add_parser(
        "unblock", help="Unblock a work order (restore to in_progress)"
    )
    wo_unblock.add_argument("work_order_id", help="Work order UUID")

    wo_task_done = work_order_sub.add_parser(
        "task-done", help="Mark a task complete and update context.md"
    )
    wo_task_done.add_argument("work_order_id", help="Work order UUID")
    wo_task_done.add_argument("task_id", help="Task UUID")
    wo_task_done.add_argument(
        "--planning-root",
        default=None,
        help="Override .planning/ directory (default: <cwd>/.planning)",
    )

    wo_tasks = work_order_sub.add_parser("tasks", help="List tasks for a work order")
    wo_tasks.add_argument("work_order_id", help="Work order UUID")
    wo_tasks.add_argument(
        "--verbose", "-v", action="store_true", help="Include full description for each task"
    )

    wo_set_order = work_order_sub.add_parser(
        "set-order", help="Set sequence_order on a work order (sparse 10/20/30)"
    )
    wo_set_order.add_argument("work_order_id", help="Work order UUID")
    wo_set_order.add_argument("sequence_order", type=int, help="Sequence order (integer, e.g. 10)")

    wo_add_dep = work_order_sub.add_parser(
        "add-dep", help="Add a dependency: work_order_id waits for depends_on_id to close"
    )
    wo_add_dep.add_argument("work_order_id", help="Work order UUID")
    wo_add_dep.add_argument("depends_on_id", help="Dependency target UUID")

    wo_remove_dep = work_order_sub.add_parser("remove-dep", help="Remove a dependency edge")
    wo_remove_dep.add_argument("work_order_id", help="Work order UUID")
    wo_remove_dep.add_argument("depends_on_id", help="Dependency target UUID")

    wo_next = work_order_sub.add_parser(
        "next", help="Show next unblocked work order for a project (ready-set selector)"
    )
    wo_next.add_argument("project_id", help="Project UUID")

    wo_verify = work_order_sub.add_parser(
        "verify", help="Run independent fresh-context review; gaps become new work orders"
    )
    wo_verify.add_argument("work_order_id", help="Work order UUID")

    wo_executor = work_order_sub.add_parser(
        "executor", help="Resolve which model should execute this WO (escalation-aware)"
    )
    wo_executor.add_argument("work_order_id", help="Work order UUID")

    wo_artifact = work_order_sub.add_parser(
        "artifact", help="Print a stored WO artifact from the authority (no disk read)"
    )
    wo_artifact.add_argument("work_order_id", help="Work order UUID")
    wo_artifact.add_argument("kind", help="Artifact kind (e.g. api_contract, review_verdict, eval)")
    wo_artifact.add_argument(
        "--instance",
        dest="instance_key",
        default="",
        help="instance_key for multi-instance kinds (e.g. the eval_type); default '' (singleton)",
    )

    wo_packet = work_order_sub.add_parser(
        "packet", help="Render a WO execution packet on demand (prints to stdout, no disk cache)"
    )
    wo_packet.add_argument("work_order_id", help="Work order UUID")
    wo_packet.add_argument(
        "--target", required=True, choices=("claude", "codex"), help="Render target adapter"
    )
    wo_packet.add_argument(
        "--storage-root", dest="storage_root", default=None, help="File-backed WO storage root"
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
    if args.work_order_command == "start":
        planning_root = Path(args.planning_root).resolve() if args.planning_root else None
        return _work_order_start(
            work_order_id=args.work_order_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            planning_root=planning_root,
            in_sequence=getattr(args, "in_sequence", False),
        )
    if args.work_order_command == "list":
        return _work_order_list(
            project_id=args.project_id,
            status_filter=args.status_filter,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "close":
        planning_root = Path(args.planning_root).resolve() if args.planning_root else None
        return _work_order_close(
            work_order_id=args.work_order_id,
            force=args.force,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            planning_root=planning_root,
        )
    if args.work_order_command == "block":
        return _work_order_block(
            work_order_id=args.work_order_id,
            reason=args.reason,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "unblock":
        return _work_order_unblock(
            work_order_id=args.work_order_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "task-done":
        planning_root = Path(args.planning_root).resolve() if args.planning_root else None
        return _work_order_task_done(
            work_order_id=args.work_order_id,
            task_id=args.task_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            planning_root=planning_root,
        )
    if args.work_order_command == "tasks":
        return _work_order_tasks(
            work_order_id=args.work_order_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            verbose=getattr(args, "verbose", False),
        )
    if args.work_order_command == "set-order":
        return _work_order_set_order(
            work_order_id=args.work_order_id,
            sequence_order=args.sequence_order,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "add-dep":
        return _work_order_add_dep(
            work_order_id=args.work_order_id,
            depends_on_id=args.depends_on_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "remove-dep":
        return _work_order_remove_dep(
            work_order_id=args.work_order_id,
            depends_on_id=args.depends_on_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "next":
        return _work_order_next(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "verify":
        return _work_order_verify(
            work_order_id=args.work_order_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "executor":
        return _work_order_executor(
            work_order_id=args.work_order_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "artifact":
        return _work_order_artifact(
            work_order_id=args.work_order_id,
            kind=args.kind,
            instance_key=getattr(args, "instance_key", ""),
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "packet":
        storage_root = Path(args.storage_root).resolve() if args.storage_root else None
        return _work_order_packet(
            work_order_id=args.work_order_id,
            target=args.target,
            storage_root=storage_root,
        )
    print(f"Unknown work-order command: {args.work_order_command}", file=sys.stderr)
    return 1
