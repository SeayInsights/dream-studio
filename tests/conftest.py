"""pytest configuration — make `hooks/` importable as a top-level package."""

from __future__ import annotations

# Windows-only: install SIGINT handler before pytest does, so pytest never
# sees the phantom signals that occur on this platform during the ingest
# pipeline's filesystem and SQLite operations. The handler in
# spool/ingestor.py is the production fix; this conftest handler is the
# test-suite-only fix that prevents pytest's own SIGINT machinery from
# printing a KeyboardInterrupt banner after the test summary. CI on Linux
# is unaffected.
import sys as _sys

if _sys.platform == "win32":
    import signal as _signal

    def _conftest_sigint_handler(signum, frame):
        # Absorb all SIGINTs during tests. Phantom SIGINTs from Windows + Python 3.12
        # fs/sqlite operations should never propagate to pytest. Real user Ctrl+C
        # in pytest goes through pytest's own signal machinery, not this handler.
        pass

    _signal.signal(_signal.SIGINT, _conftest_sigint_handler)


import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_HOOKS_DIR = _PLUGIN_ROOT / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

_PACK_NAMES = ("core", "quality", "career", "analyze", "domains", "meta")


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
    return tmp_path


import os as _os
import warnings


@pytest.fixture(autouse=True)
def reset_warnings():
    warnings.resetwarnings()
    yield


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
    _before_db_mtime = real_db.stat().st_mtime if real_db.is_file() else None

    yield

    # Teardown: reset singleton again so subsequent tests don't inherit a stale instance
    # pointing at the (now-cleaned-up) tmp DB path.
    try:
        from core.config.database import DatabaseRuntime as _DBRuntime

        _DBRuntime.reset_instance()
    except Exception:
        pass

    if _before_events_mtime is not None and real_events.exists():
        assert (
            real_events.stat().st_mtime == _before_events_mtime
        ), "Test modified real ~/.dream-studio/events. Use the spool_root fixture."
    if _before_int_mtime is not None and real_integrations.exists():
        assert (
            real_integrations.stat().st_mtime == _before_int_mtime
        ), "Test modified real ~/.dream-studio/integrations. Use the ds_home fixture."
    if _before_db_mtime is not None and real_db.is_file():
        assert real_db.stat().st_mtime == _before_db_mtime, (
            "Test wrote to real ~/.dream-studio/state/studio.db.\n"
            "Ensure DREAM_STUDIO_DB_PATH is set to a tmp path before any DB connection. "
            "The guard_real_homedir fixture sets this via monkeypatch.setenv, but a DB "
            "connection initiated before the fixture activates will bypass it."
        )
