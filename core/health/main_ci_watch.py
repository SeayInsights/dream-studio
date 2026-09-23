"""What happens to a work order after its work reaches `main`.

THE GAP THIS CLOSES. A work order reached `pushed` and then nothing watched. Merge
authorisation is pr-smoke, which is a subset; the suite that runs everything is Full CI on
`main`, and it runs AFTER the merge — so the branch carrying a failure is the one nobody
is looking at. Three times in one day a merge put main red and the work was declared done
anyway, because noticing required someone to go and look.

So this is the half that looks. It is a COMMAND rather than an agent's habit because the
durable half — the verdict, the work order status, the task carrying the failing node ids
— has to survive a session ending. An agent that only tells someone is an agent whose
finding dies with its context.

WHAT IT DECIDES, AND WHAT IT DOES NOT. It reads the CI verdict and records the
consequence. It does not fix anything: remediation is work, work belongs to a work order,
and the work order is the one that was already pushed. The findings become TASKS on that
same work order, because work found wanting after a push is that work order's unfinished
work — filing a new work order would fragment one change across several, after which the
module boundary describes part of it and the prompt chain restates a goal one row over.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

#: A pytest failure line, as `gh run view --log-failed` emits it inside a prefixed log.
#: The prefix (job, step, timestamp) varies, so the node id is matched rather than the line.
_FAILED = re.compile(r"FAILED (tests/\S+?)(?:\s+-\s|\s*$)", re.M)

#: How many node ids a single remediation task names before it is summarised. A task whose
#: acceptance criterion lists two hundred node ids is not a task anybody can pick up, and
#: the criterion stops being readable long before that.
MAX_NAMED_FAILURES = 12


def failing_node_ids(run_id: str, *, repo_root: Path | None = None) -> list[str]:
    """The pytest node ids a failed run reports, deduplicated and ordered.

    Read from `gh run view --log-failed` rather than from a parsed report, because the
    report is whatever the job chose to write and the log is what actually happened. An
    unreadable log yields an empty list: the failure is still recorded, just without the
    node ids, and a watcher that raised here would turn a red main into two problems.
    """
    try:
        proc = subprocess.run(
            ["gh", "run", "view", str(run_id), "--log-failed"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(repo_root) if repo_root else None,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0 and not proc.stdout:
        return []
    # MATCH `tests/`, NOT `tests/unit/`. Grepping the narrower prefix once reported 11
    # failures when there were 16, dropping every integration failure -- and the wrong
    # number was then repeated to the operator.
    seen: dict[str, None] = {}
    for node in _FAILED.findall(proc.stdout or ""):
        seen.setdefault(node.strip(), None)
    return list(seen)


def runnable_nodes(nodes: list[str], *, repo_root: Path | None = None) -> list[str]:
    """The node ids whose file still exists in this tree.

    Admission refuses a TEST-CHECK naming a file that does not exist, and it is right to:
    a criterion written against a missing file can never fail for the right reason. This
    is not only a fixture concern -- a merge that DELETES a test file, and breaks
    something by deleting it, reports failures naming files that are no longer there.

    Only the path is checked, not the node. Whether `::test_x` still exists inside the
    file is a question for the runner, and asking it here would mean importing the module
    to find out.
    """
    base = Path(repo_root) if repo_root else Path(".")
    return [n for n in nodes if (base / n.split("::", 1)[0]).is_file()]


def remediation_task(
    nodes: list[str],
    run_url: str | None,
    head_sha: str | None,
    *,
    unrunnable: list[str] | None = None,
) -> dict[str, str]:
    """The task a red main becomes: a title, a description, and a runnable criterion.

    THE FAILING TESTS ARE THE ACCEPTANCE CRITERION. Nothing else needs inventing — the
    question "is this fixed" already has an exact answer, and a TEST-CHECK naming the node
    ids is what `close` will execute anyway. A task whose criterion is prose would be
    admitted only with a declared reason, and there is no reason here: the check exists.
    """
    sha = (head_sha or "")[:7]
    where = f" at {sha}" if sha else ""
    if nodes:
        named = nodes[:MAX_NAMED_FAILURES]
        more = len(nodes) - len(named)
        criterion = "TEST-CHECK: " + " ".join(named)
        body = (
            f"Full CI failed on `main`{where}, so the work this order pushed is not done.\n\n"
            f"{len(nodes)} failing test(s)"
            + (f", the first {len(named)} named below" if more else "")
            + ":\n"
            + "\n".join(f"  {n}" for n in named)
            + (f"\n  ... and {more} more (see the run)" if more else "")
            + (f"\n\nRun: {run_url}" if run_url else "")
        )
        title = f"Fix {len(nodes)} test(s) failing on main{where}"
    else:
        # A RED RUN WITH NO RUNNABLE NODE IDS IS STILL RED. The job may have failed in a
        # gate step rather than in pytest, the log may be unreadable, or the failures may
        # name files this merge deleted. The task says which, instead of pretending to
        # know, and carries a DECLARED REASON rather than a criterion that cannot run --
        # the same escape any author gets, used honestly.
        criterion = ""
        body = (
            f"Full CI failed on `main`{where} with no runnable pytest node ids -- the"
            " failure was in a gate step, the log could not be read, or the failing tests"
            " name files that are not in this tree."
            + (
                "\n\nReported but unrunnable here:\n"
                + "\n".join(f"  {n}" for n in (unrunnable or [])[:MAX_NAMED_FAILURES])
                if unrunnable
                else ""
            )
            + (f"\n\nRun: {run_url}" if run_url else "")
        )
        title = f"Fix Full CI on main{where}"
    out = {"title": title, "description": body}
    if criterion:
        out["acceptance_criteria"] = criterion
    else:
        # The declared reason a criterion is absent. Admission requires 20+ characters and
        # refuses a shrug, which is the point: this says what could not be checked and why.
        out["why"] = (
            "Full CI reported a failure with no runnable test node id in this tree, so"
            " there is no check to name; the run is the evidence and the fix has to start"
            " by reading it."
        )
    return out


def work_orders_awaiting_ci(db_path: Path) -> list[dict[str, Any]]:
    """Work orders at `pushed` or `ci_issues`: the ones whose fate this run decides.

    `pushed` is the link between a merge and the work that caused it. It is deliberately
    not terminal, which is what makes this query meaningful -- a work order that had
    already closed on being pushed would be invisible here, and the run that broke it
    would have nothing to attach to.

    `ci_issues` is here because it is the other phase a work order closes from. Its fixes
    are pushed from inside that phase, and a green main is what says they worked; a
    watcher that only saw `pushed` would leave every fixed work order at `ci_issues`
    forever. Each row carries its status, because a red run means something different
    for each: new for one, already recorded for the other.
    """
    import sqlite3

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        rows = conn.execute(
            "SELECT work_order_id, title, project_id, status FROM business_work_orders"
            " WHERE status IN ('pushed', 'ci_issues') ORDER BY last_updated_at ASC"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [
        {"work_order_id": r[0], "title": r[1], "project_id": r[2], "status": r[3]} for r in rows
    ]
