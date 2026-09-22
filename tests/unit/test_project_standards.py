"""A project declares how it is verified, and Dream Studio stops assuming pytest.

THE DEFECT. `_run_one_test_check` ran a bare TEST-CHECK target as
``sys.executable -m pytest <target>`` in the work order's TARGET repo. Measured on a
scratch JS project carrying a real ``src/foo.test.js``:

    TEST-CHECK could not run: pytest USAGE ERROR - the node id is wrong or the file
    does not exist here (exit 4)
    ERROR: not found: .../src/foo.test.js

The file exists. The verdict reports a defect in the CRITERION when the fault is that
Dream Studio ran a tool the project does not use, so a reviewer reading it learns
something false about the work.
"""

from __future__ import annotations

import pathlib

import pytest

from core.projects.standards import (
    STANDARDS_PATH,
    is_pytest,
    standards_for,
    targeted_command,
    declared_test_profile,
)
from core.work_orders.verify_executor import _run_one_test_check


def _project(tmp_path: pathlib.Path, profile: str | None) -> pathlib.Path:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "foo.test.js").write_text("test('x', () => {})", encoding="utf-8")
    if profile is not None:
        (tmp_path / STANDARDS_PATH[0]).mkdir(parents=True, exist_ok=True)
        (tmp_path / pathlib.Path(*STANDARDS_PATH)).write_text(profile, encoding="utf-8")
    return tmp_path


# ── reading the declaration ─────────────────────────────────────────────────


def test_a_project_that_declares_nothing_has_no_profile(tmp_path):
    assert standards_for(_project(tmp_path, None)) == {}
    assert declared_test_profile(_project(tmp_path, None)) == {}
    assert standards_for(None) == {}


def test_both_spellings_collapse_to_one_shape(tmp_path):
    """No caller should have to know which form a project used."""
    short = declared_test_profile(_project(tmp_path / "a", "test: npm test\n"))
    long = declared_test_profile(_project(tmp_path / "b", "test:\n  command: npm test\n"))
    assert short == long == {"command": "npm test"}


def test_malformed_yaml_is_no_profile_rather_than_an_exception(tmp_path):
    """A profile is an optimisation over a working default. A syntax error in it must not
    make the project unverifiable -- without a profile, every project behaves as it did
    before profiles existed."""
    root = _project(tmp_path, "test: [unclosed\n")
    assert standards_for(root) == {}
    assert declared_test_profile(root) == {}


def test_a_yaml_document_that_is_not_a_mapping_is_no_profile(tmp_path):
    assert standards_for(_project(tmp_path, "- just\n- a list\n")) == {}


@pytest.mark.parametrize(
    "command",
    ["pytest", "pytest -q", "py.test tests/", "python -m pytest", "/usr/bin/pytest", "pytest.exe"],
)
def test_declaring_pytest_is_recognised_as_the_existing_default(command):
    assert is_pytest(command) is True


@pytest.mark.parametrize("command", ["npm test", "go test ./...", "cargo test", "dotnet test"])
def test_other_runners_are_not_pytest(command):
    assert is_pytest(command) is False


# ── what the executor does with it ──────────────────────────────────────────


def test_a_declared_non_pytest_runner_refuses_rather_than_running_pytest(tmp_path):
    """THE MUTANT THIS EXISTS FOR. Falling back to pytest here is the original bug: it
    runs a tool the project does not use and then reports the criterion as wrong."""
    check = _run_one_test_check("src/foo.test.js", _project(tmp_path, "test: npm test\n"))
    assert check["executed"] is False, "pytest was run in a project that declared npm"
    assert check["passed"] is False
    reason = str(check["not_executed_reason"])
    assert "npm test" in reason
    assert "cmd:" in reason, "the remedy is not named"
    assert "with_target" in reason


def test_with_target_is_used_verbatim_and_the_target_substituted(tmp_path):
    """Declaring `with_target` is the project saying "here is how"; it is not guessed at."""
    root = _project(
        tmp_path,
        "test:\n"
        "  command: fake-runner\n"
        "  with_target: py -c \"import sys; sys.exit(0 if sys.argv[1] == 'src/foo.test.js'"
        ' else 9)" {target}\n',
    )
    check = _run_one_test_check("src/foo.test.js", root)
    assert check["executed"] is True
    assert check["passed"] is True, check.get("error")


def test_a_project_declaring_nothing_still_runs_pytest(tmp_path):
    """The change must be invisible to every project that has no profile -- which is all
    of them until one is written."""
    check = _run_one_test_check("src/foo.test.js", _project(tmp_path, None))
    assert check["executed"] is True
    assert "pytest" in str(check["error"])


def test_a_project_declaring_pytest_still_runs_pytest(tmp_path):
    check = _run_one_test_check("src/foo.test.js", _project(tmp_path, "test: pytest -q\n"))
    assert check["executed"] is True
    assert "pytest" in str(check["error"])


def test_the_cmd_form_bypasses_the_profile_entirely(tmp_path):
    """`cmd:` is the author saying exactly what to run, which is more specific than the
    project's default and must not be second-guessed by it."""
    check = _run_one_test_check("cmd: py -c pass", _project(tmp_path, "test: npm test\n"))
    assert check["executed"] is True
    assert check["passed"] is True, check.get("error")


# ── the resolution helper, directly ─────────────────────────────────────────


def test_targeted_command_reports_no_opinion_when_there_is_none(tmp_path):
    assert targeted_command(_project(tmp_path / "a", None), "x") == (None, None)
    assert targeted_command(_project(tmp_path / "b", "test: pytest\n"), "x") == (None, None)


def test_targeted_command_refuses_rather_than_guessing(tmp_path):
    command, refusal = targeted_command(_project(tmp_path, "test: go test ./...\n"), "pkg/x")
    assert command is None
    assert refusal and "go test" in refusal
