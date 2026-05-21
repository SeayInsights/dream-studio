"""ds workflow subcommands (Slice 9b)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def cmd_start(args) -> int:
    """Initialise a workflow and print its key."""
    yaml_path = args.yaml_path
    if not Path(yaml_path).is_file():
        print(f"Error: file not found: {yaml_path}", file=sys.stderr)
        return 1

    name = args.name or Path(yaml_path).stem

    import argparse
    from control.execution.workflow.state import cmd_start as _state_start

    ns = argparse.Namespace(name=name, yaml_path=yaml_path)
    try:
        _state_start(ns)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 1
    return 0


def cmd_status(args) -> int:
    """Print status of a workflow (or all active workflows)."""
    import argparse
    from control.execution.workflow.state import cmd_status as _state_status

    ns = argparse.Namespace(key=getattr(args, "wf_key", None))
    try:
        _state_status(ns)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 1
    return 0


def cmd_list(args) -> int:
    """List all active workflows."""
    import argparse
    from control.execution.workflow.state import cmd_status as _state_status

    ns = argparse.Namespace(key=None)
    try:
        _state_status(ns)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 1
    return 0


def cmd_advance(args) -> int:
    """Execute the next wave of ready nodes in a workflow."""
    from control.execution.workflow.runner import WorkflowRunner

    dry_run = getattr(args, "dry_run", False)
    runner = WorkflowRunner(args.wf_key, dry_run=dry_run)
    try:
        executed = runner.advance()
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not executed:
        print("[workflow] no nodes ready (workflow may be done or blocked)")
    else:
        print(f"[workflow] executed: {', '.join(executed)}")
    return 0


def cmd_run(args) -> int:
    """Run a workflow to completion (all waves).

    Special case: ``ds workflow run pre-push --non-interactive`` dispatches to
    the deterministic gate runner in ``core.gates.pre_push`` instead of the
    model-driven workflow engine. The git pre-push hook (B.3) uses this path
    so the hook never blocks on an LLM round-trip.
    """
    non_interactive = bool(getattr(args, "non_interactive", False))
    if non_interactive and args.wf_key == "pre-push":
        from core.gates.pre_push import format_report, run_pre_push_gates

        report = run_pre_push_gates()
        print(format_report(report))
        return 0 if report.overall_passed else 1

    if non_interactive:
        print(
            "Error: --non-interactive is only supported for the `pre-push` workflow.",
            file=sys.stderr,
        )
        return 2

    from control.execution.workflow.runner import WorkflowRunner

    dry_run = getattr(args, "dry_run", False)
    runner = WorkflowRunner(args.wf_key, dry_run=dry_run)
    try:
        final_status = runner.run()
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"[workflow] final status: {final_status}")
    return 0 if final_status in ("completed", "running") else 1


def add_workflow_subcommand(subparsers) -> None:
    """Register the 'workflow' subcommand group onto the parent parser."""
    wf_parser = subparsers.add_parser("workflow", help="Workflow execution commands")
    wf_sub = wf_parser.add_subparsers(dest="workflow_cmd")

    # start
    p_start = wf_sub.add_parser("start", help="Initialise a workflow from a YAML file")
    p_start.add_argument("yaml_path", help="Path to workflow YAML")
    p_start.add_argument("--name", default=None, help="Workflow name (default: YAML stem)")
    p_start.set_defaults(func=cmd_start)

    # status
    p_status = wf_sub.add_parser("status", help="Show workflow status")
    p_status.add_argument("wf_key", nargs="?", default=None, help="Workflow key")
    p_status.set_defaults(func=cmd_status)

    # list
    p_list = wf_sub.add_parser("list", help="List all active workflows")
    p_list.set_defaults(func=cmd_list)

    # advance
    p_adv = wf_sub.add_parser("advance", help="Execute the next wave of ready nodes")
    p_adv.add_argument("wf_key", help="Workflow key")
    p_adv.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print what would run without invoking any skill",
    )
    p_adv.set_defaults(func=cmd_advance)

    # run
    p_run = wf_sub.add_parser("run", help="Run workflow to completion")
    p_run.add_argument("wf_key", help="Workflow key, or `pre-push` with --non-interactive")
    p_run.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Dry-run all waves without invoking any skill",
    )
    p_run.add_argument(
        "--non-interactive",
        action="store_true",
        dest="non_interactive",
        help=(
            "Run a deterministic gate workflow without invoking the LLM. "
            "Currently only supported for `pre-push` — used by hooks/git/pre-push."
        ),
    )
    p_run.set_defaults(func=cmd_run)
