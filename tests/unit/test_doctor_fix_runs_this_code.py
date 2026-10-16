"""`ds doctor --fix` re-runs THIS Dream Studio against THIS home.

Round-table B4: the repair steps spawned `sys.executable -m interfaces.cli.ds ...`
without -I and without --home. From an installed app run inside a checkout, `-m`
put the working directory first on sys.path and the repair ran the checkout's code;
and without --home it repaired the default home, not the one doctor examined.
"""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

from core.config.paths import code_root


def test_every_repair_runs_isolated_from_this_code_root_against_this_home(tmp_path, monkeypatch):
    from core.health import doctor_main, main_ci

    home = tmp_path / "home"
    (home / "events" / "failed").mkdir(parents=True)
    (home / "events" / "failed" / "e1.json").write_text("{}", encoding="utf-8")
    claude = tmp_path / "claude"
    claude.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude))
    monkeypatch.setattr(main_ci, "main_ci_status", lambda **_: {"status": "unknown", "red": False})

    spawned: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        spawned.append([str(c) for c in cmd])
        return subprocess.CompletedProcess(cmd, 0)

    # Replace only doctor_main's own handle on subprocess, not subprocess.run for everyone.
    monkeypatch.setattr(doctor_main, "subprocess", types.SimpleNamespace(run=fake_run))
    doctor_main.run_doctor_checks(source_root=code_root(), dream_studio_home=home, fix=True)

    assert spawned, "no repair was attempted"
    for cmd in spawned:
        assert cmd[:4] == [sys.executable, "-I", "-X", "utf8"], cmd
        assert "-m" not in cmd[:6], f"`-m` puts the working directory on sys.path: {cmd}"
        assert cmd[6] == str(code_root()), "the child must import the code root doctor ran from"
        assert cmd[cmd.index("--home") + 1] == str(Path(home)), cmd


def test_the_repair_command_really_runs_ds_from_elsewhere(tmp_path):
    from core.health.doctor_main import _ds_command

    proc = subprocess.run(
        _ds_command(tmp_path / "home", "--help"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=tmp_path,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert "Dream Studio global command" in proc.stdout
