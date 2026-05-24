"""Verify ds CLI commands exit 0 on success."""

import subprocess
import sys

import pytest

READ_ONLY_COMMANDS = [
    ["py", "-m", "interfaces.cli.ds", "version"],
    ["py", "-m", "interfaces.cli.ds", "doctor"],
    ["py", "-m", "interfaces.cli.ds", "integrate", "status"],
    ["py", "-m", "interfaces.cli.ds", "projection", "daemon", "status"],
]


@pytest.fixture()
def bootstrapped_db(tmp_path, monkeypatch):
    """Rehearsal-install a fresh DB and register a test project.

    Subprocesses spawned during the test inherit the monkeypatched env vars
    and therefore use this DB rather than the session-scoped empty tmp DB.
    """
    rehearsal_home = tmp_path / "rehearsal"
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(rehearsal_home))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(rehearsal_home / "state" / "studio.db"))

    result = subprocess.run(
        [
            "py",
            "-m",
            "interfaces.cli.ds",
            "rehearsal-install",
            "--rehearsal-home",
            str(rehearsal_home),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.fail(
            f"rehearsal-install failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    result = subprocess.run(
        [
            "py",
            "-m",
            "interfaces.cli.ds",
            "project",
            "register",
            "--name",
            "Test",
            "--path",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.fail(
            f"project register failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    yield rehearsal_home


@pytest.mark.parametrize("cmd", READ_ONLY_COMMANDS)
def test_read_only_command_exits_zero(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert (
        result.returncode == 0
    ), f"Command {cmd} exited {result.returncode}, expected 0. stderr: {result.stderr}"


def test_project_state_exits_zero(bootstrapped_db):
    result = subprocess.run(
        ["py", "-m", "interfaces.cli.ds", "project", "state"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (
        result.returncode == 0
    ), f"ds project state exited {result.returncode}. stderr: {result.stderr}"
    assert (
        "Test" in result.stdout
    ), f"Expected registered project 'Test' in output:\n{result.stdout}"


def test_work_order_list_exits_zero(bootstrapped_db):
    result = subprocess.run(
        ["py", "-m", "interfaces.cli.ds", "work-order", "list"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (
        result.returncode == 0
    ), f"ds work-order list exited {result.returncode}. stderr: {result.stderr}"
