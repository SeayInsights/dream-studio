"""WO-FILESDB-C4B S2: `ds escalation` operator surface (list / status / resolve).

The escalation artifacts written by C4B S1 (business_work_order_artifacts
kind='escalation', JSON status='unresolved') are now operator-manageable from the
authority: list open escalations across all WOs, inspect one WO's escalations, and
mark them resolved. Store-only and additive — the pulse open-escalation count keeps
reading disk until C4B-3, so these tests assert the store surface only.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.escalation import (
    _record_escalation_artifact,
    get_escalations,
    list_escalations,
    resolve_escalation,
)

WO_A = "wo-c4b-s2-aaaa0001"
WO_B = "wo-c4b-s2-bbbb0002"


def _insert_wo(conn: sqlite3.Connection, wo_id: str) -> None:
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id,project_id,milestone_id,title,description,status,work_order_type,created_at,updated_at)"
        " VALUES (?,'p1','m1','T','','in_progress','infrastructure','2026-01-01','2026-01-01')",
        (wo_id,),
    )


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
    _insert_wo(conn, WO_A)
    _insert_wo(conn, WO_B)
    conn.commit()
    conn.close()
    return target


# ── Domain: list_escalations ────────────────────────────────────────────────


def test_list_escalations_defaults_to_unresolved_only(db: Path):
    _record_escalation_artifact(WO_A, instance_key="retrycap", reason="cap hit", db_path=db)
    _record_escalation_artifact(WO_B, instance_key="outcome", reason="regressed", db_path=db)

    rows = list_escalations(db_path=db)
    assert len(rows) == 2
    assert {r["work_order_id"] for r in rows} == {WO_A, WO_B}
    assert all(r["status"] == "unresolved" for r in rows)


def test_list_escalations_hides_resolved_by_default_but_all_shows_them(db: Path):
    _record_escalation_artifact(WO_A, instance_key="retrycap", reason="cap hit", db_path=db)
    _record_escalation_artifact(WO_B, instance_key="outcome", reason="regressed", db_path=db)
    resolve_escalation(WO_A, db_path=db)

    open_only = list_escalations(db_path=db)
    assert [r["work_order_id"] for r in open_only] == [WO_B]

    every = list_escalations(db_path=db, include_resolved=True)
    assert {r["work_order_id"] for r in every} == {WO_A, WO_B}
    resolved = [r for r in every if r["work_order_id"] == WO_A][0]
    assert resolved["status"] == "resolved"


def test_list_escalations_empty_and_table_absent_are_graceful(db: Path, tmp_path: Path):
    assert list_escalations(db_path=db) == []
    empty = tmp_path / "empty.db"
    sqlite3.connect(str(empty)).close()
    assert list_escalations(db_path=empty) == []  # table absent -> [], no raise


def test_list_escalations_tolerates_malformed_row(db: Path):
    from core.work_orders.artifacts import set_wo_artifact

    set_wo_artifact(WO_A, "escalation", "{not valid json", instance_key="retrycap", db_path=db)
    # Malformed content parses to status 'unknown' -> excluded from the unresolved list,
    # but must not raise.
    assert list_escalations(db_path=db) == []
    every = list_escalations(db_path=db, include_resolved=True)
    assert len(every) == 1 and every[0]["status"] == "unknown"


# ── Domain: get_escalations ─────────────────────────────────────────────────


def test_get_escalations_returns_both_instances_for_one_wo(db: Path):
    _record_escalation_artifact(WO_A, instance_key="retrycap", reason="a", db_path=db)
    _record_escalation_artifact(WO_A, instance_key="outcome", reason="b", db_path=db)
    rows = get_escalations(WO_A, db_path=db)
    assert {r["type"] for r in rows} == {"retrycap", "outcome"}
    assert get_escalations(WO_B, db_path=db) == []


# ── Domain: resolve_escalation ──────────────────────────────────────────────


def test_resolve_escalation_flips_status_and_stamps_resolved_at(db: Path):
    _record_escalation_artifact(WO_A, instance_key="retrycap", reason="cap hit", db_path=db)
    result = resolve_escalation(WO_A, db_path=db)
    assert result["found"] is True
    assert result["resolved"] == ["retrycap"]

    rec = get_escalations(WO_A, db_path=db)[0]
    assert rec["status"] == "resolved"
    assert rec["resolved_at"]


def test_resolve_escalation_is_idempotent(db: Path):
    _record_escalation_artifact(WO_A, instance_key="retrycap", reason="cap hit", db_path=db)
    resolve_escalation(WO_A, db_path=db)
    second = resolve_escalation(WO_A, db_path=db)
    assert second["resolved"] == []
    assert second["already_resolved"] == ["retrycap"]


def test_resolve_escalation_single_instance_leaves_others_open(db: Path):
    _record_escalation_artifact(WO_A, instance_key="retrycap", reason="a", db_path=db)
    _record_escalation_artifact(WO_A, instance_key="outcome", reason="b", db_path=db)
    resolve_escalation(WO_A, db_path=db, instance_key="retrycap")

    by_type = {r["type"]: r["status"] for r in get_escalations(WO_A, db_path=db)}
    assert by_type == {"retrycap": "resolved", "outcome": "unresolved"}


def test_resolve_escalation_records_note(db: Path):
    _record_escalation_artifact(WO_A, instance_key="retrycap", reason="a", db_path=db)
    resolve_escalation(WO_A, db_path=db, note="operator ack via CLI")
    content = _raw_artifact(db, WO_A, "retrycap")
    assert json.loads(content)["resolution_note"] == "operator ack via CLI"


def test_resolve_escalation_unknown_wo_reports_not_found(db: Path):
    result = resolve_escalation("wo-does-not-exist", db_path=db)
    assert result["found"] is False
    assert result["resolved"] == []


def _raw_artifact(db: Path, wo: str, instance_key: str) -> str:
    from core.work_orders.artifacts import get_wo_artifact

    content = get_wo_artifact(wo, "escalation", instance_key=instance_key, db_path=db)
    assert content is not None
    return content


# ── CLI: ds escalation list / status / resolve ───────────────────────────────


@pytest.fixture
def cli(db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the CLI's default authority resolution at the fixture DB.

    The escalation handlers resolve the DB via core.config.paths.state_dir()
    (through the artifact store's _resolve_db), so redirecting state_dir to the
    tmp dir routes `ds escalation ...` at the fixture studio.db.
    """
    import core.config.paths as paths

    monkeypatch.setattr(paths, "state_dir", lambda: tmp_path)

    from interfaces.cli.ds import main

    return main


