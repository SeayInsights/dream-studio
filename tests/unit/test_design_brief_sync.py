"""Regression test for WO 2325f95d — DesignBriefProjection missing from sync_tick.

The design-brief mutations are emit-only ("projection is the sole writer"): they
write a spool event and rely on a projection pass to materialize the read-model
row. The synchronous Pattern C tick (``sync_tick``) is the only projection pass
available in a one-shot process with no daemon — but it registered
WorkOrder/Task/Milestone/Project projections and NOT DesignBriefProjection.

So a one-process caller that did ``create_design_brief`` → ``sync_tick`` →
``update_design_brief_field`` still hit "Brief not found": the tick never
materialized the brief. This test drives the full lifecycle (create → update all
six fields → lock) in one interpreter with ``sync_tick`` as the only projection
pass and asserts the read model reflects every step. Fails on main (the brief is
never materialized, so the first update returns "Brief not found"); passes once
DesignBriefProjection is registered in ``sync_tick``.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

NOW = "2026-01-01T00:00:00.000000Z"

# Six canonical brief fields (raw_output excluded — it is the wizard's scratch dump).
SIX_FIELDS = [
    ("purpose", "Help new drivers pass the written exam"),
    ("audience", "First-time license applicants"),
    ("tone", "Encouraging and clear"),
    ("design_system", "tech-minimal"),
    ("font_pairing", "Inter / Source Serif"),
    ("brand_tokens", "primary=#1e40af; radius=8px"),
]


def _reset_db_runtime() -> None:
    from core.config.database import DatabaseRuntime

    DatabaseRuntime.reset_instance()


@pytest.fixture
def live_like_home(tmp_path, monkeypatch):
    """A bootstrapped studio.db wired as the resolved authority for both the
    mutations (via dream_studio_home) and the projection engine (via
    DREAM_STUDIO_DB_PATH + DS_SPOOL_ROOT + a DatabaseRuntime reset), so
    ``sync_tick`` reads/writes this temp DB and not the live one.
    """
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    _reset_db_runtime()
    bootstrap_database(db)
    yield tmp_path, db
    _reset_db_runtime()


def _seed_project(db) -> str:
    project_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO business_projects"
            " (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (project_id, "Test", "", "active", NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id


def test_brief_lifecycle_syncs_in_one_interpreter(live_like_home):
    home, db = live_like_home
    project_id = _seed_project(db)

    from core.design_briefs.mutations import (
        create_design_brief,
        lock_design_brief,
        update_design_brief_field,
    )
    from core.projections.runner import sync_tick

    created = create_design_brief(project_id=project_id, source_root=home, dream_studio_home=home)
    assert created["ok"] is True
    brief_id = created["brief_id"]

    # The only projection pass — no daemon. Pre-fix this is a no-op for briefs
    # because DesignBriefProjection is not registered in sync_tick, so the row is
    # never materialized and the first update below returns "Brief not found".
    sync_tick()

    for field, value in SIX_FIELDS:
        res = update_design_brief_field(
            brief_id=brief_id,
            field=field,
            value=value,
            source_root=home,
            dream_studio_home=home,
        )
        assert res["ok"] is True, f"update {field!r} failed: {res}"

    locked = lock_design_brief(brief_id=brief_id, source_root=home, dream_studio_home=home)
    assert locked["ok"] is True

    # Materialize the six field updates + the lock.
    sync_tick()

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT status, purpose, audience, tone, design_system, font_pairing, brand_tokens"
            " FROM business_design_briefs WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None, "brief row must be materialized by sync_tick after the fix"
    status, purpose, audience, tone, design_system, font_pairing, brand_tokens = row
    assert status == "locked"
    assert purpose == "Help new drivers pass the written exam"
    assert audience == "First-time license applicants"
    assert tone == "Encouraging and clear"
    assert design_system == "tech-minimal"
    assert font_pairing == "Inter / Source Serif"
    assert brand_tokens == "primary=#1e40af; radius=8px"
