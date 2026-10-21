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

_LEAKER = '''
import os


def test_leaves_the_home_unset():
    os.environ.pop("DREAM_STUDIO_HOME", None)


def test_runs_after_and_must_still_see_the_session_home():
    assert os.environ.get("DREAM_STUDIO_HOME"), "the leak reached the next test"
'''

_CLEAN = '''
import os


def test_restores_through_monkeypatch(monkeypatch, tmp_path):
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


def test_still_sees_the_session_home():
    assert os.environ.get("DREAM_STUDIO_HOME")
'''

_ASSIGNS = '''
import os


def test_replaces_the_home():
    os.environ["DREAM_STUDIO_HOME"] = "C:/somewhere/else"


def test_after():
    assert os.environ["DREAM_STUDIO_HOME"] != "C:/somewhere/else"
'''


def _session(tmp_path: Path, test_source: str) -> str:
    tests = tmp_path / "tests"
    tests.mkdir()
    shutil.copyfile(REPO_ROOT / "tests" / "conftest.py", tests / "conftest.py")
    (tests / "__init__.py").write_text("", encoding="utf-8")
    (tests / "test_subject.py").write_text(test_source, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO_", "DS_"))}
    env["PYTHONPATH"] = str(REPO_ROOT)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider", "tests"],
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
