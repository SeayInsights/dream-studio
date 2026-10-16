"""Cross-platform path resolution for dream-studio hooks.

All hooks call into these helpers so that user data, plugin root, and
project context resolve the same way regardless of OS, cwd, or how the
hook was invoked (shim, direct python, test harness).
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

USER_DATA_DIRNAME = ".dream-studio"

#: Written by `ds self-install` into an app venv's prefix: the Dream Studio home that app
#: was installed into. See home_dir().
APP_HOME_MARKER = "dream-studio-home"


@lru_cache(maxsize=1)
def code_root() -> Path:
    """The directory that holds Dream Studio's packages AND its shipped runtime data.

    THE ONE PLACE THE CODE LOCATION IS RESOLVED. In a checkout this is the repository
    root. In an installed wheel it is the site-packages directory the packages were
    installed into, and the build (setup.py, pyproject's shipped-root-data) puts the
    root-level data files -- VERSION, packs.yaml, docs/canonical/*.json, ... -- at the
    same relative paths there, so `code_root() / "docs" / "canonical"` names the same
    thing in both. Resolved through importlib.resources rather than a `parents[N]` walk
    from some module's __file__, which silently meant "the checkout" wherever the module
    happened to sit.

    Read-only by contract: nothing in the runtime writes under this directory
    (tests/unit/test_cli_never_writes_code_root.py).
    """
    from importlib.resources import files

    return Path(str(files("core"))).resolve().parent


def is_source_checkout(root: Path | None = None) -> bool:
    """True when *root* (default code_root()) is a source tree, not an installed app."""
    root = code_root() if root is None else root
    return (root / "pyproject.toml").is_file()


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

    # Fallback: the code root (a checkout, or an installed app's site-packages, which
    # ships canonical/ and packs.yaml at the same relative paths). It used to be inferred
    # from this file's location -- core/, which never holds those markers -- so an
    # installed app raised here and every progressive skill mode stayed locked.
    inferred = code_root()
    if (inferred / "canonical" / "skills").is_dir() or (inferred / "packs.yaml").is_file():
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


def home_dir() -> Path:
    """The Dream Studio home -- DREAM_STUDIO_HOME, else ~/.dream-studio -- NOT created.

    THE ONE PLACE THE DEFAULT HOME IS SPELLED. Code that built `Path.home() /
    ".dream-studio"` itself ignored DREAM_STUDIO_HOME, so `ds --home X` -- which sets it --
    could not reach it: `ds --home X project register` wrote diagnostics into the real
    home (boundary-semantics lane, 2026-09-23). tests/unit/test_home_means_home.py fails
    on a new spelling in core/ or interfaces/.

    Resolving a path does not create it; user_data_dir() is the one that does.

    AN INSTALLED APP DEFAULTS TO THE HOME IT WAS INSTALLED INTO. `ds self-install --home
    H` writes H into the app venv (APP_HOME_MARKER under sys.prefix). Hooks run that
    venv's python with no `--home` and no environment of their own, so without this an
    app installed into a second home would read and write the default home's authority
    from every hook. The environment variable still wins.
    """
    override = os.environ.get("DREAM_STUDIO_HOME")
    if override:
        return Path(override).expanduser()
    installed = installed_app_home()
    return installed if installed is not None else default_home()


def default_home() -> Path:
    """The home when nothing chooses another (~/.dream-studio). NOT created.

    For the few checks that must recognise the operator's real home whatever the
    environment says (core.config.sqlite_bootstrap._is_live_authority_db); everything
    else resolves the home through home_dir().
    """
    return Path.home() / USER_DATA_DIRNAME


def installed_version(home: Path | None = None) -> tuple[str | None, str | None]:
    """(version, sha) from <home>/state/installed-version.

    `ds self-install` writes "<version> <full sha>"; the older integration installer wrote
    the bare version, which reads back with sha None. Compare versions through this, never
    the raw file text, or every self-installed home looks out of date.
    """
    marker = (home if home is not None else home_dir()) / "state" / "installed-version"
    if not marker.is_file():
        return None, None
    parts = marker.read_text(encoding="utf-8").split()
    if not parts:
        return None, None
    return parts[0], (parts[1] if len(parts) > 1 else None)


def installed_app_home() -> Path | None:
    """The home recorded by `ds self-install` in the running venv, or None outside one."""
    marker = Path(sys.prefix) / APP_HOME_MARKER
    if not marker.is_file():
        return None
    text = marker.read_text(encoding="utf-8").strip()
    return Path(text) if text else None


def user_data_dir() -> Path:
    """Return the Dream Studio home, creating it if absent."""
    path = home_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def claude_config_root() -> Path:
    """Claude Code's OWN config root -- NOT created. See claude_config_root_with_reason."""
    return claude_config_root_with_reason()[0]


def claude_config_root_with_reason() -> tuple[Path, str]:
    """Claude Code's OWN config root and why it was chosen -- NOT created. Order:

      1. CLAUDE_CONFIG_DIR env var, if set: the root this shell's `claude` uses.
      2. The active Dream Studio profile's claude_config_dir, if a profile is active
         AND that field is set on it.
      3. ~/.claude (default).

    THE ONE PLACE CLAUDE CODE'S CONFIG ROOT IS SPELLED. This is a different thing from
    home_dir() above: home_dir() is Dream Studio's own home (DREAM_STUDIO_HOME / ~/.dream-
    studio); this is the config root of the Claude Code CLI itself, which the real `claude`
    binary relocates with CLAUDE_CONFIG_DIR. An operator can run a second, separate Claude
    Code identity for a different engagement -- its own session transcripts, hooks, and
    settings.json under a directory that is not ~/.claude -- and code that spells
    `Path.home() / ".claude"` directly can never see it, no matter what that identity's
    hooks install. tests/unit/test_claude_config_root.py fails on a new spelling in core/,
    interfaces/, integrations/, or control/.

    THE ENVIRONMENT WINS OVER THE PROFILE. The profile used to come first, so a shell
    whose CLAUDE_CONFIG_DIR named one root had `ds doctor --fix` and `ds integrate
    install` write into whatever root the authority's active profile named instead -- and
    for an authority copied from somewhere else, that was another identity's real
    settings.json. An explicit environment is the operator's statement about THIS shell;
    the profile (migration 159, core/profiles/) is the default for shells that say
    nothing, so an operator with several profiles needs no env var per shell.

    The profile lookup is wrapped in one broad try/except: this function is called from
    very early/low-level contexts (the Claude Code detector, doctor health checks, hook
    setup) that must keep working with no Dream Studio authority DB at all (fresh
    checkout), a DB that predates migration 159 (no business_profiles table), or a
    locked/unreadable DB file -- every one of those must fall through to the default,
    never raise. A caught failure is not swallowed silently (that would trip
    core.gates.fail_open_census): it goes through core.telemetry.diagnostics.log_diagnostic,
    which is documented to never raise itself. The DB-file existence check before the
    lookup avoids both the round trip and creating an empty database file.

    Resolving a path does not create it.
    """
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override).expanduser(), "CLAUDE_CONFIG_DIR is set"
    try:
        from core.config.database import _default_db_path

        if _default_db_path().is_file() and _has_profile_table(_default_db_path()):
            from core.profiles.queries import active_profile

            profile = active_profile()
            if profile:
                profile_dir = profile.get("claude_config_dir")
                if profile_dir:
                    return (
                        Path(profile_dir).expanduser(),
                        f"the active Dream Studio profile {profile.get('name')!r} names it"
                        " (CLAUDE_CONFIG_DIR is not set)",
                    )
    except Exception as exc:
        from core.telemetry.diagnostics import log_diagnostic

        log_diagnostic(
            category="failure",
            source="core.config.paths.claude_config_root",
            details={"error_type": type(exc).__name__, "error_message": str(exc)},
        )
    return Path.home() / ".claude", "the default (no CLAUDE_CONFIG_DIR, no profile root)"


def _has_profile_table(db: Path) -> bool:
    """Whether the authority has business_profiles (migration 159), asked read-only.

    An authority at the shipped released version can predate the table. Querying it
    anyway raised, and the raise was logged to state/diagnostics on every `ds doctor`
    and every hook: a write from a path that must not write, about a normal state.
    """
    from core.config.database import connect_existing

    conn = connect_existing(db, read_only=True)
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'business_profiles'"
        ).fetchone()
    finally:
        conn.close()
    return row is not None


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


def _project_slug(project_path: Path | None = None) -> str:
    """Convert an absolute project path to a Claude project slug."""
    raw = str((project_path or project_root()).resolve())
    if len(raw) >= 2 and raw[1] == ":":
        raw = raw[0] + raw[2:]
    raw = raw.replace("\\", "/")
    parts = [p for p in raw.split("/") if p]
    return "-".join(parts).replace(" ", "-")


def memory_dir(project_path: Path | None = None) -> Path:
    """Return <claude_config_root()>/projects/<slug>/memory/ for the given project (or cwd)."""
    slug = _project_slug(project_path)
    path = claude_config_root() / "projects" / slug / "memory"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sessions_dir() -> Path:
    """Per-user sessions directory for handoffs and recaps."""
    path = user_data_dir() / ".sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def planning_dir() -> Path:
    """Per-user planning directory for spec/plan/handoff artifacts."""
    path = user_data_dir() / "planning"
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_planning_dir(project_name: str) -> Path:
    """Return ~/.dream-studio/projects/<name>/planning/, creating if absent."""
    path = user_data_dir() / "projects" / project_name / "planning"
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_sessions_dir(project_name: str) -> Path:
    """Return ~/.dream-studio/projects/<name>/sessions/, creating if absent."""
    path = user_data_dir() / "projects" / project_name / "sessions"
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


def check_for_update() -> None:
    """Once-per-day GitHub release check — prints to stderr if a newer version is available.

    Writes a daily sentinel before making the request so a network failure
    doesn't cause hammering on every hook call that day.
    """
    import sys as _sys
    import json as _json
    import datetime as _dt
    import urllib.request as _req

    try:
        source_ver = plugin_version()
        if source_ver == "unknown":
            return
        today = _dt.date.today().isoformat()
        sentinel = state_dir() / f".update-checked-{today}"
        if sentinel.exists():
            return
        sentinel.write_text("", encoding="utf-8")

        try:
            manifest = plugin_root() / ".claude-plugin" / "plugin.json"
            repo_url = _json.loads(manifest.read_text(encoding="utf-8")).get("repository", "")
            repo = repo_url.rstrip("/").removeprefix("https://github.com/")
        except Exception:
            repo = "SeayInsights/dream-studio"

        request = _req.Request(
            f"https://api.github.com/repos/{repo}/releases/latest",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"dream-studio/{source_ver}",
            },
        )
        with _req.urlopen(request, timeout=3) as resp:
            data = _json.loads(resp.read().decode("utf-8"))

        latest = data.get("tag_name", "").lstrip("v")
        if not latest:
            return

        def _ver(v: str) -> tuple:
            try:
                return tuple(int(x) for x in v.split("."))
            except ValueError:
                return (0,)

        if _ver(latest) <= _ver(source_ver):
            return

        try:
            root = plugin_root()
        except RuntimeError:
            root = "your dream-studio directory"

        print(
            f"\n[dream-studio] Update available: v{latest} (installed: v{source_ver})\n"
            f"  → cd {root} && git pull && make setup\n",
            file=_sys.stderr,
        )
    except Exception:
        pass


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
        # Check optional Claude Code adapter cache version.
        cache_root = claude_config_root() / "plugins" / "cache" / "dream-studio"
        if cache_root.exists():
            for version_dir in sorted(cache_root.glob("*/*/plugin.json")):
                try:
                    import json as _json

                    cache_ver = str(
                        _json.loads(version_dir.read_text(encoding="utf-8")).get("version", "")
                    )
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
