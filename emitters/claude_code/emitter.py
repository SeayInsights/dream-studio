from __future__ import annotations
import re
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


# WO-FILESDB-REVET: the Stop-event token rollup (normalize_stop -> token.consumption.recorded)
# and its raw_session_token_accumulators backing were RETIRED. They were a denormalized
# per-session total of the per-tool token.consumed events — verified noise (~2,300 near-empty
# rollup events carrying ~4k tokens, vs the real 9.2M-token cost already in token.consumed).
# Session totals now derive from token.consumed via the DuckDB token_usage_records view; there
# is no accumulator table, no session-tokens-*.json disk fallback, and no Stop token event.
# (token.consumption.recorded stays in the EventType enum for the historical rows only.)


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


# WO-SKILL-CAPTURE-REGRESSION: a Skill tool call IS a skill invocation. Claude Code's
# PostToolUse payload for the Skill tool exposes the skill name in tool_input.skill
# (e.g. "ds-project"). Skill telemetry stopped 2026-07-02 when the old on-skill-telemetry
# Stop hook path went unwired; the live emitter never captured native Skill-tool calls.
# Emitting skill.invoked here stamps trace.skill_id, which the ingestor maps to the
# skill_id column (spool/ingestor.py) so the dashboard Top Skills panel repopulates.
# The ingestor validates skill_id against ^ds-[a-z][a-z0-9-]*$, so only DS skills
# (the ds-* Skill names) are emitted; anything else is skipped rather than rejected.
_SKILL_ID_RE = re.compile(r"^ds-[a-z][a-z0-9-]*$")


def _skill_name(tool_name: str, tool_input: Any) -> str | None:
    """Return the ds-* skill id for a Skill tool call, else None."""
    if tool_name != "Skill" or not isinstance(tool_input, dict):
        return None
    name = tool_input.get("skill") or tool_input.get("command") or tool_input.get("name")
    name = str(name).strip() if name else ""
    return name if _SKILL_ID_RE.match(name) else None


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
    skill = _skill_name(tool_name, tool_input)
    if skill is not None:
        # skill_id goes in trace (the ingestor reads trace.skill_id into the skill_id
        # column) and payload (so any payload reader/raw store also sees it).
        envelopes.append(
            CanonicalEventEnvelope(
                event_type=EventType.SKILL_INVOKED.value,
                session_id=session_id,
                confidence=confidence,
                payload={
                    "skill_id": skill,
                    "outcome_status": "failed" if is_error else "completed",
                },
                project_id=project_id,
                trace={"domain": "telemetry", "skill_id": skill},
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
