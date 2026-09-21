"""How many tasks cannot be independently checked.

MEASUREMENT ONLY. This was `core/gates/task_criteria_baseline.py`, a blocking
pre-push gate that ratcheted against a checked-in ceiling -- one of nine gates
whose subject was the platform's own bookkeeping rather than whether Dream
Studio works. The gate is gone.

The COUNTING survives because it is a genuine property of gap-fanout, asserted by
behavioural tests: a gap run must not leave more uncheckable tasks than it found
(test_verify_gaps.py, test_gap_fanout.py). Deleting the measurement to delete the
gate would have taken real coverage with it.

Two ways a task is uncheckable, and they need different fixes:
  - no acceptance criterion at all -- nothing names a check
  - a criterion an open sibling also carries -- one run marks both done, so
    neither can independently fail
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


#: A declared reason lives in the task description, mirroring `--why` on `add-task`. A task
#: carrying one is not a stub -- it is a claim someone recorded as uncomputable -- so it is
#: outside the population this gate counts.
#:
#: IMPORTED, NOT RETYPED. The writer and this reader agreed on a hardcoded phrase until
#: the Warden's lane was asked of it; the marker now has one definition, beside the
#: admission check that grants the declaration.
from core.work_orders.admission import DECLARED_PREFIX as DECLARED_MARKER  # noqa: E402


def _db_path() -> Path:
    from core.config.database import _default_db_path

    return Path(_default_db_path())


def measure(db_path: Path | None = None) -> dict[str, object]:
    """Tasks with no acceptance criterion and no declared reason.

    Returns ``status: "unknown"`` with a reason when the authority cannot be read, never a
    count of zero: "I could not look" and "there are none" have different remedies, and
    collapsing them is how a gate starts passing for the wrong reason.
    """
    path = db_path or _db_path()
    if not Path(path).is_file():
        return {"status": "unknown", "reason": f"no authority database at {path}"}
    try:
        conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return {"status": "unknown", "reason": f"authority could not be opened ({exc})"}
    try:
        total = conn.execute("SELECT COUNT(*) FROM business_tasks").fetchone()[0]
        rows = conn.execute(
            "SELECT COALESCE(description, '') FROM business_tasks"
            " WHERE acceptance_criteria IS NULL OR TRIM(acceptance_criteria) = ''"
        ).fetchall()
    except sqlite3.Error as exc:
        conn.close()
        return {"status": "unknown", "reason": f"business_tasks could not be read ({exc})"}

    # A SECOND WAY TO BE UNCHECKABLE, and the count above cannot see it (WO f769de79). A
    # task with no criterion is uncheckable because nothing names a check. A task whose
    # criterion is ALSO carried by an open sibling is uncheckable for the opposite reason:
    # a check names it and names the other one too, so one run marks both done and neither
    # can independently fail.
    #
    # MEASURED SEPARATELY, AND ITS FAILURE IS NOT THE GATE'S FAILURE. This began inside the
    # try above, sharing one except with the count that BLOCKS -- so a supplementary
    # observation touching columns the primary count never needed could take the whole gate
    # to UNKNOWN, which fails closed and refuses every push. It did exactly that: the gate's
    # own test fixture has no `status` or `work_order_id` column, and five tests went red
    # reporting "business_tasks could not be read". An observation that can veto the
    # measurement it decorates is worse than no observation, so this one reports None and
    # the ceiling is decided without it.
    shared: int | None
    try:
        shared = conn.execute(
            "SELECT COUNT(*) FROM business_tasks t"
            " WHERE t.status IN ('pending', 'in_progress')"
            "   AND TRIM(COALESCE(t.acceptance_criteria, '')) != ''"
            "   AND EXISTS (SELECT 1 FROM business_tasks o"
            "               WHERE o.work_order_id = t.work_order_id"
            "                 AND o.task_id != t.task_id"
            "                 AND o.status IN ('pending', 'in_progress')"
            "                 AND TRIM(COALESCE(o.acceptance_criteria, ''))"
            "                     = TRIM(COALESCE(t.acceptance_criteria, '')))"
        ).fetchone()[0]
    except sqlite3.Error:
        shared = None
    finally:
        conn.close()

    declared = sum(1 for (description,) in rows if DECLARED_MARKER in description)
    return {
        "status": "computed",
        "total_tasks": total,
        "without_criterion": len(rows),
        "of_those_declared": declared,
        "uncheckable": len(rows) - declared,
        # REPORTED, NOT ADDED TO THE CEILING. Folding this into `uncheckable` would move a
        # blocking baseline under everyone mid-stream and refuse pushes for a number that
        # just changed meaning. Enforcement for new tasks is the Herald refusing them at
        # admission; this is the standing count of what is already filed.
        "shared_criterion": shared,
    }
