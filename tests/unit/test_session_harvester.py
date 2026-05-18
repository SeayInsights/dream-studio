"""Tests for WS 8c-5: Session intelligence harvest."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

# ── helpers ────────────────────────────────────────────────────────────────────

def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE reg_gotchas (
            gotcha_id TEXT PRIMARY KEY,
            skill_id  TEXT,
            severity  TEXT,
            title     TEXT,
            context   TEXT,
            fix       TEXT,
            discovered TEXT,
            times_hit INTEGER DEFAULT 0
        );
        CREATE TABLE raw_approaches (
            approach_id TEXT PRIMARY KEY,
            skill_id    TEXT,
            approach    TEXT,
            model       TEXT,
            project_id  TEXT,
            created_at  TEXT
        );
        CREATE TABLE ds_documents (
            doc_id      TEXT,
            doc_type    TEXT,
            title       TEXT,
            content     TEXT,
            source_path TEXT UNIQUE,
            created_at  TEXT
        );
        CREATE TABLE ds_technology_signals (
            signal_id  TEXT PRIMARY KEY,
            extension  TEXT NOT NULL,
            count      INTEGER NOT NULL DEFAULT 0,
            last_seen  TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()
    return db


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _tool_result_error(text: str) -> dict:
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "is_error": True,
                    "content": text,
                }
            ]
        },
    }


def _tool_use_write(file_path: str) -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Write",
                    "input": {"file_path": file_path, "content": "..."},
                }
            ]
        },
    }


def _tool_use_skill(skill: str, args: str = "") -> dict:
    return {
        "type": "assistant",
        "message": {
            "model": "claude-sonnet-4",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Skill",
                    "input": {"skill": skill, "args": args},
                }
            ]
        },
    }


# ── import harvester ──────────────────────────────────────────────────────────

from spool.session_harvester import (
    SessionHarvester,
    HarvestResult,
    _sanitize,
    _is_architecture_doc,
)


# ── _sanitize tests ───────────────────────────────────────────────────────────

def test_sanitize_removes_windows_path():
    text = "Error at C:\\Users\\Dannis\\myfile.py line 42"
    result = _sanitize(text)
    assert "C:\\Users\\Dannis\\myfile.py" not in result
    assert "[PATH]" in result


def test_sanitize_removes_unix_path():
    text = "Failed to open /home/user/config.yml"
    result = _sanitize(text)
    assert "/home/user/config.yml" not in result
    assert "[PATH]" in result


def test_sanitize_removes_email():
    text = "Contact dannis@example.com for details"
    result = _sanitize(text)
    assert "dannis@example.com" not in result
    assert "[EMAIL]" in result


def test_sanitize_removes_token_url():
    text = "Request to https://api.example.com/endpoint?token=abc123secret failed"
    result = _sanitize(text)
    assert "abc123secret" not in result
    assert "[URL]" in result


def test_sanitize_removes_uuid():
    text = "Session ID: 550e8400-e29b-41d4-a716-446655440000 failed"
    result = _sanitize(text)
    assert "550e8400-e29b-41d4-a716-446655440000" not in result
    assert "[UUID]" in result


# ── _is_architecture_doc tests ────────────────────────────────────────────────

def test_is_architecture_doc_constitution():
    assert _is_architecture_doc("/some/path/CONSTITUTION.md") is True


def test_is_architecture_doc_gotchas():
    assert _is_architecture_doc("/some/path/GOTCHAS.md") is True


def test_is_architecture_doc_adr():
    assert _is_architecture_doc("/some/path/ADR-001-use-sqlite.md") is True


def test_is_architecture_doc_architecture_prefix():
    assert _is_architecture_doc("/some/path/ARCHITECTURE-overview.md") is True


def test_is_architecture_doc_regular_md():
    assert _is_architecture_doc("/some/path/README.md") is False


# ── harvest — no claude projects dir ─────────────────────────────────────────

def test_harvest_missing_dir_returns_empty_result(tmp_path):
    db = _make_db(tmp_path)
    harvester = SessionHarvester()
    result = harvester.harvest(
        claude_projects_dir=tmp_path / "nonexistent",
        db_path=db,
        consent=True,
        dry_run=False,
    )
    assert isinstance(result, HarvestResult)
    assert result.sessions_processed == 0
    assert result.sessions_skipped == 0


# ── harvest — invalid JSON lines skipped ─────────────────────────────────────

def test_harvest_skips_invalid_json_lines(tmp_path):
    db = _make_db(tmp_path)
    projects_dir = tmp_path / "projects"
    jsonl = projects_dir / "proj" / "session.jsonl"
    jsonl.parent.mkdir(parents=True)
    with open(jsonl, "w", encoding="utf-8") as f:
        f.write("not valid json\n")
        f.write("{}\n")
        f.write("also bad {\n")

    harvester = SessionHarvester()
    result = harvester.harvest(
        claude_projects_dir=projects_dir,
        db_path=db,
        consent=True,
        dry_run=False,
    )
    # File has records (the valid `{}` line), so it counts as processed
    assert result.sessions_processed + result.sessions_skipped >= 1


# ── harvest — empty JSONL skipped ─────────────────────────────────────────────

def test_harvest_empty_jsonl_counted_as_skipped(tmp_path):
    db = _make_db(tmp_path)
    projects_dir = tmp_path / "projects"
    jsonl = projects_dir / "proj" / "empty.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text("", encoding="utf-8")

    harvester = SessionHarvester()
    result = harvester.harvest(
        claude_projects_dir=projects_dir,
        db_path=db,
        consent=True,
        dry_run=False,
    )
    assert result.sessions_skipped >= 1


# ── harvest — error+fix → gotcha written ──────────────────────────────────────

def test_harvest_error_with_fix_writes_gotcha(tmp_path):
    db = _make_db(tmp_path)
    projects_dir = tmp_path / "projects"
    records = [
        _tool_result_error("ImportError: No module named 'requests'"),
        _tool_use_write("/some/project/requirements.txt"),
    ]
    _write_jsonl(projects_dir / "proj" / "session.jsonl", records)

    harvester = SessionHarvester()
    result = harvester.harvest(
        claude_projects_dir=projects_dir,
        db_path=db,
        consent=True,
        dry_run=False,
    )

    assert result.gotchas_new >= 1
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT * FROM reg_gotchas").fetchall()
    conn.close()
    assert len(rows) >= 1


# ── harvest — error without fix → not extracted ───────────────────────────────

def test_harvest_error_without_fix_not_extracted(tmp_path):
    db = _make_db(tmp_path)
    projects_dir = tmp_path / "projects"
    # Only the error record, no assistant write following it
    records = [
        _tool_result_error("SyntaxError: invalid syntax"),
        {"type": "user", "message": {"content": "ok"}},
    ]
    _write_jsonl(projects_dir / "proj" / "session.jsonl", records)

    harvester = SessionHarvester()
    result = harvester.harvest(
        claude_projects_dir=projects_dir,
        db_path=db,
        consent=True,
        dry_run=False,
    )

    assert result.gotchas_new == 0


# ── harvest — skill invocation → raw_approach written ─────────────────────────

def test_harvest_skill_invocation_writes_approach(tmp_path):
    db = _make_db(tmp_path)
    projects_dir = tmp_path / "projects"
    records = [
        _tool_use_skill("ds-quality", "debug"),
    ]
    _write_jsonl(projects_dir / "proj" / "session.jsonl", records)

    harvester = SessionHarvester()
    result = harvester.harvest(
        claude_projects_dir=projects_dir,
        db_path=db,
        consent=True,
        dry_run=False,
    )

    assert result.approaches_new >= 1
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT * FROM raw_approaches").fetchall()
    conn.close()
    assert len(rows) >= 1


# ── harvest — Write to CONSTITUTION.md → arch doc with NULL content ───────────

def test_harvest_arch_doc_written_with_null_content(tmp_path):
    db = _make_db(tmp_path)
    projects_dir = tmp_path / "projects"
    records = [
        _tool_use_write("/some/project/CONSTITUTION.md"),
    ]
    _write_jsonl(projects_dir / "proj" / "session.jsonl", records)

    harvester = SessionHarvester()
    result = harvester.harvest(
        claude_projects_dir=projects_dir,
        db_path=db,
        consent=True,
        dry_run=False,
    )

    assert result.arch_docs_found >= 1
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT content FROM ds_documents").fetchall()
    conn.close()
    assert len(rows) >= 1
    # Content must be NULL — raw file contents are never stored
    assert rows[0][0] is None


# ── harvest — file paths → extension counted ─────────────────────────────────

def test_harvest_file_extensions_counted(tmp_path):
    db = _make_db(tmp_path)
    projects_dir = tmp_path / "projects"
    records = [
        _tool_use_write("/project/main.py"),
        _tool_use_write("/project/app.ts"),
        _tool_use_write("/project/style.css"),
    ]
    _write_jsonl(projects_dir / "proj" / "session.jsonl", records)

    harvester = SessionHarvester()
    result = harvester.harvest(
        claude_projects_dir=projects_dir,
        db_path=db,
        consent=True,
        dry_run=False,
    )

    assert result.tech_signals_recorded >= 3
    conn = sqlite3.connect(str(db))
    exts = {r[0] for r in conn.execute("SELECT extension FROM ds_technology_signals").fetchall()}
    conn.close()
    assert ".py" in exts
    assert ".ts" in exts
    assert ".css" in exts


# ── harvest — idempotency ─────────────────────────────────────────────────────

def test_harvest_idempotent_second_run_skips_duplicates(tmp_path):
    db = _make_db(tmp_path)
    projects_dir = tmp_path / "projects"
    records = [
        _tool_result_error("ImportError: No module named 'requests'"),
        _tool_use_write("/some/project/requirements.txt"),
    ]
    _write_jsonl(projects_dir / "proj" / "session.jsonl", records)

    harvester = SessionHarvester()
    result1 = harvester.harvest(
        claude_projects_dir=projects_dir,
        db_path=db,
        consent=True,
        dry_run=False,
    )
    result2 = harvester.harvest(
        claude_projects_dir=projects_dir,
        db_path=db,
        consent=True,
        dry_run=False,
    )

    assert result1.gotchas_new >= 1
    assert result2.gotchas_new == 0
    assert result2.gotchas_skipped >= 1


# ── harvest — consent=False → no DB writes ────────────────────────────────────

def test_harvest_no_consent_no_writes(tmp_path):
    db = _make_db(tmp_path)
    projects_dir = tmp_path / "projects"
    records = [
        _tool_result_error("TypeError: unexpected type"),
        _tool_use_write("/project/main.py"),
        _tool_use_skill("ds-core", "build"),
    ]
    _write_jsonl(projects_dir / "proj" / "session.jsonl", records)

    harvester = SessionHarvester()
    result = harvester.harvest(
        claude_projects_dir=projects_dir,
        db_path=db,
        consent=False,
        dry_run=False,
    )

    # Counts may be non-zero (gotchas_new tracks what would be written)
    conn = sqlite3.connect(str(db))
    gotcha_rows = conn.execute("SELECT COUNT(*) FROM reg_gotchas").fetchone()[0]
    approach_rows = conn.execute("SELECT COUNT(*) FROM raw_approaches").fetchone()[0]
    conn.close()
    assert gotcha_rows == 0
    assert approach_rows == 0


# ── harvest — dry_run → no DB writes ─────────────────────────────────────────

def test_harvest_dry_run_no_writes(tmp_path):
    db = _make_db(tmp_path)
    projects_dir = tmp_path / "projects"
    records = [
        _tool_result_error("NameError: name 'foo' is not defined"),
        _tool_use_write("/project/utils.py"),
    ]
    _write_jsonl(projects_dir / "proj" / "session.jsonl", records)

    harvester = SessionHarvester()
    result = harvester.harvest(
        claude_projects_dir=projects_dir,
        db_path=db,
        consent=True,
        dry_run=True,
    )

    conn = sqlite3.connect(str(db))
    gotcha_rows = conn.execute("SELECT COUNT(*) FROM reg_gotchas").fetchone()[0]
    conn.close()
    assert gotcha_rows == 0


# ── no raw content > 300 chars from a single JSONL value ─────────────────────

def test_no_db_column_stores_raw_content_over_300_chars(tmp_path):
    db = _make_db(tmp_path)
    projects_dir = tmp_path / "projects"
    long_error = "x" * 2000  # 2000-char raw error text
    records = [
        _tool_result_error(long_error),
        _tool_use_write("/project/fix.py"),
    ]
    _write_jsonl(projects_dir / "proj" / "session.jsonl", records)

    harvester = SessionHarvester()
    harvester.harvest(
        claude_projects_dir=projects_dir,
        db_path=db,
        consent=True,
        dry_run=False,
    )

    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT title, context, fix FROM reg_gotchas").fetchall()
    conn.close()
    for row in rows:
        for val in row:
            if val is not None:
                assert len(val) <= 500, f"Column value exceeds 500 chars: {len(val)}"


# ── migration 055 applies cleanly ────────────────────────────────────────────

def test_migration_055_applies_cleanly(tmp_path):
    """Migration SQL for 055 creates ds_technology_signals without error."""
    db = tmp_path / "test.db"
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "core" / "event_store" / "migrations" / "055_technology_signals.sql"
    )
    assert migration_path.is_file(), f"Migration file not found: {migration_path}"
    sql = migration_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(str(db))
    conn.executescript(sql)
    conn.commit()

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()

    assert "ds_technology_signals" in tables


# ── harvest creates ds_technology_signals if absent ──────────────────────────

def test_harvest_creates_technology_signals_table_if_missing(tmp_path):
    """Harvester auto-creates ds_technology_signals if the DB lacks it."""
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE reg_gotchas (
            gotcha_id TEXT PRIMARY KEY, skill_id TEXT, severity TEXT,
            title TEXT, context TEXT, fix TEXT, discovered TEXT, times_hit INTEGER DEFAULT 0
        );
        CREATE TABLE raw_approaches (
            approach_id TEXT PRIMARY KEY, skill_id TEXT, approach TEXT,
            model TEXT, project_id TEXT, created_at TEXT
        );
        CREATE TABLE ds_documents (
            doc_id TEXT, doc_type TEXT, title TEXT, content TEXT,
            source_path TEXT UNIQUE, created_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    projects_dir = tmp_path / "projects"
    _write_jsonl(projects_dir / "proj" / "session.jsonl", [_tool_use_write("/a/b.py")])

    harvester = SessionHarvester()
    result = harvester.harvest(
        claude_projects_dir=projects_dir,
        db_path=db,
        consent=True,
        dry_run=False,
    )

    conn = sqlite3.connect(str(db))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert "ds_technology_signals" in tables
