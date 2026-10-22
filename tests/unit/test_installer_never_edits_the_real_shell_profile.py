"""No test edits the operator's shell profile.

Defect of record, 2026-10-21 (issue #911 inventory): the installer's last step appends a PATH line
to the shell profile. On Windows it finds the profile by running ``powershell -Command $PROFILE``,
whose answer comes from the registry and ignores ``HOME`` and ``USERPROFILE`` -- so a test that
redirected the home still pointed the installer at the operator's real
``Microsoft.PowerShell_profile.ps1``. 77 tests across 26 files reached it.

``tests/conftest.py`` replaces the function the launcher looks up for every test. These pin that
the replacement is active, that a test can still reach the real function, and that nothing in the
tests asks PowerShell where the profile is without going through it.
"""

from __future__ import annotations

import re
from pathlib import Path

from integrations.installer import claude_code_launcher as launcher
from integrations.installer.claude_code import _write_path_to_profile as real_write_path_to_profile

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_global_launcher_step_leaves_the_profile_alone(tmp_path):
    result = launcher._write_global_launcher(ds_home=tmp_path / "ds_home")
    assert result["path_result"]["action"] == "skipped", result["path_result"]
    assert "never edit" in result["path_result"]["reason"]
    assert (tmp_path / "ds_home" / "bin").is_dir(), "the launcher itself is still written"


def test_the_real_function_stays_reachable_for_a_test_of_it(tmp_path, monkeypatch):
    """A test of the function itself imports it by name from the facade, bound before the
    fixture ran, and redirects the home the way test_installer_complete does."""
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert real_write_path_to_profile is not launcher._write_path_to_profile
    result = real_write_path_to_profile(tmp_path / "bin")
    assert result["action"] == "appended"
    assert (tmp_path / ".bashrc").is_file()


def test_nothing_in_the_tests_asks_powershell_where_the_profile_is():
    """The only caller of ``powershell -Command $PROFILE`` is the launcher, and it is stubbed."""
    offenders = []
    for path in sorted((REPO_ROOT / "tests").rglob("test_*.py")):
        if re.search(r"\$PROFILE", path.read_text(encoding="utf-8", errors="ignore")):
            if path.name != Path(__file__).name:
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []
