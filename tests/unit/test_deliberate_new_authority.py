"""The deliberate way out of a lost authority is a way out, not a loop.

Every refusal told the operator to set DREAM_STUDIO_CREATE_AUTHORITY to the
authority's path to start over. With it set, the authority commands and the prompt
hook still refused (the lost-authority check ignored it), and no command would create
the file. `ds migrate init` now creates a new, empty authority at the released schema
when the override names it, and the refusals name that command.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def lost(tmp_path) -> Path:
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "state" / "installed-version").write_text("0.1.0 " + "a" * 40 + "\n", encoding="utf-8")
    (tmp_path / "userhome").mkdir()
    return tmp_path


def _run(
    tmp: Path, args: list[str], *, override: bool, stdin: str = ""
) -> subprocess.CompletedProcess:
    home = tmp / "home"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO", "DS_"))}
    env.update(
        {
            "PYTHONPATH": str(REPO),
            "PYTHONIOENCODING": "utf-8",
            "DREAM_STUDIO_HOME": str(home),
            "HOME": str(tmp / "userhome"),
            "USERPROFILE": str(tmp / "userhome"),
            "CLAUDE_CONFIG_DIR": str(tmp / "claude"),
        }
    )
    if override:
        env["DREAM_STUDIO_CREATE_AUTHORITY"] = str(home / "state" / "studio.db")
    return subprocess.run(
        [sys.executable, *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp,
        env=env,
        timeout=900,
    )


def _ds(tmp: Path, *args: str, override: bool) -> subprocess.CompletedProcess:
    return _run(
        tmp, ["-m", "interfaces.cli.ds", "--home", str(tmp / "home"), *args], override=override
    )


def test_the_override_and_migrate_init_create_a_new_authority(lost):
    from core.config.sqlite_bootstrap import shipped_released_version

    db = lost / "home" / "state" / "studio.db"
    proc = _ds(lost, "migrate", "init", override=True)
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-1500:]
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        assert conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] == (
            shipped_released_version()
        )
    finally:
        conn.close()

    listed = _ds(lost, "project", "list", override=True)
    assert listed.returncode == 0, listed.stderr[-1500:]


def test_with_the_override_set_nothing_says_the_authority_is_lost(lost):
    payload = json.dumps({"session_id": "s1", "prompt": "hello", "cwd": str(lost)})
    hook = _run(
        lost, ["-m", "runtime.dispatch.hooks", "UserPromptSubmit"], override=True, stdin=payload
    )
    assert "dream-studio-authority-lost" not in hook.stdout, hook.stdout[-1500:]
    status = _ds(lost, "migrate", "status", override=True)
    assert "dream-studio-authority-lost" not in status.stdout
    assert "do not re-create it" not in status.stdout + status.stderr


def test_without_the_override_migrate_init_refuses_and_names_the_way_out(lost):
    proc = _ds(lost, "migrate", "init", override=False)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "DREAM_STUDIO_CREATE_AUTHORITY=" in out and "migrate init" in out, out[-1500:]
    assert not (lost / "home" / "state" / "studio.db").exists()
