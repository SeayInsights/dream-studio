"""Correct a misaddressed acceptance criterion, on the record.

WO 17f20d48. ``acceptance_criteria`` is write-once in the projection -- every other write
site COALESCEs it -- so a typo in a check was permanently uncorrectable. Measured on WO
1db6de49: its criterion named
``tests/unit/test_workflow_runner.py::test_a_node_without_an_observable_condition_is_not_reported_complete``
and the test is actually named ``..._is_not_reported_completed``. One character. The close
gate correctly reported MISADDRESSED (pytest exit 4) rather than treating a missing node id
as a pass, so the work order could not close although all four of its tasks were done and
shipped. The only remaining escape was ``--force``, which bypasses every other gate to fix
one string.

TWO GUARDS, because an editable acceptance criterion is a moved goalpost waiting to happen.

  1. THE NEW CRITERION MUST RESOLVE. A criterion is only repointable to something that can
     actually be found and run -- the same check the close gate runs, run here first. This
     is what makes the mechanism a typo-fixer rather than a way to point a failing check at
     something that does not exist.

  2. THE PRIOR VALUE AND A REASON ARE RECORDED, in the event payload, so the correction is
     in the stream forever. A later reader can tell a typo fix from a weakened target
     because both criteria are right there. Nothing here can prevent someone repointing to
     a trivially-passing test; the record is what makes that visible instead of silent.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_MIN_REASON = 12


def _resolves(
    acceptance_criteria: str, db_path: Path, project_root: Path | None
) -> tuple[bool, str]:
    """Can this criterion be found and run? Returns ``(resolvable, detail)``.

    Reuses ``run_executable_checks`` -- the very runner the close gate uses -- rather than
    reimplementing check dispatch. A second implementation would be free to disagree with
    the gate about what "resolves" means, and then a criterion could pass here and be
    MISADDRESSED there.

    FAILING IS FINE. A check that runs and reports failure is correctly addressed; the work
    simply is not done yet. Only a check that cannot be found is refused.
    """
    from .verify_executor import run_executable_checks

    results = run_executable_checks(
        [{"title": "repoint-probe", "acceptance_criteria": acceptance_criteria}],
        db_path,
        project_root,
    )
    checks = [c for entries in results.values() for c in entries]
    if not checks:
        return False, (
            "no executable check found in that text — a criterion must contain a "
            "TEST-CHECK, SQL-CHECK or API-CHECK line"
        )
    for check in checks:
        error = str(check.get("error") or "")
        result = str(check.get("result") or "")
        if "USAGE ERROR" in error or "USAGE ERROR" in result or "misaddressed" in error.lower():
            return False, f"the new criterion is also misaddressed: {error or result}"
    return True, "resolves"


def repoint_acceptance_criteria(
    *,
    task_id: str,
    acceptance_criteria: str,
    reason: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Replace a task's acceptance criterion, recording what it was and why."""
    from .start_shared import _require_db

    text = (reason or "").strip()
    if len(text) < _MIN_REASON:
        return {
            "ok": False,
            "error": (
                "Repointing needs a reason a later reader can weigh — enough to tell a "
                "typo fix from a moved goalpost."
            ),
        }
    new_ac = (acceptance_criteria or "").strip()
    if not new_ac:
        return {"ok": False, "error": "No acceptance criterion given."}

    db_path = _require_db(source_root, dream_studio_home)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT task_id, work_order_id, project_id, title, acceptance_criteria"
            " FROM business_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"ok": False, "error": f"Task not found: {task_id}"}

    previous = row["acceptance_criteria"] or ""
    if previous.strip() == new_ac:
        return {"ok": False, "error": "That is already the criterion; nothing to repoint."}

    project_root = None
    try:
        from .verify_executor import resolve_project_root

        resolved = resolve_project_root(row["work_order_id"], db_path)
        project_root = Path(resolved) if resolved else None
    except Exception:
        project_root = None

    resolvable, detail = _resolves(new_ac, db_path, project_root)
    if not resolvable:
        return {
            "ok": False,
            "error": (
                f"Refused — {detail}. A criterion may only be repointed to a check that "
                f"can actually be found and run; otherwise this becomes a way to point a "
                f"check at nothing. (A check that RUNS and fails is fine — that is just "
                f"work still to do.)"
            ),
        }

    now = datetime.now(UTC).isoformat()
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="task.ac_repointed",
                session_id=None,
                payload={
                    "acceptance_criteria": new_ac,
                    "previous": previous,
                    "reason": text,
                },
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "project_id": row["project_id"],
                    "work_order_id": row["work_order_id"],
                    "task_id": task_id,
                    "attribution_status": "fully_attributed",
                },
            ).to_dict()
        )
        from core.projections.runner import sync_tick as _sync_tick

        _sync_tick()
    except Exception as exc:
        return {"ok": False, "error": f"Could not record the repoint: {exc}"}

    return {
        "ok": True,
        "task_id": task_id,
        "work_order_id": row["work_order_id"],
        "title": row["title"],
        "previous": previous,
        "acceptance_criteria": new_ac,
        "reason": text,
    }
