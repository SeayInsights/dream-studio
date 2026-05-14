from __future__ import annotations

import importlib
import json
from pathlib import Path


def _work_order(target_path: Path) -> dict:
    return {
        "work_order_id": "wo-result-001",
        "project_name": "Result Test",
        "target_path": str(target_path),
        "objective": "Record observe-only result evidence.",
        "approval_mode": "observe_only",
        "risk_level": "low",
        "scope": {"include": ["README.md"], "exclude": ["secrets"]},
        "allowed_skills": ["ds-core"],
        "allowed_agents": [],
        "workflow": "observe-only",
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
        "expected_outputs": ["result artifact"],
        "stop_conditions": ["mutation"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "rendered",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def _result_text() -> str:
    return "\n".join(
        [
            "Summary: Observe-only evidence was recorded.",
            "Files inspected: README.md",
            "Files changed: none",
            "Commands: not run",
            "Forbidden actions: complied",
            "Target mutation: no",
            "Warnings: none",
            "Risks: none",
            "Next Work Order: Objective: render report review; Risk: low; Approval: observe_only; Non-goals: mutation; Validation: static checks.",
            "",
        ]
    )


def _snapshot(path: Path) -> dict[str, str]:
    return {
        str(item.relative_to(path)): item.read_text(encoding="utf-8")
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_importing_result_report_eval_modules_has_no_fake_home_side_effects(
    tmp_path, monkeypatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.delenv("DREAM_STUDIO_WORK_ORDER_ROOT", raising=False)

    importlib.import_module("core.work_orders.results")
    importlib.import_module("core.work_orders.reporting")
    importlib.import_module("core.work_orders.evals")
    importlib.import_module("interfaces.cli.ds_work_order")

    assert not (fake_home / ".dream-studio").exists()


def test_record_result_preserves_raw_text_and_creates_metadata_and_evals(tmp_path) -> None:
    from core.work_orders.results import record_result
    from core.work_orders.storage import load_work_order, save_work_order

    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("before\n", encoding="utf-8")
    before = _snapshot(target)
    storage_root = tmp_path / "store"
    save_work_order(_work_order(target), storage_root=storage_root)
    source = tmp_path / "result-source.md"
    source.write_text(_result_text(), encoding="utf-8")

    recorded = record_result("wo-result-001", source_path=source, storage_root=storage_root)
    raw_path = Path(recorded["result_path"])
    metadata_path = Path(recorded["metadata_path"])
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    stored, _ = load_work_order("wo-result-001", storage_root=storage_root)

    assert raw_path == storage_root / "wo-result-001" / "results" / "result.md"
    assert raw_path.read_text(encoding="utf-8") == _result_text()
    assert metadata["summary"] == "Observe-only evidence was recorded."
    assert metadata["raw_output_ref"] == str(raw_path)
    assert metadata["structured_findings"]["files_inspected"] == ["README.md"]
    assert metadata["structured_findings"]["files_changed"] == ["none"]
    assert metadata["next_work_order_recommendation"].startswith("Objective:")
    assert stored["status"] == "result_recorded"
    assert len(recorded["eval_paths"]) == 3
    assert (storage_root / "wo-result-001" / "evals" / "observe_only_compliance.json").is_file()
    assert (storage_root / "wo-result-001" / "evals" / "forbidden_action_compliance.json").is_file()
    assert (storage_root / "wo-result-001" / "evals" / "target_repo_mutation.json").is_file()
    mutation_eval = json.loads(
        (storage_root / "wo-result-001" / "evals" / "target_repo_mutation.json").read_text(
            encoding="utf-8"
        )
    )
    assert mutation_eval["pass_fail"] == "incomplete"
    assert _snapshot(target) == before
    assert not (tmp_path / ".dream-studio" / "state" / "studio.db").exists()


def test_record_result_requires_source_file(tmp_path) -> None:
    from core.work_orders.models import WorkOrderError
    from core.work_orders.results import record_result
    from core.work_orders.storage import save_work_order

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    save_work_order(_work_order(target), storage_root=storage_root)

    try:
        record_result(
            "wo-result-001", source_path=tmp_path / "missing.md", storage_root=storage_root
        )
    except WorkOrderError as exc:
        assert "Result source file not found" in str(exc)
    else:
        raise AssertionError("missing result source should fail")
