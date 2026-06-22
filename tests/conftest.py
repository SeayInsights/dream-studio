"""pytest configuration — make `hooks/` importable as a top-level package.

Top-of-file test isolation guard
---------------------------------
DREAM_STUDIO_HOME, DREAM_STUDIO_DB_PATH, and DS_SPOOL_ROOT are set here —
at conftest MODULE IMPORT TIME — before pytest collects tests and before any
test module is imported.

Why this must happen before ``import pytest``:
pytest imports conftest.py first, then imports each test module during
collection. Python executes module-level code at import time. Some production
modules (notably core.config.database.DatabaseRuntime) initialize a singleton
on first use and cache the DB path. If a test module's top-level import chain
reaches DatabaseRuntime before any fixture has a chance to run, the singleton
caches the real operator DB at ~/.dream-studio/state/studio.db.

By setting the env vars here, any DB path resolution that happens at import
time will see the tmp directory instead of the real one.

This resolves B3 from the 2026-05-24 final audit: 9 tests previously
contaminated the real production DB on every pytest run.
"""

from __future__ import annotations

import os as _os
import pathlib as _pathlib
import tempfile as _tempfile

# Record the real DB path for the post-test contamination guard.
_real_home_db = _pathlib.Path.home() / ".dream-studio" / "state" / "studio.db"
_REAL_DB_MTIME_AT_SESSION_START = _real_home_db.stat().st_mtime if _real_home_db.exists() else None

# Only redirect if not already set — lets callers like tox or CI override.
if "DREAM_STUDIO_DB_PATH" not in _os.environ:
    _session_tmp = _pathlib.Path(_tempfile.mkdtemp(prefix="dream-studio-test-"))
    (_session_tmp / "state").mkdir(parents=True, exist_ok=True)
    (_session_tmp / "events").mkdir(parents=True, exist_ok=True)
    (_session_tmp / "events" / "pending").mkdir(parents=True, exist_ok=True)
    (_session_tmp / "events" / "processed").mkdir(parents=True, exist_ok=True)
    _os.environ["DREAM_STUDIO_HOME"] = str(_session_tmp)
    _os.environ["DREAM_STUDIO_DB_PATH"] = str(_session_tmp / "state" / "studio.db")
    _os.environ["DS_SPOOL_ROOT"] = str(_session_tmp / "events")

# Windows-only: install SIGINT handler before pytest does, so pytest never
# sees the phantom signals that occur on this platform during the ingest
# pipeline's filesystem and SQLite operations. The handler in
# spool/ingestor.py is the production fix; this conftest handler is the
# test-suite-only fix that prevents pytest's own SIGINT machinery from
# printing a KeyboardInterrupt banner after the test summary. CI on Linux
# is unaffected.
import sys as _sys  # noqa: E402

if _sys.platform == "win32":
    import signal as _signal

    def _conftest_sigint_handler(signum, frame):
        # Absorb all SIGINTs during tests. Phantom SIGINTs from Windows + Python 3.12
        # fs/sqlite operations should never propagate to pytest. Real user Ctrl+C
        # in pytest goes through pytest's own signal machinery, not this handler.
        pass

    _signal.signal(_signal.SIGINT, _conftest_sigint_handler)


import importlib.util  # noqa: E402
import sys  # noqa: E402
import types  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_HOOKS_DIR = _PLUGIN_ROOT / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

_PACK_NAMES = ("core", "quality", "analyze", "domains", "meta")


def _find_handler(name: str) -> Path:
    """Search runtime/hooks/*/ then legacy hooks/handlers/ for a handler."""
    for pack in _PACK_NAMES:
        candidate = _PLUGIN_ROOT / "runtime" / "hooks" / pack / f"{name}.py"
        if candidate.is_file():
            return candidate
    legacy = _PLUGIN_ROOT / "hooks" / "handlers" / f"{name}.py"
    if legacy.is_file():
        return legacy
    raise FileNotFoundError(f"handler {name} not found in runtime/hooks or hooks/handlers")


def load_handler(name: str) -> types.ModuleType:
    """Import a handler by filename stem (e.g. 'on-pulse' -> on_pulse module)."""
    handler_path = _find_handler(name)
    module_name = f"handlers_{name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    assert spec and spec.loader, f"cannot load handler {name}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def pytest_configure(config):
    """Reinstall our SIGINT handler after pytest installs its own.

    Pytest registers its own SIGINT handler during configure. This hook runs
    after that, letting us reclaim the handler slot so phantom signals during
    test execution don't reach pytest's machinery. Windows-only.
    """
    if _sys.platform == "win32":
        _signal.signal(_signal.SIGINT, _conftest_sigint_handler)


