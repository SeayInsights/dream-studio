from __future__ import annotations
from pathlib import Path
from typing import Any

from canonical.events.envelope import CanonicalEventEnvelope
from canonical.events.redactor import (
    redact_bash_command,
    redact_file_path,
    redact_prompt,
    redact_tool_output,
    redact_url,
)
from canonical.events.types import EventType
from emitters.claude_code.project import _get_db_path, get_active_project_id
from emitters.claude_code.session import get_or_create_session_id


def normalize_user_prompt_submit(
    payload: dict[str, Any], root: Path | None = None
) -> list[CanonicalEventEnvelope]:
    session_id = get_or_create_session_id(root)
    confidence = "exact" if session_id is not None else "unavailable"
    raw_prompt = payload.get("prompt", "")
    redacted = redact_prompt(raw_prompt)
    return [
        CanonicalEventEnvelope(
            event_type=EventType.PROMPT_LIFECYCLE_SUBMITTED.value,
            session_id=session_id,
            confidence=confidence,
            payload=redacted,
            project_id=get_active_project_id(_get_db_path()),
            trace={"domain": "telemetry"},
        )
    ]


def _read_session_accumulator(session_id: str) -> dict[str, Any]:
    """Read per-session token totals written by token_capture after each tool call.

    WO-FILESDB-P2: prefer the authority table; fall back to the legacy JSON file
    when raw_session_token_accumulators is absent (migration 145 unreleased).
    """
    import json as _json

    try:
        from core.telemetry.session_accumulator import db_read_accumulator

        acc = db_read_accumulator(session_id)
        if acc is not None:
            return acc
    except Exception:
        pass

    acc_path = Path.home() / ".dream-studio" / "state" / f"session-tokens-{session_id}.json"
    try:
        return _json.loads(acc_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}


def normalize_stop(
    payload: dict[str, Any], root: Path | None = None
) -> list[CanonicalEventEnvelope]:
    session_id = get_or_create_session_id(root)
    confidence = "exact" if session_id is not None else "unavailable"
    usage = payload.get("usage", {})
    token_payload: dict[str, Any] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        val = usage.get(key) if usage else payload.get(key)
        if val is not None:
            token_payload[key] = val
    # Claude Code's Stop payload carries no usage field — fall back to the
    # per-session accumulator written by token_capture after each tool call.
    if not token_payload and session_id:
        token_payload = _read_session_accumulator(session_id)
    # Stamp the model so the cost view can price this turn (estimated_cost is
    # NULL for modelless rows — never fabricated). Prefer the model captured in
    # the accumulator (persisted by token_capture), else recover it from the
    # Stop payload's transcript_path via the same resolver token_capture uses.
    if token_payload and "model" not in token_payload:
        from core.telemetry.token_capture import _resolve_model, MODEL_UNRESOLVED

        acc = _read_session_accumulator(session_id) if session_id else {}
        # WO-e2c30936: stamp the sentinel rather than omit the key when the model is
        # unresolvable, so a token.consumption.recorded rollup that carries usage never
        # records a NULL model inside the dashboard_truth attribution window.
        token_payload["model"] = acc.get("model") or _resolve_model(payload) or MODEL_UNRESOLVED
    return [
        CanonicalEventEnvelope(
            event_type=EventType.TOKEN_CONSUMPTION_RECORDED.value,
            session_id=session_id,
            confidence=confidence,
            payload=token_payload,
            project_id=get_active_project_id(_get_db_path()),
            trace={"domain": "telemetry"},
        )
    ]


# WO-AGENT-TELEMETRY: a Task tool call IS a subagent invocation. Claude Code's
# PostToolUse payload for the Task tool exposes the agent identity in
# tool_input.subagent_type — the one place the hook surface names the subagent.
# This is declared in docs/canonical/event_taxonomy_v1.json (agent family); the
# EventType enum is a deliberate subset of the taxonomy, so it is emitted by its
# taxonomy string. Emitting it stamps trace.agent_id, which the ingestor maps to
# the agent_id column (spool/ingestor.py: _first(trace.agent_id, payload.agent_id)),
# so the agent_id dimension — designed for this and previously always NULL —
# finally populates.
_AGENT_EXECUTION_COMPLETED = "agent.execution.completed"


