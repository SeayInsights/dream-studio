from __future__ import annotations

from pathlib import Path


def _work_order(target_path: Path) -> dict:
    return {
        "work_order_id": "wo-forbidden-eval-001",
        "target_path": str(target_path),
        "forbidden_actions": ["no commits", "no deletes"],
    }


def test_forbidden_action_eval_passes_with_explicit_compliance(tmp_path) -> None:
    from core.work_orders.evals import create_forbidden_action_compliance_eval

    target = tmp_path / "target"
    target.mkdir()
    artifact, _ = create_forbidden_action_compliance_eval(
        work_order=_work_order(target),
        result_text="Forbidden actions: complied\n",
        result_metadata={"raw_output_ref": "result.md"},
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "pass"


def test_forbidden_action_eval_fails_with_explicit_violation(tmp_path) -> None:
    from core.work_orders.evals import create_forbidden_action_compliance_eval

    target = tmp_path / "target"
    target.mkdir()
    artifact, _ = create_forbidden_action_compliance_eval(
        work_order=_work_order(target),
        result_text="Forbidden action: violated by committed change\n",
        result_metadata={"raw_output_ref": "result.md"},
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "fail"


def test_forbidden_action_eval_is_incomplete_without_action_evidence(tmp_path) -> None:
    from core.work_orders.evals import create_forbidden_action_compliance_eval

    target = tmp_path / "target"
    target.mkdir()
    artifact, _ = create_forbidden_action_compliance_eval(
        work_order=_work_order(target),
        result_text="Summary: no action detail\n",
        result_metadata={"raw_output_ref": "result.md"},
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "incomplete"
