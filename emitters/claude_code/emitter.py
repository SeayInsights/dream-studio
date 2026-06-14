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
    """Read per-session token totals written by token_capture after each tool call."""
    import json as _json

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
    return [
        CanonicalEventEnvelope(
            event_type=EventType.TOOL_EXECUTION_COMPLETED.value,
            session_id=session_id,
            confidence=confidence,
            payload={
                "tool_name": tool_name,
                "input_summary": input_summary,
                "output_summary": output_summary,
            },
            project_id=get_active_project_id(_get_db_path()),
            trace={"domain": "telemetry"},
        )
    ]


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
