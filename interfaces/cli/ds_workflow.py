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

    ns = argparse.Namespace(
        name=name, yaml_path=yaml_path, work_order=getattr(args, "work_order", None)
    )
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


#: Where a project keeps its own gate manifest. One name, so an operator who has
#: onboarded a project knows where to put it without reading the source.
PROJECT_GATE_MANIFEST = Path(".dream-studio") / "pre-push.yaml"


def _resolve_gate_manifest(
    *,
    repo_root: str | None,
    manifest_path: str | None,
) -> dict:
    """Decide which manifest to run and against which tree.

    Returns ``{"manifest_path": Path|None, "repo_root": Path|None}``, or
    ``{"error": str}`` when the request cannot be honoured. ``None`` for either
    means "Dream Studio's own", which is what `run_pre_push_gates` already defaults to.

    THE REFUSAL IS THE POINT, and it is why a fallback is not offered. Dream Studio's
    gates measure Dream Studio: skill-sync compares canonical skills to their projections,
    `pin-tests` compares `dist/plugin` to the generator, `migration-risk` watches this
    repo's DDL sites. Run against somebody else's repository they do not report on that
    repository — they pass vacuously or fail for reasons about this one. A green result
    that means nothing is worse than a refusal, because only one of the two gets fixed.
    """
    resolved_root = Path(repo_root).expanduser().resolve() if repo_root else None

    if manifest_path:
        explicit = Path(manifest_path).expanduser().resolve()
        if not explicit.is_file():
            return {"error": f"Error: no gate manifest at {explicit}"}
        return {"manifest_path": explicit, "repo_root": resolved_root}

    if resolved_root is None:
        return {"manifest_path": None, "repo_root": None}

    if not resolved_root.is_dir():
        return {"error": f"Error: not a directory: {resolved_root}"}

    candidate = resolved_root / PROJECT_GATE_MANIFEST
    if not candidate.is_file():
        return {
            "error": (
                f"Error: {resolved_root} has no gate manifest at"
                f" {PROJECT_GATE_MANIFEST.as_posix()}.\n"
                "Dream Studio's own gates are not run in its place: they measure Dream"
                " Studio (skill projections, dist/plugin freshness, this repo's"
                " migrations), so against another repository they would pass without"
                " having looked.\n"
                f"Write {PROJECT_GATE_MANIFEST.as_posix()} declaring that project's own"
                " gates, or pass --manifest to name one."
            )
        }
    return {"manifest_path": candidate, "repo_root": resolved_root}


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

        # THE CAPABILITY WAS BUILT AND THE DOOR DID NOT OPEN IT. `run_pre_push_gates`
        # has taken `manifest_path` and `repo_root` all along, and this call passed
        # neither — so every gate run measured Dream Studio, whatever repository the
        # operator was standing in, and no other project could be gated at all.
        resolved = _resolve_gate_manifest(
            repo_root=getattr(args, "repo_root", None),
            manifest_path=getattr(args, "manifest_path", None),
        )
        if resolved.get("error"):
            print(resolved["error"], file=sys.stderr)
            return 1

        report = run_pre_push_gates(
            manifest_path=resolved["manifest_path"],
            repo_root=resolved["repo_root"],
        )
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
    # A driver that stops without saying what it is waiting on has not taken the human
    # out of the loop — it has moved them somewhere worse, because now they must
    # reconstruct the state themselves. Computing the reason and not printing it would
    # be the same defect one layer down.
    if final_status == "blocked" and runner.blocked_on:
        print("[workflow] waiting on:")
        print(runner.blocked_on)
    if final_status == "completed_with_unverified" and runner.blocked_on:
        print("[workflow] finished, but these nodes were never observed:")
        print(runner.blocked_on)
        print(
            "[workflow] Declare a completion_check on each — a cheap read that observes"
            " the effect (a git ref, an authority query). Until then this run advanced"
            " without confirming the work."
        )
    return 0 if final_status in ("completed", "completed_with_unverified", "running") else 1


def add_workflow_subcommand(subparsers) -> None:
    """Register the 'workflow' subcommand group onto the parent parser."""
    wf_parser = subparsers.add_parser("workflow", help="Workflow execution commands")
    wf_sub = wf_parser.add_subparsers(dest="workflow_cmd")

    # start
    p_start = wf_sub.add_parser("start", help="Initialise a workflow from a YAML file")
    p_start.add_argument("yaml_path", help="Path to workflow YAML")
    p_start.add_argument("--name", default=None, help="Workflow name (default: YAML stem)")
    p_start.add_argument(
        "--work-order",
        dest="work_order",
        default=None,
        help=(
            "The work order this run executes. Recorded on the run and resolvable in any"
            " node as {{workflow.work_order_id}}, so a completion_check can name its"
            " subject. Passed explicitly rather than inferred: several work orders are"
            " in_progress at once, and picking by recency is the attribution guess the"
            " stop hook was corrected for."
        ),
    )
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
    p_run.add_argument(
        "--repo-root",
        default=None,
        dest="repo_root",
        metavar="DIR",
        help=(
            "Run the gates against THIS repository instead of Dream Studio's own."
            " Its gate manifest is read from <DIR>/.dream-studio/pre-push.yaml; a"
            " repository with no manifest is refused rather than judged by Dream"
            " Studio's gates, which measure Dream Studio."
        ),
    )
    p_run.add_argument(
        "--manifest",
        default=None,
        dest="manifest_path",
        metavar="FILE",
        help="Read the gate manifest from this file, overriding the convention",
    )
    p_run.set_defaults(func=cmd_run)
