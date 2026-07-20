"""ds work-order command group — work order lifecycle management."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


def _work_order_executor(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Resolve and print the executor (model) for a WO — escalation-aware (T5).

    The autonomous execute-work-orders loop calls this to honor the escalation
    capability flag (route an escalated WO's retry to Opus); the manual path honors
    the same flag via start_work_order's ``executor`` field. Both consume
    ``escalation.resolve_executor`` so routing is identical on both surfaces.
    """
    from core.installed_runtime import resolve_installed_runtime_paths
    from core.work_orders.escalation import read_escalation, resolve_executor

    db_path = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    ).sqlite_path
    executor = resolve_executor(work_order_id, db_path=db_path)
    esc = read_escalation(work_order_id, db_path=db_path)
    result = {
        "ok": True,
        "work_order_id": work_order_id,
        "executor": executor,
        "escalated": bool(esc and (esc.get("escalation_level") or 0) >= 1),
        "escalation_level": (esc or {}).get("escalation_level", 0),
    }
    print(json.dumps(result, indent=2))
    return 0


def _work_order_artifact(
    *,
    work_order_id: str,
    kind: str,
    instance_key: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Print a WO ceremony/eval artifact stored in the authority (WO-FILESDB-C1).

    The operator/terminal read surface that replaces reading
    ``.planning/work-orders/<id>/*`` files — artifacts live in
    ``business_work_order_artifacts``, keyed by (work_order_id, kind, instance_key).
    """
    from core.installed_runtime import resolve_installed_runtime_paths
    from core.work_orders.artifacts import VALID_KINDS, get_wo_artifact

    if kind not in VALID_KINDS:
        print(
            f"Unknown artifact kind: {kind!r}. Valid: {', '.join(sorted(VALID_KINDS))}",
            file=sys.stderr,
        )
        return 1
    db_path = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    ).sqlite_path
    content = get_wo_artifact(work_order_id, kind, instance_key=instance_key, db_path=db_path)
    if content is None:
        label = f"{kind}" + (f" (instance={instance_key})" if instance_key else "")
        print(f"No {label} artifact stored for work order {work_order_id}", file=sys.stderr)
        return 1
    print(content)
    return 0


def _work_order_packet(
    *,
    work_order_id: str,
    target: str,
    storage_root: Path | None,
) -> int:
    """Render a WO execution packet on demand and print it (WO-FILESDB-C1).

    Derive-on-demand: the packet is rendered from the WO and printed to stdout —
    no ``rendered/<target>.md`` disk cache is written (that write path is retired
    in WO-FILESDB-C5). Reading the file-backed WO is a read, not a write.
    """
    from core.work_orders.models import WorkOrderError
    from core.work_orders.renderers import render_packet_text
    from core.work_orders.storage import load_work_order
    from core.work_orders.validation import validate_work_order

    try:
        work_order, _ = load_work_order(work_order_id, storage_root=storage_root)
    except WorkOrderError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    result = validate_work_order(work_order)
    if not result.ok:
        print(result.format(), file=sys.stderr)
        return 1
    print(render_packet_text(result.work_order, target))
    return 0


def _work_order_start(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
    accept_no_brief: bool = False,
    in_sequence: bool = False,
) -> int:
    """CLI wrapper around `core.work_orders.start.start_work_order`.

    Preserves the legacy operator-terminal behavior: prints a stderr WARNING
    when the work order is UI-typed but lacks a locked design brief; if the
    operator is running interactively (TTY), prompts y/N; otherwise auto-
    accepts (so test fixtures and non-interactive scripts keep working).

    Skills should call `start_work_order(accept_no_brief=...)` directly and
    never go through this CLI surface.
    """

    from core.work_orders.start import read_work_order_brief, start_work_order

    brief_data = read_work_order_brief(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not brief_data.get("ok"):
        print(json.dumps(brief_data, indent=2))
        return 1

    if brief_data.get("brief_warning") and not accept_no_brief:
        print(
            "WARNING: No locked design brief found. It is strongly recommended to run "
            "website:discover before building UI. Continue anyway? [y/N]",
            file=sys.stderr,
        )
        if sys.stdin.isatty():
            try:
                answer = sys.stdin.readline().strip().lower()
            except OSError:
                # On Windows, stdin may claim isatty()=True but fail on read
                # (WinError 1) in certain pipe/test contexts. Treat as non-interactive.
                answer = ""
            if answer not in ("y", "yes"):
                return 0
        # Non-interactive context (tests, scripts): auto-accept to preserve
        # legacy behavior — the warning is still emitted to stderr.
        accept_no_brief = True

    result = start_work_order(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
        accept_no_brief=accept_no_brief,
        brief_data=brief_data,
        in_sequence=in_sequence,
    )
    if result.get("ok") and result.get("sequence_warning"):
        print(result["sequence_warning"], file=sys.stderr)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_list(
    *,
    project_id: str | None,
    status_filter: str | None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.queries import list_work_orders

    result = list_work_orders(
        project_id=project_id,
        status_filter=status_filter,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_close(
    *,
    work_order_id: str,
    force: bool = False,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    """CLI wrapper around `core.work_orders.close.close_work_order`.

    Preserves the legacy operator-terminal behaviour by re-emitting
    `[gate.bypassed] WARNING: <reason>` to stderr from the returned
    `bypassed_gates` list. Skills should call `close_work_order` directly.
    """

    from core.work_orders.close import close_work_order

    result = close_work_order(
        work_order_id=work_order_id,
        force=force,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )

    if result.get("ok") and result.get("forced") and result.get("bypassed_gates"):
        for reason in result["bypassed_gates"]:
            print(f"[gate.bypassed] WARNING: {reason}", file=sys.stderr)

    print(json.dumps(result, indent=2))
    if result.get("ok") and result.get("next_block"):
        print(file=sys.stderr)
        print(result["next_block"], file=sys.stderr)
    return 0 if result.get("ok") else 1


def _work_order_block(
    *,
    work_order_id: str,
    reason: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.mutations import block_work_order

    result = block_work_order(
        work_order_id=work_order_id,
        reason=reason,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_unblock(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.mutations import unblock_work_order

    result = unblock_work_order(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_task_done(
    *,
    work_order_id: str,
    task_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    from core.work_orders.mutations import mark_task_done, todowrite_should_emit

    result = mark_task_done(
        work_order_id=work_order_id,
        task_id=task_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )
    if result.get("ok") and todowrite_should_emit(source_root):
        task_index = result.get("task_index", 0)
        todo_id = f"wo-{work_order_id[:8]}-{task_index}"
        print(json.dumps({"todowrite_update": {"id": todo_id, "status": "completed"}}, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_tasks(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    verbose: bool = False,
) -> int:
    from core.work_orders.queries import list_tasks

    result = list_tasks(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        verbose=verbose,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_verify(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.verify import verify_work_order

    result = verify_work_order(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=source_root / ".planning",
    )
    if not result.get("ok"):
        print(f"Error: {result.get('error', 'unknown error')}", file=sys.stderr)
        return 1
    passed = result["passed"]
    print(f"Verification {'PASSED' if passed else 'FAILED'}: {result['summary']}")
    for tv in result.get("tasks_verified", []):
        indicator = "✓" if tv["verdict"] == "pass" else ("~" if tv["verdict"] == "partial" else "✗")
        print(f"  {indicator} [{tv['verdict']}] {tv['task_title']}: {tv['evidence']}")
    spawned = result.get("spawned_work_orders", [])
    if spawned:
        print(f"\nGap work orders created ({len(spawned)}):")
        for wo in spawned:
            print(f"  [{wo['type']}] {wo['title']}  (id: {wo['work_order_id']})")
    print(f"\nVerdict: {result['verdict_path']}")
    return 0 if passed else 1


def _work_order_set_order(
    *,
    work_order_id: str,
    sequence_order: int,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.ordering import set_sequence_order

    result = set_sequence_order(
        work_order_id=work_order_id,
        sequence_order=sequence_order,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_add_dep(
    *,
    work_order_id: str,
    depends_on_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.ordering import add_dependency

    result = add_dependency(
        work_order_id=work_order_id,
        depends_on_id=depends_on_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_remove_dep(
    *,
    work_order_id: str,
    depends_on_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.ordering import remove_dependency

    result = remove_dependency(
        work_order_id=work_order_id,
        depends_on_id=depends_on_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_next(
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
