"""Integration tests for the escalation ladder (WO-ESCALATION-LADDER).

The deterministic verifier/outcome-eval owns the escalate DECISION (AD-8). When a
closed WO regresses (symptom persists / AC fails), the platform reopens it and
escalates: the retry is routed to a more capable model (Opus), re-close requires a
PASSING independent review (no silent force), and retries are capped before the
ladder hands back to the operator.

Tests:
  T2 — test_escalated_wo_routes_retry_to_opus
  T3 — test_escalated_reclose_requires_independent_review
  T5 — test_loop_and_manual_honor_escalation
  T6 — test_end_to_end
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from unittest.mock import MagicMock, patch

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-01-01T00:00:00+00:00"


@contextmanager
def _patch_close_runtime(db_path: Path):
    """Point the close path at the temp DB and neutralize the real projection tick."""
    fake = MagicMock()
    fake.sqlite_path = db_path
    with (
        patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake),
        patch("core.projections.runner.sync_tick", new=MagicMock()),
    ):
        yield


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db)
    return db


def _seed_closed_wo(db_path: Path, *, symptom: str | None, ac: str) -> str:
    """Seed a closed WO with an originating symptom + one complete task carrying ``ac``."""
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
            "  status, originating_symptom, closed_at, created_at, updated_at, last_updated_at)"
            " VALUES (?,?,?,?,?,?, 'closed', ?, ?, ?, ?, ?)",
            (
                wo,
                project_id,
                milestone_id,
                "WO",
                "d",
                "infrastructure",
                symptom,
                NOW,
                NOW,
                NOW,
                NOW,
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


def _seed_inprogress_wo(db_path: Path, *, ac: str) -> str:
    """Seed an in_progress infrastructure WO (post_build_gate=independent_review)
    with one COMPLETE task carrying ``ac`` — i.e. everything passes except whatever
    the independent_review gate decides."""
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
            "  status, created_at, updated_at, last_updated_at)"
            " VALUES (?,?,?,?,?,?, 'in_progress', ?, ?, ?)",
            (wo, project_id, milestone_id, "WO", "d", "infrastructure", NOW, NOW, NOW),
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


def _write_passing_verdict(planning_root: Path, wo: str) -> None:
    """Pre-write a passing review-verdict.json so the independent_review gate passes
    and close's inline auto-verify is skipped."""
    wo_dir = planning_root / "work-orders" / wo
    wo_dir.mkdir(parents=True, exist_ok=True)
    (wo_dir / "review-verdict.json").write_text(
        json.dumps({"ok": True, "passed": True, "work_order_id": wo, "summary": "ok"}),
        encoding="utf-8",
    )


def _wo_status(db_path: Path, wo: str) -> str:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT status FROM business_work_orders WHERE work_order_id = ?", (wo,)
        ).fetchone()[0]
    finally:
        conn.close()


