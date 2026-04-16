"""pytest configuration — make `hooks/` importable as a top-level package."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

HANDLERS_DIR = _HOOKS_DIR / "handlers"


def load_handler(name: str) -> types.ModuleType:
    """Import a handler by filename stem (e.g. 'on-pulse' -> on_pulse module)."""
    module_name = f"handlers_{name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, HANDLERS_DIR / f"{name}.py")
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
