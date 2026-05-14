"""factory_boy factories for hook payload models."""

from __future__ import annotations

import factory


class UserPromptSubmitPayloadFactory(factory.DictFactory):
    session_id = factory.Sequence(lambda n: f"session-{n:04d}")
    cwd = "/home/user/project"
    hook_event_name = "UserPromptSubmit"


class PostToolUsePayloadFactory(factory.DictFactory):
    session_id = factory.Sequence(lambda n: f"session-{n:04d}")
    tool_name = "Edit"
    tool_input = factory.LazyFunction(dict)
    tool_response = factory.LazyFunction(dict)


class HookEventFactory(factory.DictFactory):
    session_id = factory.Sequence(lambda n: f"session-{n:04d}")
    hook_event_name = "UserPromptSubmit"
    cwd = "/home/user/project"
