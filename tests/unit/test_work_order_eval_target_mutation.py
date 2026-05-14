from __future__ import annotations

from pathlib import Path


def _work_order(target_path: Path) -> dict:
    return {
        "work_order_id": "wo-target-eval-001",
        "target_path": str(target_path),
        "approval_mode": "observe_only",
    }


def _approval() -> dict:
    return {
        "approval_status": "approved",
        "approved_by": "operator",
        "approved_at": "2026-05-11T00:00:00Z",
        "approval_mode": "approval_required",
        "approved_files": ["src/app/a.ts"],
        "forbidden_files": ["src/app/forbidden.ts"],
        "approval_scope": "target mutation test",
    }


def test_target_mutation_eval_passes_for_identical_explicit_snapshots(tmp_path) -> None:
    from core.work_orders.evals import create_target_repo_mutation_eval

    target = tmp_path / "target"
    target.mkdir()
    snapshot = {"README.md": "same"}

    artifact, _ = create_target_repo_mutation_eval(
        work_order=_work_order(target),
        before_snapshot=snapshot,
        after_snapshot=dict(snapshot),
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "pass"


def test_target_mutation_eval_fails_for_changed_explicit_snapshots(tmp_path) -> None:
    from core.work_orders.evals import create_target_repo_mutation_eval

    target = tmp_path / "target"
    target.mkdir()

    artifact, _ = create_target_repo_mutation_eval(
        work_order=_work_order(target),
        before_snapshot={"README.md": "before"},
        after_snapshot={"README.md": "after"},
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "fail"
    assert "README.md" in artifact["observed_behavior"]


def test_target_mutation_eval_is_incomplete_without_snapshots(tmp_path) -> None:
    from core.work_orders.evals import create_target_repo_mutation_eval

    target = tmp_path / "target"
    target.mkdir()

    artifact, _ = create_target_repo_mutation_eval(
        work_order=_work_order(target),
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "incomplete"
    assert "evidence_unavailable" in artifact["observed_behavior"]


def test_target_mutation_eval_passes_for_approved_mutation_with_changed_file_evidence(
    tmp_path,
) -> None:
    from core.work_orders.evals import create_target_repo_mutation_eval

    target = tmp_path / "target"
    target.mkdir()
    work_order = _work_order(target)
    work_order["approval_mode"] = "approval_required"

    artifact, _ = create_target_repo_mutation_eval(
        work_order=work_order,
        approval_evidence=_approval(),
        changed_files=["src/app/a.ts"],
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "pass"


def test_target_mutation_eval_fails_for_approved_mode_unapproved_file(tmp_path) -> None:
    from core.work_orders.evals import create_target_repo_mutation_eval

    target = tmp_path / "target"
    target.mkdir()
    work_order = _work_order(target)
    work_order["approval_mode"] = "approval_required"

    artifact, _ = create_target_repo_mutation_eval(
        work_order=work_order,
        approval_evidence=_approval(),
        changed_files=["src/app/unapproved.ts"],
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "fail"
    assert "unapproved file changed" in artifact["observed_behavior"]


def test_target_mutation_eval_is_incomplete_for_approved_mode_without_changed_file_evidence(
    tmp_path,
) -> None:
    from core.work_orders.evals import create_target_repo_mutation_eval

    target = tmp_path / "target"
    target.mkdir()
    work_order = _work_order(target)
    work_order["approval_mode"] = "approval_required"

    artifact, _ = create_target_repo_mutation_eval(
        work_order=work_order,
        approval_evidence=_approval(),
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "incomplete"
    assert "changed-file evidence unavailable" in artifact["observed_behavior"]
