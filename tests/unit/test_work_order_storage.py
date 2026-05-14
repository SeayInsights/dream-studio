from __future__ import annotations

import importlib
import json
from pathlib import Path

import yaml


def _work_order(target_path: Path, *, work_order_id: str = "wo-001") -> dict:
    return {
        "work_order_id": work_order_id,
        "project_name": "Dream Studio Test",
        "target_path": str(target_path),
        "objective": "Observe target readiness without changing files.",
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
        "expected_outputs": ["status evidence"],
        "stop_conditions": ["target changes"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "draft",
        "privacy_export_classification": "local_only",
    }


def test_importing_work_order_modules_has_no_fake_home_side_effects(tmp_path, monkeypatch) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.delenv("DREAM_STUDIO_WORK_ORDER_ROOT", raising=False)

    importlib.import_module("core.work_orders.models")
    importlib.import_module("core.work_orders.storage")
    importlib.import_module("core.work_orders.validation")
    importlib.import_module("interfaces.cli.ds_work_order")

    assert not (fake_home / ".dream-studio").exists()


def test_default_storage_root_is_fake_home_safe_and_not_created(tmp_path, monkeypatch) -> None:
    from core.work_orders.storage import default_storage_root

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.delenv("DREAM_STUDIO_WORK_ORDER_ROOT", raising=False)

    root = default_storage_root()

    assert root == fake_home / ".dream-studio" / "meta" / "work-orders"
    assert not root.exists()
    assert not (fake_home / ".dream-studio" / "state" / "studio.db").exists()


def test_save_and_load_work_order_writes_only_under_storage_root(tmp_path) -> None:
    from core.work_orders.storage import load_work_order, save_work_order, status_summary

    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("before\n", encoding="utf-8")
    storage_root = tmp_path / ".dream-studio" / "meta" / "work-orders"

    saved_path = save_work_order(_work_order(target), storage_root=storage_root)
    loaded, loaded_path = load_work_order("wo-001", storage_root=storage_root)
    summary = status_summary("wo-001", storage_root=storage_root)

    assert saved_path == storage_root / "wo-001" / "work_order.json"
    assert loaded_path == saved_path
    assert loaded["storage_class"] == "file_backed"
    assert summary["status"] == "draft"
    assert summary["next_required_action"] == "run validate"
    assert (target / "README.md").read_text(encoding="utf-8") == "before\n"
    assert not (tmp_path / ".dream-studio" / "state" / "studio.db").exists()


def test_json_and_yaml_sources_load_with_file_backed_default(tmp_path) -> None:
    from core.work_orders.models import load_work_order_file

    target = tmp_path / "target"
    target.mkdir()
    data = _work_order(target)
    json_path = tmp_path / "work_order.json"
    yaml_path = tmp_path / "work_order.yaml"
    json_path.write_text(json.dumps(data), encoding="utf-8")
    yaml_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    from_json = load_work_order_file(json_path)
    from_yaml = load_work_order_file(yaml_path)

    assert from_json["storage_class"] == "file_backed"
    assert from_yaml["storage_class"] == "file_backed"
    assert from_yaml["work_order_id"] == "wo-001"
