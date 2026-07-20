"""WO-FILESDB-C1: the `ds work-order artifact` / `packet` read-surface commands.

Exercises the two authority-backed CLI handlers directly (no subprocess):
`_work_order_artifact` prints a stored artifact from
``business_work_order_artifacts``; `_work_order_packet` renders a WO execution
packet on demand and prints it — with NO ``rendered/<target>.md`` disk write.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.work_orders.artifacts import set_wo_artifact
from core.work_orders.storage import save_work_order
from interfaces.cli.commands import work_order as wo_cli

REPO_ROOT = Path(__file__).resolve().parents[2]
_MIG_DIR = REPO_ROOT / "core" / "event_store" / "migrations"
_MIG_144 = _MIG_DIR / "144_wo_artifacts.sql"
_MIG_152 = _MIG_DIR / "152_wo_artifacts_instance_key.sql"


def _db_with_table(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_MIG_144.read_text(encoding="utf-8"))
    conn.executescript(_MIG_152.read_text(encoding="utf-8"))
    conn.close()
    return db


def _point_cli_at_db(monkeypatch, db: Path) -> None:
    """Make the artifact handler resolve to *db* regardless of source_root.

    The handler imports ``resolve_installed_runtime_paths`` locally from
    ``core.installed_runtime``, so patch it at the source module.
    """

    class _Paths:
        sqlite_path = db

    monkeypatch.setattr(
        "core.installed_runtime.resolve_installed_runtime_paths", lambda **_: _Paths()
    )


def _valid_work_order(target_path: Path, *, work_order_id: str) -> dict:
    return {
        "work_order_id": work_order_id,
        "project_name": "CLI Test",
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
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def test_artifact_command_prints_stored_content(tmp_path, capsys, monkeypatch):
    db = _db_with_table(tmp_path)
    _point_cli_at_db(monkeypatch, db)
    set_wo_artifact("wo-cli", "review_verdict", '{"passed": true}', db_path=db)

    rc = wo_cli._work_order_artifact(
        work_order_id="wo-cli",
        kind="review_verdict",
        instance_key="",
        source_root=tmp_path,
        dream_studio_home=None,
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert '{"passed": true}' in out


def test_artifact_command_multi_instance(tmp_path, capsys, monkeypatch):
    db = _db_with_table(tmp_path)
    _point_cli_at_db(monkeypatch, db)
    set_wo_artifact(
        "wo-e", "eval", '{"stage":"render"}', instance_key="render_completeness", db_path=db
    )

    rc = wo_cli._work_order_artifact(
        work_order_id="wo-e",
        kind="eval",
        instance_key="render_completeness",
        source_root=tmp_path,
        dream_studio_home=None,
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert '{"stage":"render"}' in out


def test_artifact_command_unknown_kind_errors(tmp_path, capsys, monkeypatch):
    db = _db_with_table(tmp_path)
    _point_cli_at_db(monkeypatch, db)
    rc = wo_cli._work_order_artifact(
        work_order_id="wo-cli",
        kind="bogus_kind",
        instance_key="",
        source_root=tmp_path,
        dream_studio_home=None,
    )
    assert rc == 1
    assert "Unknown artifact kind" in capsys.readouterr().err


def test_artifact_command_missing_returns_1(tmp_path, capsys, monkeypatch):
    db = _db_with_table(tmp_path)
    _point_cli_at_db(monkeypatch, db)
    rc = wo_cli._work_order_artifact(
        work_order_id="wo-absent",
        kind="api_contract",
        instance_key="",
        source_root=tmp_path,
        dream_studio_home=None,
    )
    assert rc == 1
    assert "No api_contract artifact" in capsys.readouterr().err


def test_packet_command_renders_without_disk_write(tmp_path, capsys):
    storage_root = tmp_path / "wo-store"
    target = tmp_path / "proj"
    target.mkdir()
    save_work_order(_valid_work_order(target, work_order_id="wo-pkt"), storage_root=storage_root)

    rc = wo_cli._work_order_packet(
        work_order_id="wo-pkt",
        target="claude",
        storage_root=storage_root,
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "Work Order Execution Packet (claude)" in out
    # Derive-on-demand: no rendered/<target>.md cache is written to disk.
    assert not (storage_root / "wo-pkt" / "rendered").exists()


def test_packet_command_not_found_returns_1(tmp_path, capsys):
    rc = wo_cli._work_order_packet(
        work_order_id="nope",
        target="claude",
        storage_root=tmp_path / "empty-store",
    )
    assert rc == 1
    assert "not found" in capsys.readouterr().err.lower()
