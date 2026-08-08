"""WO-ATTR-FIT-HELPER: the attribution fit-check helper surfaces candidate milestones + a
coarse, deterministic fit verdict, so the attribution flow can ask instead of auto-filing when
proposed work does not clearly fit a milestone's described scope."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from core.projects.milestone_fit import candidate_milestones_for_work

# Two clearly-distinct engagements under one project + a dashboard milestone — mirrors the real
# Fulcrum case (back-office accounting vs a skill-library product funneled together).
_MILESTONES = [
    (
        "m-acct",
        "Back-Office Tooling",
        "CostPoint accounting payments invoices reconciliation ledger",
    ),
    ("m-skill", "Skill Library Platform", "skill packs library authoring routing marketplace"),
    ("m-dash", "Dashboard", "dashboard panels telemetry charts population"),
]


def _seed(tmp_path: Path, milestones=_MILESTONES) -> Path:
    db = tmp_path / "studio.db"
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, status, created_at, updated_at)"
            " VALUES ('p', 'P', 'active', 't', 't')"
        )
        for mid, title, desc in milestones:
            conn.execute(
                "INSERT INTO business_milestones (milestone_id, project_id, title, description,"
                " status, order_index, created_at, updated_at) VALUES (?,?,?,?,'active',1,'t','t')",
                (mid, "p", title, desc),
            )
        conn.commit()
    finally:
        conn.close()
    return db


def test_clear_single_fit_returns_best(tmp_path: Path):
    db = _seed(tmp_path)
    r = candidate_milestones_for_work(
        "p", "Reconcile CostPoint invoices", "accounting ledger reconciliation payments", db_path=db
    )
    assert r["verdict"] == "clear_single"
    assert r["best"] == "m-acct"


def test_ambiguous_when_multiple_clear(tmp_path: Path):
    db = _seed(tmp_path)
    r = candidate_milestones_for_work(
        "p",
        "skill packs for CostPoint accounting",
        "accounting payments skill packs library",
        db_path=db,
    )
    assert r["verdict"] == "ambiguous"


def test_no_fit_when_nothing_overlaps(tmp_path: Path):
    db = _seed(tmp_path)
    r = candidate_milestones_for_work(
        "p", "Kubernetes cluster autoscaler tuning", "helm networkpolicy pods", db_path=db
    )
    assert r["verdict"] == "no_fit"
    assert r["best"] is None


def test_no_milestones_verdict(tmp_path: Path):
    db = _seed(tmp_path, milestones=[])
    r = candidate_milestones_for_work("p", "anything at all", "x", db_path=db)
    assert r["verdict"] == "no_milestones"
    assert r["candidates"] == []


def test_candidates_carry_descriptions_and_fit(tmp_path: Path):
    db = _seed(tmp_path)
    r = candidate_milestones_for_work(
        "p", "dashboard panels not populating", "dashboard telemetry", db_path=db
    )
    dash = next(c for c in r["candidates"] if c["milestone_id"] == "m-dash")
    assert "panels" in dash["description"]
    assert dash["fit"] == "clear"
    # Generic PM words never manufacture a fit.
    assert (
        candidate_milestones_for_work("p", "add work order", "build task", db_path=db)["verdict"]
        == "no_fit"
    )
