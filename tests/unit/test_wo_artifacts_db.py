"""WO-FILESDB-P1: WO ceremony artifacts live in business_work_order_artifacts.

Verifies the authority-backed artifact store, the close-gate repoint (DB-or-disk),
the disk fallback for the transition, and graceful degradation when the table is
absent (migration 144 unreleased on the live authority DB).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.work_orders.artifacts import get_wo_artifact, has_wo_artifact, set_wo_artifact
from core.work_orders.close import run_gate_check

REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = REPO_ROOT / "core" / "event_store" / "migrations" / "144_wo_artifacts.sql"


def _db_with_table(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_MIGRATION.read_text(encoding="utf-8"))  # exercises the real DDL
    conn.close()
    return db


def _db_without_table(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    sqlite3.connect(str(db)).close()
    return db


def test_review_verdict_roundtrip(tmp_path):
    db = _db_with_table(tmp_path)
    assert set_wo_artifact("wo-1", "review_verdict", '{"passed": true}', db_path=db) is True
    assert get_wo_artifact("wo-1", "review_verdict", db_path=db) == '{"passed": true}'
    assert has_wo_artifact("wo-1", "review_verdict", db_path=db) is True
    # Upsert overwrites.
    set_wo_artifact("wo-1", "review_verdict", '{"passed": false}', db_path=db)
    assert get_wo_artifact("wo-1", "review_verdict", db_path=db) == '{"passed": false}'


def test_close_gates_read_db_artifacts(tmp_path):
    """api_contract_exists + security_scan pass from DB artifacts with NO disk files."""
    db = _db_with_table(tmp_path)
    set_wo_artifact("wo-2", "api_contract", "# contract\nunchanged", db_path=db)
    set_wo_artifact("wo-2", "security_scan", "No blocking findings; clean.", db_path=db)
    planning_root = tmp_path / "planning"  # deliberately empty — no .planning files
    conn = sqlite3.connect(str(db))
    try:
        ok_api, _ = run_gate_check(
            "api_contract_exists",
            planning_root=planning_root,
            work_order_id="wo-2",
            project_id="p",
            conn=conn,
            db_path=db,
        )
        ok_sec, _ = run_gate_check(
            "security_scan",
            planning_root=planning_root,
            work_order_id="wo-2",
            project_id="p",
            conn=conn,
            db_path=db,
        )
    finally:
        conn.close()
    assert ok_api is True
    assert ok_sec is True


def test_security_scan_blocked_in_db(tmp_path):
    db = _db_with_table(tmp_path)
    set_wo_artifact("wo-3", "security_scan", "Finding: BLOCKED critical issue", db_path=db)
    conn = sqlite3.connect(str(db))
    try:
        ok, reason = run_gate_check(
            "security_scan",
            planning_root=tmp_path / "planning",
            work_order_id="wo-3",
            project_id="p",
            conn=conn,
            db_path=db,
        )
    finally:
        conn.close()
    assert ok is False
    assert "BLOCKED" in reason


def test_disk_fallback_still_passes(tmp_path):
    """A WO with no DB row but a legacy .planning artifact still satisfies the gate."""
    db = _db_with_table(tmp_path)
    wo_dir = tmp_path / "planning" / "work-orders" / "wo-4"
    wo_dir.mkdir(parents=True)
    (wo_dir / "api-contract.md").write_text("# legacy contract", encoding="utf-8")
    conn = sqlite3.connect(str(db))
    try:
        ok, _ = run_gate_check(
            "api_contract_exists",
            planning_root=tmp_path / "planning",
            work_order_id="wo-4",
            project_id="p",
            conn=conn,
            db_path=db,
        )
    finally:
        conn.close()
    assert ok is True


def test_graceful_degradation_without_table(tmp_path):
    """When the table is absent (unreleased migration), the store degrades, not crashes."""
    db = _db_without_table(tmp_path)
    assert get_wo_artifact("wo-5", "api_contract", db_path=db) is None
    assert has_wo_artifact("wo-5", "api_contract", db_path=db) is False
    assert set_wo_artifact("wo-5", "api_contract", "x", db_path=db) is False
