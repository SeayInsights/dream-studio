from __future__ import annotations

import json
from pathlib import Path


def _work_order(target_path: Path) -> dict:
    return {
        "work_order_id": "wo-eval-render-001",
        "project_name": "Eval Render Test",
        "target_path": str(target_path),
        "objective": "Render complete packet evidence.",
        "approval_mode": "observe_only",
        "risk_level": "low",
        "scope": {"include": ["README.md"], "exclude": ["secrets"]},
        "allowed_skills": ["ds-core"],
        "allowed_agents": [],
        "workflow": "render-only",
        "forbidden_actions": [
            "no edits, writes, patches, formats, or moves",
            "no commits, staging, or pushes",
            "no deletes or removes",
            "no schema changes",
            "no dependency or package changes",
            "no external actions, network calls, publishing, deploys, or cloud actions",
            "no target repo mutation",
        ],
        "validation_commands": ["python -m pytest -q"],
        "expected_outputs": ["packet"],
        "stop_conditions": ["mutation"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "validated",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def test_render_creates_complete_eval_artifact_with_required_fields_for_codex_and_claude(
    tmp_path,
) -> None:
    from core.work_orders.renderers import render_work_order
    from core.work_orders.storage import save_work_order

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"

    required_fields = [
        "eval_id",
        "eval_type",
        "subject_type",
        "subject_id",
        "linked_work_order_id",
        "input_artifact",
        "expected_behavior",
        "observed_behavior",
        "score",
        "pass_fail",
        "evaluator",
        "evidence",
        "privacy_export_classification",
        "created_at",
    ]

    for render_target in ("codex", "claude"):
        work_order_id = f"wo-eval-render-{render_target}"
        save_work_order(
            _work_order(target) | {"work_order_id": work_order_id},
            storage_root=storage_root,
        )

        from core.work_orders.packet_store import get_packet_artifact

        render_work_order(work_order_id, target=render_target, storage_root=storage_root)
        # WO-FILESDB-C3: evals live in the packet store, not evals/*.json on disk.
        assert not (storage_root / work_order_id / "evals").exists()
        artifact = json.loads(
            get_packet_artifact(
                work_order_id,
                "eval",
                instance_key="work_order_render_completeness",
                storage_root=storage_root,
            )
        )
        packet_path = storage_root / work_order_id / "rendered" / f"{render_target}.md"
        packet_text = packet_path.read_text(encoding="utf-8")

        assert [field for field in required_fields if field not in artifact] == []
        assert "Render-Only Posture" in packet_text
        assert artifact["eval_type"] == "work_order_render_completeness"
        assert artifact["subject_type"] == "work_order"
        assert artifact["linked_work_order_id"] == work_order_id
        assert artifact["pass_fail"] == "pass"
        assert artifact["evaluator"] == "deterministic"
        assert artifact["privacy_export_classification"] == "local_only"
        assert str(storage_root) in artifact["input_artifact"]


def test_render_completeness_eval_fails_with_explicit_missing_evidence(tmp_path) -> None:
    from core.work_orders.evals import create_render_completeness_eval

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    packet_path = storage_root / "wo-eval-render-001" / "rendered" / "codex.md"
    from core.work_orders.packet_store import get_packet_artifact

    artifact, path = create_render_completeness_eval(
        work_order=_work_order(target),
        target="codex",
        packet_path=packet_path,
        packet_text="incomplete",
        storage_root=storage_root,
    )
    # WO-FILESDB-C3: stored in the packet store (path is None, no disk file).
    assert path is None
    stored = json.loads(
        get_packet_artifact(
            "wo-eval-render-001",
            "eval",
            instance_key="work_order_render_completeness",
            storage_root=storage_root,
        )
    )

    assert artifact["pass_fail"] == "fail"
    assert stored["pass_fail"] == "fail"
    assert "missing evidence" in stored["observed_behavior"]
    assert "Work Order ID" in stored["observed_behavior"]
