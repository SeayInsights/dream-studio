"""WO P5 (62aa33b1) — the dashboard PRD+SOW panel read-model (SPEC-0001; read-only).

build_prd_sow_panel returns the PRD+SOW shape (overall score, per-capability coverage,
per-milestone SOW entries) derived read-only from authority + docstore — it must NOT write
the living document (that is rescore_prd's job, not the dashboard read path).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from core.files.store import read_file_by_name, write_file
from projections.api.lib.prd_sow_panel import PANEL_SCHEMA, build_prd_sow_panel

CAP_MAP = "capabilities:\n  - capability_id: cap-a\n    title: Cap A\n    weight: 1.0\nmilestone_capabilities:\n  m1: [cap-a]\n"


def test_dashboard_prd_sow_shape(tmp_path: Path):
    studio = tmp_path / "studio.db"
    bootstrap_database(studio)
    conn = sqlite3.connect(str(studio))
    try:
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id,project_id,title,description,status,order_index,created_at,updated_at)"
            " VALUES ('m1','p','Milestone One','ship A','complete',10,'t','t')"
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id,project_id,milestone_id,title,status,verify_score,created_at,updated_at)"
            " VALUES ('w1','p','m1','WO one','closed',0.9,'t','t')"
        )
        conn.commit()
    finally:
        conn.close()

    files = tmp_path / "files.db"
    write_file("prd/capability-map.yaml", CAP_MAP, "application/yaml", "planning", db_path=files)

    panel = build_prd_sow_panel("p", db_path=studio, files_db_path=files)

    # Shape contract.
    assert panel["schema"] == PANEL_SCHEMA and panel["ok"] is True
    assert panel["project_id"] == "p"
    assert panel["overall_score"] == 90.0  # single WO composite 0.9 -> 90; cap-a delivered
    assert panel["coverage"] == 1.0
    caps = {c["capability_id"]: c for c in panel["capabilities"]}
    assert caps["cap-a"]["status"] == "scored" and caps["cap-a"]["score"] == 90.0
    m1 = next(m for m in panel["milestones"] if m["milestone_id"] == "m1")
    assert m1["set_out_to"] == "ship A" and "Delivered" in m1["accomplished"]

    # READ-ONLY: building the panel must not render/persist the living document.
    try:
        read_file_by_name("prd/prd-sow.md", project_id="p", db_path=files)
        wrote = True
    except KeyError:
        wrote = False
    assert wrote is False, "the dashboard panel read path must not write the PRD+SOW document"


def test_prd_sow_route_serves_panel_and_is_wired(monkeypatch):
    """The API route exposes the panel (named + active project) and is wired into the app."""
    import asyncio

    from projections.api.routes import prd_sow

    # The route delegates to the read-model for a named project.
    monkeypatch.setattr(
        prd_sow, "build_prd_sow_panel", lambda pid, **kw: {"ok": True, "project_id": pid}
    )
    got = asyncio.run(prd_sow.prd_sow_for_project("proj-x"))
    assert got == {"ok": True, "project_id": "proj-x"}

    # /active resolves the active project then serves its panel.
    monkeypatch.setattr(prd_sow, "_active_project_id", lambda: "active-proj")
    active = asyncio.run(prd_sow.prd_sow_active())
    assert active["project_id"] == "active-proj"

    # No active project → 404, not a raw error.
    from fastapi import HTTPException

    monkeypatch.setattr(prd_sow, "_active_project_id", lambda: None)
    try:
        asyncio.run(prd_sow.prd_sow_active())
        raised = False
    except HTTPException as exc:
        raised = exc.status_code == 404
    assert raised, "/active must 404 when there is no active project"

    # The router is mounted in the app under /api/v1/prd-sow. Read the wiring from the OpenAPI
    # schema, which flattens every registered path regardless of the FastAPI/starlette route
    # object model — `app.routes` entries vary across versions (APIRoute vs a wrapped
    # _IncludedRouter that lacks `.path`), so scanning them directly is version-fragile.
    from projections.api.main import app

    paths = app.openapi().get("paths", {})
    assert any(
        p.startswith("/api/v1/prd-sow") for p in paths
    ), "prd-sow router not wired in main.py"
