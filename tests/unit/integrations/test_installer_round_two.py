"""The installer never rewires an app home, owns hooks by exact shape, retires copied
hooks safely, and runs them in UTF-8 mode.

B3  A checkout's files-mode install aimed at a self-installed home rewrote the app's
    launcher back to the checkout, stripped the sha from installed-version and
    registered every hook twice (module and file).
S1  purge_superseded_ds_hooks decided DS ownership by substring and removed foreign
    hooks that merely contained "hooks/run.py"; dedup compared only hooks[0].
S2  Running sessions keep the old commands; deleting the copied files in the same
    install made every old hook exit non-zero (blocking Edit/Write and Stop).
S6  Module hooks ran with -I, which ignores PYTHONIOENCODING: cp1252 stdio.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from integrations.installer.base import RefusalError
from integrations.installer.claude_code import ClaudeCodeInstaller


@pytest.fixture
def canonical_root(tmp_path):
    root = tmp_path / "src" / "canonical"
    skill = root / "skills" / "ds-bootstrap"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# bootstrap", encoding="utf-8")
    (root / "agents").mkdir()
    src = root.parent
    for rel in (
        "emitters/claude_code/run.py",
        "runtime/dispatch/hooks.py",
        "runtime/dispatch/__init__.py",
        "runtime/__init__.py",
        "runtime/hooks/meta/__init__.py",
        "runtime/hooks/meta/on-edit-enforce.py",
        "runtime/hooks/meta/on-stop-enforce.py",
        "runtime/hooks/meta/on-prompt-dispatch.py",
        "control/execution/dispatch_tracking.py",
    ):
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {rel}\n", encoding="utf-8")
    return root


def _install(config_root, canonical_root, ds_home, mode):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home, hook_mode=mode
    )
    with patch("integrations.installer.claude_code_launcher._write_path_to_profile") as prof:
        prof.return_value = {"profile": "x", "action": "skipped"}
        return installer.install("execute")


def _settings(config_root: Path) -> dict:
    return json.loads((config_root / "settings.json").read_text(encoding="utf-8"))


def _commands(config_root: Path) -> list[str]:
    return [
        h["command"]
        for entries in _settings(config_root).get("hooks", {}).values()
        for e in entries
        for h in e.get("hooks", [])
    ]


# --- B3 ---------------------------------------------------------------------------


def test_files_mode_refuses_a_self_installed_home(tmp_path, canonical_root, ds_home):
    (ds_home / "app" / "current").mkdir(parents=True)
    (ds_home / "state").mkdir(parents=True, exist_ok=True)
    (ds_home / "state" / "installed-version").write_text("0.1.0 abc\n", encoding="utf-8")
    config_root = tmp_path / "claude"
    config_root.mkdir()

    with pytest.raises(RefusalError, match="ds self-install --config-root"):
        _install(config_root, canonical_root, ds_home, "files")

    assert not (config_root / "settings.json").exists()
    assert not (ds_home / "bin").exists()
    assert (ds_home / "state" / "installed-version").read_text(encoding="utf-8") == "0.1.0 abc\n"


def test_files_mode_drops_module_commands_so_nothing_runs_twice(tmp_path, canonical_root, ds_home):
    config_root = tmp_path / "claude"
    config_root.mkdir()
    _install(config_root, canonical_root, ds_home, "module")
    _install(config_root, canonical_root, ds_home, "files")
    commands = _commands(config_root)
    assert commands
    assert not [c for c in commands if " -m " in c], commands


# --- S1 ---------------------------------------------------------------------------

FOREIGN = [
    'node "C:/tools/x/hooks/run.py.js" UserPromptSubmit',
    'python "C:/other-tool/hooks/run.py" Stop',
    'python "C:/elsewhere/hooks/dispatch/hooks.py" Stop',
    "python -c \"import runpy,pathlib; runpy.run_path(str(pathlib.Path('t')/'hooks.py'))\"",
    "node -m runtime.dispatch.hooks Stop",
]


def test_purge_removes_only_dream_studio_hooks(tmp_path, canonical_root, ds_home):
    config_root = tmp_path / "claude"
    config_root.mkdir()
    hooks_dir = str(config_root / "hooks").replace("\\", "/")
    ds_old = [
        f'"C:/py/python.exe" "{hooks_dir}/run.py" Stop',
        '"C:/old-app/venv/Scripts/python.exe" -I -m runtime.dispatch.hooks Stop',
    ]
    (config_root / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {"hooks": [{"type": "command", "command": c}]} for c in FOREIGN + ds_old
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    _install(config_root, canonical_root, ds_home, "module")
    commands = _commands(config_root)
    for c in FOREIGN:
        assert c in commands, f"a foreign hook was removed: {c}"
    for c in ds_old:
        assert c not in commands, f"a superseded Dream Studio hook survived: {c}"


def test_dedup_compares_whole_entries_and_only_drops_dream_studio_duplicates():
    from integrations.targets.claude_code.settings_merge import dedup_hooks_by_normalized_command

    hook = {"type": "command", "command": '"C:/a/python.exe" -I -m runtime.dispatch.hooks Stop'}
    other = {"type": "command", "command": "echo second-guard --flag b"}
    foreign = {"type": "command", "command": "echo foreign"}
    settings = {
        "hooks": {
            "Stop": [
                {"hooks": [hook]},
                {"hooks": [hook, other]},  # same first hook, different entry: keep
                {"hooks": [{"type": "command", "command": "guard --flag a"}]},
                {"hooks": [{"type": "command", "command": "guard --flag b"}]},
                {"hooks": [foreign]},
                {"hooks": [foreign]},  # a foreign duplicate is the operator's business
                {"hooks": [dict(hook)]},  # an exact Dream Studio duplicate: dropped
            ]
        }
    }
    entries = dedup_hooks_by_normalized_command(settings)["hooks"]["Stop"]
    assert len(entries) == 6
    assert sum(1 for e in entries if e["hooks"] == [foreign]) == 2


# --- S2 ---------------------------------------------------------------------------


def test_copied_hooks_become_stubs_first_and_go_on_the_next_install(
    tmp_path, canonical_root, ds_home
):
    config_root = tmp_path / "claude"
    config_root.mkdir()
    _install(config_root, canonical_root, ds_home, "files")
    hooks = config_root / "hooks"
    entry = hooks / "dispatch" / "hooks.py"
    handler = hooks / "runtime" / "hooks" / "meta" / "on-prompt-dispatch.py"
    assert entry.is_file() and handler.is_file()

    _install(config_root, canonical_root, ds_home, "module")
    # A session that started before this install still runs `python <hooks>/dispatch/hooks.py`.
    assert entry.is_file(), "the old entry point was deleted under a running session"
    proc = subprocess.run(
        [sys.executable, str(entry), "Stop"],
        input="{}",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert proc.returncode == 0
    assert "restart" in (proc.stdout + proc.stderr).lower()

    # A later install never deletes them: a session started before the FIRST install
    # can still be running, and a missing entry point exits non-zero, which blocks it.
    _install(config_root, canonical_root, ds_home, "module")
    assert entry.is_file() and handler.is_file()
    stub_text = entry.read_text(encoding="utf-8")
    _install(config_root, canonical_root, ds_home, "module")
    assert entry.read_text(encoding="utf-8") == stub_text

    # Only an explicit purge removes the retired tree.
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=canonical_root,
        ds_home=ds_home,
        hook_mode="module",
        purge_retired_hooks=True,
    )
    with patch("integrations.installer.claude_code_launcher._write_path_to_profile") as prof:
        prof.return_value = {"profile": "x", "action": "skipped"}
        installer.install("execute")
    assert not entry.exists() and not handler.exists()
    assert not [p for p in hooks.rglob("*") if p.is_file()] if hooks.exists() else True


def test_the_enforcement_entry_points_hand_off_instead_of_exiting_zero(
    tmp_path, canonical_root, ds_home
):
    """A retired on-edit-enforce/on-stop-enforce that exits 0 switches enforcement off
    in every running session. Their stubs run the installed module instead."""
    config_root = tmp_path / "claude"
    config_root.mkdir()
    _install(config_root, canonical_root, ds_home, "files")
    _install(config_root, canonical_root, ds_home, "module")
    hooks = config_root / "hooks"
    for rel, module in (
        ("runtime/hooks/meta/on-edit-enforce.py", "runtime.hooks.meta.on-edit-enforce"),
        ("runtime/hooks/meta/on-stop-enforce.py", "runtime.hooks.meta.on-stop-enforce"),
    ):
        text = (hooks / rel).read_text(encoding="utf-8")
        assert text.startswith("# dream-studio retired hook stub")
        assert f"MODULE = {module!r}" in text, text
        assert "sys.exit(proc.returncode)" in text
        assert "Restart this Claude Code session" not in text.split("except OSError")[0]


def test_doctor_counts_retired_stubs_as_expected_not_stale(tmp_path, canonical_root, ds_home):
    from core.health.doctor_checks import _check_hook_freshness

    config_root = tmp_path / "claude"
    config_root.mkdir()
    _install(config_root, canonical_root, ds_home, "files")
    _install(config_root, canonical_root, ds_home, "module")
    info = _check_hook_freshness(canonical_root, config_root)
    assert info["ok"], info
    assert info["stale"] == []
    assert set(info.get("retired", [])) >= {"dispatch/hooks.py", "run.py"}


# --- S6 ---------------------------------------------------------------------------


def test_module_hooks_run_in_utf8_mode(tmp_path, canonical_root, ds_home):
    config_root = tmp_path / "claude"
    config_root.mkdir()
    _install(config_root, canonical_root, ds_home, "module")
    ds = [c for c in _commands(config_root) if " -m " in c]
    assert ds and all(" -I -X utf8 -m " in c for c in ds), ds
