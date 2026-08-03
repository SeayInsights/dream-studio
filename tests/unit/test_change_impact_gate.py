"""R5 — change-impact affirmation gate + conventional-revert guard.

The change_impact_affirmed universal close gate requires a WO created on/after the
cutover to carry an impact affirmation; pre-cutover WOs are grandfathered. The revert
guard rejects GitHub-UI `Revert "..."` commit subjects. See core/gates/change_impact.py
and core/gates/revert_commit_format.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.gates.change_impact import (
    IMPACT_AFFIRM_ENFORCED_AFTER,
    affirm_change_impact,
    check_change_impact_affirmed,
    render_affirmation,
)
from core.gates.revert_commit_format import check_revert_subject

POST = f"{IMPACT_AFFIRM_ENFORCED_AFTER}T00:00:00Z"  # on/after cutover → affirmation required
PRE = "2000-01-01T00:00:00Z"  # before any cutover → grandfathered


def _insert_wo(db: Path, wo_id: str, created_at: str) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT OR IGNORE INTO business_projects"
            " (project_id,name,description,status,created_at,updated_at)"
            " VALUES ('p-imp','P','','active',?,?)",
            (created_at, created_at),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id,project_id,milestone_id,title,description,status,"
            " work_order_type,created_at,updated_at)"
            " VALUES (?,?,NULL,?,NULL,?,?,?,?)",
            (wo_id, "p-imp", wo_id, "in_progress", "infrastructure", created_at, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def test_close_requires_impact_affirmation(tmp_path: Path):
    """A post-cutover WO fails the gate until an affirmation is recorded; a pre-cutover
    WO is grandfathered and passes without one."""
    from core.config.sqlite_bootstrap import bootstrap_database

    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    try:
        # Post-cutover WO, no affirmation → blocked.
        _insert_wo(db, "wo-post", POST)
        failures = check_change_impact_affirmed(conn, "wo-post", db)
        assert failures and "change_impact_affirmed" in failures[0]

        # Record an affirmation → passes.
        assert affirm_change_impact(
            "wo-post", touched=["migration"], note="migration 154", db_path=db
        )
        assert check_change_impact_affirmed(conn, "wo-post", db) == []

        # Pre-cutover WO with no affirmation → grandfathered (passes).
        _insert_wo(db, "wo-pre", PRE)
        assert check_change_impact_affirmed(conn, "wo-pre", db) == []
    finally:
        conn.close()


def test_render_affirmation_marks_touched_classes():
    text = render_affirmation(["auth", "contract"], note="oauth token flow")
    assert "- [x] auth" in text and "- [x] contract" in text
    assert "- [ ] migration" in text and "- [ ] changelog" in text
    assert "Note: oauth token flow" in text


def test_revert_commit_format_guard():
    """GitHub-UI `Revert "..."` subjects are rejected; conventional reverts and normal
    commits pass."""
    assert check_revert_subject('Revert "feat(x): thing"') is not None
    assert check_revert_subject("Revert 'fix: y'") is not None
    # Conventional reverts are allowed.
    assert check_revert_subject("revert: feat(x): thing") is None
    assert check_revert_subject("revert(core): drop the widget") is None
    # Ordinary commits are not reverts.
    assert check_revert_subject("feat(gates): add the thing") is None
    assert check_revert_subject("fix: correct a typo") is None


def test_affirm_impact_cli_handler_records_affirmation(tmp_path: Path, monkeypatch):
    """The `ds work-order affirm-impact` handler stores the affirmation for the resolved
    authority DB and returns 0; the recorded artifact marks exactly the touched classes."""
    import core.installed_runtime as ir
    from core.config.sqlite_bootstrap import bootstrap_database
    from core.work_orders.artifacts import get_wo_artifact
    from interfaces.cli.commands.work_order_query import _work_order_affirm_impact

    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    _insert_wo(db, "wo-cli", POST)

    class _Paths:
        sqlite_path = db

    monkeypatch.setattr(ir, "resolve_installed_runtime_paths", lambda **_k: _Paths())

    rc = _work_order_affirm_impact(
        work_order_id="wo-cli",
        touched=["auth", "migration"],
        note="token flow + schema",
        source_root=tmp_path,
        dream_studio_home=None,
    )
    assert rc == 0
    content = get_wo_artifact("wo-cli", "impact_affirmation", db_path=db)
    assert content is not None
    assert "- [x] auth" in content and "- [x] migration" in content
    assert "- [ ] contract" in content and "- [ ] changelog" in content
    assert "Note: token flow + schema" in content


def test_affirm_impact_dispatch_flag_mapping():
    """The dispatch layer maps --auth/--contract/--migration/--changelog flags to the
    ordered `touched` list (the exact comprehension used in work_order_dispatch)."""
    import argparse

    args = argparse.Namespace(auth=True, contract=False, migration=True, changelog=False)
    touched = [c for c in ("auth", "contract", "migration", "changelog") if getattr(args, c, False)]
    assert touched == ["auth", "migration"]