def _set_status(db_path: Path, wo: str, status: str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE business_work_orders SET status = ? WHERE work_order_id = ?", (status, wo)
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# T2 — escalated WO routes its retry to Opus
# ---------------------------------------------------------------------------


def test_escalated_wo_routes_retry_to_opus(tmp_path: Path) -> None:
    """A closed WO whose symptom regresses is reopened AND escalated: its retry
    resolves to the Opus executor, and a fresh (non-escalated) WO does not.

    AC: tests/integration/test_escalation.py::test_escalated_wo_routes_retry_to_opus
    """
    from core.eval.runner import run_outcome_eval
    from core.work_orders.escalation import (
        DEFAULT_EXECUTOR,
        read_escalation,
        resolve_executor,
    )

    db = _make_db(tmp_path)
    # Symptom that will FAIL on re-eval (table does not exist → check errors → fail).
    wo = _seed_closed_wo(
        db,
        symptom="SQL-CHECK: SELECT 1 WHERE EXISTS (SELECT 1 FROM no_such_table_zzz)",
        ac="SQL-CHECK: SELECT 1",
    )

    # Baseline: an un-escalated WO resolves to the default executor, not Opus.
    assert resolve_executor(wo, db_path=db) == DEFAULT_EXECUTOR
    assert resolve_executor(wo, db_path=db) != "opus"

    # Outcome eval detects the regression, reopens, and escalates.
    result = run_outcome_eval(
        db_path=db,
        source_root=tmp_path,
        dream_studio_home=tmp_path,
        auto_reopen=True,
        symptom_only=True,
    )
    assert result["ok"] is True, f"outcome eval failed: {result}"

    # WO reopened to in_progress.
    assert _wo_status(db, wo) == "in_progress"

    # Escalation recorded with the Opus capability flag.
    esc = read_escalation(wo, db_path=db)
    assert esc is not None, "expected an escalation row after reopen"
    assert esc["designated_executor"] == "opus"
    assert esc["escalation_level"] >= 1

    # The retry now routes to Opus on both surfaces (they call resolve_executor).
    assert resolve_executor(wo, db_path=db) == "opus"


# ---------------------------------------------------------------------------
# T3 — re-close after escalation requires a PASSING independent review
# ---------------------------------------------------------------------------


def test_escalated_reclose_requires_independent_review(tmp_path: Path) -> None:
    """An escalated WO cannot re-close without a passing independent review — not
    even with force=True. Once a passing verdict exists, close succeeds.

    AC: tests/integration/test_escalation.py::test_escalated_reclose_requires_independent_review
    """
    from core.work_orders.close import close_work_order
    from core.work_orders.escalation import mark_escalated

    db = _make_db(tmp_path)
    planning_root = tmp_path / ".planning"
    wo = _seed_inprogress_wo(db, ac="SQL-CHECK: SELECT 1")  # AC + tasks_done both pass
    mark_escalated(wo, db_path=db, reason="symptom regressed")

    # No passing verdict yet. Inline auto-verify will be unreviewable (source_root has
    # no git → no diff). force=True must NOT silently bypass the mandatory review.
    with _patch_close_runtime(db):
        forced = close_work_order(
            work_order_id=wo,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=True,
        )
    assert forced["ok"] is False, f"force must not bypass mandatory review; got: {forced}"
    assert forced.get("escalated") is True
    assert any(f.startswith("independent_review") for f in forced["failures"])
    assert _wo_status(db, wo) == "in_progress"

    # Provide a PASSING independent-review verdict → close now succeeds (no force).
    _write_passing_verdict(planning_root, wo)
    with _patch_close_runtime(db):
        ok = close_work_order(
            work_order_id=wo,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=False,
        )
    assert ok["ok"] is True, f"expected clean close with passing review; got: {ok}"
    assert ok["status"] == "closed"
    assert _wo_status(db, wo) == "closed"


# ---------------------------------------------------------------------------
# T5 — both the autonomous loop and the manual path honor the escalation routing
# ---------------------------------------------------------------------------


def test_loop_and_manual_honor_escalation(tmp_path: Path) -> None:
    """The manual path (start_work_order) and the autonomous loop both honor the
    escalation capability flag, via the single resolve_executor source of truth.

    AC: tests/integration/test_escalation.py::test_loop_and_manual_honor_escalation
    """
    from core.work_orders.escalation import mark_escalated, resolve_executor
    from core.work_orders.start import start_work_order

    db = _make_db(tmp_path)
    planning_root = tmp_path / ".planning"
    wo = _seed_inprogress_wo(db, ac="SQL-CHECK: SELECT 1")

    # Not escalated → default executor, on both the engine and the manual path.
    assert resolve_executor(wo, db_path=db) == "sonnet"
    with _patch_close_runtime(db):
        res_default = start_work_order(
            work_order_id=wo,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
        )
    assert res_default["executor"] == "sonnet"
    assert "escalation" not in res_default

    # Escalate → the manual path now resolves Opus and surfaces the escalation.
    mark_escalated(wo, db_path=db, reason="symptom regressed")
    assert resolve_executor(wo, db_path=db) == "opus"
    with _patch_close_runtime(db):
        res_esc = start_work_order(
            work_order_id=wo,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
        )
    assert res_esc["executor"] == "opus", f"manual path must honor escalation; got {res_esc}"
    assert res_esc["escalation"]["level"] >= 1
    assert res_esc["escalation"]["designated_executor"] == "opus"

    # The autonomous loop honors the same flag: the execute-work-orders workflow has an
    # escalation-probe node that calls `ds work-order executor` and an implement node
    # instructed to run the retry on the resolved executor.
    wf = (REPO_ROOT / "canonical" / "workflows" / "execute-work-orders.yaml").read_text(
        encoding="utf-8"
    )
    assert "escalation-probe" in wf
    assert "work-order executor" in wf
    assert "HONOR THE ESCALATION EXECUTOR" in wf


# ---------------------------------------------------------------------------
# T6 — end-to-end ladder: regress → escalate(Opus) → retry → cap → operator
# ---------------------------------------------------------------------------


def test_end_to_end(tmp_path: Path) -> None:
    """Full escalation ladder: a regressed closed WO is reopened and routed to Opus;
    when retries hit the configured cap, the ladder stops auto-reopening and escalates
    to the operator (no silent loop).

    AC: tests/integration/test_escalation.py::test_end_to_end
    """
    import json as _json

    from core.config.authority import set_config_value
    from core.eval.runner import run_outcome_eval
    from core.work_orders.artifacts import get_wo_artifact
    from core.work_orders.escalation import (
        RETRY_CAP_CONFIG_KEY,
        read_escalation,
        resolve_executor,
    )

    db = _make_db(tmp_path)
    set_config_value(RETRY_CAP_CONFIG_KEY, "2", db)  # low cap for the test
    wo = _seed_closed_wo(
        db,
        symptom="SQL-CHECK: SELECT 1 WHERE EXISTS (SELECT 1 FROM no_such_table_zzz)",  # always fails
        ac="SQL-CHECK: SELECT 1",
    )

    def _operator_escalation():
        # WO-FILESDB-C4B S5: the operator (retry-cap) escalation is recorded in the
        # authority store, not a disk ESC-*.md file.
        content = get_wo_artifact(wo, "escalation", instance_key="retrycap", db_path=db)
        return _json.loads(content) if content else None

    def _eval() -> None:
        run_outcome_eval(
            db_path=db,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            auto_reopen=True,
            symptom_only=True,
        )

    # Round 1: regression detected → reopen + escalate to Opus (retry 1, under cap).
    _eval()
    assert _wo_status(db, wo) == "in_progress"
    assert resolve_executor(wo, db_path=db) == "opus"
    assert read_escalation(wo, db_path=db)["retry_count"] == 1
    assert _operator_escalation() is None, "operator escalation must not fire under the cap"

    # The AI's Opus retry re-closes the WO; assume the symptom regresses again.
    _set_status(db, wo, "closed")

    # Round 2: retry 2 hits the cap (2) → escalate to OPERATOR, do NOT silently reopen.
    _eval()
    esc = read_escalation(wo, db_path=db)
    assert esc["retry_count"] == 2
    operator_esc = _operator_escalation()
    assert operator_esc is not None, "expected an operator escalation in the store at the cap"
    assert operator_esc["status"] == "unresolved"
    assert "retry cap" in operator_esc["reason"].lower()
    assert _wo_status(db, wo) == "closed", "capped WO must not be silently reopened again"
