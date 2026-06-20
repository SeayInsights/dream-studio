"""ds task command group — active task context management."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``task`` subparser tree to *subcommands*."""
    task_cmd = subcommands.add_parser("task", help="Manage active task context")
    task_sub = task_cmd.add_subparsers(dest="task_command", required=True)

    t_set_active = task_sub.add_parser("set-active", help="Set the active task context")
    t_set_active.add_argument("task_id", help="Task UUID")

    task_sub.add_parser("active", help="Show the current active task context")
    task_sub.add_parser("clear-active", help="Clear the active task context")

    t_list = task_sub.add_parser("list", help="Alias for 'ds work-order tasks <work_order_id>'")
    t_list.add_argument("work_order_id", help="Work order UUID")
    t_list.add_argument(
        "--verbose", "-v", action="store_true", help="Include full description for each task"
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(
    args: argparse.Namespace,
    source_root: Path | None = None,
    dream_studio_home: Path | None = None,
) -> int:
    # Import here to avoid circular dependency at module load time
    from interfaces.cli.commands.work_order import _work_order_tasks

    # REPO_ROOT fallback: resolve relative to this file's location (same as ds.py).
    _fallback_root = Path(__file__).resolve().parents[3]

    if args.task_command == "set-active":
        return _task_set_active(task_id=args.task_id)
    if args.task_command == "active":
        return _task_get_active()
    if args.task_command == "clear-active":
        return _task_clear_active()
    if args.task_command == "list":
        return _work_order_tasks(
            work_order_id=args.work_order_id,
            source_root=source_root or _fallback_root,
            dream_studio_home=dream_studio_home,
            verbose=getattr(args, "verbose", False),
        )
    print(f"Unknown task command: {args.task_command}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


def _task_set_active(*, task_id: str) -> int:
    from core.sdlc.active_task import set_active_task

    try:
        ctx = set_active_task(task_id)
        import dataclasses

        print(json.dumps(dataclasses.asdict(ctx), indent=2))
        return 0
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


def _task_get_active() -> int:
    from core.sdlc.active_task import get_active_task

    ctx = get_active_task()
    if ctx is None:
        print(json.dumps({"active_task": None, "message": "no active task"}, indent=2))
        return 0
    import dataclasses

    print(json.dumps({"active_task": dataclasses.asdict(ctx)}, indent=2))
    return 0


def _task_clear_active() -> int:
    from core.sdlc.active_task import clear_active_task

    removed = clear_active_task()
    print(json.dumps({"ok": True, "cleared": removed}, indent=2))
    return 0
