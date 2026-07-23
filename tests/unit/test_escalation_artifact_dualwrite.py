"""WO-FILESDB-C4B S1: escalations dual-write to the authority artifact store.

escalate_to_operator (ESC-RETRYCAP) and the outcome-regression path (ESC-OUTCOME) now
also write a business_work_order_artifacts row (kind='escalation', instance_key
'retrycap'/'outcome', content = JSON with status='unresolved'). The disk ESC-*.md write
stays during the transition (the pulse scan reads disk until C4B-3). This slice is
additive — the escalation-ladder logic is unchanged.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.artifacts import get_wo_artifact
from core.work_orders.escalation import _record_escalation_artifact, escalate_to_operator

WO = "wo-c4b-esc-0001"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    conn.execute(
        "INSERT INTO business_projects (project_id,name,description,status,created_at,updated_at)"
        " VALUES ('p1','P','','active','2026-01-01','2026-01-01')"
    )
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id,project_id,title,description,status,order_index,created_at,updated_at)"
        " VALUES ('m1','p1','M','','active',0,'2026-01-01','2026-01-01')"
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id,project_id,milestone_id,title,description,status,work_order_type,created_at,updated_at)"
        " VALUES (?,'p1','m1','T','','in_progress','infrastructure','2026-01-01','2026-01-01')",
        (WO,),
    )
    conn.commit()
    conn.close()
    return target


def test_record_escalation_artifact_writes_unresolved_json(db: Path):
    _record_escalation_artifact(WO, instance_key="retrycap", reason="cap hit", db_path=db)
    content = get_wo_artifact(WO, "escalation", instance_key="retrycap", db_path=db)
    assert content is not None
    d = json.loads(content)
    assert d["status"] == "unresolved"
    assert d["type"] == "retrycap"
    assert d["reason"] == "cap hit"
    assert d["work_order_id"] == WO


def test_outcome_instance_key_coexists_with_retrycap(db: Path):
    _record_escalation_artifact(WO, instance_key="retrycap", reason="a", db_path=db)
    _record_escalation_artifact(WO, instance_key="outcome", reason="b", db_path=db)
    # Both instances coexist (PK includes instance_key).
    assert (
        json.loads(get_wo_artifact(WO, "escalation", instance_key="retrycap", db_path=db))["type"]
        == "retrycap"
    )
    assert (
        json.loads(get_wo_artifact(WO, "escalation", instance_key="outcome", db_path=db))["type"]
        == "outcome"
    )


def test_escalate_to_operator_dual_writes(db: Path, tmp_path: Path):
    home = tmp_path / "home"
    esc_path = escalate_to_operator(
        WO, db_path=db, reason="retry cap reached", dream_studio_home=home
    )
    # disk ESC file still written (transition)
    assert esc_path.exists()
    assert "unresolved" in esc_path.read_text(encoding="utf-8")
    # artifact also written
    content = get_wo_artifact(WO, "escalation", instance_key="retrycap", db_path=db)
    assert content is not None and json.loads(content)["status"] == "unresolved"


def test_record_escalation_artifact_is_isolated_on_bad_db(tmp_path: Path):
    # Best-effort: a non-authority / table-absent DB must not raise (ladder unaffected).
    empty = tmp_path / "empty.db"
    sqlite3.connect(str(empty)).close()
    _record_escalation_artifact(WO, instance_key="retrycap", reason="x", db_path=empty)  # no raise
