"""Tests: dispatcher fail-open guarantee — SystemExit, KeyboardInterrupt, and
BaseException subclasses must never escape run_handlers or hooks.main()."""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handler(side_effect) -> tuple[str, Path]:
    """Return a (name, path) pair whose module's main() raises side_effect."""
    return ("_test_handler", Path("/nonexistent/handler.py"))


def _run_with_fake_module(side_effect, tmp_path: Path) -> None:
    """Run run_handlers with a single fake handler whose main() triggers side_effect."""
    from control.execution.dispatch_tracking import run_handlers

    fake_mod = ModuleType("_test_handler")

    def _main():
        raise side_effect

    fake_mod.main = _main  # type: ignore[attr-defined]

    handler_path = tmp_path / "fake_handler.py"
    handler_path.write_text("def main(): pass", encoding="utf-8")

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    with patch("control.execution.dispatch_tracking.load_module", return_value=fake_mod):
        # Must complete without raising — fail-open
        run_handlers([("_test_handler", handler_path)], "{}", "TestEvent", state_dir)


# ---------------------------------------------------------------------------
# run_handlers (dispatch_tracking) tests
# ---------------------------------------------------------------------------


class TestRunHandlersFailOpen:
    def test_systemexit_does_not_propagate(self, tmp_path):
        """A handler that calls sys.exit(2) must not escape run_handlers."""
        _run_with_fake_module(SystemExit(2), tmp_path)

    def test_keyboard_interrupt_does_not_propagate(self, tmp_path):
        """A handler that raises KeyboardInterrupt must not escape run_handlers."""
        _run_with_fake_module(KeyboardInterrupt(), tmp_path)

    def test_normal_exception_does_not_propagate(self, tmp_path):
        """A handler that raises Exception must not escape run_handlers (existing behavior)."""
        _run_with_fake_module(Exception("normal error"), tmp_path)

    def test_os_exit_cannot_be_caught(self, tmp_path):
        """os._exit() bypasses all Python exception handling.

        This is acceptable: os._exit() would only be called by a hostile or
        severely buggy handler. The dispatcher's out-of-process boundary (the
        hook subprocess) already isolates it from the Claude session. No
        Python-level mitigation is possible or required.

        This test documents the known limitation rather than testing prevention.
        """
        # Document: os._exit is intentionally not catchable by Python.
        # The isolation boundary is the OS process, not try/except.
        assert True, "os._exit() cannot be caught — isolation relies on OS process boundary"


# ---------------------------------------------------------------------------
# hooks.main() (runtime/dispatch/hooks.py) tests
# ---------------------------------------------------------------------------


class TestHooksMainFailOpen:
    def _run_hooks_main(self, event_name: str, side_effect, tmp_path: Path) -> int:
        """Invoke hooks.main() with a fake handler that triggers side_effect."""
        import runtime.dispatch.hooks as hooks_mod

        fake_mod = ModuleType("_test_handler")

        def _main():
            raise side_effect

        fake_mod.main = _main  # type: ignore[attr-defined]

        handler_path = tmp_path / "fake_handler.py"
        handler_path.write_text("def main(): pass", encoding="utf-8")

        with (
            patch.object(sys, "argv", ["hooks.py", event_name]),
            patch.object(sys, "stdin", io.StringIO("{}")),
            patch("runtime.dispatch.hooks._get_plugin_root", return_value=tmp_path),
            patch("control.execution.dispatch_tracking.load_module", return_value=fake_mod),
            patch(
                "runtime.dispatch.hooks._resolve_handlers",
                return_value=[("_test_handler", handler_path)],
            ),
        ):
            return hooks_mod.main()

    def test_hooks_main_systemexit_returns_0(self, tmp_path):
        """hooks.main() must return 0 even when a handler calls sys.exit()."""
        result = self._run_hooks_main("UserPromptSubmit", SystemExit(2), tmp_path)
        assert result == 0

    def test_hooks_main_keyboard_interrupt_returns_0(self, tmp_path):
        """hooks.main() must return 0 even when a handler raises KeyboardInterrupt."""
        result = self._run_hooks_main("UserPromptSubmit", KeyboardInterrupt(), tmp_path)
        assert result == 0

    def test_hooks_main_exception_returns_0(self, tmp_path):
        """hooks.main() must return 0 even when a handler raises Exception."""
        result = self._run_hooks_main("UserPromptSubmit", Exception("oops"), tmp_path)
        assert result == 0
