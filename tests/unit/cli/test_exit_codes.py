"""Verify ds CLI commands exit 0 on success."""

import subprocess
import pytest

READ_ONLY_COMMANDS = [
    ["py", "-m", "interfaces.cli.ds", "version"],
    ["py", "-m", "interfaces.cli.ds", "doctor"],
    ["py", "-m", "interfaces.cli.ds", "integrate", "status"],
    ["py", "-m", "interfaces.cli.ds", "project", "state"],
    ["py", "-m", "interfaces.cli.ds", "work-order", "list"],
    ["py", "-m", "interfaces.cli.ds", "projection", "daemon", "status"],
]


@pytest.mark.parametrize("cmd", READ_ONLY_COMMANDS)
def test_read_only_command_exits_zero(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert (
        result.returncode == 0
    ), f"Command {cmd} exited {result.returncode}, expected 0. stderr: {result.stderr}"
