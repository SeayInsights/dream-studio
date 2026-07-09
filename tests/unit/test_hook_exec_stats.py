"""WO-HOOK-EXEC-STATS: every dispatched hook logs its execution, not just on-pulse.

Before this WO only on-pulse emitted system.hook.execution.logged, so the per-hook
stats surface (the DuckDB hook_executions view) showed a single distinct hook_name.
control.execution.dispatch_tracking.run_handlers is the one place every dispatched
hook flows through, so it now emits a hook.execution.logged canonical event per
handler. These tests prove the instrumentation covers all handlers (not the
downstream spool→events_fact→view pipeline, which existing tests already cover).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from control.execution import dispatch_tracking


def _write_handler(
    dir_path: Path, name: str, body: str = "def main():\n    pass\n"
) -> tuple[str, Path]:
    path = dir_path / f"{name}.py"
    path.write_text(body, encoding="utf-8")
    return name.replace("_", "-"), path


def test_all_hooks_log_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every dispatched handler emits a hook.execution.logged event, so the
    hook_executions view sees >1 distinct hook_name (not just on-pulse)."""
    calls: list[dict] = []

    def _capture(**kwargs: object) -> None:
        calls.append(kwargs)

    # _log_hook_execution imports insert_hook_execution at call time from this
    # module, so patching the source attribute is what the emission resolves.
    monkeypatch.setattr("core.event_store.event_writer.insert_hook_execution", _capture)

    handlers = [
        _write_handler(tmp_path, "on_tool_activity"),
        _write_handler(tmp_path, "on_stop_dispatch"),
        _write_handler(
            tmp_path, "on_edit_dispatch", "def main():\n    raise RuntimeError('boom')\n"
        ),
    ]

    dispatch_tracking.run_handlers(handlers, "{}", "PostToolUse", tmp_path)

    hook_names = {c["hook_name"] for c in calls}
    # The core assertion (task 2): more than one distinct hook logs its execution.
    assert len(hook_names) > 1
    assert hook_names == {"on_tool_activity", "on_stop_dispatch", "on_edit_dispatch"}

    # Every emission carries the fields the hook_executions DuckDB view extracts.
    for call in calls:
        assert call["hook_type"] == "PostToolUse"
        assert isinstance(call["duration_ms"], int)
        assert "exit_code" in call
        assert call["status"] in ("success", "failed")

    by_name = {c["hook_name"]: c for c in calls}
    # A handler that raises is still logged, honestly, as a failed execution.
    assert by_name["on_edit_dispatch"]["status"] == "failed"
    assert by_name["on_edit_dispatch"]["exit_code"] == 1
    assert by_name["on_tool_activity"]["status"] == "success"
    assert by_name["on_tool_activity"]["exit_code"] == 0


def test_sys_exit_zero_is_a_success_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A handler that sys.exit(0)s is a clean run, not a dispatch failure."""
    calls: list[dict] = []
    monkeypatch.setattr(
        "core.event_store.event_writer.insert_hook_execution",
        lambda **kw: calls.append(kw),
    )
    handlers = [
        _write_handler(tmp_path, "clean_exit", "import sys\ndef main():\n    sys.exit(0)\n"),
        _write_handler(tmp_path, "block_exit", "import sys\ndef main():\n    sys.exit(2)\n"),
    ]

    dispatch_tracking.run_handlers(handlers, "{}", "Stop", tmp_path)

    by_name = {c["hook_name"]: c for c in calls}
    assert by_name["clean_exit"]["status"] == "success"
    assert by_name["clean_exit"]["exit_code"] == 0
    assert by_name["block_exit"]["status"] == "failed"
    assert by_name["block_exit"]["exit_code"] == 2


def test_missing_handler_is_not_logged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A handler file that does not exist (or has no main) logs no execution."""
    calls: list[dict] = []
    monkeypatch.setattr(
        "core.event_store.event_writer.insert_hook_execution",
        lambda **kw: calls.append(kw),
    )
    dispatch_tracking.run_handlers(
        [("ghost", tmp_path / "does_not_exist.py")], "{}", "PostToolUse", tmp_path
    )
    assert calls == []
