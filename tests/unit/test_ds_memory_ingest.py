"""Workstream 5d gate: ds memory ingest extraction and idempotency assertions."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── DB helper ─────────────────────────────────────────────────────────────────


def _make_db(tmp_path: Path) -> Path:
    """Create a fully-bootstrapped test DB using all migrations."""
    from core.config.sqlite_bootstrap import bootstrap_database

    db_path = tmp_path / "studio.db"
    bootstrap_database(db_path)
    return db_path


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ── Filesystem helpers ────────────────────────────────────────────────────────


def _make_sessions_tree(
    tmp_path: Path, project: str, date: str, filename: str, content: str
) -> Path:
    """Create tmp_path/sessions/<project>/<date>/<filename> with content."""
    d = tmp_path / "sessions" / project / date
    d.mkdir(parents=True, exist_ok=True)
    f = d / filename
    f.write_text(content, encoding="utf-8")
    return f


def _make_planning_file(tmp_path: Path, filename: str, content: str, subdir: str = "") -> Path:
    """Create tmp_path/planning/<subdir>/<filename> with content."""
    d = tmp_path / "planning" / subdir if subdir else tmp_path / "planning"
    d.mkdir(parents=True, exist_ok=True)
    f = d / filename
    f.write_text(content, encoding="utf-8")
    return f


def _run(tmp_path: Path, db_path: Path, **overrides) -> dict:
    """Call run_memory_ingest with sensible defaults; overrides applied last."""
    from interfaces.cli.ds_memory import run_memory_ingest

    kwargs = dict(
        sessions_dir=tmp_path / "sessions",
        planning_dir=tmp_path / "planning",
        project=None,
        dry_run=False,
        db_path=db_path,
    )
    kwargs.update(overrides)
    return run_memory_ingest(**kwargs)


# ── Pass 1: Gotcha extraction ─────────────────────────────────────────────────


def test_gotcha_extraction_finds_what_broke(tmp_path):
    db_path = _make_db(tmp_path)
    _make_sessions_tree(
        tmp_path,
        "ProjectA",
        "2026-04-17",
        "handoff-001.md",
        "## Session Summary\n\n---\n\nWhat broke: Canvas scaling was off\n\n"
        "The zoom multiplier was computed before initialization.\n\nFix: Moved init above render.\n\n---",
    )
    result = _run(tmp_path, db_path)
    assert result["ok"] is True
    assert result["gotchas"]["new"] >= 1

    conn = _connect(db_path)
    rows = conn.execute("SELECT title FROM reg_gotchas").fetchall()
    conn.close()
    titles = [r["title"] for r in rows]
    assert any("What broke" in t or "Canvas" in t for t in titles)


def test_gotcha_extraction_finds_gotcha_pattern(tmp_path):
    db_path = _make_db(tmp_path)
    _make_sessions_tree(
        tmp_path,
        "ProjectA",
        "2026-04-18",
        "recap-001.md",
        "## Recap\n\nGotcha: Migration numbering conflict\n"
        "Two branches both added migration 035. Renumber the lower-priority one.\n\n"
        "Fix: Resequenced to 036.\n",
    )
    result = _run(tmp_path, db_path)
    assert result["gotchas"]["new"] >= 1

    conn = _connect(db_path)
    rows = conn.execute("SELECT title FROM reg_gotchas").fetchall()
    conn.close()
    assert any("Gotcha" in r["title"] or "Migration" in r["title"] for r in rows)


def test_severity_regression_is_critical(tmp_path):
    from interfaces.cli.ds_memory import _infer_severity

    assert _infer_severity("This regression broke production") == "critical"
    assert _infer_severity("A regression was introduced") == "critical"


def test_severity_blocked_ci_is_high(tmp_path):
    from interfaces.cli.ds_memory import _infer_severity

    assert _infer_severity("PR was blocked in CI") == "high"
    assert _infer_severity("failed CI after merge") == "high"


def test_skill_id_canvas_is_ds_domains(tmp_path):
    from interfaces.cli.ds_memory import _infer_skill_id

    assert _infer_skill_id("canvas scaling was wrong in the editor") == "ds-domains"
    assert _infer_skill_id("iframe breakpoint was not firing") == "ds-domains"


def test_gotcha_idempotent_second_run_skips(tmp_path):
    db_path = _make_db(tmp_path)
    _make_sessions_tree(
        tmp_path,
        "ProjectA",
        "2026-04-17",
        "handoff-001.md",
        "---\nGotcha: Duplicate run check\nThis should only appear once.\n---",
    )
    result1 = _run(tmp_path, db_path)
    new1 = result1["gotchas"]["new"]
    assert new1 >= 1

    result2 = _run(tmp_path, db_path)
    assert result2["gotchas"]["new"] == 0
    assert result2["gotchas"]["skipped"] == new1


# ── Pass 2: Architecture doc extraction ───────────────────────────────────────


def test_architecture_doc_extracted_from_constitution(tmp_path):
    db_path = _make_db(tmp_path)
    _make_planning_file(
        tmp_path,
        "CONSTITUTION.md",
        "# Project Constitution\n\nNever modify core/ without a review session.\n",
    )
    result = _run(tmp_path, db_path)
    assert result["ok"] is True
    assert result["architecture_docs"]["new"] == 1

    conn = _connect(db_path)
    row = conn.execute(
        "SELECT title, doc_type FROM ds_documents WHERE doc_type = 'architecture_decision'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert "CONSTITUTION" in row["title"].upper() or "constitution" in row["title"].lower()


def test_architecture_doc_idempotent_second_run_skips(tmp_path):
    db_path = _make_db(tmp_path)
    _make_planning_file(
        tmp_path,
        "ADR-001.md",
        "# ADR 001 — Use SQLite as authority\n\nDecision: SQLite is the local authority.\n",
    )
    result1 = _run(tmp_path, db_path)
    assert result1["architecture_docs"]["new"] == 1

    result2 = _run(tmp_path, db_path)
    assert result2["architecture_docs"]["new"] == 0
    assert result2["architecture_docs"]["skipped"] == 1


# ── Pass 3: Session handoff continuity ────────────────────────────────────────


def test_session_handoff_picks_most_recent_by_date_dir(tmp_path):
    db_path = _make_db(tmp_path)
    # Older date dir
    _make_sessions_tree(tmp_path, "ProjectA", "2026-04-17", "handoff-001.md", "Old handoff content")
    # Newer date dir
    _make_sessions_tree(tmp_path, "ProjectA", "2026-05-01", "handoff-001.md", "New handoff content")
    result = _run(tmp_path, db_path)
    assert result["session_handoffs"]["updated"] == 1

    conn = _connect(db_path)
    row = conn.execute(
        "SELECT content FROM ds_documents WHERE doc_type = 'session_handoff'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["content"] == "New handoff content"


def test_session_handoff_picks_alphabetically_last_in_date_dir(tmp_path):
    db_path = _make_db(tmp_path)
    _make_sessions_tree(tmp_path, "ProjectA", "2026-05-01", "handoff-001.md", "First file")
    _make_sessions_tree(
        tmp_path, "ProjectA", "2026-05-01", "handoff-002.md", "Second file (alphabetically last)"
    )
    result = _run(tmp_path, db_path)
    assert result["session_handoffs"]["updated"] == 1

    conn = _connect(db_path)
    row = conn.execute(
        "SELECT content FROM ds_documents WHERE doc_type = 'session_handoff'"
    ).fetchone()
    conn.close()
    assert row["content"] == "Second file (alphabetically last)"


def test_session_handoff_upsert_replaces_on_second_run(tmp_path):
    db_path = _make_db(tmp_path)
    _make_sessions_tree(tmp_path, "ProjectA", "2026-04-17", "handoff-001.md", "First handoff")
    result1 = _run(tmp_path, db_path)
    assert result1["session_handoffs"]["updated"] == 1

    # Add a newer handoff
    _make_sessions_tree(tmp_path, "ProjectA", "2026-05-10", "handoff-001.md", "Updated handoff")
    result2 = _run(tmp_path, db_path)
    assert result2["session_handoffs"]["updated"] == 1

    # Verify only 1 row and content is updated
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT content FROM ds_documents WHERE doc_type = 'session_handoff'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["content"] == "Updated handoff"


# ── Dry run ───────────────────────────────────────────────────────────────────


def test_dry_run_reports_counts_without_writing(tmp_path):
    db_path = _make_db(tmp_path)
    _make_sessions_tree(
        tmp_path,
        "ProjectA",
        "2026-04-17",
        "handoff-001.md",
        "---\nGotcha: Dry run test\nThis should not be written.\n---",
    )
    _make_planning_file(tmp_path, "CONSTITUTION.md", "# Constitution\nDry run doc.")
    _make_sessions_tree(
        tmp_path, "ProjectA", "2026-05-01", "handoff-002.md", "Latest handoff for dry run"
    )

    result = _run(tmp_path, db_path, dry_run=True)
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["total_rows_written"] == 0

    # Counts > 0 — we found things that would have been written
    total_found = (
        result["gotchas"]["new"]
        + result["architecture_docs"]["new"]
        + result["session_handoffs"]["updated"]
    )
    assert total_found > 0

    # Nothing actually written to SQLite
    conn = _connect(db_path)
    gotcha_count = conn.execute("SELECT COUNT(*) FROM reg_gotchas").fetchone()[0]
    doc_count = conn.execute("SELECT COUNT(*) FROM ds_documents").fetchone()[0]
    conn.close()
    assert gotcha_count == 0
    assert doc_count == 0


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_unknown_project_dir_gives_null_project_id(tmp_path):
    """A project directory with no match in reg_projects → project_id null, no crash."""
    db_path = _make_db(tmp_path)
    _make_sessions_tree(
        tmp_path,
        "UnknownProject",
        "2026-05-01",
        "handoff-001.md",
        "Session for unknown project",
    )
    result = _run(tmp_path, db_path)
    assert result["ok"] is True
    assert result["session_handoffs"]["updated"] == 1

    conn = _connect(db_path)
    row = conn.execute(
        "SELECT project_id FROM ds_documents WHERE doc_type = 'session_handoff'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["project_id"] is None


def test_missing_sessions_dir_is_graceful_noop(tmp_path):
    """Non-existent sessions dir → ok=True, all counts 0, no crash."""
    db_path = _make_db(tmp_path)
    nonexistent = tmp_path / "does_not_exist"

    result = _run(tmp_path, db_path, sessions_dir=nonexistent)
    assert result["ok"] is True
    assert result["gotchas"]["new"] == 0
    assert result["session_handoffs"]["updated"] == 0
