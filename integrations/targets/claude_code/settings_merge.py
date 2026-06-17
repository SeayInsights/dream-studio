"""Additive JSON merge for Claude Code settings.json.

Rules:
- Never remove existing keys (except legacy DS hook commands — see purge_legacy_hooks).
- Append DS hook entries; skip if already present (same command path).
- If DS hook exists with different command path, mark for update (with backup).
- Never touch settings.local.json.
- Preserve key ordering where possible.
- Legacy `python -c` filesystem-walking DS hook commands are removed automatically
  once stable-path replacements are present.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

_DS_EMITTER_MARKERS = (
    "hooks\\run.py",  # installed path (Windows)
    "hooks/run.py",  # installed path (Unix)
    "emitters/claude_code/run.py",  # legacy: direct repo path reference
    "/'emitters'/'claude_code'/'run.py'",  # legacy: pathlib expression form
)

_DS_DISPATCHER_MARKERS = (
    "hooks\\dispatch\\hooks.py",  # installed path (Windows)
    "hooks/dispatch/hooks.py",  # installed path (Unix)
    "runtime/dispatch/hooks.py",  # legacy: direct repo path reference
    "'dispatch'/'hooks.py'",  # legacy: pathlib expression form
)


def _command_is_ds_emitter(command: str) -> bool:
    return any(m in command for m in _DS_EMITTER_MARKERS)


def _command_is_ds_dispatcher(command: str) -> bool:
    return any(m in command for m in _DS_DISPATCHER_MARKERS)


def _hook_event_has_ds_emitter(hook_list: list[Any], event_command: str) -> bool:
    """Return True if this event's hook list already has a DS emitter with the same command."""
    for entry in hook_list:
        hooks = entry.get("hooks", [])
        for h in hooks:
            if isinstance(h, dict) and _command_is_ds_emitter(h.get("command", "")):
                if h.get("command") == event_command:
                    return True
    return False


def _hook_event_has_any_ds_emitter(hook_list: list[Any]) -> bool:
    """Return True if any DS emitter (any command) is already registered for this event."""
    for entry in hook_list:
        hooks = entry.get("hooks", [])
        for h in hooks:
            if isinstance(h, dict) and _command_is_ds_emitter(h.get("command", "")):
                return True
    return False


# Marker identifying the legacy filesystem-walking one-liner pattern.
# The old installer generated: python -c "import os,pathlib,runpy,sys; ... runpy.run_path ..."
_LEGACY_COMMAND_MARKERS = ("python -c", "runpy.run_path", "pathlib.Path")


def _command_is_legacy_ds_hook(command: str) -> bool:
    """Return True if this command is a legacy DS filesystem-walking one-liner."""
    return all(m in command for m in _LEGACY_COMMAND_MARKERS)


def _event_has_stable_ds_hook(event_list: list[Any]) -> bool:
    """Return True if the event list has at least one new stable-path DS hook (emitter or dispatcher)."""
    stable_emitter_markers = ("hooks\\run.py", "hooks/run.py")
    stable_dispatcher_markers = ("hooks\\dispatch\\hooks.py", "hooks/dispatch/hooks.py")
    for entry in event_list:
        for h in entry.get("hooks", []):
            if not isinstance(h, dict):
                continue
            cmd = h.get("command", "")
            if any(m in cmd for m in stable_emitter_markers + stable_dispatcher_markers):
                return True
    return False


