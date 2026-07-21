from __future__ import annotations

import json
from pathlib import Path


def _work_order(target_path: Path, allowed_skills: list[str]) -> dict:
    return {
        "work_order_id": "wo-eval-skill-001",
        "project_name": "Eval Skill Test",
        "target_path": str(target_path),
        "objective": "Check skill identifier safety.",
        "approval_mode": "observe_only",
        "risk_level": "low",
        "scope": {"include": ["README.md"], "exclude": ["secrets"]},
        "allowed_skills": allowed_skills,
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
        "expected_outputs": ["skill eval"],
        "stop_conditions": ["unsafe identifier"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "validated",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def test_skill_identifier_safety_eval_passes_for_ds_slug(tmp_path) -> None:
    from core.work_orders.evals import create_skill_identifier_safety_eval
    from core.work_orders.packet_store import get_packet_artifact

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    artifact, path = create_skill_identifier_safety_eval(
        work_order=_work_order(target, ["ds-core", "ds-quality"]),
        storage_root=storage_root,
    )
    # WO-FILESDB-C3: eval lives in the packet store (kind='eval'), path is None.
    assert path is None
    stored = json.loads(
        get_packet_artifact(
            "wo-eval-skill-001",
            "eval",
            instance_key="skill_identifier_safety",
            storage_root=storage_root,
        )
    )

    assert artifact["eval_type"] == "skill_identifier_safety"
    assert artifact["pass_fail"] == "pass"
    assert stored["privacy_export_classification"] == "local_only"
    assert stored["score"] == 1


def test_skill_identifier_safety_eval_fails_for_legacy_forms(tmp_path) -> None:
    from core.work_orders.evals import create_skill_identifier_safety_eval
    from core.work_orders.packet_store import get_packet_artifact

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    legacy_product = "dream" "-studio" + ":core"
    legacy_ds = "d" "s" + ":core"
    _, path = create_skill_identifier_safety_eval(
        work_order=_work_order(target, [legacy_product, legacy_ds, "core"]),
        storage_root=storage_root,
    )
    assert path is None
    stored = json.loads(
        get_packet_artifact(
            "wo-eval-skill-001",
            "eval",
            instance_key="skill_identifier_safety",
            storage_root=storage_root,
        )
    )

    assert stored["pass_fail"] == "fail"
    assert stored["score"] == 0
    assert "Unsafe skill identifiers found" in stored["observed_behavior"]
    assert legacy_product in stored["observed_behavior"]
    assert legacy_ds in stored["observed_behavior"]
