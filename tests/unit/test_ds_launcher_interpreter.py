"""ds.ps1 runs the CLI with a Python that actually runs, preferring the one in use.

FOUND BY A PR'S WINDOWS CI. Two launcher tests failed only on the GitHub Windows runner:
ds.ps1 asked `py -3` first, and the launcher's default is the newest Python INSTALLED, not
the setup-python interpreter on PATH that holds the dependencies -- so the CLI died on
`import jsonschema` before it started. They passed locally and on every PR that did not
happen to select them, which is how a latent bug stays latent.

The launcher also trusted names: `Get-Command` finds the Microsoft Store alias stub for
`python`, which prints "Python was not found" and exits 9009. Every candidate is now
PROBED by running it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "ds.ps1"

pytestmark = pytest.mark.skipif(os.name != "nt", reason="ds.ps1 is the Windows launcher")

STORE_STUB = "@echo off\r\necho Python was not found; run without arguments to install from the Microsoft Store.\r\nexit /b 9009\r\n"


def _system_path() -> str:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.pathsep.join(
        [
            os.path.join(root, "System32"),
            os.path.join(root, "System32", "WindowsPowerShell", "v1.0"),
        ]
    )


def _launch(tmp_path: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(LAUNCHER),
            "version",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def test_a_store_alias_stub_is_skipped_for_a_python_that_runs(tmp_path):
    """The trap, staged: `python3` is the Store stub and `python` is a working interpreter.
    The old launcher trusted names in the order py, python3, python -- so with no `py` on
    PATH it ran the stub and exited 9009. Probing each candidate skips the stub."""
    shims = tmp_path / "shims"
    shims.mkdir()
    (shims / "python3.bat").write_text(STORE_STUB, encoding="ascii")
    (shims / "python.bat").write_text(f'@"{sys.executable}" %*\r\n', encoding="ascii")

    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PATH", "DS_PYTHON")}
    env["PATH"] = os.pathsep.join([str(shims), _system_path()])

    result = _launch(tmp_path, env)
    assert result.returncode == 0, (result.stdout[-400:], result.stderr[-400:])
    assert "9009" not in result.stdout + result.stderr


def test_an_explicit_ds_python_outranks_every_guess(tmp_path):
    """With every name on PATH a Store stub, DS_PYTHON is still honoured."""
    shims = tmp_path / "shims"
    shims.mkdir()
    for name in ("python.bat", "python3.bat"):
        (shims / name).write_text(STORE_STUB, encoding="ascii")

    env = {k: v for k, v in os.environ.items() if k.upper() != "PATH"}
    env["PATH"] = os.pathsep.join([str(shims), _system_path()])
    env["DS_PYTHON"] = sys.executable

    result = _launch(tmp_path, env)
    assert result.returncode == 0, (result.stdout[-400:], result.stderr[-400:])


def test_no_working_python_says_so_rather_than_running_a_stub(tmp_path):
    shims = tmp_path / "shims"
    shims.mkdir()
    for name in ("python.bat", "python3.bat"):
        (shims / name).write_text(STORE_STUB, encoding="ascii")

    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PATH", "DS_PYTHON")}
    env["PATH"] = os.pathsep.join([str(shims), _system_path()])

    result = _launch(tmp_path, env)
    assert result.returncode != 0
    assert "No working Python found" in result.stdout + result.stderr


# ── ds.cmd, the preferred plain-command launcher ─────────────────────────────

CMD_LAUNCHER = REPO_ROOT / "ds.cmd"


def _launch_cmd(launcher: Path, tmp_path: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["cmd", "/c", str(launcher), "version"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def test_ds_cmd_skips_a_store_alias_stub(tmp_path):
    """The old ds.cmd ran whatever `where python` found; here that is the stub, and it
    exited 9009. Probing skips it for the python3 that works."""
    shims = tmp_path / "shims"
    shims.mkdir()
    (shims / "python.bat").write_text(STORE_STUB, encoding="ascii")
    (shims / "python3.bat").write_text(f'@"{sys.executable}" %*\r\n', encoding="ascii")

    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PATH", "DS_PYTHON")}
    env["PATH"] = os.pathsep.join([str(shims), _system_path()])

    result = _launch_cmd(CMD_LAUNCHER, tmp_path, env)
    assert result.returncode == 0, (result.stdout[-400:], result.stderr[-400:])


# ── the launchers `ds install-command` writes ────────────────────────────────


def test_a_generated_launcher_runs_the_python_that_installed_it(tmp_path):
    """Written at install time, it knows the absolute interpreter that ran the install and
    tries it before anything on PATH -- here every name on PATH is a stub."""
    from core.installed_productization_setup import (
        _windows_cmd_launcher,
        _windows_powershell_launcher,
    )

    shims = tmp_path / "shims"
    shims.mkdir()
    for name in ("python.bat", "python3.bat"):
        (shims / name).write_text(STORE_STUB, encoding="ascii")
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PATH", "DS_PYTHON")}
    env["PATH"] = os.pathsep.join([str(shims), _system_path()])
    home = tmp_path / "home"

    cmd = tmp_path / "ds.cmd"
    cmd.write_text(_windows_cmd_launcher(REPO_ROOT, home), encoding="utf-8")
    result = _launch_cmd(cmd, tmp_path, env)
    assert result.returncode == 0, ("cmd", result.stdout[-400:], result.stderr[-400:])

    ps1 = tmp_path / "ds.ps1"
    ps1.write_text(_windows_powershell_launcher(REPO_ROOT, home), encoding="utf-8")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1), "version"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode == 0, ("ps1", result.stdout[-400:], result.stderr[-400:])


# ── one order, four launchers ────────────────────────────────────────────────


def _all_launchers() -> dict[str, str]:
    from core.installed_productization_setup import (
        _windows_cmd_launcher,
        _windows_powershell_launcher,
    )

    return {
        "ds.ps1": LAUNCHER.read_text(encoding="utf-8"),
        "ds.cmd": CMD_LAUNCHER.read_text(encoding="utf-8"),
        "generated ds.cmd": _windows_cmd_launcher(REPO_ROOT, REPO_ROOT),
        "generated ds.ps1": _windows_powershell_launcher(REPO_ROOT, REPO_ROOT),
    }


@pytest.mark.parametrize("name", ["ds.ps1", "ds.cmd", "generated ds.cmd", "generated ds.ps1"])
def test_every_launcher_probes_and_asks_python_before_the_py_launcher(name):
    """Four places decided which Python runs the CLI, and all four asked `py` first and
    trusted a name without running it. They agree now, and this holds them to it -- a fifth
    launcher, or one of these reverting, fails here rather than on someone's machine."""
    text = _all_launchers()[name]
    assert "import sys; sys.exit(0)" in text, f"{name} does not probe its candidates"
    python_at = text.find('"python"') if name.endswith("ps1") else text.find("call :probe python ")
    py_at = text.find('"py", "-3"') if name.endswith("ps1") else text.find("call :probe py -3")
    assert python_at != -1 and py_at != -1, f"{name} lost a candidate"
    assert python_at < py_at, f"{name} asks the py launcher before python"
