from __future__ import annotations
import pytest


def test_user_prompt_submit_normalization(spool_root):
    from emitters.claude_code.emitter import normalize_user_prompt_submit

    payload = {"prompt": "Help me write a function"}
    envelopes = normalize_user_prompt_submit(payload, root=spool_root)
    assert len(envelopes) == 1
    env = envelopes[0]
    assert env.event_type == "prompt.lifecycle.submitted"
    assert env.raw_prompt_retained is False
    assert "Help me" not in str(env.payload)
    assert "prompt_hash" in env.payload


def test_stop_normalization(spool_root):
    from emitters.claude_code.emitter import normalize_stop

    payload = {"usage": {"input_tokens": 100, "output_tokens": 200}}
    envelopes = normalize_stop(payload, root=spool_root)
    assert len(envelopes) == 1
    env = envelopes[0]
    assert env.event_type == "token.consumption.recorded"
    assert env.payload["input_tokens"] == 100
    assert env.payload["output_tokens"] == 200


def test_post_tool_use_normalization(spool_root):
    from emitters.claude_code.emitter import normalize_post_tool_use

    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": "/repo/src/main.py"},
        "tool_response": "def main():\n    pass\n",
        "is_error": False,
    }
    envelopes = normalize_post_tool_use(payload, root=spool_root)
    assert len(envelopes) == 1
    env = envelopes[0]
    assert env.event_type == "tool.execution.completed"
    assert env.payload["tool_name"] == "Read"
    assert env.payload["output_summary"]["raw_output_retained"] is False


def test_session_id_field_populated(spool_root):
    from emitters.claude_code.emitter import normalize_user_prompt_submit

    envelopes = normalize_user_prompt_submit({"prompt": "test"}, root=spool_root)
    assert envelopes[0].session_id is not None
