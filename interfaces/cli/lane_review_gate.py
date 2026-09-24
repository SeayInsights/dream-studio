"""Pre-push gate: the branch's work order is not pushed while its lane review holds it.

WHY A GATE AND NOT ONLY A STATUS. The operator's rule is that the review lanes run before
anything reaches GitHub. `advance_work_order(to="pushed")` refuses while the review blocks
-- but that governs a STATUS, and this repository pushes with plain `git push`. The bench's
receiver's-view seat found it in round three: nothing stood between an unreviewed branch
and GitHub. This runs where every push already stops: core/gates/pre_push.py.

WHAT IT GATES. The work order the branch names (`wo-<shortid>` or a full uuid, resolved by
core.gates.merge_readiness.resolve_work_order -- the same resolution merge readiness uses,
not a second one). While `review_status` blocks -- no dispatch, an unanswered lane, an open
finding -- the push fails and says why.

WHAT IT DOES NOT. A branch that names no work order, or a machine with no authority to
resolve one against, is NOT gated, and the gate prints that it is not rather than printing
a pass: plenty of legitimate changes carry no work order (merge readiness makes the same
call), and CI has no authority at all. "Not gated" and "reviewed clean" are different facts
and the output keeps them apart.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _branch() -> str | None:
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    name = (proc.stdout or "").strip()
    return name if proc.returncode == 0 and name and name != "HEAD" else None


def _authority() -> Path | None:
    from core.installed_runtime import resolve_installed_runtime_paths

    path = resolve_installed_runtime_paths(source_root=REPO_ROOT).sqlite_path
    return path if path.is_file() else None


def evaluate(branch: str | None, db_path: Path | None) -> tuple[int, str]:
    """``(exit_code, message)`` for one branch against one authority."""
    from core.gates.merge_readiness import resolve_work_order

    if not branch:
        return 0, "lane-review: NOT GATED -- detached HEAD names no branch, so no work order"
    work_order_id, why = resolve_work_order(branch=branch, db_path=db_path)
    if work_order_id is None:
        return 0, f"lane-review: NOT GATED -- {why}"

    from core.work_orders.review_answers import review_status

    status = review_status(work_order_id, db_path=db_path)
    if status["blocking"]:
        return 1, (
            f"lane-review: BLOCKED -- work order {work_order_id} is not cleared by its lane"
            f" review: {'; '.join(status['reasons'])}.\n"
            f"  ds review --status --work-order {work_order_id}"
        )
    return 0, (
        f"lane-review: clear -- work order {work_order_id}, round {status['round']}"
        f" at {str(status['sha'] or '')[:12]}"
    )


def main() -> int:
    code, message = evaluate(_branch(), _authority())
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
