from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _work_order(target_path: Path, *, work_order_id: str = "wo-render-001") -> dict:
    return {
        "work_order_id": work_order_id,
        "project_name": "Render Test",
        "target_path": str(target_path),
        "objective": "Render observe-only instructions without changing files.",
        "approval_mode": "observe_only",
        "risk_level": "medium",
        "scope": {"include": ["README.md"], "exclude": ["secrets"]},
        "allowed_skills": ["ds-core"],
        "allowed_agents": ["audit-agent"],
        "workflow": ["load Work Order", "render packet", "stop"],
        "forbidden_actions": [
            "no edits, writes, patches, formats, or moves",
            "no commits, staging, or pushes",
            "no deletes or removes",
            "no schema changes",
            "no dependency or package changes",
            "no external actions, network calls, publishing, deploys, or cloud actions",
            "no target repo mutation",
        ],
        "validation_commands": [
            "python -m pytest tests/unit/test_product_readiness_baseline.py -q"
        ],
        "expected_outputs": ["rendered packet", "render eval artifacts"],
        "stop_conditions": ["target files changed"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "validated",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def _snapshot(path: Path) -> dict[str, str]:
    return {
        str(item.relative_to(path)): item.read_text(encoding="utf-8")
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_importing_renderer_and_eval_modules_has_no_fake_home_side_effects(
    tmp_path, monkeypatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.delenv("DREAM_STUDIO_WORK_ORDER_ROOT", raising=False)

    importlib.import_module("core.work_orders.renderers")
    importlib.import_module("core.work_orders.evals")
    importlib.import_module("interfaces.cli.ds_work_order")

    assert not (fake_home / ".dream-studio").exists()


@pytest.mark.parametrize("target", ["codex", "claude"])
def test_render_writes_packet_and_evals_under_storage_only(tmp_path, target: str) -> None:
    from core.work_orders.packet_store import get_packet_artifact, list_packet_artifacts
    from core.work_orders.renderers import render_work_order
    from core.work_orders.storage import load_work_order, save_work_order

    target_repo = tmp_path / "target"
    target_repo.mkdir()
    (target_repo / "README.md").write_text("before\n", encoding="utf-8")
    before = _snapshot(target_repo)
    storage_root = tmp_path / ".dream-studio" / "meta" / "work-orders"
    save_work_order(_work_order(target_repo), storage_root=storage_root)

    result = render_work_order("wo-render-001", target=target, storage_root=storage_root)
    # WO-FILESDB-C5: the rendered packet lives in the packet store (kind='packet',
    # instance_key=target), not a rendered/<target>.md disk file. packet_path is the
    # logical ref only.
    packet_path = Path(result["packet_path"])
    packet_text = get_packet_artifact(
        "wo-render-001", "packet", instance_key=target, storage_root=storage_root
    )
    assert packet_text is not None
    stored, _ = load_work_order("wo-render-001", storage_root=storage_root)

    assert packet_path == storage_root / "wo-render-001" / "rendered" / f"{target}.md"
    assert "Render Only: true" in packet_text
    assert "Render-Only Posture" in packet_text
    assert "Work Order ID: wo-render-001" in packet_text
    assert "Target Project Path:" in packet_text
    assert "Approval Mode: observe_only" in packet_text
    assert "Risk Level: medium" in packet_text
    assert "Scope Include" in packet_text
    assert "Allowed Skills" in packet_text
    assert "Forbidden Actions" in packet_text
    assert "Validation Commands" in packet_text
    assert "Stop Conditions" in packet_text
    assert "Expected Output" in packet_text
    assert "Do not edit" in packet_text
    assert "Do not delete" in packet_text
    assert "Do not commit" in packet_text
    assert "Do not change dependencies" in packet_text
    assert "Do not change schema" in packet_text
    assert stored["status"] == "rendered"
    # WO-FILESDB-C3: eval artifacts live in the packet store (kind='eval'), so there are
    # no on-disk eval files — eval_paths is empty and the two evals are in the store.
    assert result["eval_paths"] == []
    assert len(result["evals"]) == 2
    assert len(list_packet_artifacts("wo-render-001", "eval", storage_root=storage_root)) == 2
    assert _snapshot(target_repo) == before
    assert not (tmp_path / ".dream-studio" / "state" / "studio.db").exists()


def test_render_rejects_unsupported_target(tmp_path) -> None:
    from core.work_orders.models import WorkOrderError
    from core.work_orders.renderers import render_work_order
    from core.work_orders.storage import save_work_order

    target_repo = tmp_path / "target"
    target_repo.mkdir()
    storage_root = tmp_path / "store"
    save_work_order(_work_order(target_repo), storage_root=storage_root)

    with pytest.raises(WorkOrderError, match="Unsupported render target"):
        render_work_order("wo-render-001", target="chatgpt", storage_root=storage_root)


def test_render_rejects_invalid_work_order_without_packet(tmp_path) -> None:
    from core.work_orders.models import WorkOrderError
    from core.work_orders.renderers import render_work_order
    from core.work_orders.storage import save_work_order

    target_repo = tmp_path / "target"
    target_repo.mkdir()
    storage_root = tmp_path / "store"
    bad = _work_order(target_repo)
    bad["approval_mode"] = "invalid"
    save_work_order(bad, storage_root=storage_root)

    with pytest.raises(WorkOrderError, match="approval_mode"):
        render_work_order("wo-render-001", target="codex", storage_root=storage_root)

    assert not (storage_root / "wo-render-001" / "rendered").exists()
