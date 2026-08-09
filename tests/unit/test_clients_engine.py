"""WO-CLIENT-ENGINE: the event-sourced client engine — mutations emit the right canonical events,
the projections materialize business_clients / business_projects.client_id, the queries resolve the
default + fit proposed work to a client's projects, and the backfill classifies by name/path."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

NOW = "2026-08-08T00:00:00.000000Z"


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    return db


def _seed_project(conn, pid, name, client_id=None, path=None, status="active"):
    conn.execute(
        "INSERT INTO business_projects (project_id, name, status, created_at, updated_at,"
        " project_path, client_id) VALUES (?,?,?,?,?,?,?)",
        (pid, name, status, NOW, NOW, path, client_id),
    )


# ── classify (pure) ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,path,expected",
    [
        ("Fulcrum Skill Library", r"C:\Users\x\Fulcrum", "fulcrum"),
        ("Some App", r"C:\clients\hypershift\app", "hypershift"),
        ("Hypershift Ops", None, "hypershift"),
        ("Dream Studio", r"C:\x\dream-studio", "seayinsights"),
        ("Acme", None, "seayinsights"),
    ],
)
def test_classify_project(name, path, expected):
    from core.clients.backfill import classify_project

    assert classify_project(name, path) == expected


# ── projections (direct handler calls) ──────────────────────────────────────


def test_client_projection_created_and_archived(tmp_path: Path):
    from core.projections.client_projection import ClientProjection

    conn = sqlite3.connect(str(_db(tmp_path)))
    try:
        proj = ClientProjection()
        proj.handle(
            {
                "event_id": "e1",
                "event_type": "client.created",
                "event_timestamp": NOW,
                "payload": {"client_id": "acme", "name": "Acme", "description": "d"},
            },
            conn,
        )
        conn.commit()
        row = conn.execute(
            "SELECT name, status FROM business_clients WHERE client_id='acme'"
        ).fetchone()
        assert row == ("Acme", "active")

        proj.handle(
            {
                "event_id": "e2",
                "event_type": "client.archived",
                "event_timestamp": NOW,
                "payload": {"client_id": "acme"},
            },
            conn,
        )
        conn.commit()
        assert (
            conn.execute("SELECT status FROM business_clients WHERE client_id='acme'").fetchone()[0]
            == "archived"
        )
    finally:
        conn.close()


def test_project_client_assigned_handler_sets_client_id(tmp_path: Path):
    from core.projections.project_projection import ProjectProjection

    conn = sqlite3.connect(str(_db(tmp_path)))
    try:
        _seed_project(conn, "p1", "Fulcrum Skill Library")
        conn.commit()
        ProjectProjection().handle(
            {
                "event_id": "e3",
                "event_type": "project.client_assigned",
                "event_timestamp": NOW,
                "project_id": "p1",
                "payload": {"project_id": "p1", "client_id": "fulcrum"},
            },
            conn,
        )
        conn.commit()
        assert (
            conn.execute(
                "SELECT client_id FROM business_projects WHERE project_id='p1'"
            ).fetchone()[0]
            == "fulcrum"
        )
    finally:
        conn.close()


# ── queries ─────────────────────────────────────────────────────────────────


def test_resolve_default_client_is_seayinsights(tmp_path: Path):
    from core.clients.queries import resolve_default_client

    assert resolve_default_client(db_path=_db(tmp_path)) == "seayinsights"


def test_list_and_projects_for_client(tmp_path: Path):
    from core.clients import queries

    db = _db(tmp_path)
    conn = sqlite3.connect(str(db))
    _seed_project(conn, "p1", "A", client_id="fulcrum")
    _seed_project(conn, "p2", "B", client_id="seayinsights")
    conn.commit()
    conn.close()

    ids = {c["client_id"] for c in queries.list_clients(db_path=db)}
    assert {"seayinsights", "fulcrum", "hypershift"} <= ids
    ful = queries.projects_for_client("fulcrum", db_path=db)
    assert [p["project_id"] for p in ful] == ["p1"]


def test_candidate_projects_verdict_ladder(tmp_path: Path):
    from core.clients.queries import candidate_projects_for_work

    db = _db(tmp_path)
    conn = sqlite3.connect(str(db))
    # One client, two clearly-distinct projects (the Fulcrum case).
    _seed_project(conn, "p-acct", "Back-Office Accounting", client_id="fulcrum")
    conn.execute(
        "UPDATE business_projects SET description='CostPoint accounting payments invoices"
        " reconciliation ledger' WHERE project_id='p-acct'"
    )
    _seed_project(conn, "p-portal", "Partner Portal", client_id="fulcrum")
    conn.execute(
        "UPDATE business_projects SET description='partner portal login dashboard react frontend'"
        " WHERE project_id='p-portal'"
    )
    conn.commit()
    conn.close()

    clear = candidate_projects_for_work(
        "fulcrum", "reconcile CostPoint invoices", "accounting ledger payments", db_path=db
    )
    assert clear["verdict"] == "clear_single" and clear["best"] == "p-acct"

    nofit = candidate_projects_for_work(
        "fulcrum", "kubernetes autoscaler tuning", "helm pods", db_path=db
    )
    assert nofit["verdict"] == "no_fit" and nofit["best"] is None

    empty = candidate_projects_for_work("hypershift", "anything", "x", db_path=db)
    assert empty["verdict"] == "no_projects"


# ── mutations emit the right events ─────────────────────────────────────────


def test_create_client_emits_event(monkeypatch):
    import spool.writer as sw
    from core.clients import mutations

    captured = []
    monkeypatch.setattr(sw, "write_event", lambda d: captured.append(d))
    monkeypatch.setattr("core.projections.runner.sync_tick", lambda: None)

    result = mutations.create_client(name="Acme Corp", description="a client")
    assert result["ok"] and result["client_id"] == "acme-corp"
    assert len(captured) == 1
    ev = captured[0]
    assert ev["event_type"] == "client.created"
    assert ev["payload"]["client_id"] == "acme-corp"
    assert ev["trace"]["attribution_status"] == "fully_attributed"


def test_assign_project_client_emits_event(monkeypatch):
    import spool.writer as sw
    from core.clients import mutations

    captured = []
    monkeypatch.setattr(sw, "write_event", lambda d: captured.append(d))
    monkeypatch.setattr("core.projections.runner.sync_tick", lambda: None)

    mutations.assign_project_client(project_id="p1", client_id="fulcrum")
    ev = captured[0]
    assert ev["event_type"] == "project.client_assigned"
    assert ev["payload"] == {"project_id": "p1", "client_id": "fulcrum"}
    assert ev["trace"]["project_id"] == "p1"


# ── backfill classifies + emits per project ─────────────────────────────────


def test_backfill_emits_assignment_per_null_project(tmp_path: Path, monkeypatch):
    from core.clients import backfill

    db = _db(tmp_path)
    conn = sqlite3.connect(str(db))
    _seed_project(conn, "p-ful", "Fulcrum Skill Library", path=r"C:\x\Fulcrum")
    _seed_project(conn, "p-ds", "Dream Studio", path=r"C:\x\dream-studio")
    _seed_project(conn, "p-has", "Already", client_id="seayinsights")  # not NULL -> skipped
    conn.commit()
    conn.close()

    assigns = []
    from core.clients import mutations

    # backfill imports assign_project_client from core.clients.mutations at call time.
    monkeypatch.setattr(
        mutations, "assign_project_client", lambda **kw: assigns.append(kw) or {"ok": True}
    )
    result = backfill.backfill_project_clients(db_path=db)
    got = {a["project_id"]: a["client_id"] for a in assigns}
    assert got == {"p-ful": "fulcrum", "p-ds": "seayinsights"}  # p-has skipped (already assigned)
    assert all(a["attribution_status"] == "backfill" for a in assigns)
    assert result["assigned"]["fulcrum"] == 1 and result["assigned"]["seayinsights"] == 1
