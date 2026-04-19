"""Cross-platform path resolution for dream-studio hooks.

All hooks call into these helpers so that user data, plugin root, and
project context resolve the same way regardless of OS, cwd, or how the
hook was invoked (shim, direct python, test harness).
"""

from __future__ import annotations

import os
from pathlib import Path

USER_DATA_DIRNAME = ".dream-studio"


def plugin_root() -> Path:
    """Return the installed plugin's root directory.

    Prefers the `CLAUDE_PLUGIN_ROOT` env var (set by Claude Code when
    invoking hooks). Falls back to walking up from this file's location
    until a `.claude-plugin/plugin.json` manifest is found — useful for
    tests and direct-script execution outside the Claude runtime.

    Last resort: the plugin cache location inferred from this file's path,
    so hooks degrade gracefully instead of crashing with RuntimeError.
    """
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()

    current = Path(__file__).resolve().parent
    for candidate in [current, *current.parents]:
        if (candidate / ".claude-plugin" / "plugin.json").is_file():
            return candidate

    # Fallback: infer from this file's location (hooks/lib/paths.py → ../../)
    inferred = Path(__file__).resolve().parents[1]
    if (inferred / "skills").is_dir() or (inferred / "rules").is_dir():
        return inferred

    raise RuntimeError(
        "Could not locate plugin root. Set CLAUDE_PLUGIN_ROOT or run "
        "from inside a dream-studio checkout."
    )


def plugin_version() -> str:
    """Return the plugin version string from plugin.json, or 'unknown'."""
    try:
        manifest = plugin_root() / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            import json as _json
            return str(_json.loads(manifest.read_text(encoding="utf-8")).get("version", "unknown"))
    except Exception:
        pass
    return "unknown"


def user_data_dir() -> Path:
    """Return `~/.dream-studio/`, creating it if absent."""
    path = Path.home() / USER_DATA_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_root() -> Path:
    """Return the project the user is currently working in."""
    return Path.cwd()


def meta_dir() -> Path:
    """Per-user meta directory for pulse/quality/token logs."""
    path = user_data_dir() / "meta"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_dir() -> Path:
    """Per-user state directory for transient runtime state."""
    path = user_data_dir() / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def planning_dir() -> Path:
    """Per-user planning directory for spec/plan/handoff artifacts."""
    path = user_data_dir() / "planning"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_data_dir_writable() -> bool:
    """Return True if the user data dir is writable (fast sentinel check)."""
    try:
        d = Path.home() / USER_DATA_DIRNAME
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".write-probe"
        probe.write_text("x")
        probe.unlink()
        return True
    except OSError:
        return False


def warn_version_mismatch() -> None:
    """Emit a one-time stderr warning if plugin source and cache versions differ.

    Compares plugin.json version from the running hooks location against the
    version stored in the plugin cache. Writes a sentinel to avoid repeating
    the warning more than once per day.
    """
    import sys as _sys
    try:
        source_ver = plugin_version()
        if source_ver == "unknown":
            return
        sentinel = state_dir() / f".version-warned-{source_ver}"
        if sentinel.exists():
            return
        # Check cache version (claude code plugin cache)
        cache_root = Path.home() / ".claude" / "plugins" / "cache" / "dream-studio"
        if cache_root.exists():
            for version_dir in sorted(cache_root.glob("*/*/plugin.json")):
                try:
                    import json as _json
                    cache_ver = str(_json.loads(version_dir.read_text(encoding="utf-8")).get("version", ""))
                    if cache_ver and cache_ver != source_ver:
                        print(
                            f"[dream-studio] Version mismatch: source={source_ver}, "
                            f"cache={cache_ver}. Run: cp -r skills rules docs templates "
                            f"~/.claude/plugins/cache/dream-studio/dream-studio/{cache_ver}/",
                            file=_sys.stderr,
                        )
                        sentinel.write_text(source_ver)
                except Exception:
                    pass
    except Exception:
        pass