def _subagent_type(tool_name: str, tool_input: Any) -> str | None:
    """Return the subagent identity for a Task tool call, else None."""
    if tool_name != "Task" or not isinstance(tool_input, dict):
        return None
    subagent = tool_input.get("subagent_type") or tool_input.get("subagentType")
    subagent = str(subagent).strip() if subagent else ""
    return subagent or None


def normalize_post_tool_use(
    payload: dict[str, Any], root: Path | None = None
) -> list[CanonicalEventEnvelope]:
    session_id = get_or_create_session_id(root)
    confidence = "exact" if session_id is not None else "unavailable"
    tool_name = payload.get("tool_name", payload.get("tool", ""))
    tool_input = payload.get("tool_input", payload.get("input", {}))
    tool_response = payload.get("tool_response", payload.get("output"))
    is_error = bool(payload.get("is_error", False))
    output_summary = redact_tool_output(tool_name, tool_response, is_error=is_error)
    input_summary = _redact_tool_input(tool_name, tool_input)
    project_id = get_active_project_id(_get_db_path())
    envelopes = [
        CanonicalEventEnvelope(
            event_type=EventType.TOOL_EXECUTION_COMPLETED.value,
            session_id=session_id,
            confidence=confidence,
            payload={
                "tool_name": tool_name,
                "input_summary": input_summary,
                "output_summary": output_summary,
            },
            project_id=project_id,
            trace={"domain": "telemetry"},
        )
    ]
    subagent = _subagent_type(tool_name, tool_input)
    if subagent is not None:
        # subagent_type is a safe agent-kind label (e.g. "Explore", "Plan"), not
        # free text — recorded verbatim as the agent identity. The Task prompt /
        # description are NOT included (they carry user content).
        envelopes.append(
            CanonicalEventEnvelope(
                event_type=_AGENT_EXECUTION_COMPLETED,
                session_id=session_id,
                confidence=confidence,
                payload={
                    "agent_type": subagent,
                    "outcome_status": "failed" if is_error else "completed",
                },
                project_id=project_id,
                trace={"domain": "telemetry", "agent_id": subagent, "agent_type": subagent},
            )
        )
    return envelopes


def normalize_post_compact(
    payload: dict[str, Any], root: Path | None = None
) -> list[CanonicalEventEnvelope]:
    session_id = get_or_create_session_id(root)
    context_payload: dict[str, Any] = {"compacted": True}
    tokens = payload.get("context_window_tokens") or payload.get("tokens")
    if tokens is not None:
        context_payload["context_window_tokens"] = tokens
    summary = payload.get("summary", "")
    if summary:
        context_payload["summary_length"] = len(str(summary))
    return [
        CanonicalEventEnvelope(
            event_type=EventType.CONTEXT_THRESHOLD_CROSSED.value,
            session_id=session_id,
            confidence="inferred",
            payload=context_payload,
            project_id=get_active_project_id(_get_db_path()),
            trace={"domain": "telemetry"},
        )
    ]


def _redact_tool_input(tool_name: str, tool_input: Any) -> dict[str, Any]:
    if not isinstance(tool_input, dict):
        return {"arg_count": 1, "args_retained": False}
    tool_lower = tool_name.lower()
    if tool_lower in {"read", "edit", "write"}:
        path = tool_input.get("file_path") or tool_input.get("path", "")
        return {"file_path": redact_file_path(str(path)), "contents_retained": False}
    if tool_lower == "bash":
        cmd = tool_input.get("command", "")
        return redact_bash_command(str(cmd))
    if tool_lower in {"webfetch", "websearch"}:
        url = tool_input.get("url") or tool_input.get("query", "")
        return redact_url(str(url))
    return {"arg_count": len(tool_input), "args_retained": False}
