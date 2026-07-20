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
_MIG_DIR = REPO_ROOT / "core" / "event_store" / "migrations"
_MIG_144 = _MIG_DIR / "144_wo_artifacts.sql"
_MIG_152 = _MIG_DIR / "152_wo_artifacts_instance_key.sql"


def _db_with_table(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_MIG_144.read_text(encoding="utf-8"))  # exercises the real DDL
    conn.executescript(_MIG_152.read_text(encoding="utf-8"))  # instance_key + extended kinds
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


def test_independent_review_gate_reads_db_verdict(tmp_path):
    """The independent_review gate passes from a DB-stored review_verdict (no disk file)."""
    db = _db_with_table(tmp_path)
    set_wo_artifact("wo-6", "review_verdict", '{"passed": true}', db_path=db)
    conn = sqlite3.connect(str(db))
    try:
        ok, _ = run_gate_check(
            "independent_review",
            planning_root=tmp_path / "planning",
            work_order_id="wo-6",
            project_id="p",
            conn=conn,
            db_path=db,
        )
    finally:
        conn.close()
    assert ok is True


def test_backfill_migrates_planning_artifacts(tmp_path):
    from core.work_orders.artifacts import backfill_wo_artifacts

    db = _db_with_table(tmp_path)
    planning_root = tmp_path / "planning"
    wo_dir = planning_root / "work-orders" / "wo-7"
    wo_dir.mkdir(parents=True)
    (wo_dir / "api-contract.md").write_text("# contract", encoding="utf-8")
    (wo_dir / "security-scan.md").write_text("clean", encoding="utf-8")
    (wo_dir / "review-verdict.json").write_text('{"passed": true}', encoding="utf-8")

    written = backfill_wo_artifacts(planning_root, db_path=db)
    assert written == 3
    assert get_wo_artifact("wo-7", "api_contract", db_path=db) == "# contract"
    assert get_wo_artifact("wo-7", "review_verdict", db_path=db) == '{"passed": true}'


# ── WO-FILESDB-C1: instance_key (multi-instance) + extended kinds ──────────────


def test_multi_instance_evals_coexist_by_instance_key(tmp_path):
    """kind='eval' rows are keyed by instance_key (eval_type) and coexist per WO."""
    from core.work_orders.artifacts import list_wo_artifacts

    db = _db_with_table(tmp_path)
    assert set_wo_artifact(
        "wo-e", "eval", '{"a":1}', instance_key="render_completeness", db_path=db
    )
    assert set_wo_artifact(
        "wo-e", "eval", '{"b":2}', instance_key="skill_identifier_safety", db_path=db
    )
    # Distinct instance_keys are distinct rows.
    assert (
        get_wo_artifact("wo-e", "eval", instance_key="render_completeness", db_path=db) == '{"a":1}'
    )
    assert (
        get_wo_artifact("wo-e", "eval", instance_key="skill_identifier_safety", db_path=db)
        == '{"b":2}'
    )
    # Upsert replaces same (kind, instance_key).
    set_wo_artifact("wo-e", "eval", '{"a":9}', instance_key="render_completeness", db_path=db)
    listed = list_wo_artifacts("wo-e", "eval", db_path=db)
    assert listed == [("render_completeness", '{"a":9}'), ("skill_identifier_safety", '{"b":2}')]


def test_singleton_uses_default_empty_instance_key(tmp_path):
    db = _db_with_table(tmp_path)
    set_wo_artifact("wo-s", "context", "ctx", db_path=db)
    assert get_wo_artifact("wo-s", "context", db_path=db) == "ctx"
    assert get_wo_artifact("wo-s", "context", instance_key="", db_path=db) == "ctx"


def test_extended_kinds_accepted(tmp_path):
    db = _db_with_table(tmp_path)
    for kind in ("operator_decision", "decision_request", "escalation", "report", "eval"):
        assert set_wo_artifact("wo-k", kind, "x", db_path=db) is True
        assert get_wo_artifact("wo-k", kind, db_path=db) == "x"


def test_unknown_kind_rejected(tmp_path):
    import pytest

    db = _db_with_table(tmp_path)
    with pytest.raises(ValueError):
        set_wo_artifact("wo-x", "bogus_kind", "x", db_path=db)
