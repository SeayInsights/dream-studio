from __future__ import annotations

from pathlib import Path


def _work_order(target_path: Path) -> dict:
    return {"work_order_id": "wo-next-eval-001", "target_path": str(target_path)}


def test_next_recommendation_eval_passes_for_bounded_recommendation(tmp_path) -> None:
    from core.work_orders.evals import create_next_work_order_recommendation_eval

    target = tmp_path / "target"
    target.mkdir()
    recommendation = (
        "Objective: inspect report gaps; Risk: low; Approval: observe_only; "
        "Non-goals: mutation; Validation: static checks."
    )

    artifact, _ = create_next_work_order_recommendation_eval(
        work_order=_work_order(target),
        recommendation=recommendation,
        evidence_ref="result.json",
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "pass"


def test_next_recommendation_eval_is_incomplete_when_missing(tmp_path) -> None:
    from core.work_orders.evals import create_next_work_order_recommendation_eval

    target = tmp_path / "target"
    target.mkdir()

    artifact, _ = create_next_work_order_recommendation_eval(
        work_order=_work_order(target),
        recommendation="unavailable",
        evidence_ref="report.md",
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "incomplete"


def test_next_recommendation_eval_fails_for_unbounded_recommendation(tmp_path) -> None:
    from core.work_orders.evals import create_next_work_order_recommendation_eval

    target = tmp_path / "target"
    target.mkdir()

    artifact, _ = create_next_work_order_recommendation_eval(
        work_order=_work_order(target),
        recommendation="autonomous mutate everything without approval",
        evidence_ref="result.json",
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "fail"
