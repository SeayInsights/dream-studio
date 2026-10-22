"""The suite gives the same answer whichever directory pytest is launched from.

Defect of record, 2026-10-21 (issue #911): ``pytest --rootdir <repo> <absolute paths>`` run from
a temporary directory failed 15 tests and errored 2 more -- ``test_exit_codes`` (a ``python -m
interfaces.cli.ds`` subprocess with no ``cwd=``), ``test_admission`` (a ``TEST-CHECK`` path
resolved against the working directory), ``test_agent_inlined_imports`` (``Path("canonical/
skills")``) -- and ``test_the_end_is_stamped_before_close_grades_anything`` reads
``Path("core/work_orders/close_main.py")``. Each assumed the process started in the checkout.

``tests/conftest.py`` now starts every test in the repository root. These run the very files
that failed, in a real pytest in a subprocess launched from a directory that is not the
repository, so a regression of the fixture shows as the same failures it used to.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Files that failed from another directory, and one test from each family that did.
_WERE_FAILING = (
    "tests/unit/cli/test_exit_codes.py::test_read_only_command_exits_zero",
    "tests/unit/test_admission.py::test_a_duplicate_title_is_refused",
    "tests/unit/test_admission.py::test_the_node_id_path_check_is_unchanged",
    "tests/unit/test_agent_inlined_imports.py",
    "tests/unit/test_delivery_boundary.py::test_the_end_is_stamped_before_close_grades_anything",
)


def test_the_files_that_failed_from_another_directory_pass_from_one(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--rootdir",
            str(REPO_ROOT),
            "-c",
            str(REPO_ROOT / "pyproject.toml"),
            "-p",
            "no:cacheprovider",
            "-q",
            "-o",
            "addopts=",
            *[str(REPO_ROOT / rel) for rel in _WERE_FAILING],
        ],
        cwd=str(elsewhere),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-4000:]
    assert " failed" not in out and " error" not in out, out[-4000:]
    assert " passed" in out, out[-4000:]
