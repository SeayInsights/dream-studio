"""Tests for hooks/lib/models.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.models import PostToolUsePayload, StopPayload, UserPromptSubmitPayload  # noqa: E402


class TestUserPromptSubmitPayload:
    def test_defaults(self) -> None:
        p = UserPromptSubmitPayload()
        assert p.session_id == ""
        assert p.cwd == ""
        assert p.hook_event_name == "UserPromptSubmit"

    def test_coerce_none_to_empty_string(self) -> None:
        p = UserPromptSubmitPayload(session_id=None, cwd=None)
        assert p.session_id == ""
        assert p.cwd == ""

    def test_coerce_non_none_to_string(self) -> None:
        p = UserPromptSubmitPayload(session_id=42, cwd="/home/user")
        assert p.session_id == "42"
        assert p.cwd == "/home/user"


class TestPostToolUsePayload:
    def test_defaults(self) -> None:
        p = PostToolUsePayload()
        assert p.session_id == ""
        assert p.tool_name == ""
        assert p.tool_input is None
        assert p.tool_response is None

    def test_coerce_none_to_empty_string(self) -> None:
        p = PostToolUsePayload(session_id=None, tool_name=None)
        assert p.session_id == ""
        assert p.tool_name == ""

    def test_coerce_non_none_to_string(self) -> None:
        p = PostToolUsePayload(session_id="abc", tool_name="Edit")
        assert p.session_id == "abc"
        assert p.tool_name == "Edit"


class TestStopPayload:
    def test_defaults(self) -> None:
        p = StopPayload()
        assert p.session_id == ""
        assert p.stop_hook_active is False

    def test_coerce_none_to_empty_string(self) -> None:
        p = StopPayload(session_id=None)
        assert p.session_id == ""
