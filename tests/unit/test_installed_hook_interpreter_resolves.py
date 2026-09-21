"""The interpreter written into settings.json is one that exists.

hooks/hooks.json is a template and cannot carry a machine-specific path, so every hook entry
begins with bare ``python``. ``step_settings_merge`` used to copy that verbatim into the
operator's ``~/.claude/settings.json``.

On a stock Windows box, bare ``python`` is the Microsoft Store App Execution Alias: a
zero-byte stub that prints "Python was not found" and exits 9009 without running anything.
Every Dream Studio hook would be silently dead there, and silently is the operative word --
a hook that never runs produces no error, just an absence.

The answer already existed in this repository. ``claude_code_shared._python_cmd`` resolves the
absolute ``sys.executable`` for the other install door, and its docstring records the same
lesson from WO-INSTALL-PY-ABS. Two doors disagreed about the interpreter; this one now asks
the same function instead of carrying a second answer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from interfaces.cli.setup_hooks import resolve_hook_command

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"


def _template_commands() -> list[str]:
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    return [
        hook["command"]
        for groups in data.get("hooks", {}).values()
        for group in groups
        for hook in group.get("hooks", [])
        if hook.get("command")
    ]


def test_the_template_really_does_ship_bare_python():
    """If this stops being true the substitution below is guarding nothing."""
    commands = _template_commands()
    assert commands, "hooks.json registered no commands"
    assert any(c.startswith("python ") for c in commands)


def test_every_template_command_resolves_to_a_real_interpreter():
    for command in _template_commands():
        resolved = resolve_hook_command(command)
        assert not resolved.startswith("python "), f"still bare: {resolved[:60]}"
        # The quoting convention differs per platform; the executable path is what matters.
        assert Path(sys.executable).stem in resolved


def test_an_already_resolved_command_is_left_alone():
    """A re-run must not rewrite an operator's own absolute-path edit."""
    for already in ('"C:/Python312/python.exe" -c "x"', "py script.py", "/usr/bin/python3 -c 'x'"):
        assert resolve_hook_command(already) == already


def test_resolution_is_idempotent():
    """`ds setup` runs more than once; the second run must produce the same string."""
    for command in _template_commands():
        once = resolve_hook_command(command)
        assert resolve_hook_command(once) == once


def test_a_command_that_is_not_python_is_untouched():
    assert resolve_hook_command("node index.js") == "node index.js"
    assert resolve_hook_command("") == ""
