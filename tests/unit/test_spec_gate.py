"""R2 — ratified-contract gate: a contract-bearing WO's spec must be Ratified.

The api_contract_exists close gate, for work orders created on/after the cutover,
requires the linked spec's lifecycle Status to be Ratified. Earlier WOs are
grandfathered to exists-only. See core/gates/spec_ratification.py and docs/specs/.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.gates.spec_ratification import (
    RATIFY_ENFORCED_AFTER,
    evaluate_api_contract,
    parse_spec_status,
)

# Cutover-relative so the tests never rot when RATIFY_ENFORCED_AFTER moves.
POST = f"{RATIFY_ENFORCED_AFTER}T00:00:00Z"  # on/after cutover → ratification enforced
PRE = "2000-01-01T00:00:00Z"  # before any cutover → grandfathered

_RATIFIED = (
    "# SPEC-0001: Foo\n\n- **Status:** Ratified\n\n## Normative requirements\n- R1. MUST ...\n"
)
_DRAFT = "# SPEC-0001: Foo\n\n- **Status:** Draft\n\n## Normative requirements\n- R1. MUST ...\n"


def test_api_contract_requires_ratified_spec():
    # Post-cutover: Ratified passes, Draft blocks, missing artifact fails.
    ok, _ = evaluate_api_contract(_RATIFIED, POST)
    assert ok is True

    ok, reason = evaluate_api_contract(_DRAFT, POST)
    assert ok is False and "not Ratified" in reason and "draft" in reason

    ok, reason = evaluate_api_contract(None, POST)
    assert ok is False and "not found" in reason

    # Pre-cutover: grandfathered — a Draft spec passes on existence alone...
    ok, _ = evaluate_api_contract(_DRAFT, PRE)
    assert ok is True
    # ...but the artifact must still exist.
    ok, reason = evaluate_api_contract(None, PRE)
    assert ok is False and "not found" in reason

    # Unknown creation time is treated as grandfathered (never falsely blocks).
    ok, _ = evaluate_api_contract(_DRAFT, None)
    assert ok is True


def test_cutover_boundary_is_inclusive_of_the_cutover_date():
    """A WO created exactly on the cutover date is enforced (>= cutover)."""
    on_cutover = f"{RATIFY_ENFORCED_AFTER}T09:00:00Z"
    ok, _ = evaluate_api_contract(_DRAFT, on_cutover)
    assert ok is False  # enforced on the cutover date itself


def test_parse_spec_status_handles_header_variants():
    assert parse_spec_status("- **Status:** Ratified") == "ratified"
    assert parse_spec_status("Status: Draft") == "draft"
    assert parse_spec_status("  status :  reviewed") == "reviewed"
    assert parse_spec_status("no status here") is None


def _insert_wo(db: Path, wo_id: str, created_at: str, pid: str) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT OR IGNORE INTO business_projects"
            " (project_id,name,description,status,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (pid, "P", "", "active", created_at, created_at),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id,project_id,milestone_id,title,description,status,"
            " work_order_type,created_at,updated_at)"
            " VALUES (?,?,NULL,?,NULL,?,?,?,?)",
            (wo_id, pid, wo_id, "in_progress", "api_endpoint", created_at, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def _gate(db: Path, planning_root: Path, wo_id: str, pid: str) -> tuple[bool, str]:
    from core.work_orders.close_gates import run_gate_check

    conn = sqlite3.connect(str(db))
    try:
        return run_gate_check(
            "api_contract_exists",
            planning_root=planning_root,
            work_order_id=wo_id,
            project_id=pid,
            conn=conn,
            db_path=db,
        )
    finally:
        conn.close()


def test_run_gate_check_end_to_end(tmp_path: Path):
    """Drive the real api_contract_exists gate through run_gate_check: a post-cutover
    WO with a Draft contract is blocked, ratifying it clears the gate, and a
    pre-cutover WO is grandfathered — proving the _wo_created_at + artifact + evaluator
    composition, not just the pure evaluator."""
    from core.config.sqlite_bootstrap import bootstrap_database
    from core.work_orders.artifacts import set_wo_artifact

    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    planning_root = tmp_path / "planning"
    pid = "p-spec"

    # Post-cutover WO + Draft contract → blocked; ratify → passes.
    _insert_wo(db, "wo-post", POST, pid)
    assert set_wo_artifact("wo-post", "api_contract", _DRAFT, db_path=db)
    ok, reason = _gate(db, planning_root, "wo-post", pid)
    assert ok is False and "not Ratified" in reason, reason

    set_wo_artifact("wo-post", "api_contract", _RATIFIED, db_path=db)
    ok, _ = _gate(db, planning_root, "wo-post", pid)
    assert ok is True

    # Pre-cutover WO + Draft contract → grandfathered (passes on existence).
    _insert_wo(db, "wo-pre", PRE, pid)
    assert set_wo_artifact("wo-pre", "api_contract", _DRAFT, db_path=db)
    ok, _ = _gate(db, planning_root, "wo-pre", pid)
    assert ok is True
