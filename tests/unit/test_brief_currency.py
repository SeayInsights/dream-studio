"""WO-BRIEF-CURRENCY: design_brief_locked proved existence, not currency.

The gate asked one question — does a row exist with status='locked' — so a brief
locked in May satisfied it in August, after months of UI work had moved the
surfaces it describes. A UI work order could close against a design brief that no
longer described the design.

Currency is derived from AUTHORITY state (UI-class work orders closing after the
lock), not from the repo, so it works identically for an external project DS is
only governing.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.gates.brief_currency import (
    brief_currency,
    currency_failure,
    declare_reviewed_no_change,
)
from core.work_orders.close_gates import run_gate_check

_MAY = "2026-05-01T00:00:00+00:00"
_JUNE = "2026-06-01T00:00:00+00:00"
_JULY = "2026-07-01T00:00:00+00:00"
_AUG = "2026-08-01T00:00:00+00:00"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(path)
    return path


def _project(db: Path) -> str:
    project_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", _MAY, _MAY),
    )
    conn.commit()
    conn.close()
    return project_id


def _lock_brief(db: Path, project_id: str, *, when: str = _MAY) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_design_briefs"
        " (brief_id, project_id, status, created_at, updated_at) VALUES (?,?,?,?,?)",
        (str(uuid.uuid4()), project_id, "locked", when, when),
    )
    conn.commit()
    conn.close()


def _closed_wo(
    db: Path, project_id: str, *, wo_type: str, closed_at: str, title: str = "UI work"
) -> str:
    wo_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at, closed_at)"
        " VALUES (?,?,NULL,?,'d',?,'closed',?,?,?)",
        (wo_id, project_id, title, wo_type, _MAY, closed_at, closed_at),
    )
    conn.commit()
    conn.close()
    return wo_id


def _open_ui_wo(db: Path, project_id: str) -> str:
    wo_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at)"
        " VALUES (?,?,NULL,'new screen','d','ui_page','in_progress',?,?)",
        (wo_id, project_id, _AUG, _AUG),
    )
    conn.commit()
    conn.close()
    return wo_id


def _gate(db: Path, planning: Path, wo_id: str, project_id: str) -> tuple[bool, str]:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        return run_gate_check(
            "design_brief_locked",
            planning_root=planning,
            work_order_id=wo_id,
            project_id=project_id,
            conn=conn,
            db_path=db,
        )
    finally:
        conn.close()


# ── Task 1: currency, not just existence ───────────────────────────────────────


def test_stale_locked_brief_no_longer_passes_gate(db, tmp_path):
    """The defect: a May brief satisfying the gate in August after UI work landed."""
    project_id = _project(db)
    _lock_brief(db, project_id, when=_MAY)
    _closed_wo(db, project_id, wo_type="ui_page", closed_at=_JULY, title="redesigned dashboard")
    wo_id = _open_ui_wo(db, project_id)

    passed, reason = _gate(db, tmp_path, wo_id, project_id)
    assert passed is False, "a brief locked before the surface moved is not current"
    assert "existence but not currency" in reason
    assert "redesigned dashboard" in reason, "name what moved the surface"
    assert "re-lock" in reason, "the remedy must be named"


def test_a_current_brief_passes(db, tmp_path):
    """Locked AFTER the UI work — nothing has moved since."""
    project_id = _project(db)
    _closed_wo(db, project_id, wo_type="ui_page", closed_at=_JUNE)
    _lock_brief(db, project_id, when=_JULY)
    wo_id = _open_ui_wo(db, project_id)

    passed, reason = _gate(db, tmp_path, wo_id, project_id)
    assert passed is True, reason


def test_backend_work_does_not_stale_a_ui_brief(db, tmp_path):
    """A backend stretch must not invalidate a brief that still describes the UI —
    otherwise the gate cries wolf and gets re-locked reflexively, which is worse
    than not checking."""
    project_id = _project(db)
    _lock_brief(db, project_id, when=_MAY)
    for wo_type in ("api_endpoint", "data_pipeline", "infrastructure", "documentation"):
        _closed_wo(db, project_id, wo_type=wo_type, closed_at=_JULY, title=f"{wo_type} work")
    wo_id = _open_ui_wo(db, project_id)

    passed, reason = _gate(db, tmp_path, wo_id, project_id)
    assert passed is True, reason


def test_an_open_ui_work_order_does_not_stale_the_brief(db, tmp_path):
    """Only CLOSED work moved the surface. Counting in-flight work would make the
    gate unsatisfiable: the WO being closed is itself UI work."""
    project_id = _project(db)
    _lock_brief(db, project_id, when=_MAY)
    wo_id = _open_ui_wo(db, project_id)

    passed, reason = _gate(db, tmp_path, wo_id, project_id)
    assert passed is True, reason


def test_missing_brief_still_reports_absence_not_staleness(db, tmp_path):
    project_id = _project(db)
    wo_id = _open_ui_wo(db, project_id)
    passed, reason = _gate(db, tmp_path, wo_id, project_id)
    assert passed is False
    assert "no locked design brief" in reason


def test_currency_fails_open_when_it_cannot_be_determined(db):
    """Refusing to close because DS could not read its own bookkeeping would be a
    worse defect than the staleness this catches."""

    class Broken:
        def execute(self, *_a, **_k):
            raise sqlite3.OperationalError("no such table")

    info = brief_currency("p", conn=Broken(), db_path=db)
    assert info["current"] is True
    assert "undetermined" in (info["reason"] or "")
    assert currency_failure("p", conn=Broken(), db_path=db) is None


def test_a_brief_without_a_timestamp_fails_open(db):
    """The guard for a timestamp-less brief, driven directly.

    The live schema puts NOT NULL on created_at, so this row cannot be inserted —
    the first version of this test tried and hit an IntegrityError. The guard is
    still worth having (another store, an older schema, or a future migration could
    yield None) but the test must not pretend the DB can produce it, so it drives
    the reader with a stub instead of asserting an unreachable state.
    """
    conn = sqlite3.connect(str(db))
    cols = {r[1]: r[3] for r in conn.execute("PRAGMA table_info(business_design_briefs)")}
    conn.close()
    assert (
        cols.get("created_at") == 1
    ), "created_at is NOT NULL today, which is why this path is driven with a stub"

    class NoTimestamp:
        def execute(self, *_a, **_k):
            class _R:
                @staticmethod
                def fetchone():
                    return ("brief-1", None, None)

            return _R()

    info = brief_currency("p", conn=NoTimestamp(), db_path=db)
    assert info["current"] is True, "an undeterminable brief must not block a close"
    assert "undeterminable" in (info["reason"] or "")


# ── Task 2: reviewed-no-change, in the existing idiom ──────────────────────────


def test_reviewed_no_change_declaration_passes_and_is_recorded(db, tmp_path):
    """Where the surface moved but the brief genuinely still holds. The same idiom
    the docs-drift gates use, captured as evidence rather than as a silent flag."""
    project_id = _project(db)
    _lock_brief(db, project_id, when=_MAY)
    _closed_wo(db, project_id, wo_type="ui_component", closed_at=_JUNE, title="new button")
    wo_id = _open_ui_wo(db, project_id)

    passed, _ = _gate(db, tmp_path, wo_id, project_id)
    assert passed is False, "precondition: the brief is stale"

    assert declare_reviewed_no_change(
        project_id,
        note="button reuses existing tokens; design language unchanged",
        when=_JULY,
        db_path=db,
    )
    passed, reason = _gate(db, tmp_path, wo_id, project_id)
    assert passed is True, reason

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    info = brief_currency(project_id, conn=conn, db_path=db)
    conn.close()
    assert info["reviewed_no_change_at"] == _JULY
    assert "existing tokens" in info["reviewed_no_change_note"], "the reason is recorded"


def test_the_declaration_ages_like_a_lock(db, tmp_path):
    """A boolean 'ignore staleness' would disable the gate forever. The declaration
    carries its own timestamp, so work AFTER it stales the brief again."""
    project_id = _project(db)
    _lock_brief(db, project_id, when=_MAY)
    _closed_wo(db, project_id, wo_type="ui_component", closed_at=_JUNE)
    declare_reviewed_no_change(project_id, note="still holds", when=_JULY, db_path=db)
    wo_id = _open_ui_wo(db, project_id)
    assert _gate(db, tmp_path, wo_id, project_id)[0] is True

    _closed_wo(db, project_id, wo_type="ui_page", closed_at=_AUG, title="whole new layout")
    passed, reason = _gate(db, tmp_path, wo_id, project_id)
    assert passed is False, "work after the declaration must stale the brief again"
    assert "whole new layout" in reason


# ── Task 3: the brief stays project-scoped ─────────────────────────────────────


def test_current_project_brief_satisfies_all_ui_work_orders(db, tmp_path):
    """Explicitly NOT re-scoping per work order. business_design_briefs is
    project-scoped on purpose: a brief per WO would proliferate near-duplicates and
    destroy the shared design language that is the point of having one."""
    project_id = _project(db)
    _lock_brief(db, project_id, when=_JULY)
    wo_ids = [_open_ui_wo(db, project_id) for _ in range(3)]
    for wo_id in wo_ids:
        passed, reason = _gate(db, tmp_path, wo_id, project_id)
        assert passed is True, f"{wo_id}: {reason}"


def test_the_brief_table_is_not_work_order_scoped(db):
    """Pinned: adding work_order_id to business_design_briefs would be the
    over-correction this WO explicitly rejects."""
    conn = sqlite3.connect(str(db))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(business_design_briefs)")]
    conn.close()
    assert "project_id" in cols
    assert "work_order_id" not in cols, (
        "the brief is project-scoped by design — per-WO briefs would trade one defect "
        "for a worse one"
    )


# ── Task 4: the skill-text layer (two-layer rule) ──────────────────────────────


def test_skill_text_documents_brief_currency():
    """The two-layer rule this milestone keeps enforcing: an engine change with no
    skill text is a gate an agent cannot act on. WO 55d02acf was exactly that —
    close emitted main_ci_warning and the close skill never mentioned it.
    """
    repo = Path(__file__).resolve().parents[2]
    canonical = repo / "canonical" / "skills" / "ds-project" / "modes" / "brief" / "SKILL.md"
    assert canonical.is_file(), f"brief mode SKILL.md missing at {canonical}"
    text = canonical.read_text(encoding="utf-8")

    # The distinction the gate now draws.
    assert "existence but not currency" in text
    # Both remedies, and that they differ.
    assert "re-lock" in text.lower()
    assert "reviewed-no-change" in text.lower()
    # The rule that keeps the gate from crying wolf.
    assert "ui_component" in text and "api_endpoint" in text
    # The over-correction it must not invite.
    assert "project-scoped" in text

    projected = repo / "dist" / "plugin" / "skills" / "ds-project" / "modes" / "brief" / "SKILL.md"
    assert projected.is_file(), "the projected brief SKILL.md is missing"
    assert projected.read_text(encoding="utf-8").replace("\r\n", "\n") == text.replace(
        "\r\n", "\n"
    ), "dist/plugin brief SKILL.md is stale — rebuild it"


def test_the_declaration_is_not_documented_as_a_shortcut():
    """A declaration that says 'still holds' about a brief that does not is worse
    than a stale lock, because it looks like someone checked. The guidance has to
    say so, or the escape hatch becomes the default path."""
    repo = Path(__file__).resolve().parents[2]
    text = (
        repo / "canonical" / "skills" / "ds-project" / "modes" / "brief" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "DON'T" in text
    assert "skip a real re-lock" in text
