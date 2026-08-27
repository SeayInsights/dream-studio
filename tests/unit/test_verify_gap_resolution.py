"""WO-VERIFY-GAP-RESOLUTION: closed gap WOs resolve verdicts; violations never do.

Discovered dogfooding WO-VERIFY-PROVENANCE: verify grades only WO-attributed
commits, so remediation committed under a spawned gap WO's own id is invisible
to the original WO's re-verify — a remediated-and-closed coverage gap failed
the original WO forever and blocked its close on independent_review.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-08-19T00:00:00.000000Z"


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


@contextmanager
def _patch_db(db_path: Path):
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        yield


def _seed(db_path: Path, *, project_id: str, milestone_id: str, work_order_id: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "Test", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO business_milestones"
        " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description,"
        "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,'in_progress',1,?,?,?)",
        (work_order_id, project_id, milestone_id, "Test WO", "desc", "cleanup", NOW, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, description, status,"
        "  created_at, updated_at)"
        " VALUES (?,?,?,?,?, 'complete', ?, ?)",
        (str(uuid.uuid4()), work_order_id, project_id, "T1", "do it", NOW, NOW),
    )
    conn.commit()
    conn.close()


def _grader_results(*, violations: list | None = None, coverage_gaps: list | None = None) -> dict:
    """Completion + quality pass; correctness fails on the given drivers."""
    return {
        "completion": {
            "passed": True,
            "completion_score": 1.0,
            "tasks_verified": [{"task_title": "T1", "evidence": "done", "verdict": "pass"}],
            "summary": "All tasks addressed.",
            "gaps": [],
        },
        "correctness": {
            "correctness_passed": False,
            "correctness_score": 1.0,
            "violations": violations or [],
            "coverage_gaps": coverage_gaps or [],
            "migration_gaps": [],
        },
        "quality": {"quality_passed": True, "quality_score": 1.0, "issues": []},
    }


def _run_verify(db_path: Path, tmp_path: Path, work_order_id: str, grader_results: dict) -> dict:
    planning_root = tmp_path / "planning"
    with _patch_db(db_path):
        with patch(
            "core.work_orders.verify_graders._run_graders_parallel",
            return_value=grader_results,
        ):
            with patch(
                "core.work_orders.verify_git._collect_git_commits",
                return_value="diff --git a/fake.py b/fake.py\n+# change",
            ):
                from core.work_orders.verify import verify_work_order

                return verify_work_order(
                    work_order_id=work_order_id,
                    source_root=REPO_ROOT,
                    dream_studio_home=tmp_path,
                    planning_root=planning_root,
                )


def _set_status(db_path: Path, work_order_id: str, status: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE business_work_orders SET status=? WHERE work_order_id=?", (status, work_order_id)
    )
    conn.commit()
    conn.close()


def test_closed_gap_wo_resolves_verdict(tmp_path: pytest.TempPathFactory) -> None:
    """A CLOSED work order's coverage gap spawns a sibling, and closing that sibling
    resolves the verdict.

    SCENARIO NARROWED BY WO-GAP-FANOUT. This test used to seed an OPEN parent, because
    every gap spawned a sibling regardless. A gap on an open, incomplete work order is now
    a TASK on that work order -- operator: "why are we registering more work orders
    instead of adding the appropriate tasks." So the spawn-and-resolve path is exercised
    where it is still the right behaviour: a closed work order has nowhere to put a task.

    The mechanism is unchanged and still covered; only the precondition that reaches it is
    stated explicitly now instead of being incidental.
    """
    db_path = _make_db(tmp_path)
    project_id, milestone_id, work_order_id = (str(uuid.uuid4()) for _ in range(3))
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    _set_status(db_path, work_order_id, "closed")
    graders = _grader_results(
        coverage_gaps=[{"function": "helper_fn", "file": "core/x.py"}],
    )

    first = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert first["passed"] is False
    assert first["resolved_gaps"] == []
    spawned = first["spawned_work_orders"]
    assert spawned, "a closed work order must spawn a sibling; it cannot hold a task"
    spawned_id = spawned[0]["work_order_id"]
    assert spawned_id != work_order_id, "a spawn must be a SIBLING, not the reviewed WO"

    # Gap WO still open: no discount.
    second = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert second["passed"] is False

    # AND CLOSING IT STILL DOES NOT RESOLVE -- because "add missing test coverage" is a
    # PROJECT-WIDE class, not this work order's finding.
    #
    # This is the assertion that changed, and it is worth stating why the obvious one is
    # wrong. Two mechanisms collide for a project-wide class:
    #
    #   resolve-on-closed-remediation   "this was dealt with, pass the parent"
    #   do-not-swallow-new-occurrences  "this class recurs, keep reporting it"
    #
    # The second wins. Once the class was made project-wide, a closed tracker made every
    # future gap of that class take the suppression branch -- tasks inserted nowhere, the
    # finding silently lost (WO-GAP-FANOUT defect 6). A tracker closing says nothing about
    # the NEXT occurrence, and the grader here is still reporting the gap.
    #
    # Resolution by closed remediation keeps full coverage in
    # test_closed_spawn_resolves_completion_gap, which uses a work-order-specific gap --
    # the case where "this was dealt with" is actually true of this work order.
    _set_status(db_path, spawned_id, "closed")
    third = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert (
        third["passed"] is False
    ), "a closed PROJECT-WIDE tracker must not resolve a still-reported finding"
    assert third["resolved_gaps"] == []
    fresh = [w["work_order_id"] for w in third["spawned_work_orders"]]
    assert (
        fresh and spawned_id not in fresh
    ), "a new occurrence of a project-wide class gets a FRESH tracker, never the closed one"


def test_an_open_work_orders_coverage_gap_becomes_its_own_task(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """THE NEW PRECEDENCE, asserted rather than assumed.

    The counterpart to the test above: the same coverage gap on an OPEN work order
    attaches to it instead of spawning. Spawning a sibling declared the parent complete
    and routed around the tasks_done gate, which is how a work order could be certified
    while its own reviewer-found work sat elsewhere.

    And an attached gap must NOT appear in spawned_work_orders. It used to, carrying the
    reviewed work order's own id -- close_gates.py prints that list as "Gap WOs", so the
    close named the work order being closed as its own blocking gap.
    """
    db_path = _make_db(tmp_path)
    project_id, milestone_id, work_order_id = (str(uuid.uuid4()) for _ in range(3))
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    graders = _grader_results(
        coverage_gaps=[{"function": "helper_fn", "file": "core/x.py"}],
    )

    result = _run_verify(db_path, tmp_path, work_order_id, graders)

    assert result["passed"] is False
    attached = result.get("attached_gap_tasks", [])
    assert attached, "an open, incomplete work order's gap must become a task on it"
    assert attached[0]["work_order_id"] == work_order_id
    assert attached[0].get("attached_to_reviewed") is True

    for entry in result["spawned_work_orders"]:
        assert entry["work_order_id"] != work_order_id, (
            "the reviewed work order must never appear as its own spawned gap WO -- "
            "close_gates prints that list as 'Gap WOs'"
        )


def test_blocked_gap_wo_never_resolves_verdict(tmp_path: pytest.TempPathFactory) -> None:
    """respawn_suppressed fires for any non-open status — but only exactly
    'closed' may discount. A blocked or cancelled gap WO (remediation never
    done) keeps the verdict failed (gap WO d6e7b4c0)."""
    db_path = _make_db(tmp_path)
    project_id, milestone_id, work_order_id = (str(uuid.uuid4()) for _ in range(3))
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    graders = _grader_results(
        coverage_gaps=[{"function": "helper_fn", "file": "core/x.py"}],
    )
    # A CLOSED reviewed work order is what reaches the spawn path at all: an OPEN one
    # takes the gap as a task on itself (WO-GAP-FANOUT). Without this the spawn list is
    # empty and the test failed with IndexError -- which is the split of
    # spawned_work_orders from attached_gap_tasks doing its job, since this line used to
    # be handed the REVIEWED work order's own id and carry on regardless.
    _set_status(db_path, work_order_id, "closed")

    first = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert first["passed"] is False
    spawned = first["spawned_work_orders"]
    assert spawned, "a closed work order must spawn a sibling; it cannot hold a task"
    spawned_id = spawned[0]["work_order_id"]
    assert spawned_id != work_order_id, "a spawn must be a SIBLING, not the reviewed WO"

    for not_done_status in ("blocked", "cancelled"):
        _set_status(db_path, spawned_id, not_done_status)
        rerun = _run_verify(db_path, tmp_path, work_order_id, graders)
        assert rerun["passed"] is False, f"{not_done_status} gap WO must not discount"
        assert rerun["resolved_gaps"] == []


def _graders_completion_gap() -> dict:
    """Completion grader fails a task and emits a gap; correctness/quality clean."""
    return {
        "completion": {
            "passed": False,
            "completion_score": 0.67,
            "tasks_verified": [
                {"task_title": "T1", "evidence": "weaker variant shipped", "verdict": "missing"}
            ],
            "summary": "Task T1 shipped a weaker variant.",
            "gaps": [
                {
                    "title": "Deliver T1 as specified",
                    "description": "T1 was approximated",
                    "work_order_type": "cleanup",
                    "tasks": [{"title": "Do T1 exactly", "description": "as written"}],
                }
            ],
        },
        "correctness": {
            "correctness_passed": True,
            "correctness_score": 1.0,
            "violations": [],
            "coverage_gaps": [],
            "migration_gaps": [],
        },
        "quality": {"quality_passed": True, "quality_score": 1.0, "issues": []},
    }


def test_closed_spawn_resolves_completion_gap(tmp_path: pytest.TempPathFactory) -> None:
    """WO-GAP-RES-COMPLETION: a completion-driven gap whose spawned remediation
    WO is CLOSED resolves the parent verdict — the closed (gate-checked,
    independently reviewed) WO is the completion evidence the parent diff
    cannot carry. Blocked/cancelled spawns never discount."""
    db_path = _make_db(tmp_path)
    project_id, milestone_id, work_order_id = (str(uuid.uuid4()) for _ in range(3))
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    graders = _graders_completion_gap()

    # A CLOSED reviewed work order is the precondition that reaches this path: an OPEN
    # one now takes the completion gap as a task on itself (WO-GAP-FANOUT), so a sibling
    # is only spawned when there is nowhere to put one.
    _set_status(db_path, work_order_id, "closed")

    first = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert first["passed"] is False
    spawned = first["spawned_work_orders"]
    assert spawned, "a closed work order must spawn a sibling for its completion gap"
    spawned_id = spawned[0]["work_order_id"]
    assert spawned_id != work_order_id, "a spawn must be a SIBLING, not the reviewed WO"

    # Blocked or cancelled remediation: never discounts.
    for not_done in ("blocked", "cancelled"):
        _set_status(db_path, spawned_id, not_done)
        rerun = _run_verify(db_path, tmp_path, work_order_id, graders)
        assert rerun["passed"] is False, f"{not_done} spawn must not resolve a completion gap"

    # Closed remediation: the completion gap is resolved.
    _set_status(db_path, spawned_id, "closed")
    resolved = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert resolved["passed"] is True, resolved.get("gaps")
    assert resolved["resolved_gaps"] == [spawned_id]


def test_closed_child_diffs_join_parent_evidence(tmp_path: pytest.TempPathFactory) -> None:
    """WO-GAP-EVIDENCE: a CLOSED gap WO spawned from the parent contributes its
    remediation diff to the parent's graded evidence — the completion grader
    sees the fixes committed under the child's id and can pass on merits,
    independent of grader-phrasing-stable gap keys."""
    db_path = _make_db(tmp_path)
    project_id, milestone_id, work_order_id = (str(uuid.uuid4()) for _ in range(3))
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)

    # Seed a CLOSED child gap WO carrying the parent's gap-key marker.
    child_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description,"
        "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,'closed',2,?,?,?)",
        (
            child_id,
            project_id,
            milestone_id,
            "Gap remediation",
            f"Fix the gap. [gap-key: {work_order_id}::some-category]",
            "cleanup",
            NOW,
            NOW,
            NOW,
        ),
    )
    conn.commit()
    conn.close()

    def _per_id_diffs(root, wo_id, title=None):
        if wo_id == work_order_id:
            return "diff --git a/parent.py b/parent.py\n+parent change"
        if wo_id == child_id:
            return "diff --git a/child_fix.py b/child_fix.py\n+the remediation"
        return None

    passing_graders = {
        "completion": {
            "passed": True,
            "completion_score": 1.0,
            "tasks_verified": [{"task_title": "T1", "evidence": "done", "verdict": "pass"}],
            "summary": "done",
            "gaps": [],
        },
        "correctness": {
            "correctness_passed": True,
            "correctness_score": 1.0,
            "violations": [],
            "coverage_gaps": [],
            "migration_gaps": [],
        },
        "quality": {"quality_passed": True, "quality_score": 1.0, "issues": []},
    }
    captured_prompts: dict = {}

    def _capture_graders(prompts):
        captured_prompts.update(prompts)
        return passing_graders

    with _patch_db(db_path):
        with patch(
            "core.work_orders.verify_graders._run_graders_parallel",
            side_effect=_capture_graders,
        ):
            with patch(
                "core.work_orders.verify_git._collect_git_commits", side_effect=_per_id_diffs
            ):
                from core.work_orders.verify import verify_work_order

                result = verify_work_order(
                    work_order_id=work_order_id,
                    source_root=REPO_ROOT,
                    dream_studio_home=tmp_path,
                    planning_root=tmp_path / "planning",
                )
    assert result["ok"] is True
    completion_prompt = captured_prompts.get("completion", "")
    assert "the remediation" in completion_prompt, "child diff must reach the grader"
    assert f"remediation evidence (closed gap WO {child_id})" in completion_prompt
    assert "parent change" in completion_prompt


def test_violation_never_discounted(tmp_path: pytest.TempPathFactory) -> None:
    """A rule violation keeps the verdict failed even when its spawned WO is closed."""
    db_path = _make_db(tmp_path)
    project_id, milestone_id, work_order_id = (str(uuid.uuid4()) for _ in range(3))
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    graders = _grader_results(
        violations=[
            {
                "rule": "LAYER-MAP Rule 1",
                "file": "runtime/hooks/x.py",
                "detail": "hook writes to authority table",
            }
        ],
    )

    first = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert first["passed"] is False
    for s in first["spawned_work_orders"]:
        _set_status(db_path, s["work_order_id"], "closed")

    second = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert second["passed"] is False
    assert second["resolved_gaps"] == []
