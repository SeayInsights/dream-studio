"""Shared utilities for the Dream Studio CLI.

These helpers are used across multiple command modules and the main hub (ds.py).
Keep this module dependency-free (stdlib only) so any command module can import it
without pulling in the full CLI dependency tree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _print(payload: dict[str, Any]) -> int:
    """Serialise *payload* as pretty-printed JSON and return 0."""
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _with_conn(*, source_root: Path, dream_studio_home: Path | None, callback: Any) -> int:
    """Open the authority SQLite connection and call *callback(conn)*, printing the result."""
    from core.event_store.studio_db import _connect
    from core.installed_runtime import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError(
            "Dream Studio SQLite authority is missing. Run rehearsal-install for a rehearsal "
            "home, or install/bootstrap the real runtime through an approved update plan."
        )
    with _connect(paths.sqlite_path) as conn:
        return _print(callback(conn))


def _require_home_for_install(command: str) -> Path:
    """Raise RuntimeError when --home is missing for install-class commands."""
    raise RuntimeError(
        f"{command} requires --home for this productization flow unless a live install scope "
        "has been explicitly approved."
    )


def _default_claude_settings_paths() -> list[str]:
    """Resolve the two generated .claude settings.json copies (hook-projection model).

    Mirrors install: the detected (project or user) scope copy plus the user-global
    copy. Returns deduped absolute path strings so uninstall clears both — nothing
    left hanging.
    """
    paths: list[Path] = []
    try:
        from integrations.detector import detect_claude_code

        detected = detect_claude_code()
        paths.append(Path(detected.config_root) / "settings.json")
    except Exception:  # noqa: BLE001 — detection is best-effort; user-global is the fallback
        pass
    paths.append(Path.home() / ".claude" / "settings.json")
    seen: set[str] = set()
    deduped: list[str] = []
    for p in paths:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            deduped.append(str(p))
    return deduped


def _changed_files_from_args(args: Any) -> list[str]:
    """Collect --changed-file / --changed-files args into a sorted deduped list."""
    files = list(args.changed_file or [])
    if args.changed_files:
        normalized = str(args.changed_files).replace(";", "\n").replace(",", "\n")
        files.extend(item.strip() for item in normalized.splitlines() if item.strip())
    return sorted({item for item in files if item})


def _table_exists_in_conn(conn: Any, table_name: str) -> bool:
    """Return True if *table_name* exists in the open SQLite connection."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone()
    return row is not None
