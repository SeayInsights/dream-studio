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
from collections.abc import Callable
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


# ── The operator's rules, as predicates ───────────────────────────────────────
#
# THESE WERE PROSE AND THAT WAS THE DEFECT. A paragraph handed to a model saying "no
# false-done, gates not prose" is exactly the thing it forbids: an instruction someone is
# trusted to follow. The operator caught it -- "these should be rules for the operator not
# prose though" -- in a stance whose second line was GATES, NOT PROSE.
#
# Each rule below RUNS against what actually happened in a node and returns a violation or
# nothing. The short statements are still handed to a reviewing agent, but they are derived
# from the rules rather than maintained beside them, so the text cannot drift from the
# check the way a comment drifts from its code.


@dataclass(frozen=True)
class RuleContext:
    """What a rule gets to look at. Everything here is observed, not reported."""

    node_id: str
    ynode: dict
    reported_success: bool
    check_status: str
    check_reason: str = ""
    output: str = ""
    diagnosis: str = ""
    registered: list[str] = field(default_factory=list)
    remote_before: str = ""
    remote_after: str = ""


@dataclass(frozen=True)
class OperatorRule:
    """One position the operator holds, expressed so it can fail."""

    rule_id: str
    statement: str
    check: Callable[[RuleContext], str | None]


def _no_false_done(ctx: RuleContext) -> str | None:
    if ctx.reported_success and ctx.check_status == "blocked":
        return (
            f"{ctx.node_id} reported success while its completion check reported "
            f"{ctx.check_reason or 'failure'}. The agent's account and the observation "
            f"disagree; the observation wins."
        )
    return None


def _gates_not_prose(ctx: RuleContext) -> str | None:
    if ctx.ynode.get("completion_contains") and not ctx.ynode.get("completion_check"):
        return (
            f"{ctx.node_id} declares completion_contains with no completion_check. Alone "
            f"it verifies nothing -- a declaration that cannot fail is decoration."
        )
    return None


def _absence_is_not_clean(ctx: RuleContext) -> str | None:
    declared = ctx.ynode.get("completion_check") or ctx.ynode.get("completion_contains")
    if not declared and ctx.check_status == "completed":
        return (
            f"{ctx.node_id} was recorded completed with nothing declared to observe it. "
            f"'Nobody looked' and 'nothing was wrong' are different facts."
        )
    return None


def _defect_is_registered(ctx: RuleContext) -> str | None:
    if ctx.diagnosis and not ctx.registered:
        return (
            f"{ctx.node_id} produced a diagnosis that was never written to the authority. "
            f"A finding that lives only in a run's output is lost when it scrolls."
        )
    return None


def _never_force(ctx: RuleContext) -> str | None:
    haystack = f"{ctx.output} {ctx.ynode.get('completion_check') or ''}"
    if "--force" in haystack or "force=True" in haystack:
        return (
            f"{ctx.node_id} used --force. It bypasses every gate at once and records no "
            f"reasoning about any of them; a recorded reason is the honest escape."
        )
    return None


def _never_push(ctx: RuleContext) -> str | None:
    return detect_push(ctx.remote_before, ctx.remote_after) or None


OPERATOR_RULES: tuple[OperatorRule, ...] = (
    OperatorRule(
        "no_false_done",
        "A task is done when something observable says so; a claim is not evidence.",
        _no_false_done,
    ),
    OperatorRule(
        "gates_not_prose",
        "If it matters it is a check that can fail, not an instruction someone follows.",
        _gates_not_prose,
    ),
    OperatorRule(
        "absence_is_not_clean",
        "'I could not look' and 'nothing was wrong' must not render identically.",
        _absence_is_not_clean,
    ),
    OperatorRule(
        "defect_is_registered",
        "Every finding goes to the authority; one becomes a task, several a work order.",
        _defect_is_registered,
    ),
    OperatorRule(
        "never_force",
        "--force bypasses every gate at once; record a reason instead.",
        _never_force,
    ),
    OperatorRule(
        "never_push",
        "An executing node may edit the working tree; it may not push.",
        _never_push,
    ),
)


def evaluate_operator_rules(ctx: RuleContext) -> list[str]:
    """Run every rule. Returns the violations, which is what pushing back is made of."""
    violations: list[str] = []
    for rule in OPERATOR_RULES:
        try:
            hit = rule.check(ctx)
        except Exception as exc:  # noqa: BLE001 - a broken rule must not stop the run
            hit = f"{rule.rule_id} could not be evaluated ({type(exc).__name__})"
        if hit:
            violations.append(f"[{rule.rule_id}] {hit}")
    return violations


def stance_brief() -> str:
    """The rules as text for a reviewing agent, DERIVED so it cannot drift from them."""
    lines = [
        "You are reviewing on behalf of an operator who holds these positions.",
        "Apply them; do not soften them. Each one is also enforced as a predicate.",
        "",
    ]
    lines += [f"  * {r.rule_id.upper()}: {r.statement}" for r in OPERATOR_RULES]
    lines += [
        "",
        "PUSH BACK. If the agent's account does not match what the check reported, say so",
        "plainly and name the discrepancy. Agreeing with a claim you cannot verify is the",
        "failure this plane exists to prevent.",
    ]
    return chr(10).join(lines)


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
