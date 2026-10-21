"""``install_check`` tests are opt-in: absent from a default run, present when asked for.

The marker exists so that a check about THIS machine (an install under ~/.claude) can live
in the repository without being part of the suite that gates a push. Two ways for that to go
wrong, both pinned here:

* it is collected by default -- the operator's machine decides the suite's result again;
* it is collected by default and SKIPS when the install is absent -- a test that cannot fail.

The mechanism is ``pytest_collection_modifyitems`` in ``tests/conftest.py``. Each case runs
pytest as a subprocess against the real ``tests/install_checks`` package, because the
behaviour under test is how a session is assembled, which an in-process call cannot show.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_FILE = "test_installed_copies.py"


def _collect(*args: str) -> str:
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
    proc = subprocess.run(
        # `-o addopts=` drops the project's `-v`, which turns the id listing into a tree.
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            *args,
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )
    return proc.stdout + proc.stderr


def test_a_default_run_does_not_collect_install_checks():
    out = _collect("tests/install_checks")
    assert f"{CHECK_FILE}::" not in out, f"an install check was collected by default:\n{out}"
    assert "deselected" in out, "the install checks must be reported as deselected, not skipped"


def test_marking_expression_that_excludes_them_does_not_collect_them():
    out = _collect("-m", "not install_check", "tests/install_checks")
    assert f"{CHECK_FILE}::" not in out, out


def test_asking_for_them_by_marker_collects_them():
    out = _collect("-m", "install_check", "tests/install_checks")
    assert f"{CHECK_FILE}::test_installed_claude_md_carries_the_routing_table" in out, out
    assert f"{CHECK_FILE}::test_installed_hook_copies_match_canonical" in out, out


def test_every_install_check_carries_the_marker():
    """A test added to tests/install_checks without the marker would join the default run."""
    import ast

    for path in sorted((REPO_ROOT / "tests" / "install_checks").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        marked = any(
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets)
            and "install_check" in ast.unparse(node.value)
            for node in tree.body
        )
        assert marked, f"{path.name} has no module-level pytestmark = pytest.mark.install_check"
