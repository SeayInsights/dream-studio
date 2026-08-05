"""WO P4 (742c84f8) — `ds prd` surface + milestone-close auto-refresh (SPEC-0001 R11-R12).

`ds prd show` renders the PRD+SOW living document; closing a milestone best-effort
auto-refreshes it and never blocks the close on a refresh failure.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from core.files.store import read_file_by_name, write_file
from core.prd.rescore import DOC_NAME, rescore_prd

REPO_ROOT = Path(__file__).resolve().parents[2]
_TS = "2026-08-05T00:00:00+00:00"
CAP_MAP = "capabilities:\n  - capability_id: cap-a\n    title: Cap A\n    weight: 1.0\nmilestone_capabilities:\n  m1: [cap-a]\n"


def test_prd_show_renders_document_from_engine(tmp_path: Path):
    """The `show` surface prints the docstore document the engine renders (R9/R11)."""
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
            " VALUES ('w1','p','m1','WO one','closed',0.8,'t','t')"
        )
        conn.commit()
    finally:
        conn.close()

    files = tmp_path / "files.db"
    write_file("prd/capability-map.yaml", CAP_MAP, "application/yaml", "planning", db_path=files)

    result = rescore_prd(
        "p", db_path=studio, files_db_path=files, planning_root=tmp_path / ".planning", now=_TS
    )
    assert result["ok"] and result["document_ref"] == DOC_NAME

    doc = read_file_by_name(DOC_NAME, project_id="p", db_path=files)["content"]
    if isinstance(doc, (bytes, bytearray)):
        doc = doc.decode("utf-8")
    assert "PRD + Statement of Work" in doc and "Milestone One" in doc


def _seed_closeable(tmp_path: Path) -> Path:
    """A temp home (tmp_path/state/studio.db) with a project, one milestone, and only a CLOSED
    work order — so close_milestone's open-WO precondition passes and force reaches success."""
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id,name,description,status,created_at,updated_at)"
            " VALUES ('p','P','d','active','t','t')"
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id,project_id,title,description,status,created_at,updated_at)"
            " VALUES ('m','p','M',NULL,'active','t','t')"
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id,project_id,milestone_id,title,status,work_order_type,created_at,updated_at)"
            " VALUES ('w','p','m','W','closed','infrastructure','t','t')"
        )
        conn.commit()
    finally:
        conn.close()
    return tmp_path


def test_prd_cli_handlers_resolve_project_and_render(tmp_path, monkeypatch, capsys):
    """The `ds prd` CLI handlers: rescore resolves the active project and reports the score;
    show prints the rendered document; --project overrides the active-project default."""
    from interfaces.cli.commands import prd

    home = _seed_closeable(tmp_path)  # active project 'p'

    # rescore: resolves the active project (no --project) and prints the engine's score.
    monkeypatch.setattr(
        "core.prd.rescore.rescore_prd",
        lambda pid, **kw: {
            "ok": True,
            "overall_score": 42.0,
            "coverage": 0.5,
            "document_ref": "prd/prd-sow.md",
        },
    )
    rc = prd._prd_rescore(project_id=None, source_root=REPO_ROOT, dream_studio_home=home)
    assert rc == 0
    out = capsys.readouterr().out
    assert "42.0/100" in out and "p" in out  # resolved active project + reported score

    # _resolve_project: explicit id wins; else the active project.
    assert prd._resolve_project("explicit", REPO_ROOT, home) == "explicit"
    assert prd._resolve_project(None, REPO_ROOT, home) == "p"

    # show: prints the docstore document (monkeypatched read).
    monkeypatch.setattr(
        "core.files.store.read_file_by_name", lambda name, **kw: {"content": "RENDERED PRD+SOW"}
    )
    rc2 = prd._prd_show(project_id="p", source_root=REPO_ROOT, dream_studio_home=home)
    assert rc2 == 0
    assert "RENDERED PRD+SOW" in capsys.readouterr().out


def test_prd_dispatch_routes_and_registers(tmp_path, monkeypatch):
    """register() wires a `prd` subparser with rescore/show; dispatch routes to the handlers
    and returns 1 for an unknown subcommand."""
    import argparse

    from interfaces.cli.commands import prd

    # register() attaches a parseable `prd rescore/show` tree.
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    prd.register(sub)
    ns = parser.parse_args(["prd", "rescore", "--project", "xyz"])
    assert ns.prd_command == "rescore" and ns.project == "xyz"

    routed: list[str] = []
    monkeypatch.setattr(prd, "_prd_rescore", lambda **kw: routed.append("rescore") or 0)
    monkeypatch.setattr(prd, "_prd_show", lambda **kw: routed.append("show") or 0)

    assert prd.dispatch(ns, source_root=REPO_ROOT, dream_studio_home=tmp_path) == 0
    show_ns = argparse.Namespace(prd_command="show", project=None)
    assert prd.dispatch(show_ns, source_root=REPO_ROOT, dream_studio_home=tmp_path) == 0
    assert routed == ["rescore", "show"]

    # Unknown subcommand → non-zero, no handler.
    bad = argparse.Namespace(prd_command="bogus", project=None)
    assert prd.dispatch(bad, source_root=REPO_ROOT, dream_studio_home=tmp_path) == 1


def test_prd_show_and_milestone_close_autorefresh(tmp_path, monkeypatch):
    """close_milestone auto-refreshes the PRD on its success path, and NEVER lets a refresh
    failure block the close (SPEC-0001 R12) — driven through close_milestone itself."""
    from core.milestones.close import close_milestone

    # 1. A successful close invokes rescore_prd for the milestone's project.
    home = _seed_closeable(tmp_path / "ok")
    calls: list[str] = []

    def _spy(project_id, **kwargs):
        calls.append(project_id)
        return {"ok": True}

    monkeypatch.setattr("core.prd.rescore.rescore_prd", _spy)
    res = close_milestone(
        milestone_id="m",
        force=True,
        source_root=REPO_ROOT,
        dream_studio_home=home,
        planning_root=home / ".planning",
    )
    assert res["ok"] is True and res["status"] == "complete"
    assert calls == ["p"], "close success path must auto-refresh the PRD for the project"

    # 2. A rescore that RAISES must be swallowed — the close still succeeds.
    home2 = _seed_closeable(tmp_path / "boom")

    def _boom(project_id, **kwargs):
        raise RuntimeError("rescore blew up")

    monkeypatch.setattr("core.prd.rescore.rescore_prd", _boom)
    res2 = close_milestone(
        milestone_id="m",
        force=True,
        source_root=REPO_ROOT,
        dream_studio_home=home2,
        planning_root=home2 / ".planning",
    )
    assert (
        res2["ok"] is True and res2["status"] == "complete"
    ), "a PRD auto-refresh failure must never block or fail a milestone close"
