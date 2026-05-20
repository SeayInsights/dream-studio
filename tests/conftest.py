"""pytest configuration — make `hooks/` importable as a top-level package."""

from __future__ import annotations

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
    sessions = spool / ".sessions"
    if sessions.exists():
        import shutil

        shutil.rmtree(sessions, ignore_errors=True)


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
    """
    if "DS_SPOOL_ROOT" not in _os.environ:
        guard = tmp_path / "guard_spool"
        guard.mkdir()
        monkeypatch.setenv("DS_SPOOL_ROOT", str(guard))

    if "DS_DREAM_STUDIO_HOME" not in _os.environ:
        guard_ds = tmp_path / "guard_ds_home"
        guard_ds.mkdir()
        monkeypatch.setenv("DS_DREAM_STUDIO_HOME", str(guard_ds))

    real_events = Path.home() / ".dream-studio" / "events"
    before_count = sum(1 for _ in real_events.rglob("*")) if real_events.exists() else 0
    real_integrations = Path.home() / ".dream-studio" / "integrations"
    before_int = sum(1 for _ in real_integrations.rglob("*")) if real_integrations.exists() else 0

    yield

    after_count = sum(1 for _ in real_events.rglob("*")) if real_events.exists() else 0
    assert after_count == before_count, (
        f"Test created {after_count - before_count} file(s) in real "
        f"~/.dream-studio/events. Use the spool_root fixture."
    )
    after_int = sum(1 for _ in real_integrations.rglob("*")) if real_integrations.exists() else 0
    assert after_int == before_int, (
        f"Test created {after_int - before_int} file(s) in real "
        f"~/.dream-studio/integrations. Use the ds_home fixture."
    )
