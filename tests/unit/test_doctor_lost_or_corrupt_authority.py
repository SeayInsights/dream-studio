"""An installed home whose authority is empty or corrupt does not read as healthy.

- A marked home with an EMPTY authority and no recorded baseline passed doctor: zero
  rows were notes, and with nothing to compare against there was no drop to warn on.
  That is exactly what a replaced authority looks like.
- A studio.db that is not a SQLite database made doctor, `self-install --dry-run` and
  `project state` print `{"ok": false, "error": "file is not a database"}` and nothing
  about restoring it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _home(tmp: Path) -> Path:
    home = tmp / "home"
    (home / "state").mkdir(parents=True)
    (home / "state" / "installed-version").write_text("0.1.0 " + "a" * 40 + "\n", encoding="utf-8")
    for sub in ("claude", "userhome", "work"):
        (tmp / sub).mkdir()
    return home


def _ds(tmp: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO", "DS_"))}
    env.update(
        {
            "PYTHONPATH": str(REPO),
            "PYTHONIOENCODING": "utf-8",
            "DREAM_STUDIO_HOME": str(tmp / "home"),
            "DREAM_STUDIO_DB_PATH": str(tmp / "home" / "state" / "studio.db"),
            "CLAUDE_CONFIG_DIR": str(tmp / "claude"),
            "HOME": str(tmp / "userhome"),
            "USERPROFILE": str(tmp / "userhome"),
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", "--home", str(tmp / "home"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp / "work",
        env=env,
        timeout=900,
    )


def _report(proc: subprocess.CompletedProcess) -> dict:
    start = proc.stdout.index("{")
    return json.loads(proc.stdout[start:])


def test_an_installed_homes_empty_authority_with_no_baseline_needs_attention(tmp_path, monkeypatch):
    from core.config.sqlite_bootstrap import (
        CREATE_AUTHORITY_ENV,
        bootstrap_database,
        shipped_released_version,
    )

    home = _home(tmp_path)
    db = home / "state" / "studio.db"
    monkeypatch.setenv(CREATE_AUTHORITY_ENV, str(db))
    bootstrap_database(db, target_version=shipped_released_version())
    proc = _ds(tmp_path, "doctor")
    report = _report(proc)
    assert proc.returncode == 1, proc.stdout[-1500:]
    assert report["status"] != "pass"
    warnings = report["checks"]["authority_data"]["warnings"]
    assert any("holds no" in w for w in warnings), warnings


CORRUPT = b"this is not a sqlite database at all " * 200


def test_a_corrupt_authority_routes_every_surface_to_restore(tmp_path):
    home = _home(tmp_path)
    (home / "state" / "studio.db").write_bytes(CORRUPT)

    doctor = _ds(tmp_path, "doctor")
    report = _report(doctor)
    assert "checks" in report, doctor.stdout[-1500:] + doctor.stderr[-1500:]
    assert doctor.returncode == 1
    text = json.dumps(report["checks"]["authority_data"])
    assert "restore" in text, text

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    identity = ["-c", "user.name=t", "-c", "user.email=t@t"]
    for cmd in (["init", "-q"], ["add", "."], [*identity, "commit", "-q", "-m", "one"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, capture_output=True)
    for args in (("project", "state"), ("self-install", "--dry-run", "--repo", str(repo))):
        proc = _ds(tmp_path, *args)
        out = proc.stdout + proc.stderr
        assert proc.returncode != 0, out[-1500:]
        assert "restore" in out and "not a" in out, out[-1500:]
    assert (home / "state" / "studio.db").read_bytes() == CORRUPT