def test_cli_list_then_resolve_roundtrip(cli, db: Path, capsys: pytest.CaptureFixture):
    _record_escalation_artifact(WO_A, instance_key="retrycap", reason="cap hit", db_path=db)

    assert cli(["escalation", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [e["work_order_id"] for e in listed["escalations"]] == [WO_A]

    assert cli(["escalation", "resolve", WO_A, "--json"]) == 0
    resolved = json.loads(capsys.readouterr().out)
    assert resolved["resolved"] == ["retrycap"]

    # Resolved escalation drops out of the default (unresolved-only) list.
    assert cli(["escalation", "list", "--json"]) == 0
    after = json.loads(capsys.readouterr().out)
    assert after["escalations"] == []


def test_cli_status_shows_wo_escalations(cli, db: Path, capsys: pytest.CaptureFixture):
    _record_escalation_artifact(WO_A, instance_key="outcome", reason="regressed", db_path=db)
    assert cli(["escalation", "status", WO_A, "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["work_order_id"] == WO_A
    assert out["escalations"][0]["type"] == "outcome"


def test_cli_resolve_unknown_wo_returns_nonzero(cli, capsys: pytest.CaptureFixture):
    rc = cli(["escalation", "resolve", "wo-nope", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1  # nothing to resolve -> non-zero, in both text and JSON modes
    assert out["found"] is False
    assert out["ok"] is False


def test_cli_list_table_output_when_no_escalations(cli, capsys: pytest.CaptureFixture):
    assert cli(["escalation", "list"]) == 0
    assert "No open escalations." in capsys.readouterr().out
