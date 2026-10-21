"""A test that leaves the isolation environment changed fails, and the next test is protected.

Defect of record, 2026-10-21 (issue #911): six tests in ``test_readmodel_wiring`` assigned
``os.environ["DREAM_STUDIO_HOME"]`` and removed it in ``finally``. The session home
``tests/conftest.py`` creates was then gone for the REST OF THE PROCESS, and every later test
that resolved the Dream Studio home fell back to ``~/.dream-studio`` -- the operator's real one.
The leaker passed. A neighbour failed, only in a large run, and passed alone.

The guard is ``pytest_runtest_setup`` / ``pytest_runtest_teardown`` in ``tests/conftest.py``.
Its behaviour is a property of how a pytest session is assembled, so each case runs a real
pytest in a subprocess against a COPY of that conftest, in a directory of its own: a leaking
test cannot be allowed to run inside this session to demonstrate itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_LEAKER = """
import os


def test_leaves_the_home_unset():
    os.environ.pop("DREAM_STUDIO_HOME", None)


def test_runs_after_and_must_still_see_the_session_home():
    assert os.environ.get("DREAM_STUDIO_HOME"), "the leak reached the next test"
"""

_CLEAN = """
import os


def test_restores_through_monkeypatch(monkeypatch, tmp_path):
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


def test_still_sees_the_session_home():
    assert os.environ.get("DREAM_STUDIO_HOME")
"""

_ASSIGNS = """
import os


def test_replaces_the_home():
    os.environ["DREAM_STUDIO_HOME"] = "C:/somewhere/else"


def test_after():
    assert os.environ["DREAM_STUDIO_HOME"] != "C:/somewhere/else"
"""


def _session(
    tmp_path: Path,
    test_source: str,
    extra_env: dict | None = None,
    pytest_args: tuple[str, ...] = (),
) -> str:
    tests = tmp_path / "tests"
    tests.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "tests" / "conftest.py", tests / "conftest.py")
    (tests / "__init__.py").write_text("", encoding="utf-8")
    (tests / "test_subject.py").write_text(test_source, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO_", "DS_"))}
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.update(extra_env or {})
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider", *pytest_args, "tests"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    return proc.stdout + proc.stderr


def test_a_test_that_unsets_the_session_home_is_failed_by_name_and_the_next_is_protected(tmp_path):
    out = _session(tmp_path, _LEAKER)
    assert "test_subject.py::test_leaves_the_home_unset" in out
    assert "left the isolation environment changed" in out, out
    assert "DREAM_STUDIO_HOME" in out
    # The value was put back: the NEXT test passes instead of reading the operator's home.
    assert "test_runs_after_and_must_still_see_the_session_home PASSED" in out, out


def test_a_test_that_replaces_the_session_home_is_failed(tmp_path):
    out = _session(tmp_path, _ASSIGNS)
    assert "left the isolation environment changed" in out, out
    assert "test_after PASSED" in out, out


def test_monkeypatch_is_not_a_leak(tmp_path):
    out = _session(tmp_path, _CLEAN)
    assert "left the isolation environment changed" not in out, out
    assert "2 passed" in out, out


_HOME_LEAK = """
import os


def test_changes_home_and_the_config_root():
    os.environ["HOME"] = "C:/not/the/home"
    os.environ["CLAUDE_CONFIG_DIR"] = "C:/not/the/identity"


def test_after():
    assert os.environ.get("HOME") != "C:/not/the/home"
    assert os.environ.get("CLAUDE_CONFIG_DIR") != "C:/not/the/identity"
"""


def test_a_test_that_changes_home_or_the_config_root_is_failed_and_restored(tmp_path):
    out = _session(tmp_path, _HOME_LEAK)
    assert "left the isolation environment changed" in out, out
    assert "HOME:" in out and "CLAUDE_CONFIG_DIR:" in out, out
    assert "test_after PASSED" in out, out


_FIXTURE_LEAK = """
import os

import pytest


@pytest.fixture
def sloppy_home():
    os.environ["DREAM_STUDIO_HOME"] = "C:/set/by/a/fixture"


def test_uses_the_sloppy_fixture(sloppy_home):
    assert os.environ["DREAM_STUDIO_HOME"] == "C:/set/by/a/fixture"


def test_after():
    assert os.environ["DREAM_STUDIO_HOME"] != "C:/set/by/a/fixture"
"""


def test_a_fixture_that_leaks_is_caught_because_the_snapshot_precedes_the_fixtures(tmp_path):
    out = _session(tmp_path, _FIXTURE_LEAK)
    assert "left the isolation environment changed" in out, out
    assert "test_after PASSED" in out, out


_AMBIENT = """
import os


def test_sees_no_ambient_claude_identity():
    for name in ("CLAUDE_CONFIG_DIR", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECTS_DIR"):
        assert name not in os.environ, f"{name} reached the test from the shell"


def test_can_still_set_one_for_itself(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert os.environ["CLAUDE_CONFIG_DIR"] == str(tmp_path)
"""


def test_the_shells_claude_code_identity_does_not_reach_a_test(tmp_path):
    out = _session(
        tmp_path,
        _AMBIENT,
        extra_env={
            "CLAUDE_CONFIG_DIR": str(tmp_path / "another-identity"),
            "CLAUDE_PLUGIN_ROOT": str(tmp_path / "a-plugin"),
            "CLAUDE_PROJECTS_DIR": str(tmp_path / "projects"),
        },
    )
    assert "2 passed" in out, out


_INSTALL_CHECK_AMBIENT = """
import os

import pytest

pytestmark = pytest.mark.install_check


def test_an_install_check_sees_the_operators_config_root():
    assert os.environ.get("CLAUDE_CONFIG_DIR") == os.environ["EXPECTED_CONFIG_DIR"]
"""

_NOT_AN_INSTALL_CHECK = """
import os


def test_an_ordinary_test_in_the_same_session_does_not():
    assert "CLAUDE_CONFIG_DIR" not in os.environ
"""


def test_an_install_check_sees_the_operators_config_root_and_no_other_test_does(tmp_path):
    """The scrub must not blind the tests whose whole job is to check the operator's install."""
    identity = str(tmp_path / "another-identity")
    extra_env = {"CLAUDE_CONFIG_DIR": identity, "EXPECTED_CONFIG_DIR": identity}
    checked = _session(
        tmp_path / "a",
        _INSTALL_CHECK_AMBIENT,
        extra_env=extra_env,
        pytest_args=("-m", "install_check"),
    )
    assert "1 passed" in checked, checked
    ordinary = _session(tmp_path / "b", _NOT_AN_INSTALL_CHECK, extra_env=extra_env)
    assert "1 passed" in ordinary, ordinary


def test_the_install_checks_read_the_identity_the_shell_names_not_dot_claude(tmp_path):
    """The failure the verifier reproduced: a decoy root whose CLAUDE.md says nothing is here
    must FAIL ``test_installed_claude_md_carries_the_routing_table``, not read ``~/.claude``."""
    decoy = tmp_path / "decoy-identity"
    decoy.mkdir()
    (decoy / "CLAUDE.md").write_text("DECOY nothing here" + chr(10), encoding="utf-8")
    source = (REPO_ROOT / "tests" / "install_checks" / "test_installed_copies.py").read_text(
        encoding="utf-8"
    )
    out = _session(
        tmp_path / "session",
        source,
        extra_env={"CLAUDE_CONFIG_DIR": str(decoy)},
        pytest_args=("-m", "install_check", "-k", "routing_table"),
    )
    assert "test_installed_claude_md_carries_the_routing_table FAILED" in out, out
    assert "CLAUDE.md missing routing markers" in out, out
