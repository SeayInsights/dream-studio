"""C2 — Gate evals (narrowed scope).

Tests _run_gate_check() directly for three gates not already covered by
tests/unit/test_work_order_gates.py or test_critique_gate.py:
  - api_contract_exists  (pass + fail)
  - spec_approved        (pass + fail)
  - all_tests_pass       (pass + fail)

These call run_gate_check() from core.work_orders.close — no CLI, no DB
(conn is unused for file-based gates).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.work_orders.close import run_gate_check

WO_ID = "gate-eval-wo-0001-0000-0000-0000-000000000001"
PROJECT_ID = "gate-eval-proj-0001-0000-0000-0000-000000000001"


@pytest.fixture
def wo_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".planning" / "work-orders" / WO_ID
    d.mkdir(parents=True)
    return d


def _check(gate: str, planning_root: Path) -> tuple[bool, str]:
    return run_gate_check(
        gate,
        planning_root=planning_root,
        work_order_id=WO_ID,
        project_id=PROJECT_ID,
        conn=None,
    )


# ── api_contract_exists ───────────────────────────────────────────────────────


def test_api_contract_exists_pass(wo_dir: Path, tmp_path: Path) -> None:
    (wo_dir / "api-contract.md").write_text("# API Contract\n", encoding="utf-8")
    passed, reason = _check("api_contract_exists", tmp_path / ".planning")
    assert passed is True
    assert reason == ""


def test_api_contract_exists_fail(wo_dir: Path, tmp_path: Path) -> None:
    passed, reason = _check("api_contract_exists", tmp_path / ".planning")
    assert passed is False
    assert "api_contract_exists" in reason
    assert "api-contract.md" in reason


# ── spec_approved ─────────────────────────────────────────────────────────────


def test_spec_approved_pass(wo_dir: Path, tmp_path: Path) -> None:
    (wo_dir / "spec.md").write_text("# Spec\n## Status: approved\n", encoding="utf-8")
    passed, reason = _check("spec_approved", tmp_path / ".planning")
    assert passed is True
    assert reason == ""


def test_spec_approved_fail(wo_dir: Path, tmp_path: Path) -> None:
    passed, reason = _check("spec_approved", tmp_path / ".planning")
    assert passed is False
    assert "spec_approved" in reason
    assert "spec.md" in reason


# ── all_tests_pass ────────────────────────────────────────────────────────────


def test_all_tests_pass_pass(wo_dir: Path, tmp_path: Path) -> None:
    (wo_dir / "test-results.md").write_text("All checks PASSED\n", encoding="utf-8")
    passed, reason = _check("all_tests_pass", tmp_path / ".planning")
    assert passed is True
    assert reason == ""


def test_all_tests_pass_fail_missing_file(wo_dir: Path, tmp_path: Path) -> None:
    passed, reason = _check("all_tests_pass", tmp_path / ".planning")
    assert passed is False
    assert "all_tests_pass" in reason
    assert "test-results.md" in reason


def test_all_tests_pass_fail_no_passed_marker(wo_dir: Path, tmp_path: Path) -> None:
    (wo_dir / "test-results.md").write_text("3 failed, 0 succeeded\n", encoding="utf-8")
    passed, reason = _check("all_tests_pass", tmp_path / ".planning")
    assert passed is False
    assert "all_tests_pass" in reason


# ── independent_review_passed ─────────────────────────────────────────────────


def test_independent_review_passed_pass(wo_dir: Path, tmp_path: Path) -> None:
    (wo_dir / "independent-review.md").write_text(
        "# Independent Review\n## Overall\nVERDICT: PASS\n", encoding="utf-8"
    )
    passed, reason = _check("independent_review_passed", tmp_path / ".planning")
    assert passed is True
    assert reason == ""


def test_independent_review_passed_fail_missing(wo_dir: Path, tmp_path: Path) -> None:
    passed, reason = _check("independent_review_passed", tmp_path / ".planning")
    assert passed is False
    assert "independent_review_passed" in reason
    assert "independent-review.md" in reason


def test_independent_review_passed_fail_verdict(wo_dir: Path, tmp_path: Path) -> None:
    (wo_dir / "independent-review.md").write_text(
        "# Independent Review\n## Overall\nVERDICT: FAIL\nTask 2 not evidenced.\n",
        encoding="utf-8",
    )
    passed, reason = _check("independent_review_passed", tmp_path / ".planning")
    assert passed is False
    assert "VERDICT: PASS" in reason
