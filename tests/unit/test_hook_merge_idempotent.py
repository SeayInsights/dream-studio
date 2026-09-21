"""Installing Dream Studio twice must not make it run twice.

hooks/hooks.json ships a self-locating bootstrap (``python -c "...runpy..."``);
what lands in settings.json is the resolved ``"<abs python>" "<abs script>"
<Event>``. The two strings share no tail, so a tail comparison called them
different hooks and the merge appended a second group -- and every extra group
spawns another Python process that re-imports the DS core on every matching
tool call.

Verified live on 2026-09-21: re-running the installer against an
already-deduplicated settings.json re-created the duplicate. These tests exist
so the next re-run cannot.
"""

from __future__ import annotations

import json

import pytest

from interfaces.cli import setup_hooks
from interfaces.cli.setup_hooks import hook_identity

BOOTSTRAP = (
    'python -c "import os,pathlib,runpy,sys; '
    "root=pathlib.Path(os.environ.get('CLAUDE_PLUGIN_ROOT') or os.getcwd()).resolve(); "
    "dispatcher=next((p/'runtime'/'dispatch'/'hooks.py' for p in (root,*root.parents) "
    "if (p/'runtime'/'dispatch'/'hooks.py').is_file()),None); "
    "sys.argv=[str(dispatcher),'PostToolUse']; "
    "(runpy.run_path(str(dispatcher),run_name='__main__') if dispatcher else None); "
    'sys.exit(0)"'
)
RESOLVED = '"C:/Python312/python.exe" "C:/Users/x/.claude/hooks/dispatch/hooks.py" PostToolUse'


def test_bootstrap_and_resolved_forms_are_one_hook():
    """The regression that produced the duplicate group."""
    assert hook_identity(BOOTSTRAP) == hook_identity(RESOLVED)


def test_bare_and_absolute_interpreters_are_one_hook():
    """The earlier regression, still pinned."""
    bare = 'python "C:/Users/x/.claude/hooks/run.py" Stop'
    absolute = '"C:/Python312/python.exe" "C:/Users/x/.claude/hooks/run.py" Stop'
    assert hook_identity(bare) == hook_identity(absolute)


def test_the_installer_relocates_a_script_and_it_stays_one_hook():
    """emitters/claude_code/run.py is installed as ~/.claude/hooks/run.py."""
    source = 'python "emitters/claude_code/run.py" UserPromptSubmit'
    installed = '"C:/Python312/python.exe" "C:/Users/x/.claude/hooks/run.py" UserPromptSubmit'
    assert hook_identity(source) == hook_identity(installed)


@pytest.mark.parametrize(
    "a,b,why",
    [
        (
            'python "a/run.py" Stop',
            'python "a/hooks.py" Stop',
            "different handler scripts",
        ),
        (
            'python "a/hooks.py" Stop',
            'python "a/hooks.py" PostToolUse',
            "same script, different event",
        ),
        (
            'python "a/on-edit-enforce.py"',
            'python "a/on-stop-enforce.py"',
            "the two blocking enforcers",
        ),
    ],
)
def test_genuinely_different_hooks_stay_different(a, b, why):
    """Collapsing too much would silently drop a hook -- worse than a duplicate."""
    assert hook_identity(a) != hook_identity(b), why


def test_repeated_merge_adds_nothing(tmp_path, monkeypatch):
    """The property that matters: install N times, run once."""
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(setup_hooks, "SETTINGS_JSON", settings)

    def shape() -> dict[str, int]:
        hooks = json.loads(settings.read_text(encoding="utf-8")).get("hooks", {})
        return {e: sum(len(g.get("hooks", [])) for g in groups) for e, groups in hooks.items()}

    first = setup_hooks.step_settings_merge()
    assert first.passed
    after_first = shape()
    assert after_first, "the first merge must actually install something"

    for _ in range(3):
        assert setup_hooks.step_settings_merge().passed
    assert shape() == after_first, "a re-install must not add hook commands"


def test_no_event_registers_the_same_handler_twice(tmp_path, monkeypatch):
    """Per event, each logical hook appears exactly once."""
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(setup_hooks, "SETTINGS_JSON", settings)
    setup_hooks.step_settings_merge()

    hooks = json.loads(settings.read_text(encoding="utf-8")).get("hooks", {})
    for event, groups in hooks.items():
        identities = [
            hook_identity(h.get("command", "")) for g in groups for h in g.get("hooks", [])
        ]
        assert len(identities) == len(set(identities)), f"{event} registers a handler twice"
