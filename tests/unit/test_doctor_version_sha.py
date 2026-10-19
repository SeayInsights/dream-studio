"""version_current compares the commit, not only the version string.

VERSION has said 0.1.0 for every commit, so comparing versions alone reported any
older install as current.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from core.health.doctor_checks import _check_version_current

REPO = Path(__file__).resolve().parents[2]


def _head() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()


def _home(tmp_path: Path, marker: str) -> Path:
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "state" / "installed-version").write_text(marker + "\n", encoding="utf-8")
    return home


def test_an_older_commit_with_the_same_version_is_not_current(tmp_path):
    version = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    info = _check_version_current(REPO, _home(tmp_path, f"{version} {'0' * 40}"))
    assert info["current"] is False
    assert info["code_sha"] == _head()


def test_the_same_commit_is_current(tmp_path):
    version = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    info = _check_version_current(REPO, _home(tmp_path, f"{version} {_head()}"))
    assert info["current"] is True


def test_a_marker_without_a_sha_is_unknown_not_current(tmp_path):
    version = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    info = _check_version_current(REPO, _home(tmp_path, version))
    assert info["current"] is None
    assert info["reason"]


def test_an_installed_app_compares_its_own_app_record(tmp_path):
    app = tmp_path / "app" / "0.1.0-abc"
    code_root = app / "venv" / "Lib" / "site-packages"
    code_root.mkdir(parents=True)
    (code_root / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (app / "app.json").write_text(json.dumps({"version": "0.1.0", "sha": "a" * 40}), "utf-8")
    assert _check_version_current(code_root, _home(tmp_path, f"0.1.0 {'a' * 40}"))["current"]
    other = tmp_path / "other"
    other.mkdir()
    assert _check_version_current(code_root, _home(other, f"0.1.0 {'b' * 40}"))["current"] is False
