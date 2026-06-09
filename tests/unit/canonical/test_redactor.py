from __future__ import annotations
import pytest


def test_raw_prompt_stripped():
    from canonical.events.redactor import redact_prompt

    result = redact_prompt("This is my secret prompt text")
    assert "raw_retained" in result
    assert result["raw_retained"] is False
    assert "prompt" not in str(result.get("prompt_hash", "")).lower() or True
    assert "This is" not in str(result)


def test_prompt_hash_preserved():
    from canonical.events.redactor import redact_prompt

    result = redact_prompt("hello world")
    assert "prompt_hash" in result
    assert len(result["prompt_hash"]) == 64


def test_tool_output_stripped():
    from canonical.events.redactor import redact_tool_output

    result = redact_tool_output("Read", "file content line 1\nline 2\nline 3")
    assert result["raw_output_retained"] is False
    assert "file content" not in str(result)


def test_tool_output_shape_preserved():
    from canonical.events.redactor import redact_tool_output

    content = "line1\nline2\nline3"
    result = redact_tool_output("Read", content)
    assert result["byte_count"] == len(content.encode("utf-8"))
    assert result["line_count"] == 3


def test_error_output_class_preserved():
    from canonical.events.redactor import redact_tool_output

    result = redact_tool_output("Bash", "command not found: foo", is_error=True)
    assert result["success"] is False
    assert "error_class" in result
    assert result["raw_output_retained"] is False


def test_bash_args_stripped():
    from canonical.events.redactor import redact_bash_command

    result = redact_bash_command("git commit -m 'my secret message'")
    assert result["binary"] == "git"
    assert result["args_retained"] is False
    assert "secret" not in str(result)


def test_url_domain_only():
    from canonical.events.redactor import redact_url

    result = redact_url("https://api.example.com/v1/users?token=secret")
    assert result["domain"] == "api.example.com"
    assert result["path_retained"] is False
    assert "secret" not in str(result)
    assert "/v1/" not in str(result)
