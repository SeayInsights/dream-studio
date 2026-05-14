from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "interfaces" / "cli" / "ds_work_order.py"


def _work_order(target_path: Path, *, work_order_id: str = "wo-decision-cli-001") -> dict:
    return {
        "work_order_id": work_order_id,
        "project_name": "Decision CLI Test",
        "target_path": str(target_path),
        "objective": "Create operator decision artifacts.",
        "approval_mode": "observe_only",
        "risk_level": "medium",
        "scope": {"include": ["README.md"], "exclude": ["secrets"]},
        "allowed_skills": ["ds-core"],
        "allowed_agents": [],
        "workflow": "decision cli",
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
        "expected_outputs": ["decision artifacts"],
        "stop_conditions": ["missing decision"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "draft",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def _env(fake_home: Path, storage_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["USERPROFILE"] = str(fake_home)
    env["DREAM_STUDIO_WORK_ORDER_ROOT"] = str(storage_root)
    return env


def _run(args: list[str], *, fake_home: Path, storage_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=str(REPO_ROOT),
        env=_env(fake_home, storage_root),
        capture_output=True,
        text=True,
        timeout=30,
    )


def _snapshot(path: Path) -> dict[str, str]:
    return {
        str(item.relative_to(path)): item.read_text(encoding="utf-8")
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_decision_cli_creates_shows_and_records_decision(tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("before\n", encoding="utf-8")
    before = _snapshot(target)
    storage_root = fake_home / ".dream-studio" / "meta" / "work-orders"
    source = tmp_path / "work_order.yaml"
    source.write_text(yaml.safe_dump(_work_order(target)), encoding="utf-8")

    create = _run(
        ["create", "--from-file", str(source)], fake_home=fake_home, storage_root=storage_root
    )
    request = _run(
        [
            "request-decision",
            "--id",
            "wo-decision-cli-001",
            "--phase-type",
            "push_planning",
            "--question",
            "Choose push path.",
            "--recommended",
            "RUN_BROADER_VALIDATION_FIRST",
        ],
        fake_home=fake_home,
        storage_root=storage_root,
    )
    show_pending = _run(
        ["decision-request", "--id", "wo-decision-cli-001"],
        fake_home=fake_home,
        storage_root=storage_root,
    )
    decide = _run(
        [
            "decide",
            "--id",
            "wo-decision-cli-001",
            "--decision",
            "RUN_BROADER_VALIDATION_FIRST",
            "--reason",
            "Broader validation should run first.",
            "--decided-by",
            "operator",
        ],
        fake_home=fake_home,
        storage_root=storage_root,
    )
    show_decided = _run(
        ["decision-request", "--id", "wo-decision-cli-001"],
        fake_home=fake_home,
        storage_root=storage_root,
    )

    assert create.returncode == 0, create.stderr
    assert request.returncode == 0, request.stderr
    assert show_pending.returncode == 0, show_pending.stderr
    assert decide.returncode == 0, decide.stderr
    assert show_decided.returncode == 0, show_decided.stderr
    assert "decision_request_created: wo-decision-cli-001" in request.stdout
    assert "decision_status: pending_operator_decision" in show_pending.stdout
    assert "operator_decision_recorded: wo-decision-cli-001" in decide.stdout
    assert "decision_status: decided" in show_decided.stdout
    assert "decision: RUN_BROADER_VALIDATION_FIRST" in show_decided.stdout
    assert (storage_root / "wo-decision-cli-001" / "decisions" / "request.json").is_file()
    assert (storage_root / "wo-decision-cli-001" / "decisions" / "operator_decision.json").is_file()
    assert _snapshot(target) == before
    assert not (fake_home / ".dream-studio" / "state" / "studio.db").exists()


def test_decision_cli_rejects_invalid_decision(tmp_path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    storage_root = fake_home / ".dream-studio" / "meta" / "work-orders"
    source = tmp_path / "work_order.yaml"
    source.write_text(yaml.safe_dump(_work_order(target)), encoding="utf-8")

    assert (
        _run(
            ["create", "--from-file", str(source)], fake_home=fake_home, storage_root=storage_root
        ).returncode
        == 0
    )
    assert (
        _run(
            [
                "request-decision",
                "--id",
                "wo-decision-cli-001",
                "--phase-type",
                "push_planning",
                "--question",
                "Choose push path.",
                "--recommended",
                "HOLD",
            ],
            fake_home=fake_home,
            storage_root=storage_root,
        ).returncode
        == 0
    )
    invalid = _run(
        [
            "decide",
            "--id",
            "wo-decision-cli-001",
            "--decision",
            "PUSH_NOW",
            "--reason",
            "invalid",
            "--decided-by",
            "operator",
        ],
        fake_home=fake_home,
        storage_root=storage_root,
    )

    assert invalid.returncode == 2
    assert "not allowed" in invalid.stderr