@pytest.fixture
def handler() -> Any:
    return load_handler


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Redirect HOME, Path.home, and CLAUDE_PROJECTS_DIR to a temp dir."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECTS_DIR", raising=False)
    monkeypatch.delenv("DREAM_STUDIO_HOME", raising=False)
    return tmp_path


import warnings  # noqa: E402


@pytest.fixture(autouse=True)
def reset_warnings():
    warnings.resetwarnings()
    yield


@pytest.fixture(autouse=True)
def restore_stdin():
    """Snapshot and restore ``sys.stdin`` around every test.

    Some tests replace ``sys.stdin`` (e.g. with ``io.StringIO``) and "restore"
    it to ``sys.__stdin__`` — the real console stream, whose ``isatty()`` is
    True on Windows. That leaked tty-like stdin crosses into later tests and
    makes CLI code paths that gate on ``sys.stdin.isatty()`` (notably
    ``ds work-order start``'s no-brief confirmation prompt) mis-detect an
    interactive operator and abort early — surfacing as an order-dependent
    failure of an unrelated test (WO c2d21490). Restoring to the pre-test
    value (pytest's captured stdin) keeps the leak from crossing test
    boundaries regardless of how a test mutates stdin.
    """
    saved = sys.stdin
    yield
    sys.stdin = saved


@pytest.fixture
def spool_root(tmp_path, monkeypatch):
    """Isolated per-test spool root. Sets DS_SPOOL_ROOT via monkeypatch.setenv so subprocess emitters inherit it."""
    spool = tmp_path / "events"
    spool.mkdir()
    monkeypatch.setenv("DS_SPOOL_ROOT", str(spool))
    yield spool
    # Cleanup uses per-file unlink instead of shutil.rmtree to avoid a
    # Windows + Python 3.12 issue where rmtree's internal lstat call on
    # a just-written .sessions directory delivers a spurious SIGINT.
    sessions = spool / ".sessions"
    if sessions.exists():
        for session_file in sessions.glob("*.json"):
            try:
                session_file.unlink()
            except OSError:
                pass


