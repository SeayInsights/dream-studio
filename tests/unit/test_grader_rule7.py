"""WO-GRADER-ADVERSARIAL: quality rules 7/8 + default-on independent review.

Rule 7 encodes the gw#619/#535 class (durable-state crash/race/skew, silent
persist-key vs read-key mismatch); rule 8 encodes the Fulcrum magic-link class
(config signal guarding a secret while a different knob controls reachability).
Default-on verify closes the audit finding that independent review ran only
for WO types whose post-gate happened to name it.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.verify_prompts import _QUALITY_PROMPT_TEMPLATE

REPO_ROOT = Path(__file__).resolve().parents[2]
# Pre-cutover created_at: keeps these WOs grandfathered past the
# change_impact_affirmed gate (2026-08-02 cutover) — the gate under test here
# is independent_review, not change-impact.
NOW = "2026-05-16T00:00:00.000000Z"


# ── the rubric carries the rules ────────────────────────────────────────────────


def test_rule7_durable_state_in_rubric():
    assert "(7) DURABLE-STATE ADVERSARIAL COVERAGE" in _QUALITY_PROMPT_TEMPLATE
    assert "crash mid-write" in _QUALITY_PROMPT_TEMPLATE
    assert "DURABLE_STATE_ADVERSARIAL" in _QUALITY_PROMPT_TEMPLATE
    # The #535 class: persist under one key, read under another, no error anywhere.
    assert "DIFFERENT key" in _QUALITY_PROMPT_TEMPLATE


def test_rule8_config_proxy_in_rubric():
    assert "(8) CONFIG-AS-PROXY / SIGNAL-VS-REACHABILITY" in _QUALITY_PROMPT_TEMPLATE
    # The Fulcrum magic-link class: trace what the secret is valid AGAINST.
    assert "valid AGAINST" in _QUALITY_PROMPT_TEMPLATE
    assert "CONFIG_AS_PROXY" in _QUALITY_PROMPT_TEMPLATE


# ── stub-grader flow: findings surface in the verdict ───────────────────────────


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


def _seed_wo(db_path: Path, *, wo_type: str = "cleanup") -> tuple[str, str, str]:
    project_id, milestone_id, work_order_id = (str(uuid.uuid4()) for _ in range(3))
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "Test", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description,"
        "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,'in_progress',1,?,?,?)",
        (work_order_id, project_id, milestone_id, "Test WO", "d", wo_type, NOW, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, description, acceptance_criteria,"
        "  status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?, 'complete', ?, ?)",
        (str(uuid.uuid4()), work_order_id, project_id, "T1", "do", "SQL-CHECK: SELECT 1", NOW, NOW),
    )
    # A CLOSED sibling and a second task: the structural_invariants close gate refuses a
    # work order that finishes with one task or whose milestone has no sibling. This
    # fixture is about grader rule 7, so it satisfies that gate rather than failing for a
    # reason it is not testing.
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, description, acceptance_criteria,"
        "  status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?, 'complete', ?, ?)",
        (str(uuid.uuid4()), work_order_id, project_id, "T2", "do", "SQL-CHECK: SELECT 1", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description,"
        "  work_order_type, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,'closed',?,?)",
        (str(uuid.uuid4()), project_id, milestone_id, "Earlier WO", "d", wo_type, NOW, NOW),
    )
    conn.commit()
    conn.close()
    return project_id, milestone_id, work_order_id


def _graders_with_quality_issue(category: str, detail: str) -> dict:
    return {
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
        "quality": {
            "quality_passed": False,
            "quality_score": 0.9,
            "issues": [
                {
                    "category": category,
                    "file": "core/x.py",
                    "line": "42",
                    "detail": detail,
                    "severity": "error",
                }
            ],
        },
    }


def _run_verify(db_path: Path, tmp_path: Path, work_order_id: str, graders: dict) -> dict:
    with _patch_db(db_path):
        with patch("core.work_orders.verify_graders._run_graders_parallel", return_value=graders):
            with patch(
                "core.work_orders.verify_git._collect_git_commits",
                return_value="diff --git a/core/x.py b/core/x.py\n+persist(key_a); read(key_b)",
            ):
                from core.work_orders.verify import verify_work_order

                return verify_work_order(
                    work_order_id=work_order_id,
                    source_root=REPO_ROOT,
                    dream_studio_home=tmp_path,
                    planning_root=tmp_path / "planning",
                )


def test_key_mismatch_diff_flagged(tmp_path):
    """A rule-7 finding (persist-key vs read-key mismatch) surfaces in the verdict."""
    db_path = _make_db(tmp_path)
    _, _, work_order_id = _seed_wo(db_path)
    result = _run_verify(
        db_path,
        tmp_path,
        work_order_id,
        _graders_with_quality_issue(
            "DURABLE_STATE_ADVERSARIAL",
            "persists under key_a but the read path looks up key_b; no crash/race test",
        ),
    )
    assert result["ok"] is True
    issues = result["quality"]["issues"]
    assert issues and issues[0]["category"] == "DURABLE_STATE_ADVERSARIAL"
    assert issues[0]["severity"] == "error"


def test_config_proxy_guard_flagged(tmp_path):
    """A rule-8 finding (config-as-proxy guard) surfaces in the verdict."""
    db_path = _make_db(tmp_path)
    _, _, work_order_id = _seed_wo(db_path)
    result = _run_verify(
        db_path,
        tmp_path,
        work_order_id,
        _graders_with_quality_issue(
            "CONFIG_AS_PROXY",
            "dev_link gated on FULCRUM_BASE_URL while BIND_HOST controls exposure",
        ),
    )
    assert result["ok"] is True
    issues = result["quality"]["issues"]
    assert issues and issues[0]["category"] == "CONFIG_AS_PROXY"


# ── default-on verify at close ──────────────────────────────────────────────────


def _fake_passing_verify(tmp_path: Path, db_path: Path):
    """A stand-in verify that persists a real (enveloped) passing verdict
    into the TEST authority DB (the db close's gates read)."""

    def _fake(**kwargs):
        from core.work_orders.verify_persist import _persist_review_verdict

        _persist_review_verdict(
            kwargs["work_order_id"],
            {"work_order_id": kwargs["work_order_id"], "passed": True, "gaps": []},
            planning_root=kwargs.get("planning_root") or tmp_path / "planning",
            db_path=db_path,
            project_root=None,
        )
        return {"ok": True, "passed": True, "spawned_work_orders": [], "gaps": []}

    return _fake


def test_close_autoruns_verify_when_no_verdict(tmp_path):
    """A WO whose TYPE post-gate does NOT name independent_review still gets
    verify at close (default-on) — the audit found such WOs closed with zero
    review."""
    db_path = _make_db(tmp_path)
    _, _, work_order_id = _seed_wo(db_path, wo_type="cleanup")

    calls: list[str] = []
    fake = _fake_passing_verify(tmp_path, db_path)

    def _recording_fake(**kwargs):
        calls.append(kwargs["work_order_id"])
        return fake(**kwargs)

    with _patch_db(db_path):
        with patch("core.work_orders.verify.verify_work_order", side_effect=_recording_fake):
            from core.work_orders.close import close_work_order

            result = close_work_order(
                work_order_id=work_order_id,
                source_root=tmp_path,
                dream_studio_home=tmp_path,
                planning_root=tmp_path / "planning",
            )
    assert calls == [work_order_id], "close must auto-run verify for a non-IR-typed WO"
    assert result["ok"] is True, result
    assert result["status"] == "closed"


def test_skip_verify_is_recorded_not_silent(tmp_path):
    """skip_verify still works — and leaves a gate.bypassed mark."""
    db_path = _make_db(tmp_path)
    _, _, work_order_id = _seed_wo(db_path, wo_type="cleanup")

    calls: list[str] = []
    recorded: list[tuple] = []
    with _patch_db(db_path):
        with patch(
            "core.work_orders.verify.verify_work_order",
            side_effect=lambda **kw: calls.append(kw["work_order_id"]),
        ):
            with patch(
                "core.gates.bypass_event.record_gate_bypass",
                side_effect=lambda g, r, extra=None: recorded.append((g, extra)),
            ):
                from core.work_orders.close import close_work_order

                result = close_work_order(
                    work_order_id=work_order_id,
                    skip_verify=True,
                    source_root=tmp_path,
                    dream_studio_home=tmp_path,
                    planning_root=tmp_path / "planning",
                )
    assert calls == [], "skip_verify must suppress the inline verify"
    assert result["ok"] is True, result
    assert recorded and recorded[0][0] == "independent_review"
    assert recorded[0][1] == {"work_order_id": work_order_id}


def test_documentation_type_exempt(tmp_path):
    """documentation WOs (no code) close without verify and without a bypass mark."""
    db_path = _make_db(tmp_path)
    _, _, work_order_id = _seed_wo(db_path, wo_type="documentation")

    calls: list[str] = []
    with _patch_db(db_path):
        with patch(
            "core.work_orders.verify.verify_work_order",
            side_effect=lambda **kw: calls.append(kw["work_order_id"]),
        ):
            from core.work_orders.close import close_work_order

            result = close_work_order(
                work_order_id=work_order_id,
                source_root=tmp_path,
                dream_studio_home=tmp_path,
                planning_root=tmp_path / "planning",
            )
    assert calls == []
    assert result["ok"] is True, result
