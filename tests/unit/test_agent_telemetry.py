"""WO-AGENT-TELEMETRY: subagent (Task tool) invocations emit agent-identified events.

Claude Code exposes the subagent identity to the PostToolUse hook as
tool_input.subagent_type for the Task tool. The emitter now emits an
agent.execution.completed event stamping trace.agent_id, token_capture attributes
a Task call's tokens to the agent, and the agent dashboard component reads those
agent-identified events from the DuckDB events_fact projection (the SQLite spine
never carried agent_id — it was always NULL).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _task_payload(subagent_type: str = "Explore", *, with_usage: bool = False) -> dict:
    payload: dict = {
        "session_id": "sess-1",
        "tool_name": "Task",
        "tool_input": {
            "subagent_type": subagent_type,
            "description": "run a search",
            "prompt": "sensitive user prompt text",
        },
        "tool_response": {"ok": True},
    }
    if with_usage:
        payload["usage"] = {"input_tokens": 100, "output_tokens": 50}
        payload["model"] = "claude-sonnet-4-6"
    return payload


def test_agent_id_captured_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Task PostToolUse emits agent.execution.completed carrying the subagent
    identity as trace.agent_id, and token_capture attributes the Task call's
    tokens to that agent."""
    from emitters.claude_code import emitter

    # Isolate from the DB/session — identity capture must not depend on them.
    monkeypatch.setattr(emitter, "get_active_project_id", lambda *a, **k: None)
    monkeypatch.setattr(emitter, "get_or_create_session_id", lambda *a, **k: "sess-1")

    envelopes = emitter.normalize_post_tool_use(_task_payload("Explore"))

    agent_events = [e for e in envelopes if e.event_type == "agent.execution.completed"]
    assert len(agent_events) == 1
    agent = agent_events[0]
    assert agent.trace.get("agent_id") == "Explore"
    assert agent.trace.get("agent_type") == "Explore"
    # The user prompt/description must not leak into the agent event payload.
    blob = json.dumps(agent.payload)
    assert "sensitive user prompt" not in blob

    # token_capture stamps agent_id onto the Task call's token.consumed event.
    from core.telemetry import token_capture

    captured: list = []
    monkeypatch.setattr(
        token_capture._spool_writer_mod, "write_envelopes", lambda envs: captured.extend(envs)
    )
    # Keep the unit test fast/hermetic — skip the git/subprocess context capture.
    monkeypatch.setattr(token_capture, "_capture_git_context", lambda cwd_ctx: ({}, 0.0))
    monkeypatch.setattr(token_capture, "_capture_platform_context", lambda: {})

    token_capture.handle_post_tool_use(_task_payload("Explore", with_usage=True))

    assert len(captured) == 1
    assert captured[0].trace.get("agent_id") == "Explore"
    assert captured[0].trace.get("agent_type") == "Explore"


def test_no_agent_event_for_non_task_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-Task tool call emits no agent event (only tool.execution.completed)."""
    from emitters.claude_code import emitter

    monkeypatch.setattr(emitter, "get_active_project_id", lambda *a, **k: None)
    monkeypatch.setattr(emitter, "get_or_create_session_id", lambda *a, **k: "sess-1")

    payload = {
        "session_id": "sess-1",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "tool_response": {"ok": True},
    }
    envelopes = emitter.normalize_post_tool_use(payload)
    assert not any(e.event_type == "agent.execution.completed" for e in envelopes)
    assert any(e.event_type == "tool.execution.completed" for e in envelopes)


def test_agent_component_reads_duckdb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The agent dashboard component reads agent.execution.* from events_fact, and
    never the SQLite spine (which never carried agent_id)."""
    from core.analytics import duckdb_store

    analytics_db = tmp_path / "aggregate_metrics.db"
    monkeypatch.setattr(duckdb_store, "analytics_db_path", lambda: analytics_db)

    conn = duckdb_store.connect_analytics(analytics_db, read_only=False)
    try:
        duckdb_store.ensure_analytics_schema(conn)
        for i, agent in enumerate(("Explore", "Explore", "Plan")):
            conn.execute(
                "INSERT INTO events_fact (event_id, event_type, event_timestamp,"
                " project_id, agent_id, status) VALUES (?, 'agent.execution.completed',"
                " '2026-07-08T00:00:00Z', 'p1', ?, 'completed')",
                [f"agent-{i}", agent],
            )
    finally:
        conn.close()

    from core.event_store.studio_db import _connect
    from core.telemetry.read_models import component_usage_summary

    db_path = tmp_path / "spine.db"
    _connect(db_path).close()

    summary = component_usage_summary(db_path=db_path)
    agent_rows = summary["usage"]["agent"]["rows"]
    by_id = {r["component_id"]: r for r in agent_rows}
    assert set(by_id) == {"Explore", "Plan"}
    assert by_id["Explore"]["invocation_count"] == 2
    assert by_id["Plan"]["invocation_count"] == 1
