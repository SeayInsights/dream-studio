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
    commands = [
        h.get("command", "")
        for entry in event_hooks
        for h in entry.get("hooks", [])
    ]
    assert any("existing-user-hook" in c for c in commands)


def test_merge_skips_already_installed_ds_hook():
    existing = {
        "hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": _DS_HOOK_CMD}]}]
        }
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
