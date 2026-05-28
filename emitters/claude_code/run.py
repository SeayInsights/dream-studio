#!/usr/bin/env python3
"""Spool emitter for Claude Code hooks.

Slice 1: emit-only. Handler dispatch still via hooks/run.py (deprecated, not yet deleted).
Slice 2: absorbs dispatch, fully replaces hooks/run.py.
Slice 3: Stop hook calls ingest_pending() + session cleanup. hooks/run.py entries removed.
Slice 8a: UserPromptSubmit injects enforcement message when no active work order.

Always exits 0 — spool emission is non-fatal and must not interrupt the hook chain.
"""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path

PACKS = ("core", "quality", "career", "analyze", "domains", "meta", "security")


def _enforcement_check() -> str | None:
    """Return a blocking message if no active work order, else None.

    Fail-open contract: any exception returns None so execution is never
    blocked by an observability failure.

    Work order checks require DB access which is forbidden in the emitter
    layer. Project identity is read from the flat .dream-studio-project
    marker file; work order enforcement is deferred to the runtime layer.
    """
    try:
        from emitters.claude_code.project import read_project_id

        project_id = read_project_id(None)
    except Exception:
        return None

    if not project_id:
        return None

    # TODO Slice 10: wire enforcement via runtime
    # intelligence layer once Chain 7 is complete.
    # For now fails open — no blocking enforcement.
    return None


def _get_plugin_root() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    sidecar = Path(__file__).parent / ".plugin-root"
    if sidecar.is_file():
        try:
            return Path(sidecar.read_text(encoding="utf-8").strip()).resolve()
        except Exception:
            pass
    return Path(__file__).resolve().parents[2]


def _version_check() -> str | None:
    """Compare repo VERSION file against installed version.

    Returns a notice string if update is available, None if current or check
    fails. Fail-open: any exception returns None.
    """
    try:
        plugin_root = _get_plugin_root()
        repo_version_file = plugin_root / "VERSION"
        if not repo_version_file.exists():
            return None
        repo_version = repo_version_file.read_text(encoding="utf-8").strip()
        # Resolve installed-version location via db path (allows test patching),
        # then fall back to the canonical home-based path if the derived one
        # does not exist (e.g. when DREAM_STUDIO_DB_PATH points to a test db
        # that has no installed-version sidecar).
        _db_derived: Path | None = None
        try:
            from emitters.claude_code.project import _get_db_path

            _db_derived = _get_db_path().parent.parent / "state" / "installed-version"
        except Exception:
            pass
        home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
        _home_derived: Path | None = (
            Path(home) / ".dream-studio" / "state" / "installed-version" if home else None
        )
        installed_version_file: Path | None = None
        for candidate in (_db_derived, _home_derived):
            if candidate is not None and candidate.exists():
                installed_version_file = candidate
                break
        if installed_version_file is None:
            installed_version_file = _db_derived or _home_derived
        if installed_version_file is None or not installed_version_file.exists():
            return (
                "DREAM STUDIO: Install not verified. "
                "Run: ds integrate install claude_code --execute"
            )
        installed_version = installed_version_file.read_text(encoding="utf-8").strip()
        if repo_version != installed_version:
            return (
                f"DREAM STUDIO UPDATE AVAILABLE\n"
                f"Installed: {installed_version} → "
                f"Current: {repo_version}\n"
                f"Run: ds update"
            )
        return None
    except Exception:
        return None


def _cleanup_session_file() -> None:
    """Delete the current process's session file if it exists."""
    spool_root_env = os.environ.get("DS_SPOOL_ROOT")
    if not spool_root_env:
        return
    sessions_dir = Path(spool_root_env) / ".sessions"
    pid = os.getpid()
    session_file = sessions_dir / f"{pid}.json"
    try:
        session_file.unlink(missing_ok=True)
    except OSError:
        pass


def main() -> int:
    if len(sys.argv) < 2:
        return 0

    hook_event = sys.argv[1]

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    try:
        plugin_root = _get_plugin_root()
        if str(plugin_root) not in sys.path:
            sys.path.insert(0, str(plugin_root))

        from emitters.claude_code.emitter import (
            normalize_post_compact,
            normalize_post_tool_use,
            normalize_stop,
            normalize_user_prompt_submit,
        )
        from emitters.shared.spool_writer import write_envelopes

        event_map = {
            "UserPromptSubmit": normalize_user_prompt_submit,
            "Stop": normalize_stop,
            "PostToolUse": normalize_post_tool_use,
            "PostCompact": normalize_post_compact,
        }

        normalizer = event_map.get(hook_event)
        if normalizer is not None:
            envelopes = normalizer(payload)
            write_envelopes(envelopes)
    except Exception:
        pass

    if hook_event == "UserPromptSubmit":
        try:
            version_msg = _version_check()
            enforcement_msg = _enforcement_check()
            parts = [m for m in (version_msg, enforcement_msg) if m]
            if parts:
                combined = "\n\n".join(parts)
                print(json.dumps({"type": "message", "content": combined}))
        except Exception:
            pass  # Fail open.

    if hook_event == "Stop":
        try:
            from spool.ingestor import ingest_pending

            ingest_pending()
        except Exception:
            pass
        try:
            _cleanup_session_file()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
