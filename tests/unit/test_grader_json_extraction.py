"""Tests for WO-GRADER-JSON: robust JSON extraction from grader output.

The completion grader sometimes prepends prose before its JSON fence block,
causing json.loads to fail on the full output. _extract_first_json_object
scans for the first balanced top-level JSON object so _collect_grader can
recover from prose-prefixed or trailing-text responses.
"""

from __future__ import annotations

import pytest

from core.work_orders.verify import _extract_first_json_object, _collect_grader

# ── _extract_first_json_object unit tests ──────────────────────────────────


def test_extracts_from_prose_prefix():
    text = 'Now I have enough context.\n\n{"passed": true, "score": 0.9}'
    result = _extract_first_json_object(text)
    assert result == '{"passed": true, "score": 0.9}'


def test_extracts_from_trailing_text():
    text = '{"passed": true}\n\nThat concludes the review.'
    result = _extract_first_json_object(text)
    assert result == '{"passed": true}'


def test_extracts_nested_object():
    text = 'prefix {"outer": {"inner": 1}} suffix'
    result = _extract_first_json_object(text)
    assert result == '{"outer": {"inner": 1}}'


def test_handles_braces_in_strings():
    text = 'prefix {"key": "value with { brace }"} suffix'
    result = _extract_first_json_object(text)
    assert result == '{"key": "value with { brace }"}'


def test_handles_escaped_quote_in_string():
    text = 'p {"key": "say \\"hi\\""} q'
    result = _extract_first_json_object(text)
    assert result == '{"key": "say \\"hi\\""}'


def test_returns_none_when_no_brace():
    assert _extract_first_json_object("just prose, no JSON here") is None


def test_returns_none_on_unbalanced_brace():
    assert _extract_first_json_object('{"unclosed": 1') is None


# ── _collect_grader integration via mock Popen ──────────────────────────────


class _FakeProc:
    """Minimal subprocess.Popen stand-in for _collect_grader."""

    def __init__(self, stdout_text: str):
        self._stdout = stdout_text
        self._ds_feeder = None

    def communicate(self, timeout: int = 180):  # noqa: ARG002
        return self._stdout, ""


def test_collect_grader_pure_json():
    proc = _FakeProc('{"passed": true, "score": 1.0}')
    result = _collect_grader(proc)
    assert result == {"passed": True, "score": 1.0}


def test_collect_grader_fenced_json():
    proc = _FakeProc('```json\n{"passed": true}\n```')
    result = _collect_grader(proc)
    assert result["passed"] is True


def test_collect_grader_prose_prefix():
    prose = (
        "Now I have everything needed. Let me produce the verdict.\n\n"
        '```json\n{"passed": true, "score": 0.95}\n```'
    )
    proc = _FakeProc(prose)
    result = _collect_grader(proc)
    assert result == {"passed": True, "score": 0.95}


def test_collect_grader_prose_prefix_no_fence():
    prose = 'Here is the result: {"passed": true, "score": 0.8}'
    proc = _FakeProc(prose)
    result = _collect_grader(proc)
    assert result == {"passed": True, "score": 0.8}


def test_collect_grader_garbage_raises_value_error():
    proc = _FakeProc("This is not JSON at all.")
    with pytest.raises(ValueError, match="Grader returned non-JSON"):
        _collect_grader(proc)


def test_collect_grader_default_timeout_is_sufficient():
    import inspect

    sig = inspect.signature(_collect_grader)
    default_timeout = sig.parameters["timeout"].default
    assert default_timeout >= 300, (
        f"_collect_grader default timeout {default_timeout}s is too low; "
        "completion grader prompts (task list + diff) need at least 300s on large diffs"
    )
