"""version_current compares the commit, not only the version string.

VERSION has said 0.1.0 for every commit, so comparing versions alone reported any
older install as current.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.health.doctor_checks import _check_version_current
from tests.helpers.git_repo import commit, git, init_repo

VERSION = "0.1.0"


def _source(tmp_path: Path) -> tuple[Path, str]:
    """A source checkout of this test's own and the commit it is at.

    The tests compared against THIS clone's ``HEAD``, so they needed the clone to be a git
    repository (a source tarball is not) and answered for whichever commit happened to be
    checked out. The property is the same for any commit: the doctor reads the commit of the
    code it runs and compares it with the one recorded at install.
    """
    root = init_repo(tmp_path / "src")
    head = commit(root, "one", files={"VERSION": VERSION + "\n"})
    assert git(root, "rev-parse", "HEAD") == head
    return root, head


def _home(tmp_path: Path, marker: str) -> Path:
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "state" / "installed-version").write_text(marker + "\n", encoding="utf-8")
    return home


def test_an_older_commit_with_the_same_version_is_not_current(tmp_path):
    root, head = _source(tmp_path)
    info = _check_version_current(root, _home(tmp_path, f"{VERSION} {'0' * 40}"))
    assert info["current"] is False
    assert info["code_sha"] == head


def test_the_same_commit_is_current(tmp_path):
    root, head = _source(tmp_path)
    info = _check_version_current(root, _home(tmp_path, f"{VERSION} {head}"))
    assert info["current"] is True


def test_a_marker_without_a_sha_is_unknown_not_current(tmp_path):
    root, _head = _source(tmp_path)
    info = _check_version_current(root, _home(tmp_path, VERSION))
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
