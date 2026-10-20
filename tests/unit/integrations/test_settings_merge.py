from __future__ import annotations

import json

from integrations.targets.claude_code.settings_merge import merge_settings, settings_to_json

_DS_HOOK_CMD = (
    'python -c "import os,pathlib,runpy,sys; '
    "root=pathlib.Path(os.environ.get('CLAUDE_PLUGIN_ROOT') or os.getcwd()).resolve(); "
    "emitter=next((p/'emitters'/'claude_code'/'run.py' for p in (root,*root.parents) "
    "if (p/'emitters'/'claude_code'/'run.py').is_file()),None); "
    "sys.argv=[str(emitter),'UserPromptSubmit']; "
    "(runpy.run_path(str(emitter),run_name='__main__') if emitter else None); "
    'sys.exit(0)"'
)

_TEMPLATE_ENTRIES = [
    {"event": "UserPromptSubmit", "hooks": [{"type": "command", "command": _DS_HOOK_CMD}]},
]


def test_merge_adds_hooks_to_empty_settings():
    merged, _ = merge_settings({}, _TEMPLATE_ENTRIES)
    assert "hooks" in merged
    assert "UserPromptSubmit" in merged["hooks"]
    hooks_list = merged["hooks"]["UserPromptSubmit"]
    assert len(hooks_list) >= 1


def test_merge_preserves_existing_user_hooks():
    existing = {
        "hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "existing-user-hook"}]}]
        }
    }
    merged, _ = merge_settings(existing, _TEMPLATE_ENTRIES)
    event_hooks = merged["hooks"]["UserPromptSubmit"]
    commands = [h.get("command", "") for entry in event_hooks for h in entry.get("hooks", [])]
    assert any("existing-user-hook" in c for c in commands)


def test_merge_skips_already_installed_ds_hook():
    existing = {
        "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": _DS_HOOK_CMD}]}]}
    }
    merged, skip_reasons = merge_settings(existing, _TEMPLATE_ENTRIES)
    assert any("already installed" in r for r in skip_reasons)


def test_merge_never_deletes_existing_keys():
    existing = {"theme": "dark", "model": "claude", "hooks": {}}
    merged, _ = merge_settings(existing, _TEMPLATE_ENTRIES)
    assert merged["theme"] == "dark"
    assert merged["model"] == "claude"


def test_merge_does_not_duplicate_on_second_call():
    merged_first, _ = merge_settings({}, _TEMPLATE_ENTRIES)
    merged_second, skip_reasons = merge_settings(merged_first, _TEMPLATE_ENTRIES)
    assert any("already installed" in r for r in skip_reasons)
    event_hooks = merged_second["hooks"]["UserPromptSubmit"]
    ds_entries = [
        h
        for entry in event_hooks
        for h in entry.get("hooks", [])
        if "claude_code" in h.get("command", "") and "run.py" in h.get("command", "")
    ]
    assert len(ds_entries) == 1


def test_settings_to_json_produces_valid_json():
    settings = {"hooks": {"UserPromptSubmit": [{"hooks": []}]}}
    output = settings_to_json(settings)
    parsed = json.loads(output)
    assert parsed["hooks"]["UserPromptSubmit"]


# --- a Stop hook always has a timeout -------------------------------------------------
#
# Claude Code waits for a Stop hook, and one registered with no timeout may block a turn
# for as long as the harness allows: dispatcher processes were found 63 minutes old.


def _stop_entries():
    from integrations.compiler.claude_code import _load_hooks_template

    return [e for e in _load_hooks_template() if e.get("event") == "Stop"]


def test_every_stop_hook_in_the_template_carries_a_timeout():
    entries = _stop_entries()
    assert entries, "the template registers no Stop hook at all"
    missing = [
        h["command"]
        for e in entries
        for h in e["hooks"]
        if not isinstance(h.get("timeout"), int) or h["timeout"] <= 0
    ]
    assert missing == [], f"Stop hooks with no timeout: {missing}"


def test_an_install_that_predates_the_timeout_gains_it():
    """merge_settings skips a hook already installed by command, so the timeout the
    template gained never reached an existing install: they kept running with none."""
    entry = _stop_entries()[0]
    command = entry["hooks"][0]["command"]
    existing = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}
    assert "timeout" not in existing["hooks"]["Stop"][0]["hooks"][0]

    merged, _ = merge_settings(existing, [entry])

    installed = [h for e in merged["hooks"]["Stop"] for h in e["hooks"] if h["command"] == command]
    assert len(installed) == 1, "the backfill must edit the installed hook, not add a second"
    assert installed[0]["timeout"] == entry["hooks"][0]["timeout"]


def test_a_timeout_the_operator_set_is_never_overwritten():
    entry = _stop_entries()[0]
    command = entry["hooks"][0]["command"]
    existing = {
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": command, "timeout": 5}]}]}
    }

    merged, _ = merge_settings(existing, [entry])

    assert merged["hooks"]["Stop"][0]["hooks"][0]["timeout"] == 5
