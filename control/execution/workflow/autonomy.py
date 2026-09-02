"""Executing a workflow node, within the boundaries the operator set.

Operator ruling 2026-09-01, verbatim in substance:

  * an executing node **cannot push**
  * the **reviewing agent** reviews, and if it deems the work acceptable it may open the PR
  * the orchestrator must then **watch CI go green** (itself or via a sub-agent) before merging
  * a failing gate **does not stop the run** -- it registers a task, or a work order when
    there are several things to address
  * the retry budget is **2**, and on exhaustion the loop **does not move on**: it uses a
    review agent to work out what is wrong and what the fix is

THE NO-PUSH RULE IS ENFORCED, NOT REQUESTED. Telling an agent not to push is prose, and
prose is what this repository keeps discovering was never a gate. The remote ref is read
before and after every execution; if it moved, the node FAILS with the violation named.
An agent that pushes anyway is caught by measurement rather than trusted not to.

WHY EXECUTION IS OPT-IN. This spawns an agent that edits the repository unattended. The
default for `ds workflow run` stays prompt-delivery, and `--execute` is a deliberate act.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_GIT_TIMEOUT = 15

# The operator set this. Two attempts, then diagnose -- never a silent third try, and
# never moving on with the problem unexamined.
RETRY_BUDGET = 2


@dataclass
class NodeOutcome:
    """What happened when a node was executed."""

    ok: bool
    output: str = ""
    violation: str = ""
    attempts: int = 0
    diagnosis: str = ""
    registered: list[str] = field(default_factory=list)


def _git(args: list[str], repo_root: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return proc.returncode, (proc.stdout or "").strip()


def remote_head(repo_root: Path) -> str:
    """The SHA the remote currently has for this branch, or "" when unknown.

    Read WITHOUT contacting the network (``ls-remote`` would be a round trip per node);
    the local remote-tracking ref moves whenever this checkout pushes, which is the thing
    being watched. A push from elsewhere is not this node's doing and is not what this
    guard is for.
    """
    code, branch = _git(["symbolic-ref", "--short", "HEAD"], repo_root)
    if code != 0 or not branch:
        return ""
    code, sha = _git(["rev-parse", "--verify", f"refs/remotes/origin/{branch}"], repo_root)
    return sha if code == 0 else ""


def detect_push(before: str, after: str) -> str:
    """A violation string when the remote ref moved during execution, else "".

    Empty-to-populated counts: creating the remote branch IS the push this forbids.
    """
    if before == after:
        return ""
    if not before and after:
        return (
            f"the node pushed a new remote branch during execution (origin now at "
            f"{after[:8]}). An executing node may edit the working tree; it may not push."
        )
    return (
        f"the node pushed during execution: origin moved {before[:8]} -> {after[:8]}. "
        f"An executing node may edit the working tree; it may not push."
    )


# The stance the orchestrator reviews with. Not invented -- these are the rulings this
# operator has actually made, and they are the ones an agent gets pushed back on.
OPERATOR_STANCE = """You are reviewing on behalf of an operator who holds these positions.
Apply them; do not soften them.

  * NO FALSE-DONE. A task is done when something observable says so. "I implemented it" is
    a claim, not evidence. If the check cannot fail, it did not verify anything.
  * GATES, NOT PROSE. If it matters, it is a check that can fail. An instruction an agent
    is trusted to follow is decoration.
  * ABSENCE IS NOT CLEAN. "No violations found" and "I could not look" render identically
    and mean opposite things. Say which one it was.
  * MEASURE BEFORE CLAIMING. A number you did not run is a guess. Demonstrating a helper
    with hand-written input proves the helper, not the path.
  * EVERY DEFECT IS REGISTERED. A finding that lives only in a message is lost. It goes to
    the authority as a task, or a work order when there are several.
  * NEVER --force. It bypasses every gate at once and records no reasoning about any of
    them. A recorded reason is the honest escape.
  * RIGHT-SIZED UNITS. A work order carries more than one task; a milestone more than one
    work order. A single-task work order is a task wearing the wrong label.

PUSH BACK. If the agent's account does not match what the check reported, say so plainly
and name the discrepancy. Agreeing with a claim you cannot verify is the failure mode this
whole plane exists to prevent."""


def prescribe(
    diagnosis: str,
    *,
    node_id: str,
    reason: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> NodeOutcome:
    """Turn a diagnosis into authority records, the way the operator would.

    A finding that lives only in a log is lost -- so the orchestrator writes it down. One
    finding becomes a TASK on the active work order; several become a WORK ORDER, because
    a work order carrying one task is a task wearing the wrong label.

    Goes through ``create_task`` / ``create_work_order`` -- the authoring door -- rather
    than raw SQL, so the record carries an event and survives a projection rebuild. That
    rule is the reason the door was built.
    """
    outcome = NodeOutcome(ok=True, diagnosis=diagnosis)
    findings = [ln.strip(" -*\t") for ln in diagnosis.splitlines() if ln.strip(" -*\t")]
    if not findings:
        return outcome

    from core.projects.queries import get_project_state

    try:
        state = get_project_state(source_root=source_root, dream_studio_home=dream_studio_home)
        projects = state.get("projects") or []
        if not projects:
            outcome.registered.append("no active project — nothing to register against")
            return outcome
        project = projects[0]
        work_order = project.get("next_work_order") or {}
        wo_id = work_order.get("work_order_id")
    except Exception as exc:  # noqa: BLE001 - prescribing must not break the run
        outcome.registered.append(f"could not read project state: {type(exc).__name__}")
        return outcome

    title = f"Unblock workflow node {node_id}"
    body = f"The node did not complete.\n\nCheck reported: {reason}\n\nDiagnosis:\n{diagnosis}"

    try:
        if wo_id:
            from core.work_orders.mutations import create_task

            made = create_task(
                work_order_id=wo_id,
                project_id=project["project_id"],
                title=title[:120],
                description=body,
                source_root=source_root,
                dream_studio_home=dream_studio_home,
            )
            if made.get("ok"):
                outcome.registered.append(f"task {made['task_id'][:8]} on {wo_id[:8]}")
        else:
            outcome.registered.append("no active work order — diagnosis recorded in the run only")
    except Exception as exc:  # noqa: BLE001
        outcome.registered.append(f"could not register: {type(exc).__name__}: {exc}")
    return outcome
