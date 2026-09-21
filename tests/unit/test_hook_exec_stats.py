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


def test_missing_handler_is_logged_as_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A REGISTERED handler whose file is absent is recorded, not skipped.

    THIS ASSERTION IS THE REVERSE OF THE ONE IT REPLACES, deliberately.
    `test_missing_handler_is_not_logged` required the silence, reading an absent file as
    configuration. That does not survive contact with `_resolve_handlers`, which HARDCODES
    the handler list: nothing here is optional, so a missing file cannot mean "not
    configured", only "the install is incomplete" -- a state this codebase demonstrably
    produces, since the installer has no delete op and leaves stale trees behind.

    Shipped once in 07b9d3f7, reverted in 54d95bfb because its stated cause was asserted
    without evidence and was wrong. The mechanism was sound and went out with the bad
    reason; the independent review of WO 2fde7846 objected to that narrowing, and task 5
    of that work order asks for this record by name.
    """
    calls: list[dict] = []
    monkeypatch.setattr(
        "core.event_store.event_writer.insert_hook_execution",
        lambda **kw: calls.append(kw),
    )
    dispatch_tracking.run_handlers(
        [("ghost", tmp_path / "does_not_exist.py")], "{}", "PostToolUse", tmp_path
    )

    assert len(calls) == 1, "a registered handler with no file must still be reported"
    assert calls[0]["status"] == "not_found"
    assert calls[0]["exit_code"] == 1
    assert "does_not_exist.py" in (
        calls[0]["error_message"] or ""
    ), "the record must name the path that is missing, or it cannot be acted on"


def test_a_missing_handler_writes_no_timing_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Timing stays execution-only: a handler that never ran has no runtime to report.

    Keeps the two stores meaning different things -- hook-timing.jsonl answers "how long
    did it take", the execution log answers "what happened to it".
    """
    monkeypatch.setattr("core.event_store.event_writer.insert_hook_execution", lambda **kw: None)
    dispatch_tracking.run_handlers(
        [("ghost", tmp_path / "does_not_exist.py")], "{}", "PostToolUse", tmp_path
    )
    timing = tmp_path / "hook-timing.jsonl"
    assert not timing.exists() or "ghost" not in timing.read_text(encoding="utf-8")


def test_handler_that_cannot_import_is_logged_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A handler that exists and raises on import is REPORTED, not skipped.

    This is the shape that hid WO becfca00 for the life of the install:
    on-skill-complete, on-skill-metrics, on-skill-load and on-skill-telemetry each
    raised ModuleNotFoundError at import because the installed tree ships a partial
    `control` package that shadowed the repo's. Every dispatch skipped them without a
    timing line, an execution row, or an error.
    """
    calls: list[dict] = []
    monkeypatch.setattr(
        "core.event_store.event_writer.insert_hook_execution",
        lambda **kw: calls.append(kw),
    )
    name, path = _write_handler(
        tmp_path, "broken_import", "import a_module_that_does_not_exist  # noqa\n"
    )
    dispatch_tracking.run_handlers([(name, path)], "{}", "PostToolUse", tmp_path)

    assert len(calls) == 1, "a handler that cannot be imported must still be reported"
    # underscored: the execution log normalises the dashed dispatch name, which is why
    # the live rows read `on_skill_complete` rather than `on-skill-complete`
    assert calls[0]["hook_name"] == name.replace("-", "_")
    assert calls[0]["status"] == "failed"
    assert calls[0]["exit_code"] == 1
    assert calls[0]["error_message"], "the refusal must carry why, not just that"


def test_handler_without_main_is_logged_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A handler that imports cleanly but defines no main() is a broken handler too."""
    calls: list[dict] = []
    monkeypatch.setattr(
        "core.event_store.event_writer.insert_hook_execution",
        lambda **kw: calls.append(kw),
    )
    name, path = _write_handler(tmp_path, "no_main", "X = 1\n")
    dispatch_tracking.run_handlers([(name, path)], "{}", "PostToolUse", tmp_path)

    assert len(calls) == 1
    assert calls[0]["status"] == "failed"
    assert "main" in (calls[0]["error_message"] or "")


def test_a_working_handler_is_still_logged_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive control. Without it, reporting every handler as failed would pass
    all three assertions above."""
    calls: list[dict] = []
    monkeypatch.setattr(
        "core.event_store.event_writer.insert_hook_execution",
        lambda **kw: calls.append(kw),
    )
    name, path = _write_handler(tmp_path, "healthy")
    dispatch_tracking.run_handlers([(name, path)], "{}", "PostToolUse", tmp_path)

    assert len(calls) == 1
    assert calls[0]["status"] == "success"
    assert calls[0]["exit_code"] == 0
