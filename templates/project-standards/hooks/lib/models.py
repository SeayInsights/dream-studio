"""Pydantic v2 models for hook event payloads. Copy to hooks/lib/models.py."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator


class UserPromptSubmitPayload(BaseModel):
    session_id: str = ""
    cwd: str = ""
    hook_event_name: str = "UserPromptSubmit"

    @field_validator("session_id", "cwd", mode="before")
    @classmethod
    def coerce_none(cls, v: Any) -> str:
        return str(v) if v is not None else ""


class PostToolUsePayload(BaseModel):
    session_id: str = ""
    tool_name: str = ""
    tool_input: Any = None
    tool_response: Any = None

    @field_validator("session_id", "tool_name", mode="before")
    @classmethod
    def coerce_none(cls, v: Any) -> str:
        return str(v) if v is not None else ""


class StopPayload(BaseModel):
    session_id: str = ""
    stop_hook_active: bool = False

    @field_validator("session_id", mode="before")
    @classmethod
    def coerce_none(cls, v: Any) -> str:
        return str(v) if v is not None else ""
