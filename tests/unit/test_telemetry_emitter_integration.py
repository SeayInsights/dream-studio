from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.telemetry.emitters import (
    MODE_STRICT,
    TelemetryContext,
    emit_hook_tool_activity,
    emit_skill_invocations,
    emit_token_usage_record,
)
from core.telemetry.processor import write_telemetry
from core.telemetry.token_logger import write_token_log
from core.telemetry.tool_tracking import update_activity_feed


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "telemetry.db"
    conn = _connect(path)
    conn.close()
    return path



def test_hook_tool_emitter_writes_event_and_invocations(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    result = emit_hook_tool_activity(
        hook_name="on-tool-activity",
        tool_name="Read",
        tool_input={"file_path": "core/work_orders/handoff.py"},
        context=TelemetryContext(
            project_id="dream-studio", milestone_id="telemetry_emitter_integration"
        ),
        db_path=db_path,
        mode=MODE_STRICT,
    )

    assert result.emitted is True
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT hook_id, tool_id, event_type FROM execution_events WHERE event_id = ?",
            (result.event_id,),
        ).fetchone()
        assert row is not None
        assert row["hook_id"] == "on-tool-activity"
        assert row["tool_id"] == "Read"
        assert row["event_type"] == "hook.tool_activity"
    finally:
        conn.close()


def test_update_activity_feed_preserves_legacy_json_and_dual_writes(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = _db(tmp_path)
    state_dir = tmp_path / "state"
    monkeypatch.setattr("core.config.paths.state_dir", lambda: state_dir)
    monkeypatch.setenv("DREAM_STUDIO_TELEMETRY_DB", str(db_path))

    update_activity_feed("Read", {"file_path": str(tmp_path / "example.py")})

    assert (state_dir / "activity.json").is_file()
    conn = _connect(db_path)
    try:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM execution_events WHERE event_type = 'hook.tool_activity'"
            ).fetchone()[0]
            == 1
        )
    finally:
        conn.close()


def test_skill_and_token_paths_dual_write_without_losing_legacy_outputs(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = _db(tmp_path)
    monkeypatch.setenv("DREAM_STUDIO_TELEMETRY_DB", str(db_path))

    telemetry_buffer = tmp_path / "telemetry-buffer.jsonl"
    write_telemetry(telemetry_buffer, [{"name": "ds-core", "ts": "2026-05-13T00:00:00Z"}], True)
    token_log = tmp_path / "token-log.md"
    write_token_log(token_log, "2026-05-13T00:00:00Z", "session-test", "gpt-test", 10, 20, 30, 0, 0)

    assert telemetry_buffer.is_file()
    assert "ds-core" in telemetry_buffer.read_text(encoding="utf-8")
    assert token_log.is_file()
    assert "session-test" in token_log.read_text(encoding="utf-8")

    conn = _connect(db_path)
    try:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM execution_events WHERE skill_id = 'ds-core' AND event_type = 'skill.invoked'"
            ).fetchone()[0]
            == 1
        )
        row = conn.execute(
            "SELECT project_id, process_run_id, input_tokens, output_tokens, total_tokens FROM token_usage_records"
        ).fetchone()
        assert dict(row) == {
            "project_id": "dream-studio",
            "process_run_id": "session-test",
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
        }
    finally:
        conn.close()


def test_best_effort_failure_does_not_raise(tmp_path: Path) -> None:
    empty_db = tmp_path / "empty.db"
    result = emit_route_decision(
        {"route_decision": "continue_internal", "handoff_required": False},
        db_path=empty_db,
    )

    assert result.emitted is False
    assert result.error


def test_missing_context_ids_are_recorded_as_null(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    result = emit_hook_tool_activity(
        hook_name="on-tool-activity",
        tool_name="Grep",
        tool_input={},
        db_path=db_path,
        mode=MODE_STRICT,
    )

    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT project_id, milestone_id, task_id, process_run_id FROM execution_events WHERE event_id = ?",
            (result.event_id,),
        ).fetchone()
        assert row["project_id"] is None
        assert row["milestone_id"] is None
        assert row["task_id"] is None
        assert row["process_run_id"] is None
    finally:
        conn.close()


def test_mapping_context_aliases_populate_scope_ids(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    result = emit_route_decision(
        {
            "route_decision": "continue_internal",
            "handoff_required": False,
            "recommended_next_work_order": "none",
        },
        context={
            "project_name": "Dream Studio",
            "current_milestone": "telemetry_context_completeness_maturation",
            "work_order_id": "wo-telemetry-context",
            "session_name": "session-telemetry-context",
        },
        db_path=db_path,
        mode=MODE_STRICT,
    )

    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT project_id, milestone_id, task_id, process_run_id FROM route_decision_records WHERE route_id = ?",
            (result.record_id,),
        ).fetchone()
        assert dict(row) == {
            "project_id": "Dream Studio",
            "milestone_id": "telemetry_context_completeness_maturation",
            "task_id": "wo-telemetry-context",
            "process_run_id": "session-telemetry-context",
        }
    finally:
        conn.close()
