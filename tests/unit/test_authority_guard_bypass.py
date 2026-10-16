"""The authority guard cannot be walked around through an empty file.

assert_may_create_database only asked whether
studio.db EXISTED. About 120 raw sqlite3.connect() call sites create a 0-byte file
on first touch -- the pulse's artifact read, the Stop handoff's config read, the
PostToolUse rubric check, doctor's main-CI cache -- and every guarded open after
that saw "an existing authority" and migrated it into an empty one. backup_db then
copied that empty database over studio.db.bak, the last copy of the real data.

These drive the real code paths in an installed home (state/installed-version)
whose authority is gone and require that nothing creates studio.db and that the
backup is never replaced by an empty or smaller database.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REFUSED = RuntimeError  # core.config.sqlite_bootstrap.AuthorityRefusedError


@pytest.fixture
def marked_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "state" / "installed-version").write_text("0.1.0 abc\n", encoding="utf-8")
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(home / "state" / "studio.db"))
    monkeypatch.delenv("DREAM_STUDIO_CREATE_AUTHORITY", raising=False)
    from core.config.database import DatabaseRuntime

    DatabaseRuntime.reset_instance()
    yield home
    DatabaseRuntime.reset_instance()


def _schema_less(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ds_config (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
    conn.commit()
    conn.close()


@pytest.mark.parametrize("shape", ["zero-byte", "schema-less"])
@pytest.mark.parametrize("creator", ["bootstrap_database", "_connect", "get_connection"])
def test_an_empty_or_schema_less_file_counts_as_missing(marked_home, shape, creator):
    from core.config.database import get_connection
    from core.config.sqlite_bootstrap import bootstrap_database
    from core.event_store.connection import _connect

    db = marked_home / "state" / "studio.db"
    if shape == "zero-byte":
        db.write_bytes(b"")
    else:
        _schema_less(db)
    run = {
        "bootstrap_database": lambda: bootstrap_database(db),
        "_connect": lambda: _connect(db).close(),
        "get_connection": lambda: get_connection().close(),
    }[creator]
    with pytest.raises(REFUSED, match="Refusing"):
        run()
    conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    finally:
        conn.close()
    assert "_schema_version" not in names, "the empty file was migrated into an authority"


def test_raw_readers_and_writers_never_create_the_authority(marked_home, tmp_path):
    db = marked_home / "state" / "studio.db"
    from core.config.authority import get_config_value, list_config, set_config_value
    from core.config.platform import ensure_platform_recorded
    from core.runtime_state import (
        db_clear_runtime_state,
        db_read_runtime_state,
        db_write_runtime_state,
    )
    from core.work_orders.artifacts import list_artifacts_by_kind

    assert get_config_value("context.window_tokens", db) is None
    assert list_config(db) == []
    with pytest.raises(sqlite3.Error):
        set_config_value("k", "v", db)
    assert db_read_runtime_state("platform") is None
    assert db_write_runtime_state("platform", {"x": 1}) is False
    assert db_clear_runtime_state("platform") is False
    assert list_artifacts_by_kind("escalation") == []
    ensure_platform_recorded(tmp_path / "platform.json")
    ensure_platform_recorded()
    assert not db.exists(), "a read path created studio.db"


def _real_authority(path: Path, projects: int) -> None:
    from core.config.sqlite_bootstrap import bootstrap_database

    bootstrap_database(path)
    conn = sqlite3.connect(path)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(business_projects)")]
        notnull = {r[1]: r[4] for r in conn.execute("PRAGMA table_info(business_projects)") if r[3]}
        for i in range(projects):
            values = {c: f"p{i}" for c in cols if c in notnull or c in ("project_id", "name")}
            conn.execute(
                f"INSERT INTO business_projects ({', '.join(values)}) VALUES "
                f"({', '.join('?' for _ in values)})",
                list(values.values()),
            )
        conn.commit()
    finally:
        conn.close()


def test_backup_never_replaces_a_backup_with_an_empty_or_smaller_authority(
    marked_home, monkeypatch
):
    from core.config import state

    db = marked_home / "state" / "studio.db"
    bak = marked_home / "state" / "studio.db.bak"
    monkeypatch.setenv("DREAM_STUDIO_APPLY_UNRELEASED", "1")
    _real_authority(bak, projects=2)
    original = hashlib.sha256(bak.read_bytes()).hexdigest()

    _schema_less(db)  # what a raw connect plus one CREATE TABLE leaves behind
    assert state.backup_db(force=True) is None
    assert hashlib.sha256(bak.read_bytes()).hexdigest() == original

    db.unlink()
    monkeypatch.setenv("DREAM_STUDIO_CREATE_AUTHORITY", str(db))
    _real_authority(db, projects=1)  # a real authority with FEWER business rows
    monkeypatch.delenv("DREAM_STUDIO_CREATE_AUTHORITY")
    state.backup_db(force=True)
    kept = sorted(p for p in bak.parent.glob("studio.db.bak*") if p != bak)
    assert any(
        hashlib.sha256(p.read_bytes()).hexdigest() == original for p in [bak, *kept]
    ), "the backup holding more business rows was overwritten"


def test_rehearsal_install_refuses_an_installed_home(marked_home):
    from core.installed_runtime import bootstrap_rehearsal_runtime

    with pytest.raises(REFUSED, match="installed"):
        bootstrap_rehearsal_runtime(source_root=REPO, dream_studio_home=marked_home)
    assert not (marked_home / "state" / "studio.db").exists()


def test_rehearsal_install_refuses_an_installed_home_that_still_has_its_authority(
    marked_home, monkeypatch
):
    """With the authority missing, the creation guard refuses whatever rehearsal-install
    does; only an installed home that STILL HAS its authority shows the rehearsal
    refusal itself, which keeps rehearsal-install from re-seeding the real authority."""
    from core.installed_runtime import bootstrap_rehearsal_runtime

    db = marked_home / "state" / "studio.db"
    monkeypatch.setenv("DREAM_STUDIO_APPLY_UNRELEASED", "1")
    monkeypatch.setenv("DREAM_STUDIO_CREATE_AUTHORITY", str(db))
    _real_authority(db, projects=2)
    monkeypatch.delenv("DREAM_STUDIO_CREATE_AUTHORITY")
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    with pytest.raises(REFUSED, match="Refusing rehearsal-install"):
        bootstrap_rehearsal_runtime(source_root=REPO, dream_studio_home=marked_home)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_rehearsal_install_reports_the_schema_it_reached(tmp_path, monkeypatch):
    from core.config.sqlite_bootstrap import applied_schema_version
    from core.installed_runtime import bootstrap_rehearsal_runtime

    home = tmp_path / "rehearsal"
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(home / "state" / "studio.db"))
    monkeypatch.delenv("DREAM_STUDIO_APPLY_UNRELEASED", raising=False)
    result = bootstrap_rehearsal_runtime(source_root=REPO, dream_studio_home=home)
    conn = sqlite3.connect(home / "state" / "studio.db")
    try:
        assert result["schema_version"] == applied_schema_version(conn)
    finally:
        conn.close()


def _hook(home: Path, module: str, event: str | None, payload: dict) -> int:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO", "DS_"))}
    env["DREAM_STUDIO_HOME"] = str(home)
    env["PYTHONPATH"] = str(REPO)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["DS_SPOOL_ROOT"] = str(home / "events")
    args = [sys.executable, "-m", module] + ([event] if event else [])
    return subprocess.run(
        args,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO,
        env=env,
        timeout=600,
    ).returncode


def test_real_hooks_and_doctor_never_recreate_a_lost_authority(tmp_path, monkeypatch):
    """The 2026-09-23 shape: an installed home, its studio.db gone, a good .bak beside it.
    A prompt (pulse due on a fresh home), an edit, a Stop and a plain doctor run."""
    home = tmp_path / "home"
    state_dir = home / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "installed-version").write_text("0.1.0 abc\n", encoding="utf-8")
    monkeypatch.setenv("DREAM_STUDIO_APPLY_UNRELEASED", "1")
    _real_authority(state_dir / "studio.db.bak", projects=1)
    bak_before = hashlib.sha256((state_dir / "studio.db.bak").read_bytes()).hexdigest()
    db = state_dir / "studio.db"

    prompt = {"session_id": "s1", "prompt": "hello", "cwd": str(tmp_path)}
    edit = {
        "session_id": "s1",
        "tool_name": "Edit",
        "tool_input": {"file_path": str(tmp_path / "x.py")},
        "cwd": str(tmp_path),
    }
    for module, event, payload in (
        ("emitters.claude_code.run", "UserPromptSubmit", prompt),
        ("runtime.dispatch.hooks", "UserPromptSubmit", prompt),
        ("runtime.hooks.meta.on-edit-enforce", None, edit),
        ("runtime.dispatch.hooks", "PostToolUse", edit),
        ("runtime.dispatch.hooks", "UserPromptSubmit", prompt),
        ("runtime.dispatch.hooks", "Stop", prompt),
        ("emitters.claude_code.run", "Stop", prompt),
    ):
        _hook(home, module, event, payload)
        assert not db.exists(), f"{module} {event or ''} created studio.db"

    env = {k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO", "DS_"))}
    env.update(PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", "--home", str(home), "doctor"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=tmp_path,
        env=env,
        timeout=900,
    )
    assert not db.exists(), "ds doctor created studio.db"
    assert hashlib.sha256((state_dir / "studio.db.bak").read_bytes()).hexdigest() == bak_before
