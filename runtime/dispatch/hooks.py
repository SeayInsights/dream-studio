#!/usr/bin/env python3
"""Tool-agnostic hook event dispatcher.

Input contract:
  argv[1]: event name (UserPromptSubmit | Stop | PostToolUse | PostCompact)
  stdin:   JSON payload; PostToolUse payloads include tool_name (snake_case,
           as sent by Claude Code) or toolName (camelCase, accepted for compat)

Routes to handler scripts in runtime/hooks/{pack}/ based on event name and
tool_name. Always exits 0.

Tool-specific emitters normalize their native payload into this contract
before calling this dispatcher. This module contains no tool-specific logic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _get_plugin_root() -> Path:
    # Installed to ~/.claude/hooks/dispatch/ — sidecar is one level up in hooks/.
    # .plugin-root is the sole authoritative source — written on every install to
    # point at the installed hooks dir. WO-RT removed CLAUDE_PLUGIN_ROOT and
    # parents[N] fallbacks that could resolve to the repo working tree.
    sidecar = Path(__file__).parent.parent / ".plugin-root"
    if sidecar.is_file():
        try:
            return Path(sidecar.read_text(encoding="utf-8").strip()).resolve()
        except Exception:
            pass
    return Path(__file__).parent.parent.resolve()


def _get_source_root() -> Path | None:
    """Return the DS repo root for lib imports, or None if sidecar absent."""
    sidecar = Path(__file__).parent.parent / ".ds-source-root"
    if sidecar.is_file():
        try:
            return Path(sidecar.read_text(encoding="utf-8").strip()).resolve()
        except Exception:
            pass
    return None


def _h(plugin_root: Path, pack: str, name: str) -> tuple[str, Path]:
    return (name, plugin_root / "runtime" / "hooks" / pack / f"{name}.py")


def _resolve_handlers(event_name: str, tool_name: str, plugin_root: Path) -> list[tuple[str, Path]]:
    """Return (name, path) list for the given event and tool_name."""
    if event_name == "UserPromptSubmit":
        return [_h(plugin_root, "meta", "on-prompt-dispatch")]
    if event_name == "Stop":
        return [_h(plugin_root, "meta", "on-stop-dispatch")]
    if event_name == "PostCompact":
        return [_h(plugin_root, "meta", "on-post-compact")]
    if event_name == "PostToolUse":
        handlers = [
            _h(plugin_root, "core", "on-post-tool-use"),
            _h(plugin_root, "meta", "on-tool-activity"),
        ]
        if tool_name == "Skill":
            handlers += [
                _h(plugin_root, "meta", "on-skill-metrics"),
                _h(plugin_root, "meta", "on-skill-complete"),
            ]
        elif tool_name in ("Edit", "Write", "MultiEdit"):
            handlers += [_h(plugin_root, "meta", "on-edit-dispatch")]
        elif tool_name == "Read":
            handlers += [_h(plugin_root, "meta", "on-skill-load")]
        return handlers
    return []


def _write_hook_execution(payload: str) -> None:
    """Write one queued hook-execution row. Called only from the drain.

    The producer is `_enqueue_hook_execution` in runtime/lib/enforcement.py, which
    cannot import the event store without paying the 259 ms this split exists to
    remove. It therefore ships a finished record and this turns it into a row.
    """
    try:
        record = json.loads(payload) if payload.strip() else {}
        if not record:
            return
        from core.event_store.event_writer import insert_hook_execution  # noqa: PLC0415

        insert_hook_execution(**record)
    except Exception:
        # One unwritable telemetry row must not stop the rest of the drain.
        pass


def _tool_of(raw: str) -> str:
    """Tool name from a raw payload. Queued records are re-parsed one by one."""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return ""
    return data.get("tool_name", data.get("toolName", "")) or ""


def main() -> int:
    if len(sys.argv) < 2:
        return 0

    event_name = sys.argv[1]

    try:
        raw_payload = sys.stdin.read()
    except Exception:
        raw_payload = "{}"

    # No parse here. `_run` is handed the RAW string and re-parses per queued
    # record via `_tool_of`, because a drain carries several records and one
    # main()-level tool name would have described only the first of them.

    try:
        plugin_root = _get_plugin_root()
        if str(plugin_root) not in sys.path:
            sys.path.insert(0, str(plugin_root))
        source_root = _get_source_root()
        if source_root and str(source_root) not in sys.path:
            # AHEAD OF THE PLUGIN ROOT, NOT BEHIND IT. The installed tree ships a PARTIAL
            # `control` package -- control/execution only, enough for this dispatcher --
            # while handlers import control.skills.* and control.execution.models.*, which
            # exist only in the repo. With the plugin root first, Python bound `control` to
            # the partial copy, fixed its __path__, and never looked at the repo, so every
            # such handler raised ModuleNotFoundError before running (WO becfca00). Once
            # this process imports dispatch_tracking the binding is cached for good, so the
            # order has to be right BEFORE that import, not after.
            #
            # This is also what docs/HOOK_RUNTIME.md already describes: entry hooks are
            # copies, libraries are imported from the repo. The append made the copy win.
            sys.path.insert(0, str(source_root))

        import control.execution.dispatch_tracking as _dt  # noqa: PLC0415
        from core.config import paths as _paths  # noqa: PLC0415

        state_dir = _paths.state_dir()

        def _run(name: str, payload: str) -> None:
            # The blocking enforce hooks queue a finished telemetry row rather than
            # writing it inline -- writing it cost them 259 ms of imports while the
            # user waited for permission to edit a file. Here the imports are
            # already paid for, so the row just gets written.
            if name == "hook.execution":
                _write_hook_execution(payload)
                return
            handlers = _resolve_handlers(name, _tool_of(payload), plugin_root)
            if handlers:
                _dt.run_handlers(handlers, payload, name, state_dir)

        # DRAIN FIRST. PostToolUse no longer runs handlers inline -- it appends a
        # line and exits in ~55 ms instead of ~283 ms. Its work happens here, on
        # UserPromptSubmit and Stop, which are synchronous anyway (one injects
        # context, the other blocks on enforcement) and so have already paid the
        # import bill. The frequent event got cheap by borrowing the rare one.
        if event_name in ("UserPromptSubmit", "Stop"):
            try:
                from core.config import hookq  # noqa: PLC0415

                hookq.drain(_run)
            except BaseException:
                pass

        _run(event_name, raw_payload)
    except BaseException:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