def purge_legacy_hooks(settings: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Remove legacy filesystem-walking DS hook entries from settings.

    Only removes legacy entries for events where a stable-path replacement is
    already present — never leaves an event with no DS hooks.

    Returns (cleaned_settings, list_of_removed_commands).
    """
    import copy as _copy

    result = _copy.deepcopy(settings)
    hooks_section = result.get("hooks", {})
    if not isinstance(hooks_section, dict):
        return result, []

    removed: list[str] = []

    for event, event_list in hooks_section.items():
        if not isinstance(event_list, list):
            continue
        if not _event_has_stable_ds_hook(event_list):
            continue  # No stable replacement yet — leave legacy entries in place

        cleaned: list[Any] = []
        for entry in event_list:
            hooks = entry.get("hooks", [])
            legacy_cmds = [
                h.get("command", "")
                for h in hooks
                if isinstance(h, dict) and _command_is_legacy_ds_hook(h.get("command", ""))
            ]
            if legacy_cmds:
                removed.extend(legacy_cmds)
                # Drop this entry entirely (it contained only legacy hooks)
            else:
                cleaned.append(entry)
        hooks_section[event] = cleaned

    return result, removed


def merge_settings(
    existing: dict[str, Any],
    new_hook_entries: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Merge DS hook entries into existing settings.

    Returns (merged_dict, list_of_skip_reasons).
    new_hook_entries: list from hooks_template.json, each with 'event' and 'hooks' keys.
    """
    result = OrderedDict(existing)
    if "hooks" not in result:
        result["hooks"] = {}
    hooks_section = result["hooks"]
    if not isinstance(hooks_section, dict):
        hooks_section = {}
        result["hooks"] = hooks_section

    skip_reasons: list[str] = []

    for entry in new_hook_entries:
        event = entry.get("event", "")
        new_hooks = entry.get("hooks", [])
        entry_matcher = entry.get("matcher")  # None means no matcher (fires on all tools)
        if not event or not new_hooks:
            continue

        event_list = hooks_section.get(event)
        if not isinstance(event_list, list):
            event_list = []
            hooks_section[event] = event_list

        for h in new_hooks:
            cmd = h.get("command", "")
            # Dedup: skip if same command + same matcher already registered
            if any(
                hh.get("command") == cmd
                for existing_entry in event_list
                for hh in existing_entry.get("hooks", [])
                if isinstance(hh, dict) and existing_entry.get("matcher") == entry_matcher
            ):
                skip_reasons.append(f"{event}: hook already installed (same command, same matcher)")
                continue

            new_event_entry: dict[str, Any] = {"hooks": [h]}
            if entry_matcher is not None:
                new_event_entry["matcher"] = entry_matcher

            if _command_is_ds_emitter(cmd) and _hook_event_has_any_ds_emitter(event_list):
                skip_reasons.append(
                    f"{event}: DS emitter present with different command path — update needed"
                )
            event_list.append(new_event_entry)

    return dict(result), skip_reasons


def dedup_hooks_by_normalized_command(
    settings: dict,
) -> dict:
    """Remove duplicate hook entries that differ only in slash style (/ vs \\).

    Cross-platform installs can leave both a backslash-path entry (Windows prior
    install) and a forward-slash-path entry (new template) for the same logical
    hook.  Exact string comparison in merge_settings treats them as different, so
    both survive.  This pass normalizes the path separators before comparing and
    drops any entry whose matcher+command key has already been seen.
    """
    for event in settings.get("hooks", {}):
        entries = settings["hooks"][event]
        seen: list[str] = []
        deduped: list = []
        for entry in entries:
            hooks = entry.get("hooks", [])
            matcher = entry.get("matcher", "")
            if not hooks:
                deduped.append(entry)
                continue
            cmd = hooks[0].get("command", "")
            normalized = cmd.replace("\\\\", "/").replace("\\", "/")
            key = f"{matcher}|{normalized}"
            if key not in seen:
                seen.append(key)
                deduped.append(entry)
        settings["hooks"][event] = deduped
    return settings


def purge_read_posttooluse_matcher(settings: dict[str, Any]) -> dict[str, Any]:
    """Remove any PostToolUse Read matcher entries.

    The Read matcher fires the dispatcher on every file read — pure overhead
    with no active consumer. Remove it so it never accumulates across reinstalls.
    """
    import copy as _copy

    result = _copy.deepcopy(settings)
    hooks_section = result.get("hooks", {})
    if not isinstance(hooks_section, dict):
        return result
    ptu = hooks_section.get("PostToolUse")
    if isinstance(ptu, list):
        hooks_section["PostToolUse"] = [entry for entry in ptu if entry.get("matcher") != "Read"]
    return result


def purge_all_hook_registrations(settings: dict[str, Any]) -> dict[str, Any]:
    """Remove the entire hooks section from a settings dict.

    Used for project-scope installs: hook event registrations belong only in the
    user-global ~/.claude/settings.json.  The project-scope .claude/settings.json
    must not register a second copy of runtime hooks or each event fires twice.
    """
    import copy as _copy

    result = _copy.deepcopy(settings)
    result.pop("hooks", None)
    return result


def _entry_is_ds_owned(entry: Any) -> bool:
    """Return True if a hook event entry was wired by Dream Studio.

    Matches emitter, dispatcher, and legacy one-liner commands so uninstall can
    remove every generation of DS wiring without touching foreign hooks.
    """
    if not isinstance(entry, dict):
        return False
    for h in entry.get("hooks", []):
        if not isinstance(h, dict):
            continue
        command = h.get("command", "")
        if (
            _command_is_ds_emitter(command)
            or _command_is_ds_dispatcher(command)
            or _command_is_legacy_ds_hook(command)
        ):
            return True
    return False


def deregister_ds_hooks(settings: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Remove every Dream-Studio-owned hook entry from a settings dict.

    Inverse of the additive install merge. Foreign (non-DS) hook entries are
    preserved. Events left empty are dropped; an emptied ``hooks`` section is
    removed entirely so reinstall starts clean. Never touches settings.local.json
    (the caller selects the path) or any non-``hooks`` key.

    Returns ``(new_settings, removed_count)``.
    """
    import copy as _copy

    result = _copy.deepcopy(settings)
    hooks_section = result.get("hooks")
    if not isinstance(hooks_section, dict):
        return result, 0
    removed = 0
    for event in list(hooks_section.keys()):
        entries = hooks_section.get(event)
        if not isinstance(entries, list):
            continue
        kept = [entry for entry in entries if not _entry_is_ds_owned(entry)]
        removed += len(entries) - len(kept)
        if kept:
            hooks_section[event] = kept
        else:
            hooks_section.pop(event, None)
    if not hooks_section:
        result.pop("hooks", None)
    return result, removed


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def settings_to_json(settings: dict[str, Any]) -> str:
    return json.dumps(settings, indent=2)
