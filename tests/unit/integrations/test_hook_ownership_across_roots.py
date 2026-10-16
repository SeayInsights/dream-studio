"""Which hook commands are Dream Studio's: across config roots, in uninstall, by name.

- A config root's settings.json can name Dream Studio entry scripts copied under a
  DIFFERENT root's hooks/ directory (`.claude-work` settings running
  `.claude/hooks/dispatch/hooks.py`). Ownership matched only this root's hooks/, so
  that command stayed beside the module hook and every hook fired twice.
- Uninstall decided ownership by substring (`hooks/run.py` anywhere) and dropped a
  whole entry when any of its hooks matched, taking an operator's hook with it.
- hook_identity keyed a module by its last component, so `foreignpkg.hooks` and
  Dream Studio's `runtime.dispatch.hooks` read as the same hook.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from integrations.targets.claude_code.settings_merge import (
    deregister_ds_hooks,
    is_ds_hook_command,
    purge_superseded_ds_hooks,
)
from interfaces.cli.setup_hooks import hook_identity

REPO = Path(__file__).resolve().parents[3]
MODULE_CMD = '"C:/ds/app/current/venv/Scripts/python.exe" -I -X utf8 -m runtime.dispatch.hooks Stop'


def _copied_entry(root: Path) -> Path:
    target = root / "hooks" / "dispatch" / "hooks.py"
    target.parent.mkdir(parents=True)
    shutil.copy2(REPO / "runtime" / "dispatch" / "hooks.py", target)
    return target


def test_a_ds_entry_copied_under_another_roots_hooks_is_recognised(tmp_path):
    other = _copied_entry(tmp_path / ".claude")
    this_hooks = tmp_path / ".claude-work" / "hooks"
    command = f'"C:/Python312/python.exe" "{other.as_posix()}" Stop'
    assert is_ds_hook_command(command, this_hooks)

    settings = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}
    purged, removed = purge_superseded_ds_hooks(settings, {MODULE_CMD}, this_hooks)
    assert removed == [command]
    assert "Stop" not in purged.get("hooks", {})


def test_a_look_alike_file_elsewhere_without_the_ds_signature_is_not_ours(tmp_path):
    foreign = tmp_path / "other-tool" / "hooks" / "dispatch" / "hooks.py"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("print('another tool')\n", encoding="utf-8")
    command = f'"C:/Python312/python.exe" "{foreign.as_posix()}" Stop'
    assert not is_ds_hook_command(command, tmp_path / ".claude" / "hooks")


def test_uninstall_removes_only_ds_hooks_and_keeps_the_operators_in_the_same_entry(tmp_path):
    root = tmp_path / ".claude"
    ours = _copied_entry(root)
    foreign_file = tmp_path / "other-tool" / "hooks" / "run.py"
    foreign_file.parent.mkdir(parents=True)
    foreign_file.write_text("print('mine')\n", encoding="utf-8")
    foreign = {"type": "command", "command": f'python "{foreign_file.as_posix()}" Stop'}
    ds = {"type": "command", "command": f'python "{ours.as_posix()}" Stop'}
    settings = {"hooks": {"Stop": [{"hooks": [ds, foreign]}]}}

    updated, removed = deregister_ds_hooks(settings, hooks_dir=root / "hooks")
    assert removed == 1
    assert updated["hooks"]["Stop"] == [{"hooks": [foreign]}]


def test_hook_identity_does_not_merge_a_foreign_module_with_a_ds_module():
    py = '"C:/py.exe" -I -m '
    assert hook_identity(py + "foreignpkg.hooks Stop") != hook_identity(
        py + "runtime.dispatch.hooks Stop"
    )
    assert hook_identity(py + "runtime.dispatch.hooks Stop") == hook_identity(
        '"C:/py.exe" "C:/x/.claude/hooks/dispatch/hooks.py" Stop'
    )
