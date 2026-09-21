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
import shlex
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


def test_every_template_command_resolves_to_an_executable_that_exists():
    """The bug this guards: bare ``python`` is a Store alias stub that runs nothing.

    Originally this asserted the resolved command contained the running
    interpreter. That was a proxy for the real property -- "the thing named here
    exists and will run" -- and it stopped being true when the append-only hook
    gained a compiled enqueuer, which is an executable but not a Python one.
    Assert the property directly so the guard survives the next language.
    """
    for command in _template_commands():
        resolved = resolve_hook_command(command)
        assert not resolved.startswith("python "), f"still bare: {resolved[:60]}"
        exe = shlex.split(resolved, posix=False)[0].strip('"')
        assert Path(exe).is_file(), f"resolved to something that does not exist: {exe}"


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


# ---------------------------------------------------------------------------------------
# The merge must REPLACE an equivalent hook, not append a second copy.
#
# Measured on the operator's machine: ~/.claude/settings.json held 23 hook commands where 12
# were intended. Every duplicate was a pair -- `python <script>` written by an older install,
# and `"C:/.../python.exe" <script>` written after the interpreter was resolved. The merge
# compared whole command strings, so the two looked unrelated and both were kept, and every
# handler ran twice per event. Four Stop hooks firing per turn is what made a turn feel hung.
# ---------------------------------------------------------------------------------------

import interfaces.cli.setup_hooks as setup_hooks  # noqa: E402


def _settings_at(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    monkeypatch.setattr(setup_hooks, "SETTINGS_JSON", settings)
    return settings


def _commands(settings: Path) -> list[str]:
    data = json.loads(settings.read_text(encoding="utf-8"))
    return [
        hook["command"]
        for groups in data.get("hooks", {}).values()
        for group in groups
        for hook in group.get("hooks", [])
    ]


def test_the_two_spellings_of_one_hook_have_one_identity():
    bare = 'python -c "print(1)"'
    resolved = resolve_hook_command(bare)
    assert resolved != bare, "the fixture needs the two forms to differ"
    assert setup_hooks.hook_identity(bare) == setup_hooks.hook_identity(resolved)


def test_a_hook_that_is_not_python_is_compared_whole():
    """`node a.js` and `node b.js` must not collapse into one hook."""
    assert setup_hooks.hook_identity("node a.js") != setup_hooks.hook_identity("node b.js")
    assert setup_hooks.hook_identity("node a.js") == "node a.js"


def test_the_bare_twin_is_repaired_in_place_instead_of_duplicated(tmp_path, monkeypatch):
    """The measured defect, reproduced: a settings.json written by an older install."""
    settings = _settings_at(tmp_path, monkeypatch)
    template = _template_commands()[0]
    assert template.startswith("python "), "the template should still ship the bare form"
    event = next(iter(json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]))
    settings.write_text(
        json.dumps({"hooks": {event: [{"hooks": [{"type": "command", "command": template}]}]}}),
        encoding="utf-8",
    )

    result = setup_hooks.step_settings_merge()
    assert result.passed, result.detail

    commands = _commands(settings)
    assert commands.count(template) == 0, "the bare command survived beside its resolved twin"
    assert resolve_hook_command(template) in commands
    assert len(commands) == len(set(commands)), f"duplicate hook commands: {commands}"


def test_an_operators_own_absolute_interpreter_is_left_alone(tmp_path, monkeypatch):
    """An absolute interpreter already runs, and choosing it may have been deliberate.

    Healing it would silently undo a venv or a pinned version; appending beside it would
    recreate the duplicate this fix exists to remove. Neither: it is the same hook.
    """
    settings = _settings_at(tmp_path, monkeypatch)
    template = _template_commands()[0]
    event = next(iter(json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]))
    chosen = '"C:/venv/Scripts/python.exe" ' + template[len("python ") :]  # noqa: E203
    settings.write_text(
        json.dumps({"hooks": {event: [{"hooks": [{"type": "command", "command": chosen}]}]}}),
        encoding="utf-8",
    )

    assert setup_hooks.step_settings_merge().passed
    commands = _commands(settings)
    assert chosen in commands, "the operator's interpreter was overwritten"
    assert len(commands) == len(set(commands)), f"duplicate hook commands: {commands}"
    assert (
        sum(
            1 for c in commands if setup_hooks.hook_identity(c) == setup_hooks.hook_identity(chosen)
        )
        == 1
    )


def test_running_setup_twice_adds_nothing_the_second_time(tmp_path, monkeypatch):
    settings = _settings_at(tmp_path, monkeypatch)
    assert setup_hooks.step_settings_merge().passed
    after_first = _commands(settings)
    assert after_first, "the first merge wrote nothing"

    assert setup_hooks.step_settings_merge().passed
    assert _commands(settings) == after_first
    assert len(after_first) == len(set(after_first)), f"duplicates on first run: {after_first}"
