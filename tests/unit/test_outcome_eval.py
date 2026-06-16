"""T1/T3 (WO-OUTCOME-EVAL): outcome eval over recently-closed work orders.

The behavioral eval runner measures rail-adherence from traces (PROCESS); it never
checks OUTCOME — "did the symptom actually resolve". This outcome eval re-runs each
recently-closed WO's originating_symptom + task acceptance-criteria against live/seeded
state and reports pass/fail. It is the safety net behind the close gate: a WO can close
green and still have its symptom silently regress later.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database

NOW = "2026-01-01T00:00:00+00:00"


def _seed_closed_wo(db_path: Path, *, symptom: str, ac: str = "") -> str:
    """Seed a project + a CLOSED work order with one complete task. Returns work_order_id."""
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    wo = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (project_id, "Test", "", "active", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
            "  status, closed_at, created_at, updated_at, last_updated_at, originating_symptom)"
            " VALUES (?,?,?,?,?,?, 'closed', ?, ?, ?, ?, ?)",
            (
                wo,
                project_id,
                milestone_id,
                "Test WO",
                "d",
                "infrastructure",
                NOW,
                NOW,
                NOW,
                NOW,
                symptom,
            ),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, acceptance_criteria,"
            "  status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?, 'complete', ?, ?)",
            (str(uuid.uuid4()), wo, project_id, "T1", "d", ac, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return wo


def test_outcome_eval_detects_persisting_symptom(tmp_path: Path) -> None:
    """A closed WO whose originating-symptom SQL-CHECK still fails → outcome FAIL."""
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)

    # SQL-CHECK that returns 0 (falsy) → the symptom never resolved.
    symptom = "SQL-CHECK: SELECT COUNT(*) FROM business_projects WHERE project_id='does-not-exist'"
    wo = _seed_closed_wo(db, symptom=symptom)

    from core.eval.runner import run_outcome_eval

    result = run_outcome_eval(db_path=db, source_root=tmp_path, auto_reopen=False)

    assert result["ok"] is True
    failed_ids = {f["work_order_id"] for f in result["failed"]}
    assert wo in failed_ids, f"persisting symptom not detected; got {result}"
    fail = next(f for f in result["failed"] if f["work_order_id"] == wo)
    assert fail["passed"] is False
    assert any("originating_symptom" in r for r in fail["failures"])


def test_outcome_eval_passes_when_symptom_resolved(tmp_path: Path) -> None:
    """A closed WO whose symptom SQL-CHECK now passes → outcome PASS (not in failed)."""
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)

    # SQL-CHECK that returns >=1 (truthy) — the seeded project exists.
    symptom = "SQL-CHECK: SELECT COUNT(*) FROM business_projects"
    wo = _seed_closed_wo(db, symptom=symptom)

    from core.eval.runner import run_outcome_eval

    result = run_outcome_eval(db_path=db, source_root=tmp_path, auto_reopen=False)

    assert result["ok"] is True
    assert wo not in {f["work_order_id"] for f in result["failed"]}


def test_outcome_eval_is_wired_to_a_runner() -> None:
    """T3: the outcome eval must be invoked by a live runner, not dormant.

    A registered-but-never-run eval is the same false-completion class the WO targets.
    The pulse collector (run on every UserPromptSubmit via the on-pulse hook) is the
    live periodic runner; assert it references run_outcome_eval.
    """
    from pathlib import Path as _P

    pulse = _P("interfaces/cli/pulse_collector.py").read_text(encoding="utf-8")
    assert "run_outcome_eval" in pulse, (
        "run_outcome_eval is not wired into the pulse collector — it would be a dormant, "
        "never-run eval (the false-completion class WO-OUTCOME-EVAL T3 forbids)."
    )


def test_runner_does_not_write_business_tables_directly() -> None:
    """Dependency Rule 3: the eval layer must not write business_* directly.

    The outcome eval reopens a regressed WO via core.work_orders.mutations
    (the designated business-state writer), never a raw UPDATE from core/eval/.
    """
    import re
    from pathlib import Path as _P

    src = _P("core/eval/runner.py").read_text(encoding="utf-8")
    writes = re.findall(
        r"(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|UPDATE|DELETE\s+FROM)\s+business_\w*",
        src,
        re.IGNORECASE,
    )
    assert (
        not writes
    ), f"core/eval/runner.py writes business_* directly (Rule 3 violation): {writes}"
