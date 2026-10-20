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
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

#: The modules a Dream Studio hook command runs, in module mode.
DS_HOOK_MODULES = frozenset(
    {
        "emitters.claude_code.run",
        "runtime.dispatch.hooks",
        "runtime.hooks.meta.on-edit-enforce",
        "runtime.hooks.meta.on-stop-enforce",
    }
)
#: The scripts a files-mode install copies under <config_root>/hooks and registers.
DS_HOOK_FILES = frozenset(
    {
        "run.py",
        "dispatch/hooks.py",
        "runtime/hooks/meta/on-edit-enforce.py",
        "runtime/hooks/meta/on-stop-enforce.py",
    }
)

#: Text every Dream Studio entry script carries near its top: how a copy under ANOTHER
#: config root's hooks/ directory is recognised as ours rather than by its name alone.
_DS_ENTRY_SIGNATURES = {
    "run.py": "Spool emitter for Claude Code hooks",
    "dispatch/hooks.py": "Tool-agnostic hook event dispatcher",
    "runtime/hooks/meta/on-edit-enforce.py": "Hook: on-edit-enforce",
    "runtime/hooks/meta/on-stop-enforce.py": "Hook: on-stop-enforce",
}
_RETIRED_STUB_MARKER = "# dream-studio retired hook stub"

_TOKEN = re.compile(r'"([^"]*)"|(\S+)')
_PYTHON = re.compile(r"^(python(\d+(\.\d+)?)?w?|py)(\.exe)?$", re.IGNORECASE)


def _tokens(command: str) -> list[str]:
    return [quoted if quoted else bare for quoted, bare in _TOKEN.findall(command)]


def is_ds_hook_command(command: str, hooks_dir: Path | None = None) -> bool:
    """True only for the exact shapes Dream Studio writes, never a substring match.

    - module form: a Python interpreter, its flags, then `-m <one of DS_HOOK_MODULES>`;
    - files form: a Python interpreter running one of DS_HOOK_FILES under *hooks_dir*
      (or, with no hooks_dir, under a directory named `hooks`);
    - a Dream Studio entry script copied under ANOTHER config root's hooks/ directory
      (`.claude-work` settings running `.claude/hooks/dispatch/hooks.py`), when the
      file itself carries the Dream Studio signature: left in place it ran beside the
      module hook and every hook fired twice.

    `node .../hooks/run.py.js`, `python .../other-tool/hooks/run.py` with another
    hooks_dir and no signature, a `python -c` one-liner or `node -m
    runtime.dispatch.hooks` are not ours.
    """
    tokens = _tokens(command)
    if len(tokens) < 2 or not _PYTHON.match(Path(tokens[0].replace("\\", "/")).name):
        return False
    rest = tokens[1:]
    i = 0
    while i < len(rest) and rest[i].startswith("-") and rest[i] != "-m":
        if rest[i] in ("-c",):
            return False
        i += 2 if rest[i] == "-X" else 1
    if i < len(rest) and rest[i] == "-m":
        return i + 1 < len(rest) and rest[i + 1] in DS_HOOK_MODULES
    if i >= len(rest):
        return False
    script = rest[i].replace("\\", "/")
    if hooks_dir is not None:
        if not (Path(script).is_absolute() or script.startswith("/")):
            # A relative script runs from the directory that holds the config root.
            script = (Path(hooks_dir).parent.parent / script).as_posix()
        root = str(hooks_dir).replace("\\", "/").rstrip("/") + "/"
        prefix = len(root)
        if script.lower().startswith(root.lower()):
            return script[prefix:] in DS_HOOK_FILES
        return any(
            script.endswith("/hooks/" + rel) and _carries_ds_signature(Path(script), rel)
            for rel in DS_HOOK_FILES
        )
    return any(script.endswith("/hooks/" + rel) for rel in DS_HOOK_FILES)


