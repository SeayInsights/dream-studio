"""`ds ci` — what happens to a work order after its work reaches `main`.

Merge authorisation is pr-smoke, which is a subset. The suite that runs everything is Full
CI on `main`, and it runs AFTER the merge — so the branch carrying a failure is the one
nobody is watching. This is the half that watches.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

#: How long to wait for a run that is still going. Full CI took 21.5 minutes when last
#: measured; this leaves room for a slower one without waiting on a hung job forever.
DEFAULT_TIMEOUT_SECONDS = 2700

#: Between polls. Long enough not to hammer the API, short enough that a 90-second run is
#: not reported four minutes late.
DEFAULT_POLL_SECONDS = 30


def register(subcommands: Any) -> None:
    ci = subcommands.add_parser("ci", help="Watch what happens to work after it reaches main")
    ci_sub = ci.add_subparsers(dest="ci_command", required=True)

    watch = ci_sub.add_parser(
        "watch",
        help="Wait for Full CI on main, then close the work orders it vindicates"
        " or record the failure on them",
    )
    watch.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Give up waiting after this long (default {DEFAULT_TIMEOUT_SECONDS}).",
    )
    watch.add_argument(
        "--poll-seconds",
        type=int,
        default=DEFAULT_POLL_SECONDS,
        help=f"How often to re-read the run (default {DEFAULT_POLL_SECONDS}).",
    )
    watch.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Read the current verdict and act on it without waiting for a running job.",
    )
    watch.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report what would happen to each work order and change nothing.",
    )


def dispatch(args: Any, *, source_root: Path, dream_studio_home: Path | None) -> int:
    if args.ci_command != "watch":
        print(f"Unknown ci command: {args.ci_command}", file=sys.stderr)
        return 1
    return _watch(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
        once=args.once,
        dry_run=args.dry_run,
    )


def _await_verdict(
    *, source_root: Path, timeout_seconds: int, poll_seconds: int, once: bool
) -> dict[str, Any]:
    """The CI verdict, waiting out a run that is still going.

    Read LIVE every time (`max_age_seconds=0`). A cached answer is the wrong tool here for
    the same reason it is wrong at close: this is the low-frequency, high-consequence
    moment, and being told about main by a cache is how a red one goes unnoticed.
    """
    from core.health.main_ci import main_ci_status

    deadline = time.monotonic() + max(0, timeout_seconds)
    while True:
        state = main_ci_status(repo_root=source_root, max_age_seconds=0) or {}
        status = state.get("status")
        if status != "running" or once:
            return state
        if time.monotonic() >= deadline:
            # A TIMEOUT IS UNKNOWN, NOT A FAILURE. A slow job is not a broken one, and
            # recording it as red would close work orders' fate on a guess.
            return {
                **state,
                "status": "unknown",
                "reason": f"still running after {timeout_seconds}s",
            }
        time.sleep(min(poll_seconds, max(1, int(deadline - time.monotonic()))))


def _watch(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    timeout_seconds: int,
    poll_seconds: int,
    once: bool,
    dry_run: bool,
) -> int:
    from core.health.main_ci_watch import (
        failing_node_ids,
        remediation_task,
        runnable_nodes,
        work_orders_awaiting_ci,
    )
    from core.work_orders.queries import _require_db

    db_path = _require_db(source_root, dream_studio_home)
    awaiting = work_orders_awaiting_ci(db_path)

    verdict = _await_verdict(
        source_root=source_root,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
        once=once,
    )
    status = verdict.get("status")
    report: dict[str, Any] = {
        "ok": True,
        "ci": {
            "status": status,
            "head_sha": verdict.get("head_sha"),
            "run_url": verdict.get("run_url"),
            "reason": verdict.get("reason"),
        },
        "work_orders_awaiting": [w["work_order_id"] for w in awaiting],
        "actions": [],
        "dry_run": dry_run,
    }

    # UNKNOWN CHANGES NOTHING. An absent `gh`, a rate limit, a timeout, a run nobody has
    # started: all unknown. Acting on one would either close work over an unverified main
    # or open remediation for a failure that never happened.
    if status not in ("success", "failure"):
        report["note"] = (
            "CI is neither a known pass nor a known failure, so no work order changed."
            " An unreadable signal is reported as unreadable."
        )
        print(json.dumps(report, indent=2))
        return 0

    if not awaiting:
        report["note"] = (
            "No work order is at `pushed`, so this run vindicates or breaks nothing"
            " recorded. Mark work `ds work-order pushed <id>` when it goes out."
        )
        print(json.dumps(report, indent=2))
        return 0

    nodes: list[str] = []
    if status == "failure":
        run_url = verdict.get("run_url") or ""
        run_id = run_url.rstrip("/").split("/")[-1] if run_url else ""
        reported = failing_node_ids(run_id, repo_root=source_root) if run_id else []
        # FILTERED BEFORE THE TASK IS BUILT. Admission refuses a TEST-CHECK naming a file
        # that is not there, and rightly -- but the watcher runs unattended, so an refused
        # task would leave the red main recorded on the status and nowhere else: priority
        # blocker with no work attached to pick up.
        nodes = runnable_nodes(reported, repo_root=source_root)
        unrunnable = [n for n in reported if n not in nodes]
        report["ci"]["failing_tests"] = reported
        if unrunnable:
            report["ci"]["unrunnable_here"] = unrunnable

    for wo in awaiting:
        action = _act(
            wo,
            status=status,
            verdict=verdict,
            nodes=nodes,
            unrunnable=unrunnable,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            dry_run=dry_run,
            remediation=remediation_task,
        )
        report["actions"].append(action)

    report["ok"] = all(a.get("ok", True) for a in report["actions"])
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


def _act(
    wo: dict[str, Any],
    *,
    status: str,
    verdict: dict[str, Any],
    nodes: list[str],
    unrunnable: list[str],
    source_root: Path,
    dream_studio_home: Path | None,
    dry_run: bool,
    remediation: Any,
) -> dict[str, Any]:
    """Close the work order, or record the failure on it. Never both, never neither."""
    wo_id = wo["work_order_id"]

    if status == "success":
        if dry_run:
            return {"work_order_id": wo_id, "would": "close", "ok": True}
        from core.work_orders.close import close_work_order

        result = close_work_order(
            work_order_id=wo_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
        out = {"work_order_id": wo_id, "did": "close", "ok": bool(result.get("ok"))}
        if result.get("error"):
            out["error"] = result["error"]
        # A close refused because main is red cannot happen here -- status is success --
        # but a close refused by a GATE can, and that is worth saying plainly: CI passing
        # does not mean the work order's own criteria did.
        if result.get("failures"):
            out["failures"] = result["failures"]
        return out

    task = remediation(
        nodes, verdict.get("run_url"), verdict.get("head_sha"), unrunnable=unrunnable
    )
    if dry_run:
        return {"work_order_id": wo_id, "would": "record ci_issues", "task": task, "ok": True}

    from core.work_orders.mutations import advance_work_order, create_task

    advanced = advance_work_order(
        work_order_id=wo_id,
        to="ci_issues",
        note=verdict.get("run_url"),
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    added = create_task(
        work_order_id=wo_id,
        project_id=wo["project_id"],
        title=task["title"],
        description=task["description"],
        acceptance_criteria=task.get("acceptance_criteria"),
        why=task.get("why"),
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    return {
        "work_order_id": wo_id,
        "did": "record ci_issues",
        "status": advanced.get("status"),
        "task_id": added.get("task_id"),
        "ok": bool(advanced.get("ok")) and bool(added.get("ok")),
        **(
            {"error": added.get("error") or advanced.get("error")}
            if not (advanced.get("ok") and added.get("ok"))
            else {}
        ),
    }