@pytest.fixture
def ds_home(tmp_path, monkeypatch):
    """Isolated per-test dream-studio home. Sets DS_DREAM_STUDIO_HOME so
    integrations/manifest.py and related modules never reach real ~/.dream-studio."""
    home = tmp_path / "ds_home"
    home.mkdir()
    monkeypatch.setenv("DS_DREAM_STUDIO_HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def guard_real_homedir(tmp_path, monkeypatch):
    """Auto-use: ensures no test writes to real ~/.dream-studio or ~/.claude.

    If DS_SPOOL_ROOT is not already set by a test's spool_root fixture, this
    fixture sets a fallback so spool.config.get_spool_root() never reaches ~.
    If DS_DREAM_STUDIO_HOME is not already set, sets a fallback so integration
    manifest writes never reach real ~/.dream-studio/integrations/.
    If DREAM_STUDIO_DB_PATH is not already set, sets a fallback so the
    canonical DB-path resolver (`core.config.database._default_db_path`) and
    every caller that delegates to it write to a hermetic tmp DB instead of
    the operator's real ~/.dream-studio/state/studio.db.
    If DS_ACTIVE_TASK_PATH is not already set, sets a fallback so active task
    writes never reach the real ~/.dream-studio/state/active_task.json.
    """
    if "DS_SPOOL_ROOT" not in _os.environ:
        guard = tmp_path / "guard_spool"
        guard.mkdir()
        monkeypatch.setenv("DS_SPOOL_ROOT", str(guard))

    if "DS_DREAM_STUDIO_HOME" not in _os.environ:
        guard_ds = tmp_path / "guard_ds_home"
        guard_ds.mkdir()
        monkeypatch.setenv("DS_DREAM_STUDIO_HOME", str(guard_ds))

    if "DREAM_STUDIO_DB_PATH" not in _os.environ:
        guard_db_dir = tmp_path / "guard_state"
        guard_db_dir.mkdir()
        monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(guard_db_dir / "studio.db"))

    if "DS_PLATFORM_PROFILE_PATH" not in _os.environ:
        guard_platform_dir = tmp_path / "guard_platform"
        guard_platform_dir.mkdir()
        monkeypatch.setenv("DS_PLATFORM_PROFILE_PATH", str(guard_platform_dir / "platform.json"))

    if "DS_ACTIVE_TASK_PATH" not in _os.environ:
        guard_at_dir = tmp_path / "guard_active_task"
        guard_at_dir.mkdir()
        monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(guard_at_dir / "active_task.json"))

    if "DS_MACHINE_ID_PATH" not in _os.environ:
        guard_mid_dir = tmp_path / "guard_machine_id"
        guard_mid_dir.mkdir()
        monkeypatch.setenv("DS_MACHINE_ID_PATH", str(guard_mid_dir / "machine_id"))

    if "DS_CWD_RESOLVER_ROOT" not in _os.environ:
        monkeypatch.setenv("DS_CWD_RESOLVER_ROOT", str(tmp_path))

    if "DS_DIAGNOSTICS_DIR" not in _os.environ:
        guard_diag_dir = tmp_path / "guard_diagnostics"
        guard_diag_dir.mkdir()
        monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(guard_diag_dir))

    # Reset machine_id process-level cache so each test gets a fresh hermetic ID.
    try:
        import core.telemetry.machine_id as _mid_mod

        _mid_mod._reset_cache()
    except Exception:
        pass

    # Reset DatabaseRuntime singleton so it re-initializes from the (now-patched)
    # DREAM_STUDIO_DB_PATH. Without this, a singleton initialized before the fixture
    # activates caches the real DB path and bypasses the monkeypatch entirely.
    try:
        from core.config.database import DatabaseRuntime as _DBRuntime

        _DBRuntime.reset_instance()
    except Exception:
        pass

    real_events = Path.home() / ".dream-studio" / "events"
    _before_events_mtime = real_events.stat().st_mtime if real_events.exists() else None
    real_integrations = Path.home() / ".dream-studio" / "integrations"
    _before_int_mtime = real_integrations.stat().st_mtime if real_integrations.exists() else None
    real_db = Path.home() / ".dream-studio" / "state" / "studio.db"

    # Only snapshot real DB mtime when DREAM_STUDIO_DB_PATH is NOT redirected away
    # from the real DB. When the top-of-conftest block has redirected it to a session
    # tmp dir, the spool ingestor (a background process) continuously writes real
    # operator events to the real DB — mtime would change regardless of test activity,
    # producing false positives. Trust the env-var redirect as the isolation boundary.
    _real_db_path = str(real_db.resolve())
    _db_path_env = _os.environ.get("DREAM_STUDIO_DB_PATH", "")
    _db_redirected = _db_path_env and _db_path_env != _real_db_path
    _before_db_mtime = (
        (real_db.stat().st_mtime if real_db.is_file() else None) if not _db_redirected else None
    )

    yield

    # Teardown: reset singleton again so subsequent tests don't inherit a stale instance
    # pointing at the (now-cleaned-up) tmp DB path.
    try:
        from core.config.database import DatabaseRuntime as _DBRuntime

        _DBRuntime.reset_instance()
    except Exception:
        pass

    if _before_events_mtime is not None and real_events.exists():
        if real_events.stat().st_mtime != _before_events_mtime:
            pytest.exit(
                "FATAL: Test modified real ~/.dream-studio/events. "
                "Use the spool_root fixture. Aborting session to prevent further damage.",
                returncode=2,
            )
    if _before_int_mtime is not None and real_integrations.exists():
        if real_integrations.stat().st_mtime != _before_int_mtime:
            pytest.exit(
                "FATAL: Test modified real ~/.dream-studio/integrations. "
                "Use the ds_home fixture. Aborting session to prevent further damage.",
                returncode=2,
            )
    # Only check real DB mtime when the redirect is NOT in place (fallback safety).
    # With the redirect active, the spool ingestor writes legitimately to the real DB
    # and any mtime check here would be a false positive.
    if _before_db_mtime is not None and real_db.is_file():
        if real_db.stat().st_mtime != _before_db_mtime:
            pytest.exit(
                f"FATAL: Test wrote to real production DB at {real_db}. "
                "DREAM_STUDIO_DB_PATH was not redirected at fixture time — "
                "this indicates the top-of-conftest isolation block did not run. "
                "Aborting session to prevent further damage.",
                returncode=2,
            )