def _carries_ds_signature(path: Path, rel: str) -> bool:
    """Whether the file at *path* is a copy of Dream Studio's entry script *rel* (or the
    stub a module-mode install left in its place). Reads only the first few KB."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            head = handle.read(4096)
    except OSError:
        return False
    return head.startswith(_RETIRED_STUB_MARKER) or _DS_ENTRY_SIGNATURES[rel] in head


_DS_EMITTER_MARKERS = (
    "hooks\\run.py",  # installed path (Windows)
    "hooks/run.py",  # installed path (Unix)
    "emitters/claude_code/run.py",  # legacy: direct repo path reference
    "/'emitters'/'claude_code'/'run.py'",  # legacy: pathlib expression form
    "-m emitters.claude_code.run",  # module mode: an installed app's package
)

_DS_DISPATCHER_MARKERS = (
    "hooks\\dispatch\\hooks.py",  # installed path (Windows)
    "hooks/dispatch/hooks.py",  # installed path (Unix)
    "runtime/dispatch/hooks.py",  # legacy: direct repo path reference
    "'dispatch'/'hooks.py'",  # legacy: pathlib expression form
    "-m runtime.dispatch.hooks",  # module mode: an installed app's package
)

_DS_ENFORCEMENT_MARKERS = (
    "on-edit-enforce.py",
    "on-stop-enforce.py",
    "-m runtime.hooks.meta.on-edit-enforce",  # module mode
    "-m runtime.hooks.meta.on-stop-enforce",  # module mode
)


def _command_is_ds_enforcement(command: str) -> bool:
    return any(m in command for m in _DS_ENFORCEMENT_MARKERS)


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


#: The script each legacy Dream Studio one-liner searched for, as it spelled the path.
_LEGACY_DS_TARGETS = (
    "'emitters'/'claude_code'/'run.py'",
    "'dispatch'/'hooks.py'",
    "'runtime'/'dispatch'/'hooks.py'",
    "'meta'/'on-edit-enforce.py'",
    "'meta'/'on-stop-enforce.py'",
)


def _command_is_legacy_ds_hook(command: str) -> bool:
    """Return True if this command is a legacy DS filesystem-walking one-liner.

    Any `python -c` one-liner using runpy and pathlib is not enough: it must search for
    one of Dream Studio's own hook scripts, or another tool's runpy hook was removed.
    """
    return all(m in command for m in _LEGACY_COMMAND_MARKERS) and any(
        t in command for t in _LEGACY_DS_TARGETS
    )


def _event_has_stable_ds_hook(event_list: list[Any]) -> bool:
    """Return True if the event list has at least one new stable-path DS hook
    (emitter, dispatcher, or enforcement)."""
    stable_emitter_markers = ("hooks\\run.py", "hooks/run.py", "-m emitters.claude_code.run")
    stable_dispatcher_markers = (
        "hooks\\dispatch\\hooks.py",
        "hooks/dispatch/hooks.py",
        "-m runtime.dispatch.hooks",
    )
    for entry in event_list:
        for h in entry.get("hooks", []):
            if not isinstance(h, dict):
                continue
            cmd = h.get("command", "")
            if any(m in cmd for m in stable_emitter_markers + stable_dispatcher_markers):
                return True
            # Enforcement hooks count as stable only in their direct-path form,
            # not as the legacy filesystem-walking one-liner.
            if _command_is_ds_enforcement(cmd) and not _command_is_legacy_ds_hook(cmd):
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
            installed = [
                hh
                for existing_entry in event_list
                for hh in existing_entry.get("hooks", [])
                if isinstance(hh, dict)
                and existing_entry.get("matcher") == entry_matcher
                and hh.get("command") == cmd
            ]
            if installed:
                # A TIMEOUT THE TEMPLATE GAINED REACHES AN INSTALL THAT ALREADY HAS THE HOOK.
                # The skip above is by command, so an entry registered before the template
                # carried `timeout` kept running with none -- the Stop hooks of an existing
                # install could block a turn for as long as the harness allows (stuck
                # dispatchers were found 63 minutes old). Only a MISSING timeout is filled
                # in: one the operator set is theirs and is never overwritten.
                if "timeout" in h:
                    for hh in installed:
                        hh.setdefault("timeout", h["timeout"])
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


def dedup_hooks_by_normalized_command(settings: dict, hooks_dir: Path | None = None) -> dict:
    """Remove DUPLICATE Dream Studio hook entries that differ only in slash style.

    Cross-platform installs can leave both a backslash-path entry (Windows prior
    install) and a forward-slash-path entry (new template) for the same logical
    hook. Exact string comparison in merge_settings treats them as different, so
    both survive. This pass compares WHOLE entries (matcher plus every hook's
    command, separators normalized) and drops a later copy only when the entry is
    Dream Studio's own (is_ds_hook_command). It used to key on hooks[0] alone and
    on any entry at all, so an entry with a second guard, or one differing only in
    its arguments further in, was dropped as a "duplicate", and so was an operator's
    own deliberate duplicate.
    """

    def _norm(cmd: str) -> str:
        return cmd.replace("\\\\", "/").replace("\\", "/")

    for event in settings.get("hooks", {}):
        entries = settings["hooks"][event]
        seen: set[str] = set()
        deduped: list = []
        for entry in entries:
            hooks = entry.get("hooks", []) if isinstance(entry, dict) else []
            commands = [h.get("command", "") for h in hooks if isinstance(h, dict)]
            owned = bool(commands) and all(is_ds_hook_command(c, hooks_dir) for c in commands)
            if not owned:
                deduped.append(entry)
                continue
            key = json.dumps([entry.get("matcher", ""), [_norm(c) for c in commands]])
            if key not in seen:
                seen.add(key)
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
            or _command_is_ds_enforcement(command)
            or _command_is_legacy_ds_hook(command)
        ):
            return True
    return False


def deregister_ds_hooks(
    settings: dict[str, Any], hooks_dir: Path | None = None
) -> tuple[dict[str, Any], int]:
    """Remove every Dream-Studio-owned hook command from a settings dict.

    Inverse of the additive install merge. Ownership is the exact shape
    is_ds_hook_command() accepts (with *hooks_dir*, this config root's hooks/), or a
    legacy Dream Studio one-liner, never a substring: an operator's
    `python .../other-tool/hooks/run.py` is not ours. Removal is per command, so a
    foreign hook sharing an entry with a Dream Studio one survives; an entry left with
    no hooks is dropped, an event left empty is dropped, and an emptied ``hooks``
    section is removed so reinstall starts clean. Never touches settings.local.json
    (the caller selects the path) or any non-``hooks`` key.

    Returns ``(new_settings, removed_count)``, counting removed commands.
    """
    import copy as _copy

    def _ours(command: str) -> bool:
        return is_ds_hook_command(command, hooks_dir) or _command_is_legacy_ds_hook(command)

    result = _copy.deepcopy(settings)
    hooks_section = result.get("hooks")
    if not isinstance(hooks_section, dict):
        return result, 0
    removed = 0
    for event in list(hooks_section.keys()):
        entries = hooks_section.get(event)
        if not isinstance(entries, list):
            continue
        kept = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                kept.append(entry)
                continue
            hooks = [
                h
                for h in entry["hooks"]
                if not (isinstance(h, dict) and _ours(str(h.get("command", ""))))
            ]
            removed += len(entry["hooks"]) - len(hooks)
            if hooks:
                kept.append({**entry, "hooks": hooks})
        if kept:
            hooks_section[event] = kept
        else:
            hooks_section.pop(event, None)
    if not hooks_section:
        result.pop("hooks", None)
    return result, removed


def purge_superseded_ds_hooks(
    settings: dict[str, Any], keep_commands: set[str], hooks_dir: Path | None = None
) -> tuple[dict[str, Any], list[str]]:
    """Remove every Dream-Studio-owned hook command this install does not register.

    The merge above is additive, so moving hooks from copied files to installed modules
    (or from one app interpreter to another) would otherwise leave the old command beside
    the new one and run every hook twice -- the old one from a projection the installer is
    deleting. Foreign hooks are never touched: ownership is the exact shape
    is_ds_hook_command() accepts, not a substring. An entry left with no hooks is dropped.
    """
    import copy as _copy

    result = _copy.deepcopy(settings)
    hooks_section = result.get("hooks")
    if not isinstance(hooks_section, dict):
        return result, []
    removed: list[str] = []
    for event in list(hooks_section.keys()):
        entries = hooks_section.get(event)
        if not isinstance(entries, list):
            continue
        kept_entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                kept_entries.append(entry)
                continue
            kept_hooks = []
            for h in entry.get("hooks", []):
                command = h.get("command", "") if isinstance(h, dict) else ""
                if (
                    command
                    and command not in keep_commands
                    and is_ds_hook_command(command, hooks_dir)
                ):
                    removed.append(command)
                    continue
                kept_hooks.append(h)
            if kept_hooks or not entry.get("hooks"):
                kept_entries.append({**entry, "hooks": kept_hooks})
        if kept_entries:
            hooks_section[event] = kept_entries
        else:
            hooks_section.pop(event, None)
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
