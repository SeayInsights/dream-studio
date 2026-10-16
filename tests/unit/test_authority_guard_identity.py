"""The authority guard keys on the file and on the configured authority, not on text.

Two holes in the guard's own bookkeeping:

- It remembered "this path held a real authority" by path. A long-running process
  (`ds mcp serve`, the dashboard) that verified the authority once accepted a 0-byte
  file that later replaced it at the same path, and migrated it into an empty
  authority.
- It recognised an authority only when the path was spelled exactly
  `<x>/state/studio.db`. `STATE\\Studio.db`, `state/x/../studio.db`, or an authority
  relocated with DREAM_STUDIO_DB_PATH all created a fresh, empty authority in a home
  that had an install.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import (
    CREATE_AUTHORITY_ENV,
    AuthorityRefusedError,
    bootstrap_database,
)

REPO = Path(__file__).resolve().parents[2]


def _marked(home: Path) -> Path:
    (home / "state").mkdir(parents=True, exist_ok=True)
    (home / "state" / "installed-version").write_text("0.1.0 abc\n", encoding="utf-8")
    return home


def _remove(db: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        part = Path(str(db) + suffix)
        if part.exists():
            part.unlink()


def test_a_zero_byte_replacement_is_refused_after_the_authority_was_verified(tmp_path, monkeypatch):
    from core.event_store.connection import _connect

    monkeypatch.setenv("DREAM_STUDIO_APPLY_UNRELEASED", "1")
    monkeypatch.delenv(CREATE_AUTHORITY_ENV, raising=False)
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    db = home / "state" / "studio.db"
    bootstrap_database(db)
    _marked(home)
    _connect(db).close()  # verified once, as a long-running process would

    _remove(db)
    sqlite3.connect(str(db)).close()  # a raw open somewhere re-creates it, 0 bytes
    assert db.stat().st_size == 0

    with pytest.raises(AuthorityRefusedError):
        _connect(db).close()
    assert db.stat().st_size == 0, "the empty replacement was migrated into an authority"


def test_a_schema_less_replacement_with_the_same_size_class_is_refused_too(tmp_path, monkeypatch):
    from core.event_store.connection import _connect

    monkeypatch.setenv("DREAM_STUDIO_APPLY_UNRELEASED", "1")
    monkeypatch.delenv(CREATE_AUTHORITY_ENV, raising=False)
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    db = home / "state" / "studio.db"
    bootstrap_database(db)
    _marked(home)
    _connect(db).close()

    _remove(db)
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE stray (x INTEGER)")
    conn.commit()
    conn.close()
    with pytest.raises(AuthorityRefusedError):
        _connect(db).close()


_CHILD = r"""
from core.config.sqlite_bootstrap import AuthorityRefusedError
from core.config.database import get_connection
try:
    get_connection().close()
    print("CREATED")
except AuthorityRefusedError:
    print("REFUSED")
"""


def _shape(tmp: Path, name: str) -> tuple[Path, Path]:
    home = _marked(tmp / name)
    return (
        home,
        {
            "canonical": home / "state" / "studio.db",
            "case-variant": home / "STATE" / "Studio.db",
            "dotdot": home / "state" / "x" / ".." / "studio.db",
            "renamed": home / "state" / "authority.db",
            "relocated": tmp / f"{name}-elsewhere" / "studio.db",
        }[name],
    )


@pytest.mark.parametrize("name", ["canonical", "case-variant", "dotdot", "renamed", "relocated"])
def test_the_configured_authority_of_a_marked_home_is_never_created(tmp_path, name):
    home, db = _shape(tmp_path, name)
    (tmp_path / "x").mkdir(exist_ok=True)
    (home / "state" / "x").mkdir(exist_ok=True)
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO", "DS_", "PYTHON"))
    }
    env.update(
        {
            "DREAM_STUDIO_HOME": str(home),
            "DREAM_STUDIO_DB_PATH": str(db),
            "DREAM_STUDIO_APPLY_UNRELEASED": "1",
            "PYTHONPATH": str(REPO),
        }
    )
    out = subprocess.run(
        [sys.executable, "-c", _CHILD],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert out.stdout.strip().splitlines()[-1:] == ["REFUSED"], out.stdout + out.stderr[-1500:]
    assert not Path(os.path.normpath(str(db))).exists()


def test_an_unmarked_home_still_creates_its_authority(tmp_path):
    home = tmp_path / "fresh"
    db = home / "state" / "studio.db"
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO", "DS_", "PYTHON"))
    }
    env.update(
        {
            "DREAM_STUDIO_HOME": str(home),
            "DREAM_STUDIO_DB_PATH": str(db),
            "DREAM_STUDIO_APPLY_UNRELEASED": "1",
            "PYTHONPATH": str(REPO),
        }
    )
    out = subprocess.run(
        [sys.executable, "-c", _CHILD],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert out.stdout.strip().splitlines()[-1:] == ["CREATED"], out.stdout + out.stderr[-1500:]
