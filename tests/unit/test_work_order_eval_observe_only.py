from __future__ import annotations

import json
from pathlib import Path


def _work_order(target_path: Path) -> dict:
    return {
        "work_order_id": "wo-observe-eval-001",
        "target_path": str(target_path),
        "approval_mode": "observe_only",
    }


def test_observe_only_eval_passes_with_explicit_clean_evidence(tmp_path) -> None:
    from core.work_orders.evals import create_observe_only_compliance_eval
    from core.work_orders.packet_store import get_packet_artifact

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    artifact, path = create_observe_only_compliance_eval(
        work_order=_work_order(target),
        result_text="Files changed: none\nTarget mutation: no\n",
        result_metadata={"raw_output_ref": "result.md"},
        storage_root=storage_root,
    )
    # WO-FILESDB-C3: eval lives in the packet store (kind='eval'), path is None.
    assert path is None
    stored = json.loads(
        get_packet_artifact(
            "wo-observe-eval-001",
            "eval",
            instance_key="observe_only_compliance",
            storage_root=storage_root,
        )
    )

    assert artifact["pass_fail"] == "pass"
    assert stored["privacy_export_classification"] == "local_only"


def test_observe_only_eval_fails_with_explicit_mutation_evidence(tmp_path) -> None:
    from core.work_orders.evals import create_observe_only_compliance_eval

    target = tmp_path / "target"
    target.mkdir()
    artifact, _ = create_observe_only_compliance_eval(
        work_order=_work_order(target),
        result_text="Files changed: src/app.py\n",
        result_metadata={"raw_output_ref": "result.md"},
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "fail"


def test_observe_only_eval_is_incomplete_without_explicit_evidence(tmp_path) -> None:
    from core.work_orders.evals import create_observe_only_compliance_eval

    target = tmp_path / "target"
    target.mkdir()
    artifact, _ = create_observe_only_compliance_eval(
        work_order=_work_order(target),
        result_text="",
        result_metadata=None,
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "incomplete"


def test_approval_required_work_order_does_not_get_misleading_observe_only_failure(
    tmp_path,
) -> None:
    from core.work_orders.evals import create_observe_only_compliance_eval

    target = tmp_path / "target"
    target.mkdir()
    work_order = _work_order(target)
    work_order["approval_mode"] = "approval_required"

    artifact, _ = create_observe_only_compliance_eval(
        work_order=work_order,
        result_text="Files changed: src/app/a.ts\n",
        result_metadata={"raw_output_ref": "result.md"},
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "incomplete"
    assert "approved_mutation_compliance is the applicable eval" in artifact["observed_behavior"]
