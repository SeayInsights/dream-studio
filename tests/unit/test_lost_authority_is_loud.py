"""A home that has had an install and lost its authority says so everywhere.

With studio.db gone from an installed home every surface read as healthy:
UserPromptSubmit printed the onboarding banner and "Pulse check complete ...
HEALTHY", `ds escalation list` said "No open escalations." and exited 0, `ds pulse`
said HEALTHY, `ds validate` exited 0 with ready:false and no guidance, and `ds migrate
status` advised `migrate activate`, which the guard then refuses.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def lost(tmp_path) -> Path:
    home = tmp_path / "home"
    (home / "state" / "backups" / "self-install-x").mkdir(parents=True)
    (home / "state" / "installed-version").write_text("0.1.0 " + "a" * 40 + "\n", encoding="utf-8")
    for sub in ("claude", "userhome", "project"):
        (tmp_path / sub).mkdir()
    return tmp_path


def _env(tmp: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO", "DS_"))}
    env.update(
        {
            "PYTHONPATH": str(REPO),
            "PYTHONIOENCODING": "utf-8",
            "DREAM_STUDIO_HOME": str(tmp / "home"),
            "DREAM_STUDIO_DB_PATH": str(tmp / "home" / "state" / "studio.db"),
            "CLAUDE_CONFIG_DIR": str(tmp / "claude"),
            "HOME": str(tmp / "userhome"),
            "USERPROFILE": str(tmp / "userhome"),
        }
    )
    return env


def _run(tmp: Path, args: list[str], stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp / "project",
        env=_env(tmp),
        timeout=900,
    )


def test_a_prompt_in_a_home_that_lost_its_authority_carries_the_restore_guidance(lost):
    payload = json.dumps(
        {
            "session_id": "s1",
            "prompt": "hello",
            "cwd": str(lost / "project"),
            "hook_event_name": "UserPromptSubmit",
        }
    )
    proc = _run(lost, ["-m", "runtime.dispatch.hooks", "UserPromptSubmit"], payload)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = proc.stdout
    assert "restore" in out.lower() and "authority" in out.lower(), out[-2000:]
    assert "HEALTHY" not in out, out[-2000:]
    assert "studio-onboard" not in out, "the onboarding nag must not hide a lost authority"
    assert not (lost / "home" / "state" / "studio.db").exists()


@pytest.mark.parametrize(
    "command",
    [
        ["escalation", "list"],
        ["pulse"],
        ["validate"],
        ["migrate", "status"],
    ],
)
def test_cli_commands_refuse_loudly_in_a_home_that_lost_its_authority(lost, command):
    proc = _run(lost, ["-m", "interfaces.cli.ds", "--home", str(lost / "home"), *command])
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out[-2000:]
    assert "restore" in out.lower(), out[-2000:]
    assert "HEALTHY" not in out and "No open escalations" not in out, out[-2000:]
    assert "migrate activate" not in out, out[-2000:]
    assert not (lost / "home" / "state" / "studio.db").exists()
